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
