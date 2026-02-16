"""API routes for Dredge"""

from html import escape
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import logging
from sqlmodel import Session, select, col

from app.core.registry import RegistryClientFactory
from app.core.finops import CostCalculator
from app.core.db import get_session
from app.core.notify import send_notification
from app.models import ImageStatus, AuditLog, RegistryConfig, RegistryType, AppSettings, CleanupPolicy, ImageArtifact

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, session: Session = Depends(get_session)):
    """Render the dashboard"""
    # Fetch settings
    settings = session.get(AppSettings, 1)
    
    # Fetch registry count
    reg_count = session.query(RegistryConfig).count()
    
    # Calculate real metrics from Docker
    monthly_waste = 0
    reclaimable_gb = 0
    efficiency = 100
    has_scanned = False
    
    total_images = 0
    total_volumes = 0
    
    try:
        client = RegistryClientFactory.get_client()
        images = client.list_images()
        volumes = client.list_volumes()
        
        total_images = len(images)
        total_volumes = len(volumes)
        total_image_bytes = sum(img.size_bytes for img in images)
        total_volume_bytes = sum(vol.size_bytes for vol in volumes)
        total_bytes = total_image_bytes + total_volume_bytes
        
        if total_bytes > 0:
            has_scanned = True
            reclaimable_gb = total_bytes / (1024 ** 3)
            monthly_waste = CostCalculator.calculate_monthly_cost(total_bytes)
            # Simple efficiency calculation (100% if nothing to clean, lower if there's waste)
            efficiency = 100
    except Exception as e:
        logger.warning(f"Could not fetch Docker metrics for dashboard: {e}")
    
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "monthly_waste": monthly_waste,
            "reclaimable_gb": reclaimable_gb,
            "efficiency": efficiency,
            "registry_count": reg_count,
            "settings": settings,
            "has_scanned": has_scanned,
            "total_images": total_images,
            "total_volumes": total_volumes,
        }
    )


@router.get("/images", response_class=HTMLResponse)
async def images_view(request: Request, session: Session = Depends(get_session)):
    """Render the images view with combined results from all registries"""
    try:
        source_filter = request.query_params.get("source")
        settings = session.get(AppSettings, 1)
        
        # 1. Fetch Local Images
        local_client = RegistryClientFactory.get_client()
        images = local_client.list_images()
        
        # 2. Fetch Remote Images (Active Registries Only)
        remote_configs = session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
        for config in remote_configs:
            try:
                remote_client = RegistryClientFactory.get_client(config)
                images.extend(remote_client.list_images())
            except Exception as re:
                logger.error(f"Failed to fetch images from registry {config.name}: {str(re)}")

        # 3. Collect unique sources BEFORE filtering (Fix for disappearing sources)
        all_sources = sorted(list(set([img.source for img in images] + ["Local"])))

        # 4. Apply Filtering
        if source_filter and source_filter != "All":
            images = [img for img in images if img.source == source_filter]
        
    except Exception as e:
        logger.error(f"Failed to fetch images for view: {str(e)}")
        images = []
        all_sources = ["Local"]
        settings = None
        
    return templates.TemplateResponse(
        request,
        "images.html",
        {
            "images": images,
            "sources": all_sources,
            "current_source": source_filter or "All",
            "settings": settings,
        }
    )


@router.get("/volumes", response_class=HTMLResponse)
async def volumes_view(request: Request, session: Session = Depends(get_session)):
    """Render the volumes view with combined results"""
    try:
        source_filter = request.query_params.get("source")
        settings = session.get(AppSettings, 1)
        
        # Local volumes
        local_client = RegistryClientFactory.get_client()
        volumes = local_client.list_volumes()
        
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


@router.delete("/volumes/{name}", response_class=HTMLResponse)
async def delete_volume(name: str, session: Session = Depends(get_session)):
    """Delete a Docker volume"""
    try:
        client = RegistryClientFactory.get_client()
        result = client.delete_volume(session, name)
        
        if result["success"]:
            session.commit()
            return HTMLResponse(content="")
        else:
            return HTMLResponse(
                content=f'<tr class="error-row"><td colspan="7" style="color: var(--danger);">{result["message"]}</td></tr>',
                status_code=200
            )
    except Exception as e:
        logger.error(f"Volume deletion failed: {str(e)}", exc_info=True)
        return HTMLResponse(
            content=f'<tr class="error-row"><td colspan="7" style="color: var(--danger);">Deletion failed: {escape(str(e))}</td></tr>',
            status_code=500
        )


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
    form_data = await request.form()
    statement = select(CleanupPolicy).limit(1)
    policy = session.exec(statement).first()
    
    if policy:
        policy.keep_count = int(form_data.get("keep_count", 3))
        policy.max_age_days = int(form_data.get("max_age_days", 30))
        policy.regex_whitelist = str(form_data.get("regex_whitelist", ""))
        policy.enabled = form_data.get("enabled") == "on"
        
        session.add(policy)
        session.commit()
        
    return templates.TemplateResponse(
        request,
        "policies.html",
        {"policy": policy, "updated": True}
    )


@router.get("/logs", response_class=HTMLResponse)
async def logs_view(request: Request, session: Session = Depends(get_session)):
    """Render the logs view"""
    # Fetch latest 50 logs
    statement = select(AuditLog).order_by(col(AuditLog.timestamp).desc()).limit(50)
    logs = session.exec(statement).all()
    settings = session.get(AppSettings, 1)
    
    return templates.TemplateResponse(
        request,
        "logs.html",
        {
            "logs": logs,
            "settings": settings,
        }
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
    """Test connection to a registry before saving"""
    try:
        form_data = await request.form()
        
        name = str(form_data.get("name", "Test Registry")).strip()
        reg_type = str(form_data.get("type", "DOCKERHUB"))
        endpoint = str(form_data.get("endpoint", "")).strip()
        username = str(form_data.get("username", "")).strip() or None
        password = str(form_data.get("password", "")).strip() or None
        
        # Check if we are testing an existing registry (reg_id in form)
        # We need to add a hidden input for reg_id in the edit form for this to work
        reg_id = form_data.get("reg_id")
        
        # Logic: If password is empty AND we have a reg_id, fetch existing password from DB
        encrypted_password = None
        if password:
            encrypted_password = encrypt_secret(password)
        elif reg_id:
            # Try to fetch existing password
            existing_reg = session.get(RegistryConfig, int(reg_id))
            if existing_reg and existing_reg.password:
                encrypted_password = existing_reg.password
        
        # Create a temporary config object
        temp_config = RegistryConfig(
            name=name,
            type=RegistryType(reg_type),
            endpoint=endpoint,
            username=username,
            password=encrypted_password
        )
        
        # Instantiate client and test
        client = RegistryClientFactory.get_client(temp_config)
        result = client.test_connection()
        
        icon = "check-circle" if result["success"] else "x-circle"
        color = "var(--primary)" if result["success"] else "var(--danger)"
        
        return f"""
        <div class="connection-result" style="margin-top: 1rem; padding: 0.75rem; border-radius: 4px; background-color: rgba(0,0,0,0.2); border: 1px solid {color}; display: flex; align-items: center; gap: 0.5rem;">
            <i data-lucide="{icon}" style="color: {color}; width: 18px;"></i>
            <span style="font-size: 0.9rem; color: var(--text-main);">{result['message']}</span>
        </div>
        <script>lucide.createIcons();</script>
        """
        
    except Exception as e:
        return f"""
        <div class="connection-result" style="margin-top: 1rem; padding: 0.75rem; border-radius: 4px; background-color: rgba(231, 76, 60, 0.1); border: 1px solid var(--danger); color: var(--danger);">
            <i data-lucide="alert-circle" style="vertical-align: middle; margin-right: 0.5rem;"></i>
            Error: {str(e)}
        </div>
        <script>lucide.createIcons();</script>
        """

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
    """Delete a registry configuration"""
    registry = session.get(RegistryConfig, reg_id)
    if registry:
        session.delete(registry)
        session.commit()
    
    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = '{"showMessage": {"message": "Registry Removed", "type": "info"}}'
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
    
    if settings:
        if section == "finops":
            settings.provider_name = str(form_data.get("provider_name"))
            settings.custom_price_per_gb = float(form_data.get("custom_price_per_gb", 0.10))
            settings.currency_symbol = str(form_data.get("currency_symbol", "$"))
        elif section == "notifications":
            settings.notification_urls = str(form_data.get("notification_urls", "")).strip() or None
            
        settings.updated_at = datetime.utcnow()
        session.add(settings)
        session.commit()
        
    return templates.TemplateResponse(
        f"partials/settings_{section}.html",
        {"settings": settings, "updated": True, "section": section}
    )


@router.post("/settings/reset", response_class=HTMLResponse)
async def reset_database(request: Request, session: Session = Depends(get_session)):
    """Reset the database (Danger Zone)"""
    # Logic to flush tables could go here
    # For MVP just return success message
    return HTMLResponse(content="<p style='color: var(--danger);'>Database reset not fully implemented for safety.</p>")


@router.post("/settings/notify-test", response_class=HTMLResponse)
async def test_notification(response: Response):
    """Send a test notification via Apprise"""
    await send_notification(
        title="Dredge - Test Notification",
        body="If you're reading this, your ChatOps integration is working! ⚓"
    )
    response.headers["HX-Trigger"] = '{"showMessage": "Test Notification Sent"}'
    return HTMLResponse(content="")


@router.post("/scan-dashboard", response_class=HTMLResponse)
async def scan_dashboard(request: Request, response: Response, session: Session = Depends(get_session)):
    """Scan Docker images/volumes and return dashboard summary"""
    try:
        client = RegistryClientFactory.get_client()
        
        # Get images and volumes
        images = client.list_images()
        volumes = client.list_volumes()
        
        # Calculate metrics
        total_images = len(images)
        total_volumes = len(volumes)
        total_image_bytes = sum(img.size_bytes for img in images)
        total_volume_bytes = sum(vol.size_bytes for vol in volumes)
        total_bytes = total_image_bytes + total_volume_bytes
        total_gb = total_bytes / (1024 ** 3)
        monthly_cost = CostCalculator.calculate_monthly_cost(total_bytes)
        
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
        
        response.headers["HX-Trigger"] = '{"showMessage": "Scan Complete"}'
        return HTMLResponse(content=html)
        
    except Exception as e:
        logger.error(f"Dashboard scan failed: {str(e)}", exc_info=True)
        return HTMLResponse(
            content=f'<div style="text-align: center; padding: 2rem; color: var(--danger);"><p>Scan failed: {escape(str(e))}</p><p style="font-size: 0.9rem; margin-top: 0.5rem;">Please check Docker daemon connection.</p></div>',
            status_code=500
        )


@router.post("/scan", response_class=HTMLResponse)
async def scan_images(request: Request, response: Response, session: Session = Depends(get_session)):
    """Scan Docker images and return HTML table rows"""
    try:
        # Initialize Docker client
        client = RegistryClientFactory.get_client()
        
        # Get all images
        images = client.list_images()
        
        # Calculate total stats
        total_size_bytes = sum(img.size_bytes for img in images)
        total_cost = CostCalculator.calculate_monthly_cost(total_size_bytes)
        
        # Trigger Toast
        response.headers["HX-Trigger"] = '{"showMessage": "Scan Complete: ' + f'{total_size_bytes / (1024**3):.2f} GB' + ' analyzed"}'
        
        # Phase 5: Trigger Notification
        if total_size_bytes > 0:
            await send_notification(
                title="Dredge Scan Completed",
                body=f"Identified {total_size_bytes / (1024**3):.2f} GB of potential waste across local/remote registries."
            )
        
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
            status_class = status.value.lower()
            
            # ID for the row (must be safe for CSS selectors)
            row_id = f"image-{digest_escaped.replace(':', '-')}"
            
            html_rows.append(f"""
                <tr id="{row_id}">
                    <td><input type="checkbox" name="image-select" value="{digest_escaped}"></td>
                    <td>{repo}</td>
                    <td>{tag}</td>
                    <td>{size_gb:.2f} GB</td>
                    <td>{created}</td>
                    <td><span class="badge {status_class}">{status.value}</span></td>
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
@router.delete("/images/batch", response_class=HTMLResponse)
async def batch_delete_images(request: Request, session: Session = Depends(get_session)):
    """Batch delete selected images"""
    try:
        form_data = await request.form()
        # Form values are "digest|source" if we update frontend, but currently just digest from scan endpoint
        # The frontend update I made sends value="{{ image.digest }}|{{ image.source }}"
        
        selected = form_data.getlist("selected_images")
        
        if not selected:
            response = HTMLResponse(content="")
            response.headers["HX-Trigger"] = '{"showMessage": {"message": "No images selected", "type": "error"}}'
            return response
            
        success_count = 0
        fail_count = 0
        
        # We need clients for all active registries
        local_client = RegistryClientFactory.get_client()
        remote_configs = session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
        remote_clients = {conf.name: RegistryClientFactory.get_client(conf) for conf in remote_configs}
        
        for item in selected:
            # Parse value: "digest|source" or just "digest" (legacy)
            if "|" in item:
                digest, source = item.split("|", 1)
            else:
                digest = item
                source = "Local"
                
            try:
                # Select correct client
                if source == "Local":
                    client = local_client
                else:
                    client = remote_clients.get(source)
                    if not client:
                        logger.warning(f"No client found for source: {source}")
                        fail_count += 1
                        continue
                        
                # Perform deletion
                result = client.delete_image(session, digest, dry_run=False, force=True)
                if result["success"]:
                    success_count += 1
                else:
                    fail_count += 1
                    logger.warning(f"Failed to delete {digest}: {result['message']}")
                    
            except Exception as e:
                logger.error(f"Error deleting {digest}: {e}")
                fail_count += 1
        
        session.commit()
        
        # Trigger reload of the table or just show message
        # Ideally we refresh the whole list to reflect changes
        # But HTMX expects a snippet to replace target.
        # Since we targeted #image-table, we should re-render the table.
        
        return await images_view(request, session)
        
    except Exception as e:
        logger.error(f"Batch delete failed: {e}")
        return HTMLResponse(
            content=f'<div class="alert error">Batch deletion failed: {escape(str(e))}</div>',
            status_code=500
        )

@router.delete("/images/{digest}", response_class=HTMLResponse)
async def purge_image(digest: str, response: Response, session: Session = Depends(get_session)):
    """Purge (permanently delete) a Docker image"""
    try:
        # SECURITY FIX: The registry client already validates digest format
        client = RegistryClientFactory.get_client()
        
        # Perform real deletion (dry_run=False)
        result = client.delete_image(session, digest, dry_run=False)
        
        if result["success"]:
            session.commit()
            
            # Phase 5: Trigger Notification
            settings = session.get(AppSettings, 1)
            symbol = settings.currency_symbol if settings else "$"
            await send_notification(
                title="Image Purged",
                body=f"Successfully purged image {digest}. Savings: {symbol}{result['savings_usd']:.2f}/mo."
            )
            
            response.headers["HX-Trigger"] = '{"showMessage": "Image Purged Successfully"}'
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
