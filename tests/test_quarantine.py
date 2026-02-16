"""Tests for quarantine and cleanup functionality"""

import pytest
from datetime import datetime, timedelta
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.models import ImageArtifact, ImageStatus
from app.services.cleaner import (
    mark_for_deletion,
    get_expired_images,
    restore_from_quarantine
)


@pytest.fixture(name="session")
def session_fixture():
    """Create in-memory SQLite session for testing"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="sample_image")
def sample_image_fixture(session: Session):
    """Create a sample image for testing"""
    image = ImageArtifact(
        tags=["nginx:latest"],
        size_bytes=150000000,  # 150 MB
        digest="sha256:abc123def456",
        status=ImageStatus.ACTIVE
    )
    session.add(image)
    session.commit()
    session.refresh(image)
    return image


def test_mark_for_deletion_success(session: Session, sample_image: ImageArtifact):
    """Test successfully quarantining an image"""
    result = mark_for_deletion(session, sample_image.digest, quarantine_hours=24)
    session.commit()
    session.refresh(result)
    
    assert result is not None
    assert result.status == ImageStatus.QUARANTINED
    assert result.expires_at is not None
    
    # Check expiration is approximately 24 hours from now
    expected_expiry = datetime.utcnow() + timedelta(hours=24)
    time_diff = abs((result.expires_at - expected_expiry).total_seconds())
    assert time_diff < 10  # Within 10 seconds


def test_mark_for_deletion_not_found(session: Session):
    """Test quarantining non-existent image returns None"""
    result = mark_for_deletion(session, "sha256:nonexistent", quarantine_hours=24)
    
    assert result is None


def test_mark_for_deletion_empty_digest(session: Session):
    """Test empty digest raises ValueError"""
    with pytest.raises(ValueError, match="image_digest cannot be empty"):
        mark_for_deletion(session, "", quarantine_hours=24)
    
    with pytest.raises(ValueError, match="image_digest cannot be empty"):
        mark_for_deletion(session, "   ", quarantine_hours=24)


def test_mark_for_deletion_negative_hours(session: Session, sample_image: ImageArtifact):
    """Test negative quarantine hours raises ValueError"""
    with pytest.raises(ValueError, match="quarantine_hours must be non-negative"):
        mark_for_deletion(session, sample_image.digest, quarantine_hours=-1)


def test_mark_for_deletion_already_quarantined(session: Session, sample_image: ImageArtifact):
    """Test quarantining already quarantined image is idempotent"""
    # First quarantine
    result1 = mark_for_deletion(session, sample_image.digest, quarantine_hours=24)
    session.commit()
    first_expiry = result1.expires_at
    
    # Second quarantine - should not change expiry time
    result2 = mark_for_deletion(session, sample_image.digest, quarantine_hours=48)
    session.commit()
    
    assert result2.expires_at == first_expiry


def test_get_expired_images_empty(session: Session):
    """Test get_expired_images with no expired images"""
    result = get_expired_images(session)
    
    assert result == []


def test_get_expired_images_with_expired(session: Session):
    """Test get_expired_images finds expired images"""
    # Create expired image
    expired_image = ImageArtifact(
        tags=["old:latest"],
        size_bytes=100000000,
        digest="sha256:expired123",
        status=ImageStatus.QUARANTINED,
        expires_at=datetime.utcnow() - timedelta(hours=1)  # Expired 1 hour ago
    )
    
    # Create non-expired image
    active_image = ImageArtifact(
        tags=["new:latest"],
        size_bytes=200000000,
        digest="sha256:active456",
        status=ImageStatus.ACTIVE
    )
    
    # Create quarantined but not expired
    quarantined_image = ImageArtifact(
        tags=["pending:latest"],
        size_bytes=150000000,
        digest="sha256:pending789",
        status=ImageStatus.QUARANTINED,
        expires_at=datetime.utcnow() + timedelta(hours=12)  # Expires in 12 hours
    )
    
    session.add(expired_image)
    session.add(active_image)
    session.add(quarantined_image)
    session.commit()
    
    result = get_expired_images(session)
    
    assert len(result) == 1
    assert result[0].digest == "sha256:expired123"


def test_restore_from_quarantine_success(session: Session, sample_image: ImageArtifact):
    """Test successfully restoring a quarantined image"""
    # First quarantine the image
    mark_for_deletion(session, sample_image.digest, quarantine_hours=24)
    session.commit()
    session.refresh(sample_image)
    
    assert sample_image.status == ImageStatus.QUARANTINED
    
    # Now restore it
    result = restore_from_quarantine(session, sample_image.digest)
    session.commit()
    session.refresh(result)
    
    assert result is not None
    assert result.status == ImageStatus.ACTIVE
    assert result.expires_at is None


def test_restore_from_quarantine_not_found(session: Session):
    """Test restoring non-existent image returns None"""
    result = restore_from_quarantine(session, "sha256:nonexistent")
    
    assert result is None


def test_restore_from_quarantine_empty_digest(session: Session):
    """Test empty digest raises ValueError"""
    with pytest.raises(ValueError, match="image_digest cannot be empty"):
        restore_from_quarantine(session, "")
    
    with pytest.raises(ValueError, match="image_digest cannot be empty"):
        restore_from_quarantine(session, "   ")


def test_restore_from_quarantine_not_quarantined(session: Session, sample_image: ImageArtifact):
    """Test restoring active image does nothing"""
    assert sample_image.status == ImageStatus.ACTIVE
    
    result = restore_from_quarantine(session, sample_image.digest)
    session.commit()
    session.refresh(result)
    
    assert result.status == ImageStatus.ACTIVE
    assert result.expires_at is None
