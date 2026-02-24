"""Docker Registry abstraction"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple
import boto3
import google.auth
from google.oauth2 import service_account
from google.cloud import artifactregistry_v1
from azure.identity import DefaultAzureCredential
from azure.containerregistry import ContainerRegistryClient
from botocore.exceptions import ClientError
import docker
from docker.errors import APIError, ImageNotFound, NotFound
from datetime import datetime
import re
import logging
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlmodel import Session, select
from app.models import ImageArtifact, AuditLog, VolumeArtifact, VolumeStatus, RegistryConfig, RegistryType
from app.core.finops import CostCalculator
from app.core.security import decrypt_secret
from app.core.bloat import BloatAnalyzer
import json

logger = logging.getLogger(__name__)


from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

# Simple global cache for image listings to prevent redundant API calls during filtering
_IMAGE_CACHE: Dict[str, Tuple[List[ImageArtifact], datetime]] = {}
_CACHE_TTL = timedelta(minutes=5)

def create_resilient_session() -> requests.Session:
    """Create a requests session with exponential backoff retries."""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,  # 1s, 2s, 4s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "DELETE"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def get_cached_images(key: str) -> Optional[List[ImageArtifact]]:
    """Retrieve images from cache if not expired"""
    if key in _IMAGE_CACHE:
        images, timestamp = _IMAGE_CACHE[key]
        if datetime.utcnow() - timestamp < _CACHE_TTL:
            logger.debug(f"Cache hit for images: {key}")
            return images
        else:
            logger.debug(f"Cache expired for images: {key}")
            del _IMAGE_CACHE[key]
    return None

def set_cached_images(key: str, images: List[ImageArtifact]):
    """Store images in cache with current timestamp"""
    _IMAGE_CACHE[key] = (images, datetime.utcnow())
    logger.debug(f"Cached {len(images)} images for: {key}")

def clear_image_cache(key: Optional[str] = None):
    """Clear specific or all image caches"""
    global _IMAGE_CACHE
    if key:
        if key in _IMAGE_CACHE:
            del _IMAGE_CACHE[key]
    else:
        _IMAGE_CACHE = {}
    logger.info("Image cache cleared")

class BaseRegistryClient(ABC):

    """Abstract base class for registry clients"""
    
    @abstractmethod
    def list_images(self, limit: int = 100, bypass_cache: bool = False) -> List[ImageArtifact]:
        """List all images in the registry
        
        Args:
            limit: Maximum number of images to return
            bypass_cache: If True, forces a fresh fetch from the provider
        """
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
    
    def list_images(self, limit: int = 100, bypass_cache: bool = False) -> List[ImageArtifact]:
        """List all local Docker images"""
        import time
        start = time.time()
        cache_key = f"local_{limit}"
        if not bypass_cache:
            cached = get_cached_images(cache_key)
            if cached: 
                logger.info(f"Local images cache hit in {(time.time() - start)*1000:.2f}ms")
                return cached

        try:
            # Docker Py doesn't support server-side limit in list(), so we slice locally
            images = self.client.images.list()
            # Sort by Created (newest first)
            images.sort(key=lambda x: x.attrs.get('Created', ''), reverse=True)
            
            # Apply limit
            images = images[:limit]
            
            artifacts = []
            
            for img in images:
                # Extract tags (remove 'latest' duplicates)
                tags = img.tags if img.tags else [f"<none>:{img.short_id}"]
                
                # Bloat Analysis
                size = img.attrs.get('Size', 0)
                analysis = BloatAnalyzer.analyze_image(tags, size)
                
                # Create ImageArtifact
                artifact = ImageArtifact(
                    tags=tags,
                    size_bytes=size,
                    created_at=datetime.fromisoformat(
                        img.attrs.get('Created', datetime.utcnow().isoformat()).replace('Z', '+00:00')
                    ),
                    digest=img.id or "unknown",
                    source="Local",
                    bloat_score=analysis['score'],
                    bloat_issues=json.dumps(analysis['issues']) if analysis['issues'] else None
                )
                artifacts.append(artifact)
            
            logger.info(f"Successfully listed {len(artifacts)} images")
            set_cached_images(cache_key, artifacts)
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
        """Delete a Docker image with audit logging and dry-run support."""
        if not image_id or not image_id.strip():
            raise ValueError("image_id cannot be empty")
        
        image_id = image_id.strip()
        
        if image_id.startswith('sha256:'):
            if not re.match(r'^sha256:[a-f0-9]{64}$', image_id):
                raise ValueError(f"Invalid image_id format: {image_id}")
        elif not re.match(r'^[\w\-\./:]+$', image_id):
            raise ValueError(f"Invalid image_id format: {image_id}")
        
        try:
            img = self.client.images.get(image_id)
            image_tags = img.tags if img.tags else [f"<none>:{img.short_id}"]
            size_bytes = img.attrs.get('Size', 0)
            actual_digest = img.id or "unknown"
            
            monthly_cost = CostCalculator.calculate_monthly_cost(size_bytes, source=img.attrs.get('Source', 'Local'))
            
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
                result["message"] = (
                    f"DRY RUN: Would delete image {image_tags[0]} "
                    f"({size_bytes / (1024**3):.2f} GB, ${monthly_cost:.2f}/mo savings)"
                )
                logger.info(result["message"], extra={"image_id": actual_digest, "dry_run": True})
                
                audit_entry = AuditLog(
                    action="DELETE",
                    image_id=actual_digest,
                    image_tags=image_tags,
                    source="Local",
                    bytes_freed=size_bytes,
                    savings_usd=monthly_cost,
                    dry_run=True
                )
                session.add(audit_entry)
                
            else:
                try:
                    self.client.images.remove(image_id, force=force)
                    clear_image_cache()
                    result["message"] = (
                        f"Successfully deleted image {image_tags[0]} "
                        f"({size_bytes / (1024**3):.2f} GB freed, ${monthly_cost:.2f}/mo savings)"
                    )
                    logger.info(result["message"], extra={"image_id": actual_digest, "dry_run": False})
                    
                    audit_entry = AuditLog(
                        action="DELETE",
                        image_id=actual_digest,
                        image_tags=image_tags,
                        source="Local",
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
                
            savings_usd = CostCalculator.calculate_monthly_cost(size_bytes, source=v.attrs.get('Source', 'Local'))
            
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
                action="DELETE",
                image_id=f"volume:{name}",
                image_tags=[f"volume:{name}"],
                source="Local",
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
        self.session = create_resilient_session()
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
        """Test connection to remote registry using a real API call"""
        try:
            # First perform generic V2 auth
            self._authenticate()
            
            # Provider-specific lightweight API calls to verify auth/connectivity
            if self.config.type == RegistryType.DOCKERHUB:
                # Docker Hub: Check repo listing for user (using hub API)
                hub_url = f"https://hub.docker.com/v2/repositories/{self.username}"
                # Get hub token (handled in authenticate but let's be explicit)
                login_resp = requests.post("https://hub.docker.com/v2/users/login", 
                    json={"username": self.username, "password": self.password}, timeout=10)
                if login_resp.status_code != 200:
                    return {"success": False, "message": "Auth Failed: Invalid Hub credentials", "type": "AUTH_ERROR"}
                
                # Check listing
                token = login_resp.json().get("token")
                resp = requests.get(hub_url, headers={"Authorization": f"JWT {token}"}, params={"page_size": 1}, timeout=10)
                if resp.status_code == 200:
                    return {"success": True, "message": f"Connected as {self.username}"}
                return {"success": False, "message": f"Access Denied: Could not list repos ({resp.status_code})", "type": "AUTH_ERROR"}

            elif self.config.type == RegistryType.GHCR:
                # GHCR: Check /user/packages
                resp = self.session.get("https://api.github.com/user/packages", params={"package_type": "container"}, timeout=10)
                if resp.status_code == 200:
                    return {"success": True, "message": "Authenticated with GHCR (read:packages)"}
                elif resp.status_code in [401, 403]:
                    return {"success": False, "message": "Auth Failed: Check token scopes", "type": "AUTH_ERROR"}
                return {"success": False, "message": f"GHCR Error: {resp.status_code}", "type": "NETWORK_ERROR"}
            
            # Generic V2 Check
            resp = self.session.get(f"{self.endpoint}/v2/_catalog", params={"n": 1}, timeout=10)
            if resp.status_code == 200:
                return {"success": True, "message": "Connected to Registry V2 API"}
            elif resp.status_code in [401, 403]:
                return {"success": False, "message": "Authentication Failed (V2)", "type": "AUTH_ERROR"}
            
            return {"success": False, "message": f"Registry returned {resp.status_code}", "type": "NETWORK_ERROR"}

        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"Network error: {str(e)}", "type": "NETWORK_ERROR"}
        except Exception as e:
            return {"success": False, "message": str(e), "type": "UNKNOWN_ERROR"}

        """Test connection to remote registry"""
        try:
            # Force re-authentication check
            self._authenticate()
            
            # Try to list catalog or check root
            # DOCKERHUB check
            if self.config.type == RegistryType.DOCKERHUB:
                # 1. Strict Auth Check: Try to login to get JWT
                # This verifies username/password combination matches
                auth_success = False
                login_msg = ""
                login_resp = None
                
                if self.username and self.password:
                    try:
                        login_url = "https://hub.docker.com/v2/users/login"
                        login_resp = requests.post(
                            login_url, 
                            json={"username": self.username, "password": self.password},
                            timeout=10
                        )

                        
                        if login_resp.status_code == 200:
                            auth_success = True
                            login_msg = f"Successfully authenticated as {self.username}"
                        elif login_resp.status_code == 401:
                            login_msg = "Authentication failed: Invalid username or token"
                        else:
                            login_msg = f"Login failed: {login_resp.status_code} {login_resp.text[:100]}"
                            logger.error(f"Docker Hub Login Failed: {login_resp.status_code} {login_resp.text}")
                    except Exception as e:
                        login_msg = f"Login connection error: {str(e)}"
                
                # 2. Check Repo Access (Public or Private)
                # If login worked, this confirms we can see repos.
                # If login failed, this checks if we can at least see public repos.
                
                hub_url = f"https://hub.docker.com/v2/repositories/{self.username}"
                headers = {}
                if auth_success and login_resp and login_resp.status_code == 200:
                    token = login_resp.json().get("token")
                    headers = {"Authorization": f"JWT {token}"}
                
                try:
                    resp = requests.get(hub_url, headers=headers, params={"page_size": 1}, timeout=10)
                    if resp.status_code == 200:
                        if self.username and self.password and not auth_success:
                            # Login failed but public access works
                            return {
                                "success": False, 
                                "message": f"Credentials Invalid! Public access only. ({login_msg})"
                            }
                        return {
                            "success": True, 
                            "message": f"Connected! {login_msg or 'Public access verified.'}"
                        }
                    else:
                        if auth_success:
                            return {"success": True, "message": f"Authenticated, but could not list repos: {resp.status_code}"}
                        return {"success": False, "message": f"Connection failed: {login_msg or resp.status_code}"}
                except Exception as e:
                     return {"success": False, "message": f"Repo check failed: {str(e)}"}
            
            # GHCR check
            elif self.config.type == RegistryType.GHCR:
                gh_session = requests.Session()
                if self.username and self.password:
                    gh_session.auth = (self.username, self.password)
                
                # Check /user/packages instead of /user to verify read:packages scope
                resp = gh_session.get("https://api.github.com/user/packages", params={"package_type": "container", "per_page": 1}, timeout=10)
                
                if resp.status_code == 200:
                    # Get user info from packages listing if possible, or just confirm access
                    return {"success": True, "message": f"Successfully authenticated with GitHub Packages (read:packages)"}
                elif resp.status_code == 401:
                    # Parse specific error if available
                    try:
                        error_msg = resp.json().get("message", "Unknown error")
                    except:
                        error_msg = resp.text
                    return {"success": False, "message": f"Authentication failed: {error_msg}. Check if your token has 'read:packages' scope."}
                elif resp.status_code == 403:
                    # Check for SSO requirement
                    try:
                        error_msg = resp.json().get("message", "Unknown error")
                    except:
                        error_msg = resp.text
                    return {"success": False, "message": f"Access Forbidden (403): {error_msg}. If using SSO, authorize the token."}
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

    def list_images(self, limit: int = 100, bypass_cache: bool = False) -> List[ImageArtifact]:
        """List images in the registry"""
        import time
        start = time.time()
        cache_key = f"remote_{self.config.id}_{limit}"
        if not bypass_cache:
            cached = get_cached_images(cache_key)
            if cached: 
                logger.info(f"Remote images cache hit for {self.config.name} in {(time.time() - start)*1000:.2f}ms")
                return cached

        artifacts = []
        
        if self.config.type == RegistryType.DOCKERHUB:
            artifacts = self._list_dockerhub_images(limit=limit)
        elif self.config.type == RegistryType.GHCR:
            artifacts = self._list_ghcr_images(limit=limit)
        else:
            # Generic V2 Catalog API
            try:
                # V2 _catalog usually returns paginated results via 'n' param
                catalog_url = f"{self.endpoint}/v2/_catalog"
                # Pass limit if supported
                resp = self.session.get(catalog_url, params={"n": limit}, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    repositories = data.get("repositories", [])
                    
                    count = 0
                    for repo in repositories:
                        if count >= limit: break
                        
                        tags = self._list_tags(repo)
                        for tag in tags:
                            if count >= limit: break
                            artifacts.append(self._create_artifact(repo, tag))
                            count += 1
            except Exception as e:
                logger.error(f"Failed to list images from {self.config.name}: {e}")
            
        if artifacts:
            set_cached_images(cache_key, artifacts)
            
        return artifacts


    def _list_ghcr_images(self, limit: int = 100) -> List[ImageArtifact]:
        """List images using GitHub API with concurrent version checking"""
        # https://docs.github.com/en/rest/packages/packages?apiVersion=2022-11-28#list-packages-for-the-authenticated-user
        
        if not self.username or not self.password:
            return []
            
        artifacts = []
        import concurrent.futures
        
        # We use the GitHub API, not the Registry API for listing
        gh_session = requests.Session()
        gh_session.auth = (self.username, self.password) # PAT is password
        gh_session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        })
        
        # 1. List packages
        url = "https://api.github.com/user/packages"
        params = {"package_type": "container", "per_page": min(limit, 100)}
        
        packages = []
        try:
            while url and len(packages) < limit:
                logger.info(f"Fetching GHCR packages from {url}")
                resp = gh_session.get(url, params=params, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"GHCR API error: {resp.status_code} {resp.text}")
                    break
                    
                data = resp.json()
                logger.info(f"GHCR: Found {len(data)} packages on page")
                if not data: break
                packages.extend(data)
                
                if "next" in resp.links:
                    url = resp.links["next"]["url"]
                    params = {}
                else:
                    url = None
        except Exception as e:
            logger.error(f"GHCR Package list error: {e}")
            return []

        logger.info(f"GHCR: Total packages to scan: {len(packages)}")

        # 2. Fetch versions concurrently
        import base64
        auth_str = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        
        def fetch_package_versions(pkg):
            local_artifacts = []
            pkg_name = pkg.get("name")
            try:
                owner = pkg.get("owner", {}).get("login")
                full_name = f"{owner}/{pkg_name}"
                v_url = f"https://api.github.com/user/packages/container/{pkg_name}/versions"
                
                # Use the existing gh_session for version fetching
                v_resp = gh_session.get(v_url, params={"per_page": 20}, timeout=10)

                if v_resp.status_code == 200:
                    versions = v_resp.json()
                    for ver in versions:
                        tags = ver.get("metadata", {}).get("container", {}).get("tags", [])
                        if not tags: continue 
                        
                        # Size fetching (requires Registry API)
                        # Optimization: Skip size fetch for list view to be super fast?
                        # Or fetch concurrently? 
                        # For now, let's try to get it but fail gracefully/quickly.
                        size = 0
                        # ... (Size fetching logic omitted for speed or implemented if critical)
                        
                        created_at_str = ver.get("created_at")
                        if created_at_str:
                            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                        else:
                            created_at = datetime.utcnow()
                        
                        digest = ver.get("name", "") 
                        
                        for tag in tags:
                            analysis = BloatAnalyzer.analyze_image([tag], size)
                            local_artifacts.append(ImageArtifact(
                                tags=[f"ghcr.io/{full_name}:{tag}"],
                                size_bytes=size, # 0 for now to speed up
                                created_at=created_at,
                                digest=digest,
                                source=self.config.name,
                                bloat_score=analysis['score'],
                                bloat_issues=json.dumps(analysis['issues']) if analysis['issues'] else None
                            ))
            except Exception as e:
                logger.warning(f"Failed to fetch versions for {pkg_name}: {e}")
            return local_artifacts

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_pkg = {executor.submit(fetch_package_versions, pkg): pkg for pkg in packages}
            for future in concurrent.futures.as_completed(future_to_pkg):
                try:
                    res = future.result()
                    artifacts.extend(res)
                except Exception as e:
                    logger.error(f"Thread error: {e}")
                    
        return artifacts[:limit]

    def _list_dockerhub_images(self, limit: int = 100) -> List[ImageArtifact]:
        """List images using Docker Hub API with concurrent tag fetching"""
        if not self.username:
            return []
            
        artifacts = []
        import concurrent.futures
        
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
            
            repo_list = []
            
            # 1. Fetch Repositories first (Pagination)
            while hub_url and len(repo_list) < limit: # Crude limit check
                try:
                    resp = hub_session.get(hub_url, params={"page_size": min(limit, 100)}, timeout=10)
                    if resp.status_code != 200:
                        break
                        
                    data = resp.json()
                    repos = data.get("results", [])
                    repo_list.extend(repos)
                    
                    if len(repo_list) >= limit: 
                        break
                        
                    hub_url = data.get("next")
                except Exception as e:
                    logger.error(f"Error fetching Hub repos: {e}")
                    break
            
            # 2. Fetch Tags concurrently
            def fetch_repo_tags(repo):
                repo_name = f"{repo.get('namespace')}/{repo.get('name')}"
                local_artifacts = []
                try:
                    # Create a new session or reuse? Requests session is not thread-safe if sharing connection pool?
                    # Actually Session is thread-safe for connection reuse if configured, but let's use a fresh one or lock.
                    # Simpler: Just use requests.get with headers if token needed.
                    headers = hub_session.headers # Copy headers (auth)
                    
                    tags_url = f"https://hub.docker.com/v2/repositories/{repo_name}/tags"
                    # Just fetch one page of recent tags
                    tags_resp = hub_session.get(tags_url, params={"page_size": 25}, timeout=10)
                    
                    if tags_resp.status_code == 200:
                        tags = tags_resp.json().get("results", [])
                        for tag in tags:
                            size = tag.get('full_size', 0)
                            last_updated = tag.get('last_updated')
                            created_at = datetime.utcnow()
                            if last_updated:
                                try:
                                    created_at = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                                except: pass
                                
                            full_tag = f"{repo_name}:{tag['name']}"
                            analysis = BloatAnalyzer.analyze_image([full_tag], size)
                            
                            local_artifacts.append(ImageArtifact(
                                tags=[full_tag],
                                size_bytes=size,
                                created_at=created_at,
                                digest=tag.get('images', [{}])[0].get('digest', ''),
                                source=self.config.name,
                                bloat_score=analysis['score'],
                                bloat_issues=json.dumps(analysis['issues']) if analysis['issues'] else None
                            ))
                except Exception as e:
                    logger.warning(f"Failed to fetch tags for {repo_name}: {e}")
                return local_artifacts

            # Execute concurrent fetch
            # Cap workers to avoid rate limits (e.g., 5-10)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                future_to_repo = {executor.submit(fetch_repo_tags, repo): repo for repo in repo_list}
                for future in concurrent.futures.as_completed(future_to_repo):
                    try:
                        res = future.result()
                        artifacts.extend(res)
                        if len(artifacts) >= limit:
                            # We can stop collecting, but cancelling futures is hard. 
                            # We just slice at the end.
                            pass
                    except Exception as e:
                        logger.error(f"Thread error: {e}")

        except Exception as e:
            logger.error(f"Docker Hub API error: {e}")
            
        return artifacts[:limit]

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
            
        full_tag = f"{repo}:{tag}"
        analysis = BloatAnalyzer.analyze_image([full_tag], size)
        
        return ImageArtifact(
            tags=[full_tag],
            size_bytes=size,
            created_at=created,
            digest=digest,
            source=self.config.name,
            bloat_score=analysis['score'],
            bloat_issues=json.dumps(analysis['issues']) if analysis['issues'] else None
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
                    clear_image_cache() # Invalidate on change
                    message = f"Successfully deleted {image_id} from Docker Hub"
                else:
                    message = f"Failed to delete {image_id}: {del_resp.text}"
            
            elif self.config.type == RegistryType.GHCR:
                 # GHCR Deletion (Delete Package Version)
                 # https://docs.github.com/en/rest/packages/packages?apiVersion=2022-11-28#delete-a-package-version-for-the-authenticated-user
                 
                 # 1. We need the package version ID to delete.
                 # image_id usually comes as "ghcr.io/owner/package:tag"
                 # We need to map tag -> version ID
                 
                 if not self.username or not self.password:
                     raise ValueError("Credentials required for deletion")
                     
                 gh_session = requests.Session()
                 gh_session.auth = (self.username, self.password)
                 gh_session.headers.update({
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28"
                 })
                 
                 # Parse Owner/Package/Tag
                 # Example: ghcr.io/adam-benyekkou/dredge:latest
                 # image_id might be the full string from listing
                 
                 clean_id = image_id.replace("ghcr.io/", "")
                 parts = clean_id.split(":")
                 if len(parts) != 2:
                     return {"success": False, "message": f"Invalid GHCR ID format: {image_id}"}
                 
                 full_repo = parts[0] # owner/package
                 tag = parts[1]
                 
                 repo_parts = full_repo.split("/")
                 if len(repo_parts) != 2:
                     return {"success": False, "message": f"Invalid repo format: {full_repo}"}
                     
                 owner = repo_parts[0]
                 package_name = repo_parts[1]
                 
                 # Step A: Find Version ID by Tag
                 # GET /user/packages/container/{package_name}/versions
                 # We filter manually since API filtering by tag isn't direct
                 
                 version_id = None
                 find_url = f"https://api.github.com/user/packages/container/{package_name}/versions"
                 
                 # Pagination search for the tag
                 found = False
                 while find_url and not found:
                     resp = gh_session.get(find_url, params={"per_page": 100})
                     if resp.status_code != 200:
                         logger.error(f"Failed to list versions for {package_name}: {resp.status_code}")
                         break
                         
                     versions = resp.json()
                     for v in versions:
                         tags = v.get("metadata", {}).get("container", {}).get("tags", [])
                         if tag in tags:
                             version_id = v.get("id")
                             found = True
                             break
                     
                     if "next" in resp.links:
                         find_url = resp.links["next"]["url"]
                     else:
                         find_url = None
                 
                 if not version_id:
                     return {"success": False, "message": f"Could not find version ID for tag: {tag}"}
                     
                 # Step B: Delete Package Version
                 # DELETE /user/packages/{package_type}/{package_name}/versions/{package_version_id}
                 del_url = f"https://api.github.com/user/packages/container/{package_name}/versions/{version_id}"
                 del_resp = gh_session.delete(del_url)
                 
                 if del_resp.status_code == 204:
                     success = True
                     clear_image_cache()
                     message = f"Successfully deleted {image_id} (Version {version_id}) from GHCR"
                 else:
                     message = f"Failed to delete version {version_id}: {del_resp.status_code} {del_resp.text}"

            else:
                # Generic V2 Deletion (Manifest Deletion)
                # Need digest first
                url = f"{self.endpoint}/v2/{repo_name}/manifests/{tag}"
                headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
                head_resp = self.session.head(url, headers=headers, timeout=10)
                
                if head_resp.status_code == 200:
                    digest = head_resp.headers.get("Docker-Content-Digest")
                    if digest:
                        del_url = f"{self.endpoint}/v2/{repo_name}/manifests/{digest}"
                        del_resp = self.session.delete(del_url, timeout=10)
                        if del_resp.status_code == 202:
                            success = True
                            clear_image_cache()
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
                action="DELETE",
                image_id=image_id,
                image_tags=[image_id],
                source=self.config.name if hasattr(self, 'config') else "Remote",
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
        if config.type == RegistryType.ECR:
            return AWSRegistryClient(config)
        if config.type == RegistryType.GAR:
            return GARRegistryClient(config)
        if config.type == RegistryType.ACR:
            return ACRRegistryClient(config)
        return DockerRegistryClient(config)
class AWSRegistryClient(BaseRegistryClient):
    """Client for AWS Elastic Container Registry (ECR)"""
    
    def __init__(self, config: RegistryConfig):
        self.config = config
        self.access_key = config.username
        self.secret_key = decrypt_secret(config.password) if config.password else None
        
        # Parse region from endpoint or use default
        # Endpoint example: 123456789012.dkr.ecr.us-east-1.amazonaws.com
        self.region = "us-east-1"
        if config.endpoint:
            match = re.search(r'\.ecr\.([\w\-]+)\.amazonaws\.com', config.endpoint)
            if match:
                self.region = match.group(1)

    def _get_session(self):
        return boto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region
        )

    def test_connection(self) -> dict:
        try:
            client = self._get_session().client('ecr')
            client.describe_repositories(maxResults=1)
            return {"success": True, "message": f"Connected to ECR in {self.region}"}
        except ClientError as e:
            return {"success": False, "message": f"AWS Auth Failed: {e.response['Error']['Message']}"}
        except Exception as e:
            return {"success": False, "message": f"Connection Error: {str(e)}"}

    def list_images(self, limit: int = 100, bypass_cache: bool = False) -> List[ImageArtifact]:
        cache_key = f"ecr_{self.config.id}"
        if not bypass_cache:
            cached = get_cached_images(cache_key)
            if cached: return cached

        artifacts = []
        try:
            client = self._get_session().client('ecr')
            repos_resp = client.describe_repositories()
            
            for repo in repos_resp.get('repositories', []):
                repo_name = repo['repositoryName']
                images_resp = client.describe_images(repositoryName=repo_name)
                
                for img in images_resp.get('imageDetails', []):
                    tags = [f"{repo_name}:{t}" for t in img.get('imageTags', [])]
                    if not tags:
                        tags = [f"{repo_name}:<none>"]
                    
                    # AWS ECR returns imageSizeInBytes
                    size = img.get('imageSizeInBytes', 0)
                    digest = img.get('imageDigest', '')
                    created_at = img.get('imagePushedAt', datetime.utcnow())
                    
                    analysis = BloatAnalyzer.analyze_image(tags, size)
                    
                    artifacts.append(ImageArtifact(
                        tags=tags,
                        size_bytes=size,
                        created_at=created_at,
                        digest=digest,
                        source=self.config.name,
                        bloat_score=analysis['score'],
                        bloat_issues=json.dumps(analysis['issues']) if analysis['issues'] else None
                    ))
                    
                    if len(artifacts) >= limit:
                        break
                if len(artifacts) >= limit:
                    break
                    
            set_cached_images(cache_key, artifacts)
            return artifacts
        except Exception as e:
            logger.error(f"Failed to list ECR images: {e}")
            return []

    def get_manifest_size(self, digest: str) -> int:
        return 0 # Size already retrieved during list

    def delete_image(self, session: Session, image_id: str, dry_run: bool = True, force: bool = False) -> dict:
        """Delete image from AWS ECR."""
        success = False
        message = ""
        bytes_freed = 0
        savings_usd = 0.0
        repo_name = ""
        image_identifier = {}
        if image_id.startswith("sha256:"):
            from app.models import ImageArtifact
            image = session.exec(select(ImageArtifact).where(ImageArtifact.digest == image_id)).first()
            if image and image.tags:
                repo_name = image.tags[0].split(':')[0]
                image_identifier = {'imageDigest': image_id}
            else:
                return {"success": False, "message": f"Could not find repository for digest {image_id}"}
        elif ":" in image_id:
            repo_name, tag = image_id.split(':', 1)
            image_identifier = {'imageTag': tag}
        else:
            return {"success": False, "message": f"Invalid image identifier for ECR: {image_id}"}
        if dry_run:
            return {"success": True, "message": f"DRY RUN: Would delete {image_id} from {repo_name}", "dry_run": True}
        try:
            client = self._get_session().client('ecr')
            resp = client.batch_delete_image(repositoryName=repo_name, imageIds=[image_identifier])
            if resp.get('imageIds'):
                success = True
                message = f"Successfully deleted {image_id} from {repo_name}"
            else:
                failure = resp.get('failures', [{}])[0]
                success = False
                message = f"Failed to delete: {failure.get('failureReason', 'Unknown reason')}"
        except Exception as e:
            logger.error(f"ECR deletion failed: {e}")
            message = f"AWS Error: {str(e)}"
            success = False
        return {"success": success, "message": message, "image_id": image_id, "bytes_freed": bytes_freed, "savings_usd": savings_usd, "dry_run": False}

    def list_volumes(self) -> List[VolumeArtifact]:
        return []

    def delete_volume(self, session, name, force=False) -> dict:
        return {"success": False, "message": "Volumes not supported for ECR"}
class GARRegistryClient(BaseRegistryClient):
    """Client for Google Artifact Registry (GAR)"""
    
    def __init__(self, config: RegistryConfig):
        self.config = config
        self.credentials_json = decrypt_secret(config.password) if config.password else None
        self.project_id = config.username

    def _get_client(self):
        if not self.credentials_json:
            raise ValueError("GAR credentials JSON missing")
            
        info = json.loads(self.credentials_json)
        credentials = service_account.Credentials.from_service_account_info(info)
        return artifactregistry_v1.ArtifactRegistryClient(credentials=credentials)

    def test_connection(self) -> dict:
        try:
            client = self._get_client()
            client.list_locations(name=f"projects/{self.project_id}")
            return {"success": True, "message": "Connected to Google Artifact Registry"}
        except Exception as e:
            return {"success": False, "message": f"GAR Connection Failed: {str(e)}"}

    def list_images(self, limit: int = 100, bypass_cache: bool = False) -> List[ImageArtifact]:
        cache_key = f"gar_{self.config.id}"
        if not bypass_cache:
            cached = get_cached_images(cache_key)
            if cached: return cached

        artifacts = []
        try:
            client = self._get_client()
            parent = self.config.endpoint if self.config.endpoint else f"projects/{self.project_id}/locations/us-central1/repositories/default"
            
            packages = client.list_packages(parent=parent)
            for pkg in packages:
                versions = client.list_versions(parent=pkg.name)
                for ver in versions:
                    pkg_name_short = pkg.name.split('/')[-1]
                    tags = [f"{pkg_name_short}:{t}" for t in ver.related_tags]
                    if not tags:
                        tags = [f"{pkg_name_short}:<none>"]
                        
                    digest = ver.name.split('/')[-1]
                    size = 0 
                    created_at = ver.create_time or datetime.utcnow()
                    
                    analysis = BloatAnalyzer.analyze_image(tags, size)
                    
                    artifacts.append(ImageArtifact(
                        tags=tags,
                        size_bytes=size,
                        created_at=created_at,
                        digest=digest,
                        source=self.config.name,
                        bloat_score=analysis['score']
                    ))
                    if len(artifacts) >= limit: break
                if len(artifacts) >= limit: break
                
            set_cached_images(cache_key, artifacts)
            return artifacts
        except Exception as e:
            logger.error(f"GAR list failed: {e}")
            return []

    def get_manifest_size(self, digest: str) -> int:
        return 0

    def delete_image(self, session: Session, image_id: str, dry_run: bool = True, force: bool = False) -> dict:
        if dry_run:
            return {"success": True, "message": "DRY RUN: Would delete GAR image version", "dry_run": True}
        try:
            client = self._get_client()
            client.delete_version(name=image_id)
            return {"success": True, "message": "GAR Version deleted"}
        except Exception as e:
            return {"success": False, "message": f"GAR Delete Failed: {str(e)}"}

    def list_volumes(self) -> List[VolumeArtifact]:
        return []

    def delete_volume(self, session, name, force=False) -> dict:
        return {"success": False, "message": "Volumes not supported for GAR"}


class ACRRegistryClient(BaseRegistryClient):
    """Client for Azure Container Registry (ACR) using Docker V2 API with OAuth2 token exchange.

    Supports ACR admin user credentials (username + password) by exchanging them for
    an ACR access token, then using that token against the standard Docker V2 Registry API.
    This avoids requiring AAD / managed identity and works with the credentials stored in
    RegistryConfig (username = admin username, password = admin password or service-principal
    client-secret).
    """

    def __init__(self, config: RegistryConfig):
        self.config = config
        # Normalize endpoint — strip scheme if present
        endpoint = (config.endpoint or "").strip()
        for prefix in ("https://", "http://"):
            if endpoint.startswith(prefix):
                endpoint = endpoint[len(prefix):]
        self.registry = endpoint.rstrip("/")  # e.g. myregistry.azurecr.io
        self.base_url = f"https://{self.registry}"
        self.username = config.username
        self.password = decrypt_secret(config.password) if config.password else None
        self.session = create_resilient_session()
        self._authenticate()

    def _authenticate(self):
        """Exchange admin credentials for an ACR OAuth2 access token.

        ACR token endpoint accepts admin username/password via grant_type=password and
        returns a short-lived access_token that is used as a Bearer token for V2 API calls.
        Falls back to HTTP Basic auth if the token exchange fails.
        """
        if not self.username or not self.password:
            return

        try:
            resp = requests.post(
                f"{self.base_url}/oauth2/token",
                data={
                    "grant_type": "password",
                    "service": self.registry,
                    "username": self.username,
                    "password": self.password,
                    "scope": "registry:catalog:* repository:*:metadata_read repository:*:delete repository:*:pull",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                access_token = resp.json().get("access_token")
                if access_token:
                    self.session.headers.update({"Authorization": f"Bearer {access_token}"})
                    logger.debug(f"ACR OAuth2 token obtained for {self.registry}")
                    return
            logger.warning(f"ACR token exchange returned {resp.status_code}; falling back to Basic auth")
        except Exception as e:
            logger.warning(f"ACR OAuth2 token exchange failed: {e}; falling back to Basic auth")

        # Basic auth fallback (works for some ACR configurations)
        self.session.auth = (self.username, self.password)

    def test_connection(self) -> dict:
        """Test ACR connection by performing an authenticated GET /v2/ call."""
        try:
            resp = self.session.get(f"{self.base_url}/v2/", timeout=10)
            if resp.status_code == 200:
                return {"success": True, "message": f"Connected to ACR: {self.registry}"}
            if resp.status_code in (401, 403):
                return {
                    "success": False,
                    "message": "ACR Authentication Failed: Check admin credentials or token scopes",
                    "type": "AUTH_ERROR",
                }
            return {
                "success": False,
                "message": f"ACR returned unexpected status {resp.status_code}",
                "type": "NETWORK_ERROR",
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"Network error: {str(e)}", "type": "NETWORK_ERROR"}
        except Exception as e:
            return {"success": False, "message": str(e), "type": "UNKNOWN_ERROR"}

    def _get_repositories(self, limit: int = 100) -> List[str]:
        """List all repositories in the registry with Link-header pagination."""
        repos: List[str] = []
        url = f"{self.base_url}/v2/_catalog"
        while url and len(repos) < limit:
            resp = self.session.get(url, params={"n": min(100, limit - len(repos))}, timeout=10)
            if resp.status_code != 200:
                logger.error(f"ACR catalog listing failed: {resp.status_code} {resp.text[:200]}")
                break
            repos.extend(resp.json().get("repositories") or [])
            # Follow Link header for next page
            link = resp.headers.get("Link", "")
            if 'rel="next"' in link:
                match = re.search(r'<([^>]+)>', link)
                if match:
                    path = match.group(1)
                    url = f"{self.base_url}{path}" if path.startswith("/") else path
                else:
                    break
            else:
                break
        return repos[:limit]

    def _get_tags(self, repo_name: str) -> List[str]:
        """List all tags for a repository with Link-header pagination."""
        tags: List[str] = []
        url = f"{self.base_url}/v2/{repo_name}/tags/list"
        while url:
            resp = self.session.get(url, params={"n": 100}, timeout=10)
            if resp.status_code != 200:
                break
            tags.extend(resp.json().get("tags") or [])
            link = resp.headers.get("Link", "")
            if 'rel="next"' in link:
                match = re.search(r'<([^>]+)>', link)
                if match:
                    path = match.group(1)
                    url = f"{self.base_url}{path}" if path.startswith("/") else path
                else:
                    break
            else:
                break
        return tags

    def _get_manifest_info(self, repo_name: str, tag: str) -> Tuple[str, int, datetime]:
        """Fetch the manifest digest and compressed layer size for a given tag."""
        digest = ""
        size = 0
        created_at = datetime.utcnow()
        try:
            headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
            resp = self.session.get(
                f"{self.base_url}/v2/{repo_name}/manifests/{tag}",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                digest = resp.headers.get("Docker-Content-Digest", "")
                data = resp.json()
                size = data.get("config", {}).get("size", 0) + sum(
                    layer.get("size", 0) for layer in data.get("layers", [])
                )
        except Exception:
            pass
        return digest, size, created_at

    def list_images(self, limit: int = 100, bypass_cache: bool = False) -> List[ImageArtifact]:
        """List all images in ACR with full pagination support."""
        cache_key = f"acr_{self.config.id}_{limit}"
        if not bypass_cache:
            cached = get_cached_images(cache_key)
            if cached:
                return cached

        artifacts: List[ImageArtifact] = []
        try:
            repos = self._get_repositories(limit=limit)
            for repo_name in repos:
                tags = self._get_tags(repo_name)
                if not tags:
                    # Represent untagged manifests with a placeholder
                    artifacts.append(ImageArtifact(
                        tags=[f"{repo_name}:<none>"],
                        size_bytes=0,
                        created_at=datetime.utcnow(),
                        digest="",
                        source=self.config.name,
                        bloat_score=100,
                    ))
                    continue

                for tag in tags:
                    digest, size, created_at = self._get_manifest_info(repo_name, tag)
                    full_tag = f"{repo_name}:{tag}"
                    analysis = BloatAnalyzer.analyze_image([full_tag], size)
                    artifacts.append(ImageArtifact(
                        tags=[full_tag],
                        size_bytes=size,
                        created_at=created_at,
                        digest=digest,
                        source=self.config.name,
                        bloat_score=analysis["score"],
                        bloat_issues=json.dumps(analysis["issues"]) if analysis["issues"] else None,
                    ))
                    if len(artifacts) >= limit:
                        break
                if len(artifacts) >= limit:
                    break

            set_cached_images(cache_key, artifacts)
        except Exception as e:
            logger.error(f"ACR list_images failed: {e}")

        return artifacts

    def get_manifest_size(self, digest: str) -> int:
        return 0  # Size captured during list_images via manifest fetch

    def delete_image(
        self,
        session: Session,
        image_id: str,
        dry_run: bool = True,
        force: bool = False,
    ) -> dict:
        """Delete an ACR image by targeting its manifest digest directly.

        Accepts ``repo@sha256:<digest>`` or ``repo:tag`` as ``image_id``.
        For tag-based IDs the manifest digest is resolved first via a HEAD
        request so the correct, immutable manifest is deleted.
        """
        if dry_run:
            return {
                "success": True,
                "message": f"DRY RUN: Would delete ACR image {image_id}",
                "image_id": image_id,
                "image_tags": [image_id],
                "bytes_freed": 0,
                "savings_usd": 0.0,
                "dry_run": True,
            }

        try:
            # --- Resolve repo + digest ---
            if "@" in image_id:
                # Format: repo@sha256:<digest>
                repo, digest = image_id.split("@", 1)
            elif ":" in image_id:
                repo, tag = image_id.rsplit(":", 1)
                if tag.startswith("sha256:"):
                    digest = tag
                else:
                    # Resolve tag → digest via HEAD request
                    head_resp = self.session.head(
                        f"{self.base_url}/v2/{repo}/manifests/{tag}",
                        headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
                        timeout=10,
                    )
                    if head_resp.status_code != 200:
                        return {
                            "success": False,
                            "message": f"Could not resolve tag '{tag}' to digest: HTTP {head_resp.status_code}",
                        }
                    digest = head_resp.headers.get("Docker-Content-Digest", "")
                    if not digest:
                        return {"success": False, "message": f"Registry returned no digest for tag '{tag}'"}
            else:
                return {"success": False, "message": f"Invalid ACR image identifier: {image_id}"}

            # --- Delete manifest by digest ---
            del_resp = self.session.delete(
                f"{self.base_url}/v2/{repo}/manifests/{digest}",
                timeout=10,
            )
            if del_resp.status_code in (200, 202):
                clear_image_cache(f"acr_{self.config.id}_{100}")
                audit_entry = AuditLog(
                    action="DELETE",
                    image_id=image_id,
                    image_tags=[image_id],
                    source=self.config.name,
                    bytes_freed=0,
                    savings_usd=0.0,
                    dry_run=False,
                )
                session.add(audit_entry)
                return {
                    "success": True,
                    "message": f"Successfully deleted {image_id} from ACR ({self.registry})",
                    "image_id": image_id,
                    "image_tags": [image_id],
                    "bytes_freed": 0,
                    "savings_usd": 0.0,
                    "dry_run": False,
                }
            return {
                "success": False,
                "message": f"ACR deletion failed: HTTP {del_resp.status_code} — {del_resp.text[:200]}",
            }

        except Exception as e:
            logger.error(f"ACR delete_image error: {e}")
            return {"success": False, "message": f"ACR Delete Error: {str(e)}"}

    def list_volumes(self) -> List[VolumeArtifact]:
        return []

    def delete_volume(self, session, name, force=False) -> dict:
        return {"success": False, "message": "Volumes not supported for ACR"}

