"""Domain models for Dredge"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON as SAJSON


class ImageStatus(str, Enum):
    """Image lifecycle status.
    
    Attributes:
        ACTIVE: Image is active and in use
        QUARANTINED: Image marked for deletion with 24h grace period
        DELETED: Image has been permanently deleted
    """
    
    ACTIVE = "ACTIVE"
    QUARANTINED = "QUARANTINED"
    DELETED = "DELETED"


class RegistryType(str, Enum):
    """Supported registry providers."""
    DOCKERHUB = "DOCKERHUB"
    GHCR = "GHCR"
    ECR = "ECR"
    ACR = "ACR"
    GCR = "GCR"
    GAR = "GAR"
    CUSTOM = "CUSTOM"


class VolumeStatus(str, Enum):
    """Volume lifecycle status.
    
    Attributes:
        ACTIVE: Volume is in use by a container
        DANGLING: Volume is not used by any container
        DELETED: Volume has been removed
    """
    
    ACTIVE = "ACTIVE"
    DANGLING = "DANGLING"
    DELETED = "DELETED"


class ImageArtifact(SQLModel, table=True):
    """Docker image artifact model.
    
    Represents a Docker image with metadata for tracking lifecycle and costs.
    
    Attributes:
        id: Primary key identifier
        tags: List of image tags (e.g., ['nginx:latest', 'nginx:1.21'])
        size_bytes: Image size in bytes
        created_at: Timestamp when image was created
        digest: SHA256 digest of the image
        status: Current lifecycle status (ACTIVE/QUARANTINED/DELETED)
        expires_at: Timestamp when quarantined image will be deleted (None if not quarantined)
    """
    
    id: Optional[int] = Field(default=None, primary_key=True)
    tags: List[str] = Field(default=[], sa_column=Column(SAJSON))
    size_bytes: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    digest: str = Field(default="", max_length=255)
    source: str = Field(default="Local", max_length=255)
    status: ImageStatus = Field(default=ImageStatus.ACTIVE)
    expires_at: Optional[datetime] = Field(default=None)
    bloat_score: int = Field(default=100) # 0-100 (100 = Optimized)
    bloat_issues: Optional[str] = Field(default=None) # JSON list of issues
    
    @property
    def issues_list(self):
        """Parse bloat issues from JSON string"""
        if self.bloat_issues:
            try:
                import json
                return json.loads(self.bloat_issues)
            except:
                return [self.bloat_issues]
        return []


class VolumeArtifact(SQLModel, table=True):
    """Docker volume artifact model.
    
    Represents a Docker volume with metadata for tracking usage and costs.
    
    Attributes:
        id: Primary key identifier
        name: Unique name of the volume
        driver: Volume driver (e.g., 'local')
        size_bytes: Estimated volume size in bytes
        created_at: Timestamp when volume was created
        status: Current status (ACTIVE/DANGLING/DELETED)
        labels: Dictionary of labels associated with the volume
    """
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=255, index=True)
    driver: str = Field(max_length=100)
    size_bytes: int = Field(default=0)
    source: str = Field(default="Local", max_length=255)
    created_at: Optional[datetime] = Field(default=None)
    status: VolumeStatus = Field(default=VolumeStatus.ACTIVE)
    labels: List[str] = Field(default=[], sa_column=Column(SAJSON))


class CleanupPolicy(SQLModel, table=True):
    """Cleanup policy for automated image lifecycle management.
    
    Defines rules for automatically quarantining images based on age, count, or patterns.
    
    Attributes:
        id: Primary key identifier
        name: Human-readable policy name
        keep_count: Minimum number of images to keep (most recent)
        max_age_days: Maximum age in days before image is quarantined
        regex_whitelist: Regex pattern for tags to exclude from cleanup (e.g., '^prod-.*')
        enabled: Whether policy is currently active
        created_at: Timestamp when policy was created
    """
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=255)
    keep_count: int = Field(default=3, ge=0)
    max_age_days: int = Field(default=30, ge=0)
    regex_whitelist: str = Field(default="", max_length=500)
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Scheduling fields
    schedule_enabled: bool = Field(default=False)  # Whether to run on schedule
    schedule_cron: Optional[str] = Field(default=None, max_length=100)  # Cron expression
    next_run: Optional[datetime] = Field(default=None)  # Next scheduled run time
    last_run: Optional[datetime] = Field(default=None)  # Last execution time
    run_count: int = Field(default=0)  # Total number of executions


class AuditLog(SQLModel, table=True):
    """Audit log for image lifecycle operations.
    
    Tracks all image operations (quarantine, unquarantine, purge, delete) for compliance and cost analysis.
    
    Attributes:
        id: Primary key identifier
        action: Operation performed (QUARANTINE, UNQUARANTINE, PURGE, DELETE)
        image_id: Digest of the image
        image_tags: Snapshot of image tags at operation time
        source: Registry source (Local, Docker Hub, GHCR, etc.)
        bytes_freed: Storage space freed by deletion/purge (in bytes)
        savings_usd: Monthly cost savings from deletion/purge
        timestamp: When the operation occurred
        dry_run: Whether this was a dry-run operation (no actual deletion)
    """
    
    id: Optional[int] = Field(default=None, primary_key=True)
    action: str = Field(max_length=50, index=True)  # QUARANTINE, UNQUARANTINE, PURGE, DELETE
    image_id: str = Field(max_length=255, index=True)
    image_tags: List[str] = Field(default=[], sa_column=Column(SAJSON))
    source: str = Field(default="Local", max_length=255)
    bytes_freed: int = Field(default=0)
    savings_usd: float = Field(default=0.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    dry_run: bool = Field(default=False)


class RegistryConfig(SQLModel, table=True):
    """Configuration for remote Docker registries.
    
    Stores credentials and endpoints for scanning remote registries.
    
    Attributes:
        id: Primary key identifier
        name: Human-readable name (e.g., 'Docker Hub Prod')
        type: Registry provider type (DOCKERHUB, ECR, etc.)
        endpoint: Registry URL/endpoint
        username: Authentication username
        password: Authentication password/token (plain text for MVP, consider encryption)
        is_active: Whether this registry is enabled for scanning
        created_at: Creation timestamp
    """
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=255)
    type: RegistryType = Field(default=RegistryType.DOCKERHUB)
    endpoint: str = Field(default="", max_length=500)
    username: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=1000)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


from passlib.context import CryptContext

# Use PBKDF2-SHA256 which is secure and avoids the bcrypt compatibility bug
# that causes "password cannot be longer than 72 bytes" even with short passwords
# in some passlib/bcrypt version combinations.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

class AppSettings(SQLModel, table=True):
    """Global application settings for FinOps and UI.
    
    Singleton row to store user preferences.
    """
    
    id: int = Field(default=1, primary_key=True)
    admin_username: str = Field(default="admin", max_length=100)
    admin_password: str = Field(default="admin", max_length=255) # Hashed password
    provider_name: str = Field(default="AWS", max_length=100)
    custom_price_per_gb: float = Field(default=0.10) # Local / ECR / Default
    dockerhub_price_per_gb: float = Field(default=0.00) # Docker Hub (fair use, no per-GB charge)
    ghcr_price_per_gb: float = Field(default=0.25) # GitHub Packages storage
    github_hrc_price_per_gb: float = Field(default=0.07) # GitHub Actions Cache
    currency_symbol: str = Field(default="$", max_length=5)
    monthly_budget: float = Field(default=0.00) # Monthly budget goal (0 = disabled)
    last_budget_alert_at: Optional[datetime] = Field(default=None) # Timestamp of last budget alert
    notification_urls: Optional[str] = Field(default=None, max_length=1000)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MetricSnapshot(SQLModel, table=True):
    """Daily snapshot of infrastructure metrics for trend analysis.
    
    Captured daily to visualize cost and usage trends over time.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    date: datetime = Field(default_factory=datetime.utcnow, index=True)
    total_images: int = Field(default=0)
    total_volumes: int = Field(default=0)
    total_gb: float = Field(default=0.0)
    total_cost_usd: float = Field(default=0.0)
    efficiency_score: int = Field(default=0)
