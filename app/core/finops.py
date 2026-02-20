"""FinOps cost calculation engine"""


from app.core.db import engine
from app.models import AppSettings
from sqlmodel import Session

class CostCalculator:
    """Calculate storage costs for Docker images"""
    
    @classmethod
    def calculate_monthly_cost(
        cls,
        size_bytes: int,
        source: str = "Local"
    ) -> float:
        """
        Calculate monthly storage cost for a given size.
        
        Args:
            size_bytes: Size in bytes
            source: Image source (e.g., 'Local', 'Docker Hub', 'GHCR')
            
        Returns:
            Monthly cost in configured currency
        """
        # Convert bytes to GB
        size_gb = size_bytes / (1024 ** 3)
        
        # Fetch settings from DB
        with Session(engine) as session:
            settings = session.get(AppSettings, 1)
            
            if not settings:
                return size_gb * 0.10
            
            # Determine price based on source
            if source == "Docker Hub":
                price = settings.dockerhub_price_per_gb
            elif source == "GitHub Packages" or source == "GHCR":
                price = settings.ghcr_price_per_gb
            elif source == "GitHub HRC":
                price = settings.github_hrc_price_per_gb
            else:
                price = settings.custom_price_per_gb
                
        return size_gb * price


async def check_budget(session: Session):
    """Check if current usage exceeds budget and notify"""
    from app.core.registry import RegistryClientFactory
    from app.core.notify import send_notification
    from datetime import datetime
    
    settings = session.get(AppSettings, 1)
    if not settings or settings.monthly_budget <= 0:
        return

    # Calculate current total cost
    try:
        client = RegistryClientFactory.get_client()
        images = client.list_images()
        volumes = client.list_volumes()
        
        total_cost = 0
        for img in images:
            total_cost += CostCalculator.calculate_monthly_cost(img.size_bytes, img.source)
        for vol in volumes:
            total_cost += CostCalculator.calculate_monthly_cost(vol.size_bytes, vol.source)
            
        if total_cost > settings.monthly_budget:
            # Check if alert sent today
            today = datetime.utcnow().date()
            if settings.last_budget_alert_at and settings.last_budget_alert_at.date() == today:
                return
                
            await send_notification(
                title="⚠️ Budget Exceeded",
                body=f"Current monthly spend ({settings.currency_symbol}{total_cost:.2f}) has exceeded your budget of {settings.currency_symbol}{settings.monthly_budget:.2f}."
            )
            
            settings.last_budget_alert_at = datetime.utcnow()
            session.add(settings)
            session.commit()
            
    except Exception as e:
        # Don't crash scheduler if registry check fails
        print(f"Budget check failed: {e}")
