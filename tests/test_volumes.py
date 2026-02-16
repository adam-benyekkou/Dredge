"""Tests for volume management functionality"""

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import VolumeStatus


@pytest.mark.asyncio
async def test_volumes_page_renders():
    """Test volumes page renders with volume data"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # We need to mock the instance creation or the method on the class
        from app.models import VolumeArtifact
        real_vol = VolumeArtifact(
            name="test-vol-123",
            driver="local",
            size_bytes=1048576,
            status=VolumeStatus.DANGLING
        )
        with patch("app.web.routes.LocalDockerClient.list_volumes", return_value=[real_vol]):
            response = await client.get("/volumes")
            assert response.status_code == 200
            assert b"Volumes" in response.content
            assert b"test-vol-123" in response.content


@pytest.mark.asyncio
async def test_delete_volume_endpoint():
    """Test volume deletion endpoint"""
    vol_name = "test-vol-to-delete"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.web.routes.LocalDockerClient.delete_volume") as mock_delete:
            mock_delete.return_value = {
                "success": True,
                "name": vol_name,
                "bytes_freed": 1024,
                "savings_usd": 0.01,
                "message": "Deleted"
            }
            response = await client.delete(f"/volumes/{vol_name}")
            assert response.status_code == 200
            assert response.content == b""
            mock_delete.assert_called_once()
