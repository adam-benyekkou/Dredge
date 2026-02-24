"""Quarantine routes for Dredge"""

from fastapi import APIRouter, Depends, Request, Body
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from typing import List
import logging
from datetime import datetime

from app.core.db import get_session
from app.models import ImageArtifact, ImageStatus, AuditLog, AppSettings
from app.core.registry import RegistryClientFactory, clear_image_cache
from app.core.finops import CostCalculator

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/quarantine", response_class=HTMLResponse)
async def quarantine_view(request: Request, session: Session = Depends(get_session)):
    """View quarantined images."""
    statement = select(ImageArtifact).where(ImageArtifact.status == ImageStatus.QUARANTINED)
    quarantined_images = session.exec(statement).all()
    
    return templates.TemplateResponse(
        request,
        "quarantine.html",
        {
            "quarantined_images": quarantined_images,
            "quarantined_count": len(quarantined_images)
        }
    )


@router.post("/quarantine/restore/{image_id}", response_class=HTMLResponse)
async def restore_image(image_id: int, session: Session = Depends(get_session)):
    """Restore a quarantined image to active status."""
    try:
        image = session.get(ImageArtifact, image_id)
        if not image:
            return HTMLResponse(content="Image not found", status_code=404)
        
        # Audit log
        audit = AuditLog(
            action="UNQUARANTINE",
            image_id=image.digest,
            image_tags=image.tags,
            source=image.source,
            bytes_freed=0,
            savings_usd=0.0,
            timestamp=datetime.utcnow()
        )
        session.add(audit)
        
        image.status = ImageStatus.ACTIVE
        image.expires_at = None
        session.add(image)
        session.commit()
        
        clear_image_cache()
        
        logger.info(f"Unquarantined image: {image.tags[0] if image.tags else image.digest[:12]}")
        
        return HTMLResponse(
            content="",
            headers={"HX-Trigger": '{"showMessage": {"message": "Image restored successfully", "type": "success"}}'}
        )
    except Exception as e:
        logger.error(f"Failed to restore image: {e}", exc_info=True)
        return HTMLResponse(
            content="",
            status_code=500,
            headers={"HX-Trigger": f'{{"showMessage": {{"message": "Failed to restore image: {str(e)}", "type": "error"}}}}'}
        )


@router.post("/quarantine/restore/bulk", response_class=HTMLResponse)
async def restore_bulk(
    image_ids: List[int] = Body(..., embed=True),
    session: Session = Depends(get_session)
):
    """Restore multiple quarantined images to active status."""
    try:
        if not image_ids:
            return HTMLResponse(content="No images selected", status_code=400)
        
        restored_count = 0
        for image_id in image_ids:
            image = session.get(ImageArtifact, image_id)
            if image:
                # Audit log
                audit = AuditLog(
                    action="UNQUARANTINE",
                    image_id=image.digest,
                    image_tags=image.tags,
                    source=image.source,
                    bytes_freed=0,
                    savings_usd=0.0,
                    timestamp=datetime.utcnow()
                )
                session.add(audit)
                
                image.status = ImageStatus.ACTIVE
                image.expires_at = None
                session.add(image)
                restored_count += 1
        
        session.commit()
        
        clear_image_cache()
        
        logger.info(f"Bulk unquarantined {restored_count} images")
        
        return HTMLResponse(
            content="",
            headers={"HX-Trigger": f'{{"showMessage": {{"message": "{restored_count} image(s) restored successfully", "type": "success"}}}}'}
        )
    except Exception as e:
        logger.error(f"Failed to restore images: {e}", exc_info=True)
        return HTMLResponse(
            content="",
            status_code=500,
            headers={"HX-Trigger": f'{{"showMessage": {{"message": "Failed to restore images: {str(e)}", "type": "error"}}}}'}
        )


@router.delete("/quarantine/purge/{image_id}", response_class=HTMLResponse)
async def purge_image(image_id: int, session: Session = Depends(get_session)):
    """Permanently purge a quarantined image (delete from registry AND database)."""
    try:
        image = session.get(ImageArtifact, image_id)
        if not image:
            return HTMLResponse(content="Image not found", status_code=404)
        
        # Calculate savings before deletion
        savings_usd = CostCalculator.calculate_monthly_cost(image.size_bytes, image.source)
        
        # Delete from registry first
        client = RegistryClientFactory.get_client()
        if image.source != "Local":
            remote_configs = session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
            conf = next((c for c in remote_configs if c.name == image.source), None)
            if conf:
                client = RegistryClientFactory.get_client(conf)
        result = client.delete_image(session, image.digest, dry_run=False)
        
        if not result["success"]:
            error_msg = result.get('message', 'Unknown error')
            logger.warning(f"Purge failed for registry deletion: {error_msg}")
            return HTMLResponse(
                content="",
                status_code=500,
                headers={"HX-Trigger": f'{{"showMessage": {{"message": "Failed to delete from registry: {error_msg}", "type": "error"}}}}'}
            )
        
        # Audit log
        audit = AuditLog(
            action="PURGE",
            image_id=image.digest,
            image_tags=image.tags,
            source=image.source,
            bytes_freed=image.size_bytes,
            savings_usd=savings_usd,
            timestamp=datetime.utcnow()
        )
        session.add(audit)
        
        # Delete from database
        session.delete(image)
        session.commit()
        
        clear_image_cache()
        
        logger.info(f"Purged image: {image.tags[0] if image.tags else image.digest[:12]} (freed {image.size_bytes} bytes, ${savings_usd:.2f}/mo)")
        
        return HTMLResponse(
            content="",
            headers={"HX-Trigger": '{"showMessage": {"message": "Image purged successfully", "type": "success"}}'}
        )
    except Exception as e:
        logger.error(f"Failed to purge image: {e}", exc_info=True)
        return HTMLResponse(
            content="",
            status_code=500,
            headers={"HX-Trigger": f'{{"showMessage": {{"message": "Failed to purge image: {str(e)}", "type": "error"}}}}'}
        )


@router.delete("/quarantine/purge/bulk", response_class=HTMLResponse)
async def purge_bulk(
    image_ids: List[int] = Body(..., embed=True),
    session: Session = Depends(get_session)
):
    """Permanently purge multiple quarantined images (delete from registry AND database)."""
    try:
        if not image_ids:
            return HTMLResponse(content="No images selected", status_code=400)
        
        client = RegistryClientFactory.get_client()
        purged_count = 0
        failed_count = 0
        total_savings = 0.0
        
        for image_id in image_ids:
            image = session.get(ImageArtifact, image_id)
            if image:
                # Calculate savings
                savings_usd = CostCalculator.calculate_monthly_cost(image.size_bytes, image.source)
                
                # Delete from registry
                client = RegistryClientFactory.get_client()
                if image.source != "Local":
                    remote_configs = session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
                    conf = next((c for c in remote_configs if c.name == image.source), None)
                    if conf:
                        client = RegistryClientFactory.get_client(conf)
                result = client.delete_image(session, image.digest, dry_run=False)
                
                if result["success"]:
                    # Audit log
                    audit = AuditLog(
                        action="PURGE",
                        image_id=image.digest,
                        image_tags=image.tags,
                        source=image.source,
                        bytes_freed=image.size_bytes,
                        savings_usd=savings_usd,
                        timestamp=datetime.utcnow()
                    )
                    session.add(audit)
                    
                    # Delete from database
                    session.delete(image)
                    purged_count += 1
                    total_savings += savings_usd
                else:
                    failed_count += 1
                    logger.warning(f"Failed to purge {image.digest[:12]}: {result.get('message', 'Unknown error')}")
        
        session.commit()
        
        clear_image_cache()
        
        logger.info(f"Bulk purged {purged_count} images (failed: {failed_count}, savings: ${total_savings:.2f}/mo)")
        
        msg = f"{purged_count} image(s) purged successfully"
        if failed_count > 0:
            msg += f" ({failed_count} failed)"
        
        return HTMLResponse(
            content="",
            headers={"HX-Trigger": f'{{"showMessage": {{"message": "{msg}", "type": "success"}}}}'}
        )
    except Exception as e:
        logger.error(f"Failed to purge images: {e}", exc_info=True)
        return HTMLResponse(
            content="",
            status_code=500,
            headers={"HX-Trigger": f'{{"showMessage": {{"message": "Failed to purge images: {str(e)}", "type": "error"}}}}'}
        )
