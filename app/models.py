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
    status: ImageStatus = Field(default=ImageStatus.ACTIVE)
    expires_at: Optional[datetime] = Field(default=None)


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


class AuditLog(SQLModel, table=True):
    """Audit log for image deletion operations.
    
    Tracks all deletion operations for compliance and cost analysis.
    
    Attributes:
        id: Primary key identifier
        image_id: Digest of the deleted image
        image_tags: Snapshot of image tags at deletion time
        bytes_freed: Storage space freed by deletion (in bytes)
        savings_usd: Monthly cost savings from deletion
        timestamp: When the deletion occurred
        dry_run: Whether this was a dry-run operation (no actual deletion)
    """
    
    id: Optional[int] = Field(default=None, primary_key=True)
    image_id: str = Field(max_length=255, index=True)
    image_tags: List[str] = Field(default=[], sa_column=Column(SAJSON))
    bytes_freed: int = Field(default=0)
    savings_usd: float = Field(default=0.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    dry_run: bool = Field(default=False)
