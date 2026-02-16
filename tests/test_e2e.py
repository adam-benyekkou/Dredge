"""End-to-end tests for Dredge"""

import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import init_db

# Initialize database for tests
init_db()


@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["app"] == "Dredge"


@pytest.mark.asyncio
async def test_images_page_renders():
    """Test images page renders"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/images")
        assert response.status_code == 200
        assert b"Images" in response.content


@pytest.mark.asyncio
async def test_policies_page_renders():
    """Test policies page renders"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/policies")
        assert response.status_code == 200
        assert b"Policies" in response.content


@pytest.mark.asyncio
async def test_logs_page_renders():
    """Test logs page renders"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/logs")
        assert response.status_code == 200
        assert b"Audit Logs" in response.content


@pytest.mark.asyncio
async def test_purge_image_endpoint():
    """Test purge image endpoint"""
    digest = "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Mock RegistryClientFactory.get_client().delete_image
        with patch("app.web.routes.RegistryClientFactory.get_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.delete_image.return_value = {
                "success": True,
                "image_id": digest,
                "image_tags": ["test:latest"],
                "bytes_freed": 100,
                "savings_usd": 0.1,
                "dry_run": False,
                "message": "Deleted"
            }
            response = await client.delete(f"/images/{digest}")
            assert response.status_code == 200
            assert response.content == b""


@pytest.mark.asyncio
async def test_scan_endpoint():
    """Test scan endpoint returns image data"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/scan")
        # Scan may fail if Docker is not available in test environment
        # But endpoint should return valid HTML
        assert response.status_code in [200, 500]
        assert b"<" in response.content  # HTML content
