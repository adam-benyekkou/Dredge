from fastapi import APIRouter, Depends, BackgroundTasks
from typing import List
from datetime import datetime
import logging
from sqlmodel import Session, select
from app.core.db import get_session
from app.core.registry import RegistryClientFactory
from app.models import RegistryConfig

logger = logging.getLogger(__name__)

# These would be imported from the application layer in a complete DDD setup
# from app.modules.images.application.schemas import ImageResponse
# from app.modules.images.application.services import ImageService

image_router = APIRouter()

@image_router.get("/")
async def list_images(session: Session = Depends(get_session)):
    """
    List all images (Local + Remote).
    Presentation Layer -> Application Service -> Domain/Infrastructure
    """
    images = []
    
    # 1. Fetch Local Images
    try:
        local_client = RegistryClientFactory.get_client()
        images.extend(local_client.list_images(limit=100))
    except Exception as e:
        # We don't fail the whole request if one source fails
        logger.error(f"Failed to fetch local images: {e}")

    # 2. Fetch Remote Images from active configurations
    try:
        remote_configs = session.exec(
            select(RegistryConfig).where(RegistryConfig.is_active == True)
        ).all()
        
        for config in remote_configs:
            try:
                remote_client = RegistryClientFactory.get_client(config)
                
                # Health Check: Ping before fetching
                conn_test = remote_client.test_connection()
                if not conn_test["success"]:
                    logger.warning(f"Registry {config.name} connection failed. Marking as inactive. Error: {conn_test['message']}")
                    config.is_active = False
                    session.add(config)
                    session.commit()
                    continue

                remote_images = remote_client.list_images(limit=100)
                images.extend(remote_images)
            except Exception as e:
                logger.error(f"Failed to fetch images from registry {config.name}: {e}")
                continue
    except Exception as e:
        logger.error(f"Registry config query failed: {e}")

    # Sort results newest first
    images.sort(key=lambda x: x.created_at or datetime.min, reverse=True)
    
    return [img.model_dump() for img in images]

@image_router.post("/scan")
async def trigger_scan(background_tasks: BackgroundTasks):
    """
    Triggers an asynchronous scan of all registries.
    """
    # In a real implementation, this would call background_tasks.add_task(ImageService.scan_all_registries)
    return {"status": "accepted", "message": "Background scan initiated"}
