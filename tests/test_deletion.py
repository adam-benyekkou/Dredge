"""Tests for image deletion functionality"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool
from docker.errors import APIError, ImageNotFound

from app.core.registry import LocalDockerClient
from app.models import AuditLog


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


@pytest.fixture(name="mock_docker_client")
def mock_docker_client_fixture():
    """Create a LocalDockerClient with mocked Docker client"""
    with patch('app.core.registry.docker.from_env') as mock_from_env:
        mock_client = MagicMock()
        mock_from_env.return_value = mock_client
        
        # Create the LocalDockerClient (will use mocked docker.from_env)
        local_client = LocalDockerClient()
        
        yield local_client, mock_client


def create_mock_image(
    image_id="sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    tags=None,
    size=150000000
):
    """Helper to create a mock Docker image object"""
    if tags is None:
        tags = ["nginx:latest"]
    
    mock_img = Mock()
    mock_img.id = image_id
    mock_img.tags = tags
    mock_img.short_id = image_id[:19]  # "sha256:1234567890a"
    mock_img.attrs = {"Size": size}
    return mock_img


def test_delete_image_dry_run_success(session: Session, mock_docker_client):
    """Test dry-run deletion creates audit log without removing image"""
    client, mock_client = mock_docker_client
    
    # Setup mock image
    mock_img = create_mock_image()
    mock_client.images.get.return_value = mock_img
    
    # Perform dry-run deletion
    result = client.delete_image(
        session,
        "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        dry_run=True
    )
    
    # Verify result
    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["bytes_freed"] == 150000000
    assert result["image_tags"] == ["nginx:latest"]
    assert "DRY RUN" in result["message"]
    
    # Verify image was NOT actually deleted
    mock_client.images.remove.assert_not_called()
    
    # Verify audit log entry was created
    audit_entries = session.exec(select(AuditLog)).all()
    assert len(audit_entries) == 1
    assert audit_entries[0].dry_run is True
    assert audit_entries[0].bytes_freed == 150000000


def test_delete_image_real_deletion_success(session: Session, mock_docker_client):
    """Test real deletion removes image and creates audit log"""
    client, mock_client = mock_docker_client
    
    # Setup mock image
    mock_img = create_mock_image()
    mock_client.images.get.return_value = mock_img
    mock_client.images.remove.return_value = None  # Successful deletion
    
    # Perform real deletion
    result = client.delete_image(
        session,
        "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        dry_run=False
    )
    
    # Verify result
    assert result["success"] is True
    assert result["dry_run"] is False
    assert result["bytes_freed"] == 150000000
    assert "Successfully deleted" in result["message"]
    
    # Verify image was actually deleted
    mock_client.images.remove.assert_called_once_with(
        "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        force=False
    )
    
    # Verify audit log entry was created
    audit_entries = session.exec(select(AuditLog)).all()
    assert len(audit_entries) == 1
    assert audit_entries[0].dry_run is False
    assert audit_entries[0].bytes_freed == 150000000


def test_delete_image_with_force_flag(session: Session, mock_docker_client):
    """Test deletion with force flag for images with dependents"""
    client, mock_client = mock_docker_client
    
    # Setup mock image
    mock_img = create_mock_image()
    mock_client.images.get.return_value = mock_img
    mock_client.images.remove.return_value = None
    
    # Perform forced deletion
    result = client.delete_image(
        session,
        "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        dry_run=False,
        force=True
    )
    
    # Verify force flag was passed to Docker
    mock_client.images.remove.assert_called_once_with(
        "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        force=True
    )
    assert result["success"] is True


def test_delete_image_not_found(session: Session, mock_docker_client):
    """Test deleting non-existent image returns appropriate result"""
    client, mock_client = mock_docker_client
    
    # Setup mock to raise ImageNotFound
    mock_client.images.get.side_effect = ImageNotFound("Image not found")
    
    # Attempt deletion
    result = client.delete_image(
        session,
        "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        dry_run=False
    )
    
    # Verify result
    assert result["success"] is False
    assert "Image not found" in result["message"]
    assert result["bytes_freed"] == 0
    
    # Verify no audit log was created
    audit_entries = session.exec(select(AuditLog)).all()
    assert len(audit_entries) == 0


def test_delete_image_empty_id_raises_error(session: Session, mock_docker_client):
    """Test empty image_id raises ValueError"""
    client, _ = mock_docker_client
    
    with pytest.raises(ValueError, match="image_id cannot be empty"):
        client.delete_image(session, "", dry_run=True)
    
    with pytest.raises(ValueError, match="image_id cannot be empty"):
        client.delete_image(session, "   ", dry_run=True)


def test_delete_image_invalid_format_raises_error(session: Session, mock_docker_client):
    """Test invalid image_id format raises ValueError"""
    client, _ = mock_docker_client
    
    # Invalid characters
    with pytest.raises(ValueError, match="Invalid image_id format"):
        client.delete_image(session, "invalid@image#id!", dry_run=True)
    
    # Invalid sha256 format
    with pytest.raises(ValueError, match="Invalid image_id format"):
        client.delete_image(session, "sha256:invalid", dry_run=True)


def test_delete_image_conflict_with_dependents(session: Session, mock_docker_client):
    """Test deletion fails gracefully when image has dependent children"""
    client, mock_client = mock_docker_client
    
    # Setup mock image
    mock_img = create_mock_image()
    mock_client.images.get.return_value = mock_img
    
    # Setup mock to raise conflict error
    conflict_error = APIError("conflict: image has dependent child images")
    mock_client.images.remove.side_effect = conflict_error
    
    # Attempt deletion without force
    result = client.delete_image(
        session,
        "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        dry_run=False,
        force=False
    )
    
    # Verify result
    assert result["success"] is False
    assert "dependent children" in result["message"]
    assert "force=True" in result["message"]


def test_delete_image_with_tag_instead_of_digest(session: Session, mock_docker_client):
    """Test deletion using image tag instead of digest"""
    client, mock_client = mock_docker_client
    
    # Setup mock image
    mock_img = create_mock_image(
        image_id="sha256:def456",
        tags=["myapp:v1.0"]
    )
    mock_client.images.get.return_value = mock_img
    mock_client.images.remove.return_value = None
    
    # Delete using tag
    result = client.delete_image(
        session,
        "myapp:v1.0",
        dry_run=False
    )
    
    # Verify deletion used the tag
    mock_client.images.remove.assert_called_once_with("myapp:v1.0", force=False)
    assert result["success"] is True
    assert result["image_tags"] == ["myapp:v1.0"]


def test_delete_image_calculates_cost_savings(session: Session, mock_docker_client):
    """Test that cost savings are calculated correctly"""
    client, mock_client = mock_docker_client
    
    # Setup mock image with 1GB size
    size_1gb = 1024 ** 3  # 1 GB in bytes
    mock_img = create_mock_image(size=size_1gb)
    mock_client.images.get.return_value = mock_img
    
    # Perform dry-run deletion
    result = client.delete_image(
        session,
        "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        dry_run=True
    )
    
    # Verify cost calculation (AWS default: $0.10/GB/month)
    assert result["bytes_freed"] == size_1gb
    assert result["savings_usd"] == pytest.approx(0.10, rel=0.01)
    
    # Verify audit log has same values
    audit_entry = session.exec(select(AuditLog)).first()
    assert audit_entry.bytes_freed == size_1gb
    assert audit_entry.savings_usd == pytest.approx(0.10, rel=0.01)


def test_delete_image_api_error_raises_runtime_error(session: Session, mock_docker_client):
    """Test unexpected API errors are raised as RuntimeError"""
    client, mock_client = mock_docker_client
    
    # Setup mock to raise unexpected API error
    mock_client.images.get.side_effect = APIError("Unexpected API error")
    
    # Verify RuntimeError is raised
    with pytest.raises(RuntimeError, match="Docker API error"):
        client.delete_image(
            session,
            "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            dry_run=True
        )
