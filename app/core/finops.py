"""FinOps cost calculation engine"""


class CostCalculator:
    """Calculate storage costs for Docker images"""
    
    # Pricing constants (USD per GB per month)
    AWS_PRICE_PER_GB = 0.10
    AZURE_PRICE_PER_GB = 0.13
    GCP_PRICE_PER_GB = 0.10
    
    @classmethod
    def calculate_monthly_cost(
        cls,
        size_bytes: int,
        provider: str = "AWS"
    ) -> float:
        """
        Calculate monthly storage cost for a given size.
        
        Args:
            size_bytes: Size in bytes
            provider: Cloud provider ("AWS", "AZURE", "GCP")
            
        Returns:
            Monthly cost in USD
        """
        # Convert bytes to GB
        size_gb = size_bytes / (1024 ** 3)
        
        # Get price per GB based on provider
        price_map = {
            "AWS": cls.AWS_PRICE_PER_GB,
            "AZURE": cls.AZURE_PRICE_PER_GB,
            "GCP": cls.GCP_PRICE_PER_GB,
        }
        
        price_per_gb = price_map.get(provider.upper(), cls.AWS_PRICE_PER_GB)
        
        return size_gb * price_per_gb
