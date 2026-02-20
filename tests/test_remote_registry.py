import pytest
from unittest.mock import MagicMock, patch
from app.models import RegistryConfig, RegistryType
from app.core.registry import DockerRegistryClient, ImageArtifact

@pytest.fixture(autouse=True)
def bypass_image_cache():
    """Bypass image cache for all tests to ensure fresh listings"""
    with patch("app.core.registry.get_cached_images", return_value=None):
        yield

@pytest.fixture
def mock_config():
    return RegistryConfig(
        name="Test Hub",
        type=RegistryType.DOCKERHUB,
        endpoint=None,
        username="testuser",
        password="encrypted_secret"
    )

@pytest.fixture
def mock_decrypt():
    with patch("app.core.registry.decrypt_secret", return_value="real_password") as m:
        yield m

@pytest.fixture
def client(mock_config, mock_decrypt):
    with patch("requests.Session") as mock_session:
        # Mock initial auth check
        mock_session.return_value.get.return_value.status_code = 200
        client = DockerRegistryClient(mock_config)
        client.session = mock_session.return_value
        return client

def test_dockerhub_list_images(client):
    # Mock Hub API response
    with patch("requests.Session") as mock_hub_session:
        # Mock Login
        mock_hub_session.return_value.post.return_value.status_code = 200
        mock_hub_session.return_value.post.return_value.json.return_value = {"token": "jwt_token"}
        
        # Mock Repos List
        mock_hub_session.return_value.get.side_effect = [
            # 1. Repos list
            MagicMock(status_code=200, json=lambda: {
                "results": [{"namespace": "testuser", "name": "app"}],
                "next": None
            }),
            # 2. Tags list
            MagicMock(status_code=200, json=lambda: {
                "results": [{
                    "name": "latest",
                    "full_size": 1024,
                    "last_updated": "2023-01-01T12:00:00Z",
                    "images": [{"digest": "sha256:123"}]
                }]
            })
        ]
        
        # Inject the mock session into the method's scope requires patching requests.Session 
        # inside the method or mocking where it's instantiated. 
        # Since we instantiate a NEW session in _list_dockerhub_images, we patch requests.Session
        with patch("requests.Session", return_value=mock_hub_session.return_value):
            images = client.list_images()
            
            assert len(images) == 1
            assert images[0].tags == ["testuser/app:latest"]
            assert images[0].size_bytes == 1024
            assert images[0].source == "Test Hub"

def test_dockerhub_delete_image_success(client):
    # Setup
    image_id = "testuser/app:latest"
    
    with patch("requests.Session") as mock_hub_session:
        # Mock Login
        mock_hub_session.return_value.post.return_value.status_code = 200
        mock_hub_session.return_value.post.return_value.json.return_value = {"token": "jwt_token"}
        
        # Mock Delete
        mock_hub_session.return_value.delete.return_value.status_code = 204
        
        with patch("requests.Session", return_value=mock_hub_session.return_value):
            result = client.delete_image(MagicMock(), image_id, dry_run=False)
            
            assert result["success"] is True
            assert "Successfully deleted" in result["message"]
            
            # Verify Delete URL
            expected_url = "https://hub.docker.com/v2/repositories/testuser/app/tags/latest/"
            mock_hub_session.return_value.delete.assert_called_with(expected_url)

def test_dockerhub_delete_image_dry_run(client):
    image_id = "testuser/app:latest"
    result = client.delete_image(MagicMock(), image_id, dry_run=True)
    
    assert result["success"] is True
    assert result["dry_run"] is True
    assert "DRY RUN" in result["message"]
    # Ensure no network calls were made (requests.Session is patched in fixture but not used here)

def test_ghcr_list_images_fallback(mock_config, mock_decrypt):
    mock_config.type = RegistryType.GHCR
    
    with patch("requests.Session") as mock_session:
        client = DockerRegistryClient(mock_config)
        client.session = mock_session.return_value
        
        # Mock GH API
        # We expect 2 calls:
        # 1. Packages list
        # 2. Versions list
        mock_session.return_value.get.side_effect = [
            # Packages list
            MagicMock(status_code=200, json=lambda: [
                {"name": "my-container", "owner": {"login": "testuser"}}
            ]),
            # Versions list
            MagicMock(status_code=200, json=lambda: [
                {
                    "name": "sha256:abc...",
                    "created_at": "2023-01-01T12:00:00Z",
                    "metadata": {"container": {"tags": ["v1"]}}
                }
            ])
        ]
        
        # We need to patch requests.Session for the internal call in _list_ghcr_images
        with patch("requests.Session", return_value=mock_session.return_value):
            images = client.list_images()
            
            assert len(images) == 1
            assert images[0].tags == ["ghcr.io/testuser/my-container:v1"]
            assert images[0].source == "Test Hub"
