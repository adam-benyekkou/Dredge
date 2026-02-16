"""API routes for Dredge"""

from html import escape
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import logging
from sqlmodel import Session, select, col

from app.core.registry import LocalDockerClient
from app.core.finops import CostCalculator
from app.core.db import get_session
from app.models import ImageStatus, AuditLog

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the dashboard"""
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "monthly_waste": 0,
            "reclaimable_gb": 0,
            "efficiency": 100,
        }
    )


@router.get("/images", response_class=HTMLResponse)
async def images_view(request: Request, session: Session = Depends(get_session)):
    """Render the images view"""
    try:
        client = LocalDockerClient()
        images = client.list_images()
    except Exception as e:
        logger.error(f"Failed to fetch images for view: {str(e)}")
        images = []
        
    return templates.TemplateResponse(
        "images.html",
        {
            "request": request,
            "images": images,
        }
    )


@router.get("/policies", response_class=HTMLResponse)
async def policies_view(request: Request, session: Session = Depends(get_session)):
    """Render the policies view"""
    return templates.TemplateResponse(
        "policies.html",
        {
            "request": request,
        }
    )


@router.get("/logs", response_class=HTMLResponse)
async def logs_view(request: Request, session: Session = Depends(get_session)):
    """Render the logs view"""
    # Fetch latest 50 logs
    statement = select(AuditLog).order_by(col(AuditLog.timestamp).desc()).limit(50)
    logs = session.exec(statement).all()
    
    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "logs": logs,
        }
    )


@router.post("/scan", response_class=HTMLResponse)
async def scan_images(request: Request, session: Session = Depends(get_session)):
    """Scan Docker images and return HTML table rows"""
    try:
        # Initialize Docker client
        client = LocalDockerClient()
        
        # Get all images
        images = client.list_images()
        
        # Calculate total stats
        total_size_bytes = sum(img.size_bytes for img in images)
        total_cost = CostCalculator.calculate_monthly_cost(total_size_bytes)
        
        # Build HTML response for HTMX (WITH XSS PROTECTION)
        html_rows = []
        for img in images:
            # SECURITY FIX: Escape all user-controlled data
            repo = escape(img.tags[0].split(':')[0] if img.tags else 'N/A')
            tag = escape(img.tags[0].split(':')[1] if ':' in (img.tags[0] if img.tags else '') else 'latest')
            digest_escaped = escape(img.digest)
            size_gb = img.size_bytes / (1024 ** 3)
            cost = CostCalculator.calculate_monthly_cost(img.size_bytes)
            created = escape(img.created_at.strftime('%Y-%m-%d %H:%M') if img.created_at else 'N/A')
            
            # Status badge logic
            status = ImageStatus.ACTIVE  # Default for scan for now
            status_class = status.lower()
            
            # ID for the row (must be safe for CSS selectors)
            row_id = f"image-{digest_escaped.replace(':', '-')}"
            
            html_rows.append(f"""
                <tr id="{row_id}">
                    <td><input type="checkbox" name="image-select" value="{digest_escaped}"></td>
                    <td>{repo}</td>
                    <td>{tag}</td>
                    <td>{size_gb:.2f} GB</td>
                    <td>{created}</td>
                    <td><span class="badge {status_class}">{status}</span></td>
                    <td>${cost:.2f}/mo</td>
                    <td>
                        <button 
                            class="action-btn danger" 
                            hx-delete="/images/{digest_escaped}"
                            hx-confirm="Are you sure you want to purge this image?"
                            hx-target="#{row_id}"
                            hx-swap="outerHTML"
                        >
                            Purge
                        </button>
                    </td>
                </tr>
            """)
        
        result_html = f"""
            <div class="images-table">
                <table>
                    <thead>
                        <tr>
                            <th><input type="checkbox" id="select-all"></th>
                            <th>Repository</th>
                            <th>Tag</th>
                            <th>Size</th>
                            <th>Created</th>
                            <th>Status</th>
                            <th>Monthly Cost</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(html_rows)}
                    </tbody>
                </table>
            </div>
            <p style="margin-top: 1rem; color: var(--text-muted);">
                Found {len(images)} images | Total: {total_size_bytes / (1024**3):.2f} GB | Monthly cost: ${total_cost:.2f}
            </p>
        """
        
        return HTMLResponse(content=result_html)
        
    except Exception as e:
        # SECURITY FIX: Log full error internally, return generic message
        logger.error(f"Scan failed: {str(e)}", exc_info=True)
        return HTMLResponse(
            content='<p style="color: var(--danger);">Scan failed. Please check Docker daemon connection.</p>',
            status_code=500
        )


@router.delete("/images/{digest}", response_class=HTMLResponse)
async def purge_image(digest: str, session: Session = Depends(get_session)):
    """Purge (permanently delete) a Docker image"""
    try:
        # SECURITY FIX: The registry client already validates digest format
        client = LocalDockerClient()
        
        # Perform real deletion (dry_run=False)
        result = client.delete_image(session, digest, dry_run=False)
        
        if result["success"]:
            session.commit()
            # Return empty response or something indicating success for HTMX to swap
            # Since target is the row itself, returning empty string removes the row
            return HTMLResponse(content="")
        else:
            logger.warning(f"Purge failed for {digest}: {result['message']}")
            # Could return a row with an error message instead of removing it
            return HTMLResponse(
                content=f'<tr class="error-row"><td colspan="8" style="color: var(--danger);">{result["message"]}</td></tr>',
                status_code=200 # HTMX still swaps it
            )
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Purge failed: {str(e)}", exc_info=True)
        return HTMLResponse(
            content=f'<tr class="error-row"><td colspan="8" style="color: var(--danger);">Purge failed: {escape(str(e))}</td></tr>',
            status_code=500
        )
