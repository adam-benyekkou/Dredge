
import logging
from sqlmodel import Session, select
from taskiq import TaskiqScheduler

from app.core.db import engine
from app.core.auth import AuthFactory
from app.core.registry import RegistryClientFactory
from app.models import RegistryConfig, RegistryType

logger = logging.getLogger(__name__)

# Note: Taskiq broker and scheduler should be initialized in a central location (e.g., app/tk.py)
# but we implement the logic here as requested.

async def refresh_registry_credentials():
    """Periodic task to refresh Cloud registry tokens before they expire."""
    logger.info("Starting registry credential refresh task")
    
    with Session(engine) as session:
        statement = select(RegistryConfig).where(RegistryConfig.is_active == True)
        registries = session.exec(statement).all()
        
        for registry in registries:
            # We only need to refresh Tier 3 (Cloud) providers
            # AWS tokens expire in 12h, GCP in 1h.
            # Basic Auth (Tier 1) credentials are usually static PATs or passwords.
            
            is_cloud = registry.type in [RegistryType.ECR, RegistryType.GCR, RegistryType.GAR]
            # Also check endpoint URL as a fallback for CUSTOM type that might be cloud-based
            is_cloud_url = any(cloud_marker in registry.endpoint for cloud_marker in ["ecr.aws", "pkg.dev", "gcr.io"])
            
            if is_cloud or is_cloud_url:
                logger.info(f"Refreshing credentials for {registry.type} registry: {registry.name} ({registry.endpoint})")
                try:
                    # Pass the full registry config object to the factory
                    authenticator = AuthFactory.get_authenticator(registry)
                    # Authenticate strictly using the URL
                    await authenticator.authenticate(registry.endpoint)
                except Exception as e:
                    logger.error(f"Failed to refresh credentials for {registry.name}: {e}")

async def monitor_registry_health():
    """Periodic health check for registries. Marks as inactive if connection fails."""
    logger.info("Starting registry health monitoring task")
    
    with Session(engine) as session:
        # Check all registries (including currently inactive ones to see if they recovered)
        # However, request was "show as inactive if it cant perform connection".
        # Usually we only want to auto-disable active ones.
        statement = select(RegistryConfig).where(RegistryConfig.is_active == True)
        registries = session.exec(statement).all()
        
        for registry in registries:
            try:
                client = RegistryClientFactory.get_client(registry)
                result = client.test_connection()
                
                if not result["success"]:
                    logger.warning(f"Health check failed for {registry.name}. Marking as inactive. Error: {result['message']}")
                    registry.is_active = False
                    session.add(registry)
                else:
                    logger.debug(f"Health check passed for {registry.name}")
            except Exception as e:
                logger.error(f"Error during health check for {registry.name}: {e}")
                registry.is_active = False
                session.add(registry)
        
        session.commit()

# In a real Taskiq setup, the schedule would be defined in the broker/scheduler configuration:
# scheduler.add_task(refresh_registry_credentials, cron="*/55 * * * *")
# scheduler.add_task(monitor_registry_health, cron="*/5 * * * *") # Every 5 minutes
