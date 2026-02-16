"""Docker Registry abstraction"""

from abc import ABC, abstractmethod
from typing import List
import docker
from docker.errors import APIError
from datetime import datetime
import re
import logging

from app.models import ImageArtifact

logger = logging.getLogger(__name__)


class BaseRegistryClient(ABC):
    """Abstract base class for registry clients"""
    
    @abstractmethod
    def list_images(self) -> List[ImageArtifact]:
        """List all images in the registry"""
        pass
    
    @abstractmethod
    def get_manifest_size(self, digest: str) -> int:
        """Get the size of an image by digest"""
        pass
    
    @abstractmethod
    def delete_image(self, image_id: str, dry_run: bool = True) -> bool:
        """Delete an image (dry_run for Phase 1 MVP)"""
        pass


class LocalDockerClient(BaseRegistryClient):
    """Client for local Docker daemon"""
    
    def __init__(self):
        """Initialize Docker client"""
        try:
            self.client = docker.from_env()
            logger.info("Docker client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Docker daemon: {e}")
            raise ConnectionError(f"Failed to connect to Docker daemon: {e}")
    
    def list_images(self) -> List[ImageArtifact]:
        """List all local Docker images"""
        try:
            images = self.client.images.list()
            artifacts = []
            
            for img in images:
                # Extract tags (remove 'latest' duplicates)
                tags = img.tags if img.tags else [f"<none>:{img.short_id}"]
                
                # Create ImageArtifact
                artifact = ImageArtifact(
                    tags=tags,
                    size_bytes=img.attrs.get('Size', 0),
                    created_at=datetime.fromisoformat(
                        img.attrs.get('Created', datetime.utcnow().isoformat()).replace('Z', '+00:00')
                    ),
                    digest=img.id
                )
                artifacts.append(artifact)
            
            logger.info(f"Successfully listed {len(artifacts)} images")
            return artifacts
        
        except APIError as e:
            logger.error(f"Docker API error: {e}")
            raise RuntimeError(f"Docker API error: {e}")
        except Exception as e:
            logger.error(f"Failed to list images: {e}")
            raise RuntimeError(f"Failed to list images: {e}")
    
    def get_manifest_size(self, digest: str) -> int:
        """Get image size by digest
        
        Args:
            digest: Image digest (format: sha256:...)
            
        Returns:
            Size in bytes
            
        Raises:
            ValueError: If digest format is invalid
            RuntimeError: If Docker API call fails
        """
        # INPUT VALIDATION: Verify digest format
        if not re.match(r'^sha256:[a-f0-9]{64}$', digest):
            raise ValueError(f"Invalid digest format: {digest}")
        
        try:
            img = self.client.images.get(digest)
            return img.attrs.get('Size', 0)
        except APIError as e:
            logger.error(f"Docker API error getting size for {digest}: {e}")
            raise RuntimeError(f"Docker API error: {e}")
    
    def delete_image(self, image_id: str, dry_run: bool = True) -> bool:
        """Delete an image (Not implemented in MVP)"""
        raise NotImplementedError("Image deletion not available in Phase 1 MVP")
