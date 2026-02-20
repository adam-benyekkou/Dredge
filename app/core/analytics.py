"""Analytics engine for metric tracking"""

import logging
from datetime import datetime
from sqlmodel import Session, select
from app.core.db import engine
from app.models import MetricSnapshot, AppSettings
from app.core.registry import RegistryClientFactory
from app.core.finops import CostCalculator

logger = logging.getLogger(__name__)

async def capture_daily_snapshot(session: Session):
    """Capture current metrics and save to history"""
    try:
        logger.info("Capturing daily metric snapshot...")
        
        # Calculate current metrics
        client = RegistryClientFactory.get_client()
        images = client.list_images()
        volumes = client.list_volumes()
        
        total_images = len(images)
        total_volumes = len(volumes)
        
        total_bytes = sum(img.size_bytes for img in images) + sum(vol.size_bytes for vol in volumes)
        total_gb = total_bytes / (1024 ** 3)
        
        # Calculate cost
        monthly_cost = 0
        for img in images:
            monthly_cost += CostCalculator.calculate_monthly_cost(img.size_bytes, img.source)
        for vol in volumes:
            monthly_cost += CostCalculator.calculate_monthly_cost(vol.size_bytes, vol.source)
            
        # Calculate efficiency (simple heuristic)
        # Assume "waste" is untagged images + dangling volumes
        waste_bytes = 0
        for img in images:
            if not img.tags: # Untagged
                waste_bytes += img.size_bytes
        for vol in volumes:
            if vol.status == "DANGLING":
                waste_bytes += vol.size_bytes
                
        efficiency_score = 100
        if total_bytes > 0:
            waste_ratio = waste_bytes / total_bytes
            efficiency_score = max(0, int(100 - (waste_ratio * 100)))
            
        # Check if snapshot already exists for today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        existing = session.exec(
            select(MetricSnapshot).where(MetricSnapshot.date >= today_start)
        ).first()
        
        if existing:
            # Update existing
            existing.total_images = total_images
            existing.total_volumes = total_volumes
            existing.total_gb = total_gb
            existing.total_cost_usd = monthly_cost
            existing.efficiency_score = efficiency_score
            session.add(existing)
            logger.info("Updated existing daily snapshot")
        else:
            # Create new
            snapshot = MetricSnapshot(
                total_images=total_images,
                total_volumes=total_volumes,
                total_gb=total_gb,
                total_cost_usd=monthly_cost,
                efficiency_score=efficiency_score
            )
            session.add(snapshot)
            logger.info("Created new daily snapshot")
            
        session.commit()
        
    except Exception as e:
        logger.error(f"Failed to capture metric snapshot: {e}", exc_info=True)
