
import base64
import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple

import docker
from docker.errors import APIError

from app.models import RegistryConfig, RegistryType

logger = logging.getLogger(__name__)

class AuthenticationError(Exception):
    """Clean exception for registry authentication failures."""
    pass

class RegistryAuthenticator(ABC):
    """Abstract base class for registry authenticators."""

    @abstractmethod
    async def authenticate(self, registry_url: str) -> bool:
        """Interface for authenticating with a registry.
        
        Args:
            registry_url: The URL of the registry to authenticate with.
            
        Returns:
            bool: True if authentication was successful, False otherwise.
            
        Raises:
            AuthenticationError: If authentication fails with a specific error.
        """
        pass

class BasicAuthenticator(RegistryAuthenticator):
    """Tier 1: Basic Authentication using username/password or PAT."""

    def __init__(self, config: RegistryConfig):
        self.config = config

    async def authenticate(self, registry_url: str) -> bool:
        if not self.config.username or not self.config.password:
            logger.error(f"Missing credentials for registry: {registry_url}")
            return False

        try:
            client = docker.from_env()
            client.login(
                username=self.config.username,
                password=self.config.password,
                registry=registry_url
            )
            logger.info(f"Successfully authenticated with {registry_url} using Basic Auth")
            return True
        except APIError as e:
            logger.error(f"Authentication failed for {registry_url}: {e}")
            raise AuthenticationError(f"Failed to authenticate with {registry_url}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during authentication for {registry_url}: {e}")
            return False

class AWSAuthenticator(RegistryAuthenticator):
    """Tier 3: AWS ECR Cloud Auto-Auth."""
    
    # AWS Authenticator is usually stateless as it uses environmental credentials,
    # but we accept config in __init__ for consistency if needed in future (e.g. assume role).
    def __init__(self, config: Optional[RegistryConfig] = None):
        self.config = config

    async def authenticate(self, registry_url: str) -> bool:
        try:
            import boto3
        except ImportError:
            logger.error("boto3 not installed. Cannot use AWSAuthenticator.")
            return False

        try:
            # Auto-discovery using standard boto3 credential chain
            # If we needed to use a specific region from the URL, we could parse registry_url here
            # e.g., 123456789012.dkr.ecr.us-east-1.amazonaws.com
            
            # Use specific region if implied by URL, else default
            region = None
            if "ecr." in registry_url:
                parts = registry_url.split('.')
                if len(parts) >= 4:
                    # simplistic parsing: 123.dkr.ecr.us-west-2.amazonaws.com
                    # parts: [123, dkr, ecr, us-west-2, amazonaws, com]
                    # This is brittle, better to rely on boto3 defaults or config if provided
                    pass

            ecr = boto3.client('ecr') # relies on env vars or ~/.aws/credentials
            response = ecr.get_authorization_token()
            auth_data = response['authorizationData'][0]
            token = auth_data['authorizationToken']
            
            # Decode base64 token to get 'AWS:password'
            decoded_token = base64.b64decode(token).decode('utf-8')
            username, password = decoded_token.split(':')

            client = docker.from_env()
            client.login(
                username=username,
                password=password,
                registry=registry_url
            )
            logger.info(f"Successfully authenticated with ECR {registry_url}")
            return True
        except Exception as e:
            logger.error(f"AWS ECR Authentication failed for {registry_url}: {e}")
            raise AuthenticationError(f"AWS ECR Authentication failed: {e}")

class GCPAuthenticator(RegistryAuthenticator):
    """Tier 3: GCP Artifact Registry Cloud Auto-Auth."""

    def __init__(self, config: Optional[RegistryConfig] = None):
        self.config = config

    async def authenticate(self, registry_url: str) -> bool:
        try:
            import google.auth
            from google.auth.transport.requests import Request
        except ImportError:
            logger.error("google-auth not installed. Cannot use GCPAuthenticator.")
            return False

        try:
            scopes = ['https://www.googleapis.com/auth/cloud-platform']
            credentials, project = google.auth.default(scopes=scopes)
            credentials.refresh(Request())
            
            token = credentials.token
            username = "oauth2accesstoken"

            client = docker.from_env()
            client.login(
                username=username,
                password=token,
                registry=registry_url
            )
            logger.info(f"Successfully authenticated with GCP registry {registry_url}")
            return True
        except Exception as e:
            logger.error(f"GCP Authentication failed for {registry_url}: {e}")
            raise AuthenticationError(f"GCP Authentication failed: {e}")

class AuthFactory:
    """Selects the right provider based on the registry URL or type."""

    @staticmethod
    def get_authenticator(registry: RegistryConfig) -> RegistryAuthenticator:
        """Factory method to get the appropriate authenticator.
        
        Args:
            registry: The RegistryConfig object containing type and credentials.
            
        Returns:
            An instance of a RegistryAuthenticator subclass.
        """
        registry_url = registry.endpoint
        registry_type = registry.type

        if registry_type == RegistryType.ECR or "ecr.aws" in registry_url:
            return AWSAuthenticator(registry)
        if registry_type in [RegistryType.GCR, RegistryType.GAR] or "pkg.dev" in registry_url or "gcr.io" in registry_url:
            return GCPAuthenticator(registry)
        
        return BasicAuthenticator(registry)
