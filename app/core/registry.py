"""Docker Registry abstraction"""

from abc import ABC, abstractmethod
from typing import List, Optional
import docker
from docker.errors import APIError, ImageNotFound, NotFound
from datetime import datetime
import re
import logging
import requests
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlmodel import Session
from app.models import ImageArtifact, AuditLog, VolumeArtifact, VolumeStatus, RegistryConfig, RegistryType
from app.core.finops import CostCalculator
from app.core.security import decrypt_secret

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



    @abstractmethod
    def test_connection(self) -> dict:
        """Test registry connection and authentication"""
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

    def test_connection(self) -> dict:
        """Test connection to local Docker daemon"""
        try:
            self.client.ping()
            version = self.client.version()
            return {
                "success": True, 
                "message": f"Connected to Docker Engine v{version.get('Version', 'unknown')}"
            }
        except Exception as e:
            return {"success": False, "message": f"Connection failed: {str(e)}"}
    
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
                    digest=img.id,
                    source="Local"
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
                    labels=labels,
                    source="Local"
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


class DockerRegistryClient(BaseRegistryClient):
    """Client for V2-compliant registries (Docker Hub, GHCR, etc.)"""

    def __init__(self, config: RegistryConfig):
        self.config = config
        self.endpoint = self._normalize_endpoint(config.endpoint, config.type)
        self.username = config.username
        self.password = decrypt_secret(config.password) if config.password else None
        self.session = requests.Session()
        self.token = None
        
        # Initial authentication
        self._authenticate()

    def _normalize_endpoint(self, endpoint: Optional[str], reg_type: RegistryType) -> str:
        """Normalize endpoint URL"""
        if endpoint and endpoint.strip():
            url = endpoint.strip().rstrip("/")
            if not url.startswith("http"):
                url = f"https://{url}"
            return url
        
        # Default endpoints
        if reg_type == RegistryType.DOCKERHUB:
            return "https://registry-1.docker.io"
        elif reg_type == RegistryType.GHCR:
            return "https://ghcr.io"
        
        return "https://registry-1.docker.io" # Fallback

    def _authenticate(self):
        """Perform V2 authentication flow"""
        try:
            # 1. Attempt request to root/v2 to check auth requirements
            resp = self.session.get(f"{self.endpoint}/v2/", timeout=10)
            
            if resp.status_code == 401:
                auth_header = resp.headers.get("Www-Authenticate")
                if auth_header:
                    self._get_token(auth_header)
                elif self.username and self.password:
                    # Basic Auth Fallback
                    self.session.auth = (self.username, self.password)
            elif resp.status_code == 200:
                logger.info(f"Registry {self.config.name} allows anonymous access or is already authenticated")
                
        except Exception as e:
            logger.error(f"Authentication check failed for {self.config.name}: {e}")

    def test_connection(self) -> dict:
        """Test connection to remote registry"""
        try:
            # Force re-authentication check
            self._authenticate()
            
            # Try to list catalog or check root
            # DOCKERHUB check
            if self.config.type == RegistryType.DOCKERHUB:
                # 1. Strict Auth Check: Try to login to get JWT
                # This verifies username/password combination matches
                if self.username and self.password:
                    login_url = "https://hub.docker.com/v2/users/login"
                    login_resp = requests.post(
                        login_url, 
                        json={"username": self.username, "password": self.password},
                        timeout=10
                    )
                    
                    if login_resp.status_code == 200:
                        return {"success": True, "message": f"Successfully authenticated as {self.username}"}
                    elif login_resp.status_code == 401:
                        return {"success": False, "message": "Authentication failed: Invalid username or token"}
                    else:
                        return {"success": False, "message": f"Login failed: {login_resp.status_code} {login_resp.reason}"}
                
                # If no password provided (anonymous?), check if user exists
                hub_url = f"https://hub.docker.com/v2/repositories/{self.username}"
                resp = requests.get(hub_url, params={"page_size": 1})
                if resp.status_code == 200:
                    return {"success": True, "message": f"Verified public access to {self.username} (Warning: No credentials provided)"}
                else:
                    return {"success": False, "message": f"User not found or connection failed: {resp.status_code}"}
            
            # GHCR check
            elif self.config.type == RegistryType.GHCR:
                gh_session = requests.Session()
                if self.username and self.password:
                    gh_session.auth = (self.username, self.password)
                resp = gh_session.get("https://api.github.com/user", timeout=10)
                if resp.status_code == 200:
                    user = resp.json().get("login")
                    return {"success": True, "message": f"Successfully connected to GitHub API as {user}"}
                else:
                    return {"success": False, "message": f"GitHub API connection failed: {resp.status_code} {resp.reason}"}

            # Generic V2 check
            resp = self.session.get(f"{self.endpoint}/v2/", timeout=10)
            if resp.status_code == 200:
                return {"success": True, "message": f"Successfully connected to {self.endpoint}"}
            elif resp.status_code == 401:
                return {"success": False, "message": "Authentication failed (401)"}
            else:
                return {"success": False, "message": f"Connection failed: {resp.status_code} {resp.reason}"}
                
        except Exception as e:
            return {"success": False, "message": f"Connection error: {str(e)}"}

    def _get_token(self, auth_header: str):
        """Parse Www-Authenticate header and retrieve Bearer token"""
        params = {}
        # Parse header (simplified parser)
        for part in auth_header.replace("Bearer ", "").split(","):
            if "=" in part:
                key, value = part.split("=", 1)
                params[key.strip()] = value.strip('"')
        
        realm = params.get("realm")
        service = params.get("service")
        
        if not realm:
            return

        token_params = {"service": service} if service else {}
        
        # For Docker Hub, offline_token scope might be needed for refresh, but simpler to just get token
        auth = (self.username, self.password) if self.username and self.password else None
            
        try:
            token_resp = requests.get(realm, params=token_params, auth=auth, timeout=10)
            if token_resp.status_code == 200:
                token_data = token_resp.json()
                self.token = token_data.get("token") or token_data.get("access_token")
                if self.token:
                    self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        except Exception as e:
            logger.error(f"Failed to get token from {realm}: {e}")

    def list_images(self) -> List[ImageArtifact]:
        """List images in the registry"""
        artifacts = []
        
        if self.config.type == RegistryType.DOCKERHUB:
            return self._list_dockerhub_images()
        elif self.config.type == RegistryType.GHCR:
            return self._list_ghcr_images()
        
        # Generic V2 Catalog API
        try:
            catalog_url = f"{self.endpoint}/v2/_catalog"
            resp = self.session.get(catalog_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                repositories = data.get("repositories", [])
                
                for repo in repositories:
                    tags = self._list_tags(repo)
                    for tag in tags:
                        artifacts.append(self._create_artifact(repo, tag))
        except Exception as e:
            logger.error(f"Failed to list images from {self.config.name}: {e}")
            
        return artifacts


    def _list_ghcr_images(self) -> List[ImageArtifact]:
        """List images using GitHub API (GHCR doesn't support _catalog)"""
        # https://docs.github.com/en/rest/packages/packages?apiVersion=2022-11-28#list-packages-for-the-authenticated-user
        
        if not self.username or not self.password:
            return []
            
        artifacts = []
        
        # We use the GitHub API, not the Registry API for listing
        # Need to decide if we list User packages or Org packages
        # For MVP, try listing authenticated user's packages
        
        gh_session = requests.Session()
        gh_session.auth = (self.username, self.password) # PAT is password
        gh_session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        })
        
        # 1. List packages for authenticated user
        # GET /user/packages?package_type=container
        url = "https://api.github.com/user/packages"
        params = {"package_type": "container", "per_page": 100}
        
        try:
            while url:
                resp = gh_session.get(url, params=params, timeout=10)
                if resp.status_code != 200:
                    # Fallback: maybe they provided an Org name as username? 
                    # But standard is PAT which is user-scoped.
                    logger.warning(f"GHCR API error: {resp.status_code} {resp.text}")
                    break
                    
                data = resp.json()
                for pkg in data:
                    pkg_name = pkg.get("name")
                    owner = pkg.get("owner", {}).get("login")
                    full_name = f"{owner}/{pkg_name}"
                    
                    # 2. List versions (tags) for each package
                    # GET /user/packages/container/{package_name}/versions
                    v_url = f"https://api.github.com/user/packages/container/{pkg_name}/versions"
                    v_resp = gh_session.get(v_url, params={"per_page": 100})
                    
                    if v_resp.status_code == 200:
                        versions = v_resp.json()
                        for ver in versions:
                            tags = ver.get("metadata", {}).get("container", {}).get("tags", [])
                            if not tags:
                                continue # Skip untagged images
                            
                            # Size is not always in package metadata, sometimes need manifest
                            # For MVP we default to 0 if not found
                            size = 0 
                            
                            created_at_str = ver.get("created_at")
                            if created_at_str:
                                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                            else:
                                created_at = datetime.utcnow()
                            
                            digest = ver.get("name", "") # Digest is the version name in GHCR API usually sha256:...
                            
                            for tag in tags:
                                artifacts.append(ImageArtifact(
                                    tags=[f"ghcr.io/{full_name}:{tag}"],
                                    size_bytes=size, 
                                    created_at=created_at,
                                    digest=digest,
                                    source=self.config.name
                                ))
                
                # Pagination
                # Link: <https://api.github.com/user/packages?page=2>; rel="next", ...
                if "next" in resp.links:
                    url = resp.links["next"]["url"]
                    params = {} # Params are in the link URL
                else:
                    url = None
        except Exception as e:
            logger.error(f"GHCR API error: {e}")
            
        return artifacts

    def _list_dockerhub_images(self) -> List[ImageArtifact]:
        """List images using Docker Hub API"""
        if not self.username:
            return []
            
        artifacts = []
        try:
            # Hub API (v2) - List repositories for user
            hub_url = f"https://hub.docker.com/v2/repositories/{self.username}"
            hub_session = requests.Session()
            
            # Login to Hub API to get JWT (separate from Registry Token)
            if self.password:
                login_url = "https://hub.docker.com/v2/users/login"
                login_resp = hub_session.post(login_url, json={"username": self.username, "password": self.password})
                if login_resp.status_code == 200:
                    token = login_resp.json().get("token")
                    hub_session.headers.update({"Authorization": f"JWT {token}"})
            
            # Pagination loop
            while hub_url:
                try:
                    resp = hub_session.get(hub_url, params={"page_size": 100}, timeout=10)
                    if resp.status_code != 200:
                        break
                        
                    data = resp.json()
                    repos = data.get("results", [])
                    
                    for repo in repos:
                        repo_name = f"{repo.get('namespace')}/{repo.get('name')}"
                        # Fetch tags for this repo (Parallelize or Lazy Load?)
                        # Optimization: Only fetch 5 recent tags for MVP speed, or use a separate thread pool?
                        # For now, we wrap in try/except so one failed repo doesn't kill the loop
                        try:
                            tags_url = f"https://hub.docker.com/v2/repositories/{repo_name}/tags"
                            tags_resp = hub_session.get(tags_url, params={"page_size": 25}, timeout=5)
                            if tags_resp.status_code == 200:
                                tags = tags_resp.json().get("results", [])
                                for tag in tags:
                                    # Parse size and date
                                    size = tag.get('full_size', 0)
                                    last_updated = tag.get('last_updated')
                                    created_at = datetime.utcnow()
                                    if last_updated:
                                        try:
                                            created_at = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                                        except: pass
                                        
                                    artifacts.append(ImageArtifact(
                                        tags=[f"{repo_name}:{tag['name']}"],
                                        size_bytes=size,
                                        created_at=created_at,
                                        digest=tag.get('images', [{}])[0].get('digest', ''),
                                        source=self.config.name
                                    ))
                        except Exception as e:
                            logger.warning(f"Failed to fetch tags for {repo_name}: {e}")
                    
                    hub_url = data.get("next") # Pagination
                except Exception as e:
                    logger.error(f"Error during Hub pagination: {e}")
                    break
                            
        except Exception as e:
            logger.error(f"Docker Hub API error: {e}")
            
        return artifacts

    def _list_tags(self, repo_name: str) -> List[str]:
        """List tags for a repository (V2 Registry API)"""
        try:
            url = f"{self.endpoint}/v2/{repo_name}/tags/list"
            resp = self.session.get(url, timeout=10)
            
            # Handle token refresh if needed (401)
            if resp.status_code == 401:
                auth_header = resp.headers.get("Www-Authenticate")
                if auth_header:
                    self._get_token(auth_header)
                    resp = self.session.get(url, timeout=10)
            
            if resp.status_code == 200:
                return resp.json().get("tags", []) or []
        except Exception:
            pass
        return []

    def _create_artifact(self, repo: str, tag: str) -> ImageArtifact:
        """Create ImageArtifact from V2 manifest"""
        size = 0
        digest = ""
        created = datetime.utcnow()
        
        try:
            url = f"{self.endpoint}/v2/{repo}/manifests/{tag}"
            headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
            resp = self.session.get(url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                digest = resp.headers.get("Docker-Content-Digest", "")
                data = resp.json()
                size = data.get("config", {}).get("size", 0) + sum(l.get("size", 0) for l in data.get("layers", []))
        except Exception:
            pass
            
        return ImageArtifact(
            tags=[f"{repo}:{tag}"],
            size_bytes=size,
            created_at=created,
            digest=digest,
            source=self.config.name
        )

    def get_manifest_size(self, digest: str) -> int:
        return 0

    def delete_image(self, session: Session, image_id: str, dry_run: bool = True, force: bool = False) -> dict:
        """Delete image from remote registry.
        
        Supports Docker Hub deletion (via Hub API) and generic V2 deletion (via manifest).
        """
        success = False
        message = ""
        bytes_freed = 0
        savings_usd = 0.0
        
        # 1. Parse image_id to get repo and tag/digest
        # image_id format from list_images: "repo:tag" or "namespace/repo:tag"
        try:
            repo_tag = image_id.split(":")
            if len(repo_tag) != 2:
                return {"success": False, "message": f"Invalid image ID format: {image_id}"}
            
            repo_name = repo_tag[0]
            tag = repo_tag[1]
            
            # Dry Run
            if dry_run:
                return {
                    "success": True,
                    "image_id": image_id,
                    "image_tags": [image_id],
                    "bytes_freed": 0,
                    "savings_usd": 0.0,
                    "dry_run": True,
                    "message": f"DRY RUN: Would delete remote image {image_id}"
                }

            # Real Deletion
            if self.config.type == RegistryType.DOCKERHUB:
                # Docker Hub Deletion
                if not self.username or not self.password:
                    raise ValueError("Credentials required for deletion")

                hub_session = requests.Session()
                # Login
                login_url = "https://hub.docker.com/v2/users/login"
                login_resp = hub_session.post(login_url, json={"username": self.username, "password": self.password})
                if login_resp.status_code != 200:
                    raise ValueError("Failed to authenticate with Docker Hub API")
                
                token = login_resp.json().get("token")
                hub_session.headers.update({"Authorization": f"JWT {token}"})
                
                # Delete Tag
                # URL: DELETE https://hub.docker.com/v2/repositories/{namespace}/{repo}/tags/{tag}/
                # repo_name might be "namespace/repo" already
                delete_url = f"https://hub.docker.com/v2/repositories/{repo_name}/tags/{tag}/"
                del_resp = hub_session.delete(delete_url)
                
                if del_resp.status_code == 204:
                    success = True
                    message = f"Successfully deleted {image_id} from Docker Hub"
                else:
                    message = f"Failed to delete {image_id}: {del_resp.text}"
            
            elif self.config.type == RegistryType.GHCR:
                 # GHCR Deletion (Delete Package Version)
                 # https://docs.github.com/en/rest/packages/packages?apiVersion=2022-11-28#delete-a-package-version-for-the-authenticated-user
                 # DELETE /user/packages/{package_type}/{package_name}/versions/{package_version_id}
                 
                 # NOTE: Tag deletion is complex in GHCR via API. You usually delete the version ID (digest).
                 # We need to map tag -> version_id first.
                 pass # Todo: proper GHCR deletion mapping

            else:
                # Generic V2 Deletion (Manifest Deletion)
                # Need digest first
                url = f"{self.endpoint}/v2/{repo_name}/manifests/{tag}"
                headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
                head_resp = self.session.head(url, headers=headers)
                
                if head_resp.status_code == 200:
                    digest = head_resp.headers.get("Docker-Content-Digest")
                    if digest:
                        del_url = f"{self.endpoint}/v2/{repo_name}/manifests/{digest}"
                        del_resp = self.session.delete(del_url)
                        if del_resp.status_code == 202:
                            success = True
                            message = f"Successfully deleted {image_id} (manifest)"
                        else:
                            message = f"Failed to delete manifest: {del_resp.status_code} {del_resp.text}"
                    else:
                        message = "Could not retrieve manifest digest"
                else:
                    message = f"Image not found or access denied: {head_resp.status_code}"

        except Exception as e:
            logger.error(f"Remote deletion error: {e}")
            message = f"Error: {str(e)}"

        # Audit Log
        if success:
             audit_entry = AuditLog(
                image_id=image_id,
                image_tags=[image_id],
                bytes_freed=0, # Hard to know exact size freed remotely without more queries
                savings_usd=0.0,
                dry_run=False
            )
             session.add(audit_entry)

        return {
            "success": success,
            "message": message,
            "image_id": image_id,
            "image_tags": [image_id],
            "bytes_freed": 0,
            "savings_usd": 0.0,
            "dry_run": False
        }

    def list_volumes(self) -> List[VolumeArtifact]:
        return []

    def delete_volume(self, session, name, force=False) -> dict:
        return {"success": False, "message": "Remote volumes not supported"}


class RegistryClientFactory:
    """Factory for creating registry clients based on configuration"""
    
    @staticmethod
    def get_client(config: Optional[RegistryConfig] = None) -> BaseRegistryClient:
        """Get the appropriate registry client.
        
        If no config is provided, returns the LocalDockerClient.
        """
        if config is None:
            return LocalDockerClient()
        
        return DockerRegistryClient(config)
