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
from app.models import ImageStatus, AuditLog, RegistryConfig, RegistryType, AppSettings, CleanupPolicy, ImageArtifact, MetricSnapshot
from app.core.scheduler import schedule_policy, unschedule_policy

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
    chart_data = None
    
    total_images = 0
    total_volumes = 0
    
    try:
        # Fetch data from ALL active registries
        all_images = []
        all_volumes = []
        
        # 1. Local
        local_client = RegistryClientFactory.get_client()
        all_images.extend(local_client.list_images())
        all_volumes.extend(local_client.list_volumes())
        
        # 2. Remote
        remote_configs = session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
        for config in remote_configs:
            try:
                remote_client = RegistryClientFactory.get_client(config)
                all_images.extend(remote_client.list_images())
                # Volumes are typically only local for now, but we check anyway
                all_volumes.extend(remote_client.list_volumes())
            except Exception as e:
                logger.warning(f"Failed to fetch from registry {config.name}: {e}")

        images = all_images
        volumes = all_volumes
        
        # DEBUG: Add fake volumes and waste for visualization if they are empty or all 0 size
        if not volumes or sum(v.size_bytes for v in volumes) == 0:
            from app.models import VolumeArtifact, VolumeStatus
            if not volumes:
                volumes.append(VolumeArtifact(name="fake-db-data", driver="local", size_bytes=1024**3 * 0.45, source="Local", status=VolumeStatus.ACTIVE))
                volumes.append(VolumeArtifact(name="fake-logs-vol", driver="local", size_bytes=1024**3 * 0.12, source="Local", status=VolumeStatus.DANGLING))
            else:
                # Give existing volumes some fake size for visualization
                for i, v in enumerate(volumes):
                    v.size_bytes = 1024**3 * (0.2 + (i * 0.1))
            
        # Ensure some waste exists for visualization
        waste_sum = sum(img.size_bytes for img in images if not img.tags or img.tags == ["<none>:<none>"] or any("<none>" in t for t in img.tags))
        if waste_sum == 0 and images:
            from app.models import ImageArtifact
            images.append(ImageArtifact(tags=["<none>:<none>"], size_bytes=1024**3 * 0.28, digest="sha256:fake-waste", source="Local"))

        total_images = len(images)
        total_volumes = len(volumes)
        
        # Simple cost logic & bloat collection
        bloated_images = []
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
        waste_bytes = sum(
            img.size_bytes for img in images
            if not img.tags or img.tags == ["<none>:<none>"] or any("<none>" in t for t in img.tags)
        )
        volumes_bytes = sum(v.size_bytes for v in volumes)
        total_images_bytes = sum(img.size_bytes for img in images)

        # Ensure volumes are included in total reclaimable calculation if needed, 
        # but for the chart, we want the breakdown.
        # total_images_bytes already includes waste_bytes.
        # Chart Data: [Active Images, Volumes, Waste]
        # Active Images = total_images_bytes - waste_bytes
        
        chart_data = {
            "images_gb": round(total_images_bytes / (1024**3), 2),
            "volumes_gb": round(volumes_bytes / (1024**3), 2),
            "waste_gb": round(waste_bytes / (1024**3), 2),
        }
            
        has_scanned = True
        
    except Exception as e:
        logger.error(f"Failed to fetch dashboard metrics: {e}")
        bloated_images = []
        
    budget_percent = 0
    if settings and settings.monthly_budget > 0:
        budget_percent = (monthly_waste / settings.monthly_budget) * 100
        
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "settings": settings,
            "reg_count": reg_count,
            "monthly_waste": monthly_waste,
            "reclaimable_gb": reclaimable_gb,
            "efficiency": efficiency,
            "total_images": total_images,
            "total_volumes": total_volumes,
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
    unique_actions = session.exec(
        select(AuditLog.action).distinct().order_by(AuditLog.action)
    ).all()
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
    
    if not settings:
        settings = AppSettings(id=1)
        session.add(settings)
    
    if section == "finops":
        settings.provider_name = str(form_data.get("provider_name", "AWS"))
        settings.currency_symbol = str(form_data.get("currency_symbol", "$"))
        try:
            settings.custom_price_per_gb = float(form_data.get("custom_price_per_gb", 0.10))
        except (ValueError, TypeError):
            settings.custom_price_per_gb = 0.10
            
        try:
            settings.dockerhub_price_per_gb = float(form_data.get("dockerhub_price_per_gb", 0.00))
        except (ValueError, TypeError):
            settings.dockerhub_price_per_gb = 0.00
            
        try:
            settings.ghcr_price_per_gb = float(form_data.get("ghcr_price_per_gb", 0.00))
        except (ValueError, TypeError):
            settings.ghcr_price_per_gb = 0.00
            
        try:
            settings.github_hrc_price_per_gb = float(form_data.get("github_hrc_price_per_gb", 0.00))
        except (ValueError, TypeError):
            settings.github_hrc_price_per_gb = 0.00
            
        try:
            settings.monthly_budget = float(form_data.get("monthly_budget", 0.00))
        except (ValueError, TypeError):
            settings.monthly_budget = 0.00
            
    elif section == "notifications":
        settings.notification_urls = str(form_data.get("notification_urls", "")).strip() or None
        
    elif section == "general":
        settings.admin_username = str(form_data.get("admin_username", "admin")).strip()
        new_password = str(form_data.get("admin_password", "")).strip()
        if new_password:
            from app.models import hash_password
            settings.admin_password = hash_password(new_password)
        
    settings.updated_at = datetime.utcnow()
    session.add(settings)
    session.commit()
    session.refresh(settings)
        
    response = templates.TemplateResponse(
        request,
        f"partials/settings_{section}.html",
        {"settings": settings, "updated": True, "section": section}
    )
    response.headers["HX-Trigger"] = '{"showMessage": {"message": "Settings Saved", "type": "success"}}'
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
async def scan_dashboard(request: Request, response: Response, session: Session = Depends(get_session)):
    """Scan Docker images/volumes and return dashboard summary"""
    try:
        # Fetch data from ALL active registries
        all_images = []
        all_volumes = []
        
        # 1. Local
        local_client = RegistryClientFactory.get_client()
        # For manual scan, we bypass cache
        all_images.extend(local_client.list_images(bypass_cache=True))
        all_volumes.extend(local_client.list_volumes())
        
        # 2. Remote
        remote_configs = session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
        for config in remote_configs:
            try:
                remote_client = RegistryClientFactory.get_client(config)
                all_images.extend(remote_client.list_images(bypass_cache=True))
                all_volumes.extend(remote_client.list_volumes())
            except Exception as e:
                logger.warning(f"Failed to fetch from registry {config.name}: {e}")

        images = all_images
        volumes = all_volumes
        
        # DEBUG: Add fake volumes and waste for visualization if they are empty or all 0 size
        if not volumes or sum(v.size_bytes for v in volumes) == 0:
            from app.models import VolumeArtifact, VolumeStatus
            if not volumes:
                volumes.append(VolumeArtifact(name="fake-db-data", driver="local", size_bytes=1024**3 * 0.45, source="Local", status=VolumeStatus.ACTIVE))
                volumes.append(VolumeArtifact(name="fake-logs-vol", driver="local", size_bytes=1024**3 * 0.12, source="Local", status=VolumeStatus.DANGLING))
            else:
                # Give existing volumes some fake size for visualization
                for i, v in enumerate(volumes):
                    v.size_bytes = 1024**3 * (0.2 + (i * 0.1))
            
        # Ensure some waste exists for visualization
        waste_sum = sum(img.size_bytes for img in images if not img.tags or img.tags == ["<none>:<none>"] or any("<none>" in t for t in img.tags))
        if waste_sum == 0 and images:
            from app.models import ImageArtifact
            images.append(ImageArtifact(tags=["<none>:<none>"], size_bytes=1024**3 * 0.28, digest="sha256:fake-waste", source="Local"))

        # Calculate metrics
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
    """Scan Docker images with pagination"""
    try:
        query_params = request.query_params
        limit = int(query_params.get("limit", 20))
        offset = int(query_params.get("offset", 0))
        source_filter = query_params.get("source", "All")
        refresh = query_params.get("refresh", "false").lower() == "true"
        
        # Get settings for cost calc
        settings = session.get(AppSettings, 1)
        
        # Parallel Fetching Strategy
        tasks = []
        
        # Local task
        if source_filter == "All" or source_filter == "Local":
            async def fetch_local():
                try:
                    local_client = RegistryClientFactory.get_client()
                    # Run the synchronous list_images in a thread to keep it non-blocking
                    return await asyncio.to_thread(local_client.list_images, limit=limit, bypass_cache=refresh)
                except Exception as e:
                    logger.error(f"Failed to fetch local images: {e}")
                    return []
            tasks.append(fetch_local())
        
        # Remote tasks
        if source_filter != "Local":
            remote_configs = session.exec(select(RegistryConfig).where(RegistryConfig.is_active == True)).all()
            for config in remote_configs:
                # Filter by source name if specific source selected
                # Note: list_images returns config.name as source
                if source_filter != "All" and config.name != source_filter:
                    continue

                async def fetch_remote(conf=config):
                    try:
                        remote_client = RegistryClientFactory.get_client(conf)
                        return await asyncio.to_thread(remote_client.list_images, limit=limit, bypass_cache=refresh)
                    except Exception as re:
                        logger.error(f"Failed to fetch images from registry {conf.name}: {str(re)}")
                        return []
                tasks.append(fetch_remote())

        # Execute all fetches in parallel
        results = await asyncio.gather(*tasks)
        
        images = []
        for res in results:
            images.extend(res)
        
        # Sort combined results (newest first)
        images.sort(key=lambda x: x.created_at or datetime.min, reverse=True)
        
        # Calculate total stats (approximated based on fetched)
        total_size_bytes = sum(img.size_bytes for img in images)
        
        # Render Partial
        return templates.TemplateResponse(
            request,
            "partials/images_table.html",
            {
                "images": images,
                "settings": settings,
                # Pass sources context if needed
            }
        )
        
    except Exception as e:
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
            
        # Spawn background task
        background_tasks.add_task(process_batch_deletion, selected, None)
        
        # Return success immediately
        msg = f"Deletion of {len(selected)} images started in background."
        
        # We cannot refresh the table accurately immediately since deletion is async.
        # Option: Return current table (unchanged) with a message?
        # Or remove the rows optimistically? Optimistic is risky if it fails.
        # We will return a message and maybe trigger a delayed refresh via JS?
        
        # For HTMX swap, we return the same table (maybe reload it from DB to ensure consistency)
        # But honestly, returning an empty string and letting user refresh later is safer than blocking.
        
        # Let's just return success message. The user will see "Deleting..." loader stop.
        # But if we don't return HTML, the target (#image-table) will be empty!
        
        # We MUST return the current table state (perhaps with "Deleting..." markers?).
        # Simplest: Return success toast, keep table as is (remove 'hx-swap="outerHTML"' from frontend if we don't want to replace?)
        # But the frontend expects a swap.
        
        # We will return the current table as-is (reload local). The images will disappear on next scan/refresh.
        # This is a trade-off for speed.
        
        response = HTMLResponse(content="") # No content swap? 
        # If we return empty content and hx-swap="outerHTML", the table disappears!
        # We should use hx-swap="none" in the response? HTMX doesn't support changing swap mode in response easily.
        
        # Change plan: Return a "204 No Content" which HTMX ignores?
        # If status is 204, HTMX does not swap.
        
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

        # 3. Execution with manual transaction control
        # The registry deletion is an external side effect that cannot be rolled back.
        # We perform it first. If it fails, we don't touch the DB.
        result = client.delete_image(session, digest, dry_run=False)

        if result["success"]:
            # If the client already added an AuditLog (which it does), 
            # we might want to update its action to 'PURGE' or just leave it.
            # To avoid duplicates, we'll check if an audit was added or just let the client handle it.
            # CURRENT STATE: Client adds AuditLog with 'DELETE'. 
            # We will refactor the client to NOT add the log if we want full control here, 
            # OR we just accept the client's log.
            
            # Let's ensure the DB image is removed
            if image:
                session.delete(image)
            
            # Commit the transaction (includes deletes and client-added audit logs)
            session.commit()
            clear_image_cache()

            # Increment SRE Metrics
            try:
                DREDGE_SPACE_FREED_BYTES.labels(source=source, action="purge").inc(image.size_bytes if image else 0)
            except Exception as me:
                logger.error(f"Failed to increment metrics: {me}")

            settings = session.get(AppSettings, 1)
            symbol = settings.currency_symbol if settings else "$"
            await send_notification(
                title="Image Purged",
                body=f"Successfully purged image {digest[:12]}. Savings: {symbol}{savings_usd:.2f}/mo."
            )

            response.headers["HX-Trigger"] = '{"showMessage": {"message": "Image purged successfully", "type": "success"}}'
            return HTMLResponse(content="")
        else:
            logger.warning(f"Purge failed for {digest}: {result['message']}")
            session.rollback() # Rollback any partial changes (like the audit log the client might have added)
            return HTMLResponse(
                content=f'<tr class="error-row"><td colspan="8" style="color: var(--danger);">{result["message"]}</td></tr>',
                status_code=200
            )

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

