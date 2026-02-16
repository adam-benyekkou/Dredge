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
        provider: str = None
    ) -> float:
        """
        Calculate monthly storage cost for a given size.
        
        Args:
            size_bytes: Size in bytes
            provider: Cloud provider (optional override)
            
        Returns:
            Monthly cost in configured currency
        """
        # Convert bytes to GB
        size_gb = size_bytes / (1024 ** 3)
        
        # Fetch settings from DB
        with Session(engine) as session:
            settings = session.get(AppSettings, 1)
            if not settings:
                price_per_gb = 0.10
            else:
                price_per_gb = settings.custom_price_per_gb
        
        return size_gb * price_per_gb
