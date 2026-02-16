"""Image cleanup and quarantine service"""

from datetime import datetime, timedelta
from typing import Optional
from sqlmodel import Session, select
import logging

from app.models import ImageArtifact, ImageStatus

logger = logging.getLogger(__name__)


def mark_for_deletion(
    session: Session,
    image_digest: str,
    quarantine_hours: int = 24
) -> Optional[ImageArtifact]:
    """Mark an image for deletion with quarantine period.
    
    Implements soft-delete by setting image status to QUARANTINED and scheduling
    deletion after the quarantine period. This provides a grace period to prevent
    accidental deletions.
    
    Args:
        session: Database session for transaction management
        image_digest: SHA256 digest of the image to quarantine
        quarantine_hours: Hours until permanent deletion (default: 24)
    
    Returns:
        Updated ImageArtifact if found and quarantined, None if not found
    
    Raises:
        ValueError: If image_digest is empty or quarantine_hours is negative
        
    Example:
        >>> from sqlmodel import Session, create_engine
        >>> engine = create_engine("sqlite:///dredge.db")
        >>> with Session(engine) as session:
        ...     image = mark_for_deletion(
        ...         session,
        ...         "sha256:abc123...",
        ...         quarantine_hours=24
        ...     )
        ...     session.commit()
    """
    # Input validation
    if not image_digest or not image_digest.strip():
        raise ValueError("image_digest cannot be empty")
    
    if quarantine_hours < 0:
        raise ValueError("quarantine_hours must be non-negative")
    
    # Find the image
    statement = select(ImageArtifact).where(ImageArtifact.digest == image_digest)
    image = session.exec(statement).first()
    
    if not image:
        logger.warning(f"Image not found for quarantine: {image_digest}")
        return None
    
    # Skip if already quarantined or deleted
    if image.status in [ImageStatus.QUARANTINED, ImageStatus.DELETED]:
        logger.info(f"Image already {image.status.value}: {image_digest}")
        return image
    
    # Update status to quarantined
    image.status = ImageStatus.QUARANTINED
    image.expires_at = datetime.utcnow() + timedelta(hours=quarantine_hours)
    
    session.add(image)
    
    logger.info(
        f"Image quarantined: {image_digest} | "
        f"Expires at: {image.expires_at.isoformat()} | "
        f"Size: {image.size_bytes / (1024**3):.2f} GB"
    )
    
    return image


def get_expired_images(session: Session) -> list[ImageArtifact]:
    """Get all quarantined images past their expiration time.
    
    Queries for images in QUARANTINED status where expires_at is in the past.
    These images are ready for permanent deletion.
    
    Args:
        session: Database session
    
    Returns:
        List of expired ImageArtifact objects ready for deletion
        
    Example:
        >>> from sqlmodel import Session, create_engine
        >>> engine = create_engine("sqlite:///dredge.db")
        >>> with Session(engine) as session:
        ...     expired = get_expired_images(session)
        ...     for img in expired:
        ...         print(f"Ready to delete: {img.digest}")
    """
    now = datetime.utcnow()
    statement = (
        select(ImageArtifact)
        .where(ImageArtifact.status == ImageStatus.QUARANTINED)
        .where(ImageArtifact.expires_at <= now)
    )
    
    images = session.exec(statement).all()
    
    logger.info(f"Found {len(images)} expired images ready for deletion")
    
    return list(images)


def restore_from_quarantine(
    session: Session,
    image_digest: str
) -> Optional[ImageArtifact]:
    """Restore a quarantined image back to ACTIVE status.
    
    Removes quarantine status and clears expiration time. Allows recovery
    of accidentally quarantined images before permanent deletion.
    
    Args:
        session: Database session for transaction management
        image_digest: SHA256 digest of the image to restore
    
    Returns:
        Updated ImageArtifact if found and restored, None if not found
    
    Raises:
        ValueError: If image_digest is empty
        
    Example:
        >>> from sqlmodel import Session, create_engine
        >>> engine = create_engine("sqlite:///dredge.db")
        >>> with Session(engine) as session:
        ...     image = restore_from_quarantine(session, "sha256:abc123...")
        ...     session.commit()
    """
    if not image_digest or not image_digest.strip():
        raise ValueError("image_digest cannot be empty")
    
    statement = select(ImageArtifact).where(ImageArtifact.digest == image_digest)
    image = session.exec(statement).first()
    
    if not image:
        logger.warning(f"Image not found for restoration: {image_digest}")
        return None
    
    if image.status != ImageStatus.QUARANTINED:
        logger.info(f"Image not quarantined, cannot restore: {image_digest}")
        return image
    
    # Restore to active status
    image.status = ImageStatus.ACTIVE
    image.expires_at = None
    
    session.add(image)
    
    logger.info(f"Image restored from quarantine: {image_digest}")
    
    return image
