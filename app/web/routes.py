"""API routes for Dredge"""

import asyncio
from html import escape
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Depends, HTTPException, Response, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import logging
from sqlmodel import Session, select, col
from sqlalchemy import func

from app.core.registry import RegistryClientFactory, clear_image_cache
from app.core.finops import CostCalculator
from app.core.db import get_session
from app.core.notify import send_notification
from app.core.metrics import DREDGE_SPACE_FREED_BYTES
from app.models import (
    ImageStatus, AuditLog, RegistryConfig, RegistryType, 
    AppSettings, CleanupPolicy, ImageArtifact, MetricSnapshot,
    VolumeArtifact, VolumeStatus
)
from app.core.scheduler import schedule_policy, unschedule_policy

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, session: Session = Depends(get_session)):
    """Render the dashboard"""
    # Fetch settings
    settings = session.get(AppSettings, 1)
    
    # Calculate real metrics from Docker
    monthly_waste = 0
    reclaimable_gb = 0
    efficiency = 100
    has_scanned = False
    chart_data = None
    
    images = []
    volumes = []
    bloated_images = []
    
    try:
        # 1. Try Live Scan (Local)
        try:
            local_client = RegistryClientFactory.get_client()
            images.extend(local_client.list_images())
            volumes.extend(local_client.list_volumes())
        except Exception as e:
            logger.warning(f"Local Docker scan failed: {e}")

        # 2. Try Remote Registries
        remote_configs = session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
        for config in remote_configs:
            try:
                remote_client = RegistryClientFactory.get_client(config)
                images.extend(remote_client.list_images())
            except Exception as e:
                logger.warning(f"Failed to fetch from registry {config.name}: {e}")

        # 3. ALWAYS use Database for chart composition (fake data priority)
        #    This ensures seeded fake data shows up in the donut chart
        db_images = session.exec(select(ImageArtifact)).all()
        db_volumes = session.exec(select(VolumeArtifact)).all()
        
        # Use DB data for chart - this is the seeded fake data
        if db_images:
            images = db_images
        if db_volumes:
            volumes = db_volumes
            
        # If we have data now, process it
        if images or volumes:
            has_scanned = True
            
            # Simple cost logic & bloat collection
            for img in images:
                monthly_waste += CostCalculator.calculate_monthly_cost(img.size_bytes, img.source)
                reclaimable_gb += img.size_bytes / (1024**3)
                
                if img.bloat_score < 80:
                    bloated_images.append(img)
                    
            for vol in volumes:
                monthly_waste += CostCalculator.calculate_monthly_cost(vol.size_bytes, vol.source)
                reclaimable_gb += vol.size_bytes / (1024**3)

            # Sort bloated images by score (worst first)
            bloated_images.sort(key=lambda x: x.bloat_score)
            bloated_images = bloated_images[:5]

            # Build storage composition data for donut chart
            total_images_bytes = sum(img.size_bytes for img in images)
            waste_bytes = sum(
                img.size_bytes for img in images
                if not img.tags or img.tags == ["<none>:<none>"] or any("<none>" in t for t in img.tags)
            )
            
            # Separate active vs dangling volumes
            dangling_volumes = [v for v in volumes if v.status.value == "DANGLING"]
            active_volumes = [v for v in volumes if v.status.value != "DANGLING"]
            
            dangling_volumes_bytes = sum(v.size_bytes for v in dangling_volumes)
            active_volumes_bytes = sum(v.size_bytes for v in active_volumes)
            
            # Final safety check for chart values
            images_gb = total_images_bytes / (1024**3)
            active_vol_gb = active_volumes_bytes / (1024**3)
            dangling_vol_gb = dangling_volumes_bytes / (1024**3)
            w_gb = waste_bytes / (1024**3)
            
            chart_data = {
                "images_gb": round(images_gb, 2),
                "active_volumes_gb": round(active_vol_gb, 2),
                "dangling_volumes_gb": round(dangling_vol_gb, 2),
                "waste_gb": round(w_gb, 2),
            }
            
            # Calculate efficiency: (active resources / total resources) * 100
            total_resources_gb = images_gb + active_vol_gb + dangling_vol_gb + w_gb
            active_resources_gb = images_gb - w_gb + active_vol_gb  # Active images + Active volumes (excludes waste)
            
            if total_resources_gb > 0:
                efficiency = (active_resources_gb / total_resources_gb) * 100
            else:
                efficiency = 100  # Default when no resources
        
    except Exception as e:
        logger.error(f"Failed to process dashboard metrics: {e}", exc_info=True)
        
    # Fetch registries for UI
    active_registries = session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
    registry_count = session.exec(select(func.count(RegistryConfig.id))).one()
    
    budget_percent = 0
    if settings and settings.monthly_budget > 0:
        budget_percent = (monthly_waste / settings.monthly_budget) * 100
        
    if chart_data is None:
        chart_data = {"images_gb": 0, "active_volumes_gb": 0, "dangling_volumes_gb": 0, "waste_gb": 0}

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "settings": settings,
            "registry_count": registry_count,
            "active_registries": active_registries,
            "monthly_waste": monthly_waste,
            "reclaimable_gb": reclaimable_gb,
            "efficiency": efficiency,
            "total_images": len(images),
            "total_volumes": len(volumes),
            "has_scanned": has_scanned,
            "budget_percent": budget_percent,
            "bloated_images": bloated_images,
            "chart_data": chart_data,
        }
    )


@router.get("/images", response_class=HTMLResponse)
async def images_view(request: Request, session: Session = Depends(get_session)):
    """Render the images view shell (Data loaded via HTMX)"""
    try:
        settings = session.get(AppSettings, 1)
        
        # Collect unique sources from CONFIG, not live data, for the filter dropdown
        # This is fast and doesn't require network calls
        all_sources = ["Local"]
        remote_configs = session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
        for conf in remote_configs:
            # Clean names for dropdown
            name = conf.name or conf.type.value
            if name not in all_sources:
                all_sources.append(name)
        
        # We assume Docker Hub / GHCR are standard names if used in types, but let's stick to what list_images returns
        # Actually, list_images returns config.name. So using config.name is correct.
        
    except Exception as e:
        logger.error(f"Failed to init images view: {str(e)}")
        all_sources = ["Local"]
        settings = None
        
    return templates.TemplateResponse(
        request,
        "images.html",
        {
            "images": [], # Empty initially for lazy load
            "sources": all_sources,
            "current_source": request.query_params.get("source", "All"),
            "settings": settings,
            "lazy_load": True # Flag to trigger HTMX load
        }
    )


@router.get("/volumes", response_class=HTMLResponse)
async def volumes_view(request: Request, session: Session = Depends(get_session)):
    """Render the volumes view with combined results"""
    try:
        source_filter = request.query_params.get("source")
        settings = session.get(AppSettings, 1)
        
        # Local volumes
        volumes = []
        try:
            local_client = RegistryClientFactory.get_client()
            volumes = local_client.list_volumes()
        except Exception as e:
            logger.warning(f"Failed to fetch live volumes: {e}")
            
        # Fallback to DB
        if not volumes:
            volumes = session.exec(select(VolumeArtifact)).all()
        
        # Apply Filtering
        if source_filter and source_filter != "All":
            volumes = [v for v in volumes if v.source == source_filter]
            
        all_sources = ["Local"] # Volumes are always local for now
        
    except Exception as e:
        logger.error(f"Failed to fetch volumes for view: {str(e)}")
        volumes = []
        all_sources = ["Local"]
        settings = None
        
    return templates.TemplateResponse(
        request,
        "volumes.html",
        {
            "volumes": volumes,
            "sources": all_sources,
            "current_source": source_filter or "All",
            "settings": settings,
        }
    )


@router.delete("/volumes/batch", response_class=HTMLResponse)
async def batch_delete_volumes(request: Request, session: Session = Depends(get_session)):
    """Batch delete selected volumes (Mocked for Demo)"""
    try:
        form_data = await request.form()
        selected = form_data.getlist("selected_volumes")
        if not selected:
            response = HTMLResponse(content="")
            response.headers["HX-Trigger"] = '{"showMessage": {"message": "No volumes selected", "type": "error"}}'
            return response
        msg = f"Action simulated in Demo Mode: Purged {len(selected)} volumes."
        response = HTMLResponse(content="")
        response.headers["HX-Trigger"] = f'{{"showMessage": {{"message": "{msg}", "type": "success"}}, "refreshVolumes": true}}'
        return response
        
    except Exception as e:
        logger.error(f"Batch volume delete failed: {e}")
        return HTMLResponse(
            content=f'<div class="alert error">Batch deletion failed: {escape(str(e))}</div>',
            status_code=500
        )


@router.delete("/volumes/{name}", response_class=HTMLResponse)
async def delete_volume(name: str, session: Session = Depends(get_session)):
    """Delete a Docker volume (Mocked for Demo)"""
    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = '{"showMessage": {"message": "Action simulated in Demo Mode: Volume purged", "type": "success"}}'
    return response


@router.get("/policies", response_class=HTMLResponse)
async def policies_view(request: Request, session: Session = Depends(get_session)):
    """Render the policies view"""
    statement = select(CleanupPolicy).limit(1)
    policy = session.exec(statement).first()
    
    if not policy:
        policy = CleanupPolicy(name="Default Cleanup")
        session.add(policy)
        session.commit()
        session.refresh(policy)
        
    return templates.TemplateResponse(
        request,
        "policies.html",
        {"policy": policy}
    )


@router.post("/policies", response_class=HTMLResponse)
async def update_policy(request: Request, session: Session = Depends(get_session)):
    """Update cleanup policy"""
    try:
        form_data = await request.form()
        statement = select(CleanupPolicy).limit(1)
        policy = session.exec(statement).first()
        
        # New scheduling fields
        schedule_enabled = form_data.get("schedule_enabled") == "on"
        schedule_cron = form_data.get("schedule_cron", "").strip()
        
        if policy:
            policy.keep_count = int(form_data.get("keep_count", 3))
            policy.max_age_days = int(form_data.get("max_age_days", 30))
            policy.regex_whitelist = str(form_data.get("regex_whitelist", ""))
            policy.enabled = form_data.get("enabled") == "on"
            
            # Update scheduling
            policy.schedule_enabled = schedule_enabled
            policy.schedule_cron = schedule_cron if schedule_cron else None
            
            session.add(policy)
            session.commit()
            session.refresh(policy)
            
            # Apply scheduling change
            if policy.schedule_enabled and policy.schedule_cron:
                schedule_policy(policy)
            else:
                unschedule_policy(policy.id)
                
        return templates.TemplateResponse(
            request,
            "policies.html",
            {"policy": policy, "updated": True}
        )
    except Exception as e:
        logger.error(f"Failed to update policy: {e}", exc_info=True)
        return templates.TemplateResponse(
            request,
            "policies.html",
            {"policy": None, "error": str(e)}
        )


@router.delete("/policies/{policy_id}")
async def delete_policy(policy_id: int, session: Session = Depends(get_session)):
    """Delete a cleanup policy"""
    try:
        policy = session.get(CleanupPolicy, policy_id)
        
        if not policy:
            return HTMLResponse(content="Policy not found", status_code=404)
        
        # Unschedule before deleting
        unschedule_policy(policy_id)
        
        session.delete(policy)
        session.commit()
        
        return HTMLResponse(
            content="",
            headers={"HX-Trigger": '{"showMessage": {"message": "Policy deleted", "type": "success"}}'}
        )
    except Exception as e:
        logger.error(f"Failed to delete policy: {e}", exc_info=True)
        return HTMLResponse(
            content="",
            status_code=500,
            headers={"HX-Trigger": f'{{"showMessage": {{"message": "Error: {str(e)}", "type": "error"}}}}'}
        )


@router.get("/logs", response_class=HTMLResponse)
async def logs_view(
    request: Request,
    session: Session = Depends(get_session),
    page: int = 1,
    limit: int = 50,
    action_filter: Optional[str] = None,
    source_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
):
    """Render the logs view with pagination and filters"""
    # Build base query
    statement = select(AuditLog)
    
    # Apply action filter
    if action_filter and action_filter != "ALL":
        if action_filter == "PURGE":
            statement = statement.where(AuditLog.action.in_(["PURGE", "DELETE"]))
        else:
            statement = statement.where(AuditLog.action == action_filter)
    
    # Apply source filter
    if source_filter and source_filter != "ALL":
        statement = statement.where(AuditLog.source == source_filter)
    
    # Apply date range filter
    if date_from:
        try:
            from_date = datetime.strptime(date_from, "%Y-%m-%d")
            statement = statement.where(AuditLog.timestamp >= from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, "%Y-%m-%d")
            # Add 1 day to include the entire end date
            to_date = to_date + timedelta(days=1)
            statement = statement.where(AuditLog.timestamp < to_date)
        except ValueError:
            pass
    
    # Get total count with filters applied
    count_statement = select(func.count()).select_from(statement.alias())
    total_count = session.exec(count_statement).one()
    
    # Calculate offset
    offset = (page - 1) * limit
    
    # Fetch paginated logs
    statement = statement.order_by(col(AuditLog.timestamp).desc()).limit(limit).offset(offset)
    logs = session.exec(statement).all()
    
    # Calculate pagination metadata
    total_pages = max(1, (total_count + limit - 1) // limit)
    has_prev = page > 1
    has_next = page < total_pages
    
    # Get unique actions and sources for filter dropdowns
    raw_actions = session.exec(
        select(AuditLog.action).distinct().order_by(AuditLog.action)
    ).all()
    # Normalize: treat DELETE as PURGE and deduplicate
    unique_actions = sorted(set("PURGE" if a == "DELETE" else a for a in raw_actions))
    unique_sources = session.exec(
        select(AuditLog.source).distinct().order_by(AuditLog.source)
    ).all()
    
    settings = session.get(AppSettings, 1)
    
    return templates.TemplateResponse(
        request,
        "logs.html",
        {
            "logs": logs,
            "settings": settings,
            "page": page,
            "limit": limit,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_prev": has_prev,
            "has_next": has_next,
            "action_filter": action_filter or "ALL",
            "source_filter": source_filter or "ALL",
            "date_from": date_from or "",
            "date_to": date_to or "",
            "unique_actions": unique_actions,
            "unique_sources": unique_sources,
        }
    )


@router.get("/logs/export")
async def export_logs(
    request: Request,
    session: Session = Depends(get_session),
    action_filter: Optional[str] = None,
    source_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
):
    """Export audit logs to CSV with filters applied"""
    from fastapi.responses import StreamingResponse
    import csv
    from io import StringIO
    
    # Build query with same filter logic as logs_view
    statement = select(AuditLog)
    
    if action_filter and action_filter != "ALL":
        statement = statement.where(AuditLog.action == action_filter)
    
    if source_filter and source_filter != "ALL":
        statement = statement.where(AuditLog.source == source_filter)
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, "%Y-%m-%d")
            statement = statement.where(AuditLog.timestamp >= from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, "%Y-%m-%d")
            to_date = to_date + timedelta(days=1)
            statement = statement.where(AuditLog.timestamp < to_date)
        except ValueError:
            pass
    
    statement = statement.order_by(col(AuditLog.timestamp).desc())
    logs = session.exec(statement).all()
    
    # Get settings for currency symbol
    settings = session.get(AppSettings, 1)
    symbol = settings.currency_symbol if settings else "$"
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "Timestamp",
        "Action",
        "Source",
        "Image/Resource",
        "Image ID",
        "Space Freed (GB)",
        f"Monthly Savings ({symbol})",
        "Dry Run"
    ])
    
    # Write data
    for log in logs:
        writer.writerow([
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.action,
            log.source,
            log.image_tags[0] if log.image_tags else log.image_id[:20],
            log.image_id,
            round(log.bytes_freed / (1024**3), 2),
            round(log.savings_usd, 2),
            "Yes" if log.dry_run else "No"
        ])
    
    # Return as downloadable file
    output.seek(0)
    filename = f"dredge_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/registries", response_class=HTMLResponse)
async def registries_view(request: Request, session: Session = Depends(get_session)):
    """Render the registries management view"""
    statement = select(RegistryConfig).order_by(RegistryConfig.created_at)
    registries = session.exec(statement).all()
    
    return templates.TemplateResponse(
        request,
        "registries.html",
        {
            "registries": registries,
        }
    )


from app.core.security import encrypt_secret


@router.post("/registries/test", response_class=HTMLResponse)
async def test_registry_connection(request: Request, session: Session = Depends(get_session)):
    """Test connection to a registry (Mocked for Demo)"""
    return HTMLResponse(
        content='<div class="alert success">Connection successful (Demo Mode)</div>',
        headers={"HX-Trigger": '{"showMessage": {"message": "Connection Successful", "type": "success"}}'}
    )
@router.post("/registries", response_class=HTMLResponse)
async def add_registry(request: Request, session: Session = Depends(get_session)):
    """Add a new remote registry"""
    try:
        form_data = await request.form()
        
        name = str(form_data.get("name", "")).strip()
        reg_type = str(form_data.get("type", "DOCKERHUB"))
        endpoint = str(form_data.get("endpoint", "")).strip()
        username = str(form_data.get("username", "")).strip() or None
        password = str(form_data.get("password", "")).strip() or None
        
        # Validation
        if not name:
            raise HTTPException(status_code=400, detail="Registry name is required")
        
        # Encrypt password before storing
        encrypted_password = encrypt_secret(password) if password else None
        
        new_reg = RegistryConfig(
            name=name,
            type=RegistryType(reg_type),
            endpoint=endpoint,
            username=username,
            password=encrypted_password,
        )
        
        session.add(new_reg)
        session.commit()
        
        logger.info(f"Added new registry: {name} (Type: {reg_type})")
        
    except Exception as e:
        logger.error(f"Failed to add registry: {str(e)}")
        # In a real app, we'd return a better error to the UI
    
    # Return the updated list via HTMX
    statement = select(RegistryConfig).order_by(RegistryConfig.created_at)
    registries = session.exec(statement).all()
    
    # If HTMX request, we return the partial with a success trigger
    response = templates.TemplateResponse(
        request,
        "partials/registries_list.html",
        {
            "registries": registries,
        }
    )
    response.headers["HX-Trigger"] = '{"showMessage": {"message": "Registry Added Successfully", "type": "success"}}'
    return response


@router.get("/registries/{reg_id}/edit", response_class=HTMLResponse)
async def edit_registry_modal(reg_id: int, request: Request, session: Session = Depends(get_session)):
    """Return the edit registry modal"""
    registry = session.get(RegistryConfig, reg_id)
    if not registry:
        raise HTTPException(status_code=404, detail="Registry not found")
        
    return templates.TemplateResponse(
        request,
        "partials/edit_registry_modal.html",
        {"registry": registry}
    )


@router.put("/registries/{reg_id}", response_class=HTMLResponse)
async def update_registry(reg_id: int, request: Request, session: Session = Depends(get_session)):
    """Update an existing registry configuration"""
    registry = session.get(RegistryConfig, reg_id)
    if not registry:
        raise HTTPException(status_code=404, detail="Registry not found")
        
    try:
        form_data = await request.form()
        
        name = str(form_data.get("name", "")).strip()
        reg_type = str(form_data.get("type", "DOCKERHUB"))
        endpoint = str(form_data.get("endpoint", "")).strip()
        username = str(form_data.get("username", "")).strip() or None
        password = str(form_data.get("password", "")).strip() or None
        
        # Validation
        if not name:
            raise HTTPException(status_code=400, detail="Registry name is required")
            
        # Update fields
        registry.name = name
        registry.type = RegistryType(reg_type)
        registry.endpoint = endpoint
        registry.username = username
        
        # Only update password if provided
        if password:
            registry.password = encrypt_secret(password)
            
        session.add(registry)
        session.commit()
        session.refresh(registry)
        
        logger.info(f"Updated registry: {name} (ID: {reg_id})")
        
    except Exception as e:
        logger.error(f"Failed to update registry: {str(e)}")
        # In a real app, handle error UI
        
    # Return the updated list via HTMX
    registries = session.exec(select(RegistryConfig).order_by(RegistryConfig.created_at)).all()
    
    response = templates.TemplateResponse(
        request,
        "partials/registries_list.html",
        {"registries": registries}
    )
    response.headers["HX-Trigger"] = '{"showMessage": {"message": "Registry Updated Successfully", "type": "success"}}'
    return response


@router.delete("/registries/{reg_id}", response_class=HTMLResponse)
async def delete_registry(reg_id: int, session: Session = Depends(get_session)):
    """Delete a registry configuration (Mocked for Demo) Surpress delete."""
    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = '{"showMessage": {"message": "Action simulated in Demo Mode: Registry Removed", "type": "info"}}'
    return response


@router.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request, session: Session = Depends(get_session)):
    """Render the global settings view"""
    settings = session.get(AppSettings, 1)
    section = request.query_params.get("section", "finops")
    
    context = {
        "request": request,
        "settings": settings,
        "section": section
    }
    
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(f"partials/settings_{section}.html", context)
        
    return templates.TemplateResponse("settings.html", context)


@router.post("/settings", response_class=HTMLResponse)
async def update_settings(request: Request, session: Session = Depends(get_session)):
    """Update global application settings"""
    form_data = await request.form()
    settings = session.get(AppSettings, 1)
    section = str(form_data.get("section", "finops"))
    
    if not settings:
        settings = AppSettings(id=1)
        session.add(settings)
    
    # Demo Mode: Bypass save
    response = templates.TemplateResponse(
        request,
        f"partials/settings_{section}.html",
        {"settings": settings, "updated": True, "section": section}
    )
    response.headers["HX-Trigger"] = '{"showMessage": {"message": "Action simulated in Demo Mode: Settings Saved", "type": "success"}}'
    return response


@router.post("/settings/reset", response_class=HTMLResponse)
async def reset_database(request: Request, session: Session = Depends(get_session)):
    """Reset the database (Danger Zone)"""
    # Logic to flush tables could go here
    # For MVP just return success message
    return HTMLResponse(content="<p style='color: var(--danger);'>Database reset not fully implemented for safety.</p>")


@router.post("/auth/logout", response_class=HTMLResponse)
async def logout(response: Response):
    """Logout by clearing the access_token cookie"""
    response.delete_cookie("access_token")
    # Redirect to home or return a trigger to reload/redirect
    return HTMLResponse(
        content="<script>window.location.reload();</script>",
        headers={"HX-Trigger": '{"showMessage": {"message": "Logged out successfully", "type": "info"}}'}
    )


@router.post("/settings/notify-test", response_class=HTMLResponse)
async def test_notification(response: Response):
    """Send a test notification via Apprise"""
    await send_notification(
        title="Dredge - Test Notification",
        body="If you're reading this, your ChatOps integration is working! ⚓"
    )
    response.headers["HX-Trigger"] = '{"showMessage": "Test Notification Sent"}'
    return HTMLResponse(content="")


@router.get("/api/metrics/history")
async def metrics_history(session: Session = Depends(get_session)):
    """Get metrics history for charts"""
    try:
        # Get last 30 days
        cutoff = datetime.utcnow() - timedelta(days=30)
        statement = select(MetricSnapshot).where(MetricSnapshot.date >= cutoff).order_by(MetricSnapshot.date)
        snapshots = session.exec(statement).all()
        
        return [
            {
                "date": s.date.isoformat(),
                "total_cost_usd": s.total_cost_usd,
                "total_gb": s.total_gb,
                "total_images": s.total_images
            }
            for s in snapshots
        ]
    except Exception as e:
        logger.error(f"Failed to fetch metrics history: {e}")
        return []
@router.post("/scan-dashboard", response_class=HTMLResponse)
async def scan_dashboard(request: Request, response: Response, session: Session = Depends(get_session)):
    """Scan Docker images/volumes and return dashboard summary"""
    try:
        images = []
        volumes = []
        
        # Demo Mode: Bypass live scans and use seeded fake data
        pass
        # 3. Fallback to DB
        if not images:
            images = session.exec(select(ImageArtifact)).all()
        if not volumes:
            volumes = session.exec(select(VolumeArtifact)).all()

        total_images = len(images)
        total_volumes = len(volumes)
        
        total_bytes = 0
        monthly_cost = 0
        
        for img in images:
            total_bytes += img.size_bytes
            monthly_cost += CostCalculator.calculate_monthly_cost(img.size_bytes, img.source)
            
        for vol in volumes:
            total_bytes += vol.size_bytes
            monthly_cost += CostCalculator.calculate_monthly_cost(vol.size_bytes, vol.source)
            
        total_gb = total_bytes / (1024 ** 3)
        
        # Get settings for currency
        settings = session.get(AppSettings, 1)
        symbol = settings.currency_symbol if settings else "$"
        
        # Trigger notification
        await send_notification(
            title="Dredge Scan Completed",
            body=f"Found {total_images} images and {total_volumes} volumes totaling {total_gb:.2f} GB."
        )
        
        # Return dashboard summary HTML
        html = f"""
        <div style="text-align: center; padding: 2rem; background: rgba(0,119,182,0.05); border: 1px solid var(--primary); border-radius: 8px;">
            <i data-lucide="check-circle" style="width: 48px; height: 48px; color: var(--accent); margin-bottom: 1rem;"></i>
            <h3 style="color: var(--text-main); margin-bottom: 0.5rem;">Scan Complete</h3>
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.5rem; margin-top: 1.5rem; max-width: 500px; margin-left: auto; margin-right: auto;">
                <div>
                    <div style="font-size: 2rem; font-weight: 700; color: var(--accent);">{total_images}</div>
                    <div style="font-size: 0.9rem; color: var(--text-muted);">Images</div>
                </div>
                <div>
                    <div style="font-size: 2rem; font-weight: 700; color: var(--accent);">{total_volumes}</div>
                    <div style="font-size: 0.9rem; color: var(--text-muted);">Volumes</div>
                </div>
                <div>
                    <div style="font-size: 2rem; font-weight: 700; color: var(--text-main);">{total_gb:.2f} GB</div>
                    <div style="font-size: 0.9rem; color: var(--text-muted);">Total Size</div>
                </div>
                <div>
                    <div style="font-size: 2rem; font-weight: 700; color: var(--danger);">{symbol}{monthly_cost:.2f}</div>
                    <div style="font-size: 0.9rem; color: var(--text-muted);">Monthly Cost</div>
                </div>
            </div>
            <div style="margin-top: 1.5rem; display: flex; gap: 1rem; justify-content: center;">
                <a href="/images" class="btn outline">View Images</a>
                <a href="/volumes" class="btn outline">View Volumes</a>
            </div>
        </div>
        """
        
        response.headers["HX-Trigger"] = '{"showMessage": {"message": "Scan Complete", "type": "success"}, "refreshDashboard": true}'
        return HTMLResponse(content=html)
        
    except Exception as e:
        logger.error(f"Dashboard scan failed: {str(e)}", exc_info=True)
        return HTMLResponse(
            content=f'<div style="text-align: center; padding: 2rem; color: var(--danger);"><p>Scan failed: {escape(str(e))}</p><p style="font-size: 0.9rem; margin-top: 0.5rem;">Please check Docker daemon connection.</p></div>',
            status_code=500
        )


@router.post("/scan", response_class=HTMLResponse)
async def scan_images(request: Request, response: Response, session: Session = Depends(get_session)):
    """Scan images — returns DB images as table HTML for demo"""
    source_filter = request.query_params.get("source")
    settings = session.get(AppSettings, 1)

    statement = select(ImageArtifact)
    images = session.exec(statement).all()

    if source_filter and source_filter != "All":
        images = [img for img in images if img.source == source_filter]

    response.headers["HX-Trigger"] = '{"showMessage": {"message": "Scan complete (Demo Mode)", "type": "success"}}'
    return templates.TemplateResponse(
        request,
        "partials/images_table.html",
        {"images": images, "settings": settings},
    )

@router.post("/images/{digest}/restore", response_class=HTMLResponse)
async def restore_image(digest: str, response: Response, session: Session = Depends(get_session)):
    """Restore a quarantined image to ACTIVE status"""
    try:
        statement = select(ImageArtifact).where(ImageArtifact.digest == digest)
        image = session.exec(statement).first()
        
        if not image:
            # Try finding in Local Docker
            client = RegistryClientFactory.get_client()
            images = client.list_images()
            image = next((img for img in images if img.digest == digest), None)
            if image:
                session.add(image)
        
        if image:
            image.status = ImageStatus.ACTIVE
            image.expires_at = None
            session.add(image)
            session.commit()
            
            response.headers["HX-Trigger"] = '{"showMessage": "Image Restored to Active"}'
            return HTMLResponse(content="") # Row will be removed or updated via frontend logic
            
        raise HTTPException(status_code=404, detail="Image not found")
    except Exception as e:
        logger.error(f"Restore failed: {str(e)}")
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)

async def process_batch_deletion(selected_items: list[str], session: Session):
    """Background task for processing batch purges (registry + DB)"""
    try:
        success_count = 0
        fail_count = 0

        from app.core.db import engine

        with Session(engine) as bg_session:
            local_client = RegistryClientFactory.get_client()
            remote_configs = bg_session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
            remote_clients = {conf.name: RegistryClientFactory.get_client(conf) for conf in remote_configs}

            for item in selected_items:
                # Parse value: "digest|source" or just "digest"
                if "|" in item:
                    digest, source = item.split("|", 1)
                else:
                    digest = item
                    source = "Local"

                try:
                    # Select client
                    if source == "Local":
                        client = local_client
                    else:
                        client = remote_clients.get(source)
                        if not client:
                            logger.warning(f"No client found for source: {source}")
                            fail_count += 1
                            continue

                    # Look up image in DB for audit info
                    image = bg_session.exec(
                        select(ImageArtifact).where(ImageArtifact.digest == digest)
                    ).first()
                    savings_usd = CostCalculator.calculate_monthly_cost(image.size_bytes, source) if image else 0.0

                    # Perform registry deletion
                    result = client.delete_image(bg_session, digest, dry_run=False, force=True)
                    if result["success"]:
                        # Log PURGE
                        audit = AuditLog(
                            action="PURGE",
                            image_id=digest,
                            image_tags=image.tags if image else [],
                            source=source,
                            bytes_freed=image.size_bytes if image else 0,
                            savings_usd=savings_usd,
                            timestamp=datetime.utcnow()
                        )
                        bg_session.add(audit)

                        # Remove from database
                        if image:
                            bg_session.delete(image)

                        success_count += 1
                        logger.info(f"Purged {digest} from {source}")
                    else:
                        fail_count += 1
                        logger.warning(f"Failed to purge {digest}: {result['message']}")

                except Exception as e:
                    logger.error(f"Error purging {digest}: {e}")
                    fail_count += 1

            bg_session.commit()
            clear_image_cache()
            logger.info(f"Batch purge complete: {success_count} success, {fail_count} failed")

    except Exception as e:
        logger.error(f"Background batch purge failed: {e}", exc_info=True)

from fastapi import BackgroundTasks

@router.delete("/images/batch", response_class=HTMLResponse)
async def batch_delete_images(request: Request, background_tasks: BackgroundTasks):
    """Batch delete selected images (Async)"""
    try:
        form_data = await request.form()
        selected = form_data.getlist("selected_images")
        
        if not selected:
            response = HTMLResponse(content="")
            response.headers["HX-Trigger"] = '{"showMessage": {"message": "No images selected", "type": "error"}}'
            return response
            
        # Demo Mode: Bypass background task
        msg = f"Action simulated in Demo Mode: Deletion of {len(selected)} images started"
        response = Response(status_code=204)
        response.headers["HX-Trigger"] = f'{{"showMessage": {{"message": "{msg}", "type": "info"}}}}'
        return response
    except Exception as e:
        logger.error(f"Batch delete failed: {e}")
        return HTMLResponse(
            content=f'<div class="alert error">Batch deletion failed: {escape(str(e))}</div>',
            status_code=500
        )

@router.delete("/images/{digest}", response_class=HTMLResponse)
async def purge_image(digest: str, response: Response, session: Session = Depends(get_session)):
    """Purge (permanently delete) a Docker image from registry AND database with transactional safety"""
    try:
        # 1. Look up image in DB for context
        statement = select(ImageArtifact).where(ImageArtifact.digest == digest)
        image = session.exec(statement).first()

        if not image:
            # If not in DB, we still try to delete from registry if caller knows the digest
            source = "Local"
            savings_usd = 0.0
            image_tags = []
        else:
            source = image.source
            savings_usd = CostCalculator.calculate_monthly_cost(image.size_bytes, source)
            image_tags = image.tags or []

        # 2. Pick the right client
        client = RegistryClientFactory.get_client()
        if source != "Local":
            remote_configs = session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
            conf = next((c for c in remote_configs if c.name == source), None)
            if conf:
                client = RegistryClientFactory.get_client(conf)

        # Demo Mode: Simulate success
        response.headers["HX-Trigger"] = '{"showMessage": {"message": "Action simulated in Demo Mode: Image purged", "type": "success"}}'
        return HTMLResponse(content="")

    except Exception as e:
        session.rollback()
        logger.error(f"Purge failed: {str(e)}", exc_info=True)
        return HTMLResponse(
            content=f'<tr class="error-row"><td colspan="8" style="color: var(--danger);">Purge failed: {escape(str(e))}</td></tr>',
            status_code=500
        )

@router.post("/policies/run", response_class=HTMLResponse)
async def run_policies(request: Request, session: Session = Depends(get_session)):
    """Manually trigger policy enforcement or preview candidates."""
    try:
        query_params = request.query_params
        preview = query_params.get("preview", "false").lower() == "true"
        confirmed = query_params.get("confirmed", "false").lower() == "true"
        
        from app.core.policies import PolicyEnforcer
        enforcer = PolicyEnforcer(session)
        
        # If we need a preview, run in dry_run mode
        # For manual runs, ignore the enabled flag
        if preview:
            result = enforcer.run_all(dry_run=True, ignore_enabled=True)
            return templates.TemplateResponse(
                request,
                "partials/policy_preview_modal.html",
                {
                    "request": request,
                    "candidates": result["candidates"],
                    "quarantined_count": len(result["candidates"])
                }
            )
            
        # Actual run (either direct or confirmed)
        # For manual runs, ignore the enabled flag
        result = enforcer.run_all(dry_run=False, ignore_enabled=True)
        
        msg = f"Policy Run Complete: Quarantined {result['quarantined']} images."
        if result['errors'] > 0:
            msg += f" ({result['errors']} errors occurred)"
            
        type = "success" if result['errors'] == 0 else "warning"
        
        return HTMLResponse(
            content="",
            headers={"HX-Trigger": f'{{"showMessage": {{"message": "{msg}", "type": "{type}"}}}}'}
        )
    except Exception as e:
        logger.error(f"Policy run failed: {e}", exc_info=True)
        return HTMLResponse(
            content="",
            status_code=500,
            headers={"HX-Trigger": f'{{"showMessage": {{"message": "Policy Run Failed: {str(e)}", "type": "error"}}}}'}
        )

