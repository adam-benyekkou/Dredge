"""Docker Registry abstraction"""

from abc import ABC, abstractmethod
from typing import List
import docker
from docker.errors import APIError, ImageNotFound, NotFound
from datetime import datetime
import re
import logging

from sqlmodel import Session
from app.models import ImageArtifact, AuditLog, VolumeArtifact, VolumeStatus
from app.core.finops import CostCalculator

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
    def delete_image(
        self,
        session: Session,
        image_id: str,
        dry_run: bool = True,
        force: bool = False
    ) -> dict:
        """Delete an image with audit logging and dry-run support"""
        pass

    @abstractmethod
    def list_volumes(self) -> List[VolumeArtifact]:
        """List all volumes in the host/registry"""
        pass

    @abstractmethod
    def delete_volume(
        self,
        session: Session,
        name: str,
        force: bool = False
    ) -> dict:
        """Delete a volume with audit logging"""
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
    
    def delete_image(
        self,
        session: Session,
        image_id: str,
        dry_run: bool = True,
        force: bool = False
    ) -> dict:
        """Delete a Docker image with audit logging and dry-run support.
        
        Performs permanent deletion of a Docker image from the local daemon.
        Records all deletions in the audit log for compliance and cost tracking.
        
        Security features:
        - Input validation for image_id format (prevents injection)
        - Dry-run mode by default (prevents accidental deletion)
        - Audit trail for all operations
        - Force flag required for images with dependent children
        
        Args:
            session: Database session for audit log persistence
            image_id: Image digest or tag (e.g., 'sha256:abc123...' or 'nginx:latest')
            dry_run: If True, simulates deletion without actually removing (default: True)
            force: If True, removes image even if it has dependent children (default: False)
        
        Returns:
            Dictionary with deletion results:
            {
                "success": bool,
                "image_id": str,
                "image_tags": List[str],
                "bytes_freed": int,
                "savings_usd": float,
                "dry_run": bool,
                "message": str
            }
        
        Raises:
            ValueError: If image_id is empty or has invalid format
            RuntimeError: If Docker API call fails
            
        Example:
            >>> from sqlmodel import Session, create_engine
            >>> engine = create_engine("sqlite:///dredge.db")
            >>> with Session(engine) as session:
            ...     client = LocalDockerClient()
            ...     # Dry run first
            ...     result = client.delete_image(session, "sha256:abc123...", dry_run=True)
            ...     print(f"Would free: {result['bytes_freed']} bytes")
            ...     # Real deletion
            ...     result = client.delete_image(session, "sha256:abc123...", dry_run=False)
            ...     session.commit()
        """
        # INPUT VALIDATION: Prevent empty or whitespace-only IDs
        if not image_id or not image_id.strip():
            raise ValueError("image_id cannot be empty")
        
        image_id = image_id.strip()
        
        # INPUT VALIDATION: Basic format check (sha256 digest or valid tag)
        # If starts with sha256:, it MUST be a valid 64-char hex digest
        if image_id.startswith('sha256:'):
            if not re.match(r'^sha256:[a-f0-9]{64}$', image_id):
                raise ValueError(f"Invalid image_id format: {image_id}")
        # Otherwise, allow valid image tag format
        elif not re.match(r'^[\w\-\./:]+$', image_id):
            raise ValueError(f"Invalid image_id format: {image_id}")
        
        try:
            # Get image details before deletion
            img = self.client.images.get(image_id)
            image_tags = img.tags if img.tags else [f"<none>:{img.short_id}"]
            size_bytes = img.attrs.get('Size', 0)
            actual_digest = img.id
            
            # Calculate cost savings
            monthly_cost = CostCalculator.calculate_monthly_cost(size_bytes)
            
            result = {
                "success": True,
                "image_id": actual_digest,
                "image_tags": image_tags,
                "bytes_freed": size_bytes,
                "savings_usd": monthly_cost,
                "dry_run": dry_run,
                "message": ""
            }
            
            if dry_run:
                # Simulate deletion without actually removing
                result["message"] = (
                    f"DRY RUN: Would delete image {image_tags[0]} "
                    f"({size_bytes / (1024**3):.2f} GB, ${monthly_cost:.2f}/mo savings)"
                )
                logger.info(result["message"])
                
                # Record dry-run in audit log
                audit_entry = AuditLog(
                    image_id=actual_digest,
                    image_tags=image_tags,
                    bytes_freed=size_bytes,
                    savings_usd=monthly_cost,
                    dry_run=True
                )
                session.add(audit_entry)
                
            else:
                # REAL DELETION
                try:
                    self.client.images.remove(image_id, force=force)
                    result["message"] = (
                        f"Successfully deleted image {image_tags[0]} "
                        f"({size_bytes / (1024**3):.2f} GB freed, ${monthly_cost:.2f}/mo savings)"
                    )
                    logger.info(result["message"])
                    
                    # Record real deletion in audit log
                    audit_entry = AuditLog(
                        image_id=actual_digest,
                        image_tags=image_tags,
                        bytes_freed=size_bytes,
                        savings_usd=monthly_cost,
                        dry_run=False
                    )
                    session.add(audit_entry)
                    
                except APIError as e:
                    error_msg = str(e)
                    if "conflict" in error_msg.lower():
                        result["success"] = False
                        result["message"] = (
                            f"Cannot delete {image_tags[0]}: Image has dependent children. "
                            f"Use force=True to delete anyway."
                        )
                        logger.warning(result["message"])
                    else:
                        raise
            
            return result
            
        except ImageNotFound:
            logger.warning(f"Image not found: {image_id}")
            return {
                "success": False,
                "image_id": image_id,
                "image_tags": [],
                "bytes_freed": 0,
                "savings_usd": 0.0,
                "dry_run": dry_run,
                "message": f"Image not found: {image_id}"
            }
            
        except APIError as e:
            logger.error(f"Docker API error during deletion: {e}")
            raise RuntimeError(f"Docker API error: {e}")
        
        except Exception as e:
            logger.error(f"Unexpected error during deletion: {e}")
            raise RuntimeError(f"Failed to delete image: {e}")

    def list_volumes(self) -> List[VolumeArtifact]:
        """List all local Docker volumes with size information.
        
        Uses docker system df to retrieve volume usage and size data.
        
        Returns:
            List of VolumeArtifact objects
            
        Raises:
            RuntimeError: If Docker API call fails
        """
        try:
            # Get volume data including size from system df
            df_data = self.client.df()
            volumes_info = df_data.get('Volumes', [])
            
            artifacts = []
            for vol in volumes_info:
                # Map volume info
                name = vol.get('Name', 'unknown')
                size_bytes = vol.get('UsageData', {}).get('Size', 0)
                ref_count = vol.get('UsageData', {}).get('RefCount', 0)
                
                # Determine status
                status = VolumeStatus.ACTIVE if ref_count > 0 else VolumeStatus.DANGLING
                
                # Get more details from individual volume inspection
                try:
                    v = self.client.volumes.get(name)
                    created_at_str = v.attrs.get('CreatedAt')
                    created_at = None
                    if created_at_str:
                        # Format: 2026-02-16T12:00:00Z or similar
                        created_at = datetime.fromisoformat(
                            created_at_str.replace('Z', '+00:00')
                        )
                    
                    labels = [f"{k}={v}" for k, v in v.attrs.get('Labels', {}).items()]
                    driver = v.attrs.get('Driver', 'local')
                except Exception:
                    created_at = None
                    labels = []
                    driver = 'local'

                artifact = VolumeArtifact(
                    name=name,
                    driver=driver,
                    size_bytes=size_bytes,
                    created_at=created_at,
                    status=status,
                    labels=labels
                )
                artifacts.append(artifact)
            
            logger.info(f"Successfully listed {len(artifacts)} volumes")
            return artifacts
            
        except APIError as e:
            logger.error(f"Docker API error listing volumes: {e}")
            raise RuntimeError(f"Docker API error: {e}")
        except Exception as e:
            logger.error(f"Failed to list volumes: {e}")
            raise RuntimeError(f"Failed to list volumes: {e}")

    def delete_volume(
        self,
        session: Session,
        name: str,
        force: bool = False
    ) -> dict:
        """Delete a Docker volume and record in audit log.
        
        Security features:
        - Input validation for volume name
        - Audit trail for deletion
        
        Args:
            session: Database session
            name: Name of the volume to delete
            force: If True, removes volume even if in use (default: False)
            
        Returns:
            Dictionary with deletion results
        """
        if not name or not name.strip():
            raise ValueError("volume name cannot be empty")
            
        try:
            # Get info before deletion
            v = self.client.volumes.get(name)
            
            # Estimate size (might be 0 if not tracked by df recently)
            # For volumes, size calculation is expensive, we rely on cached df if possible
            # But for simple MVP, we just try to get it
            size_bytes = 0
            try:
                df = self.client.df()
                for vol_info in df.get('Volumes', []):
                    if vol_info.get('Name') == name:
                        size_bytes = vol_info.get('UsageData', {}).get('Size', 0)
                        break
            except Exception as e:
                logger.warning(f"Could not retrieve volume size for {name} from df: {e}")
                pass
                
            savings_usd = CostCalculator.calculate_monthly_cost(size_bytes)
            
            # Remove volume
            v.remove(force=force)
            
            result = {
                "success": True,
                "name": name,
                "bytes_freed": size_bytes,
                "savings_usd": savings_usd,
                "message": f"Successfully deleted volume {name} ({size_bytes / (1024**2):.2f} MB freed)"
            }
            
            # Audit Log
            audit_entry = AuditLog(
                image_id=f"volume:{name}",
                image_tags=[f"volume:{name}"],
                bytes_freed=size_bytes,
                savings_usd=savings_usd,
                dry_run=False
            )
            session.add(audit_entry)
            
            logger.info(result["message"])
            return result
            
        except NotFound:
            return {"success": False, "message": f"Volume not found: {name}"}
        except APIError as e:
            logger.error(f"Docker API error deleting volume {name}: {e}")
            return {"success": False, "message": f"Docker API error: {str(e)}"}
        except Exception as e:
            logger.error(f"Failed to delete volume {name}: {e}")
            return {"success": False, "message": f"Failed to delete volume: {str(e)}"}
