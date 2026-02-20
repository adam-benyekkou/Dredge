"""End-to-end tests for Dredge"""

import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import init_db

# Initialize database for tests
init_db()


@pytest.fixture(name="client")
async def client_fixture():
    """Authenticated client for tests"""
    # Create an access token for a test user
    from app.core.auth_jwt import create_access_token
    from datetime import timedelta
    access_token = create_access_token(data={"sub": "admin"}, expires_delta=timedelta(minutes=15))
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Set the access token cookie
        client.cookies.set("access_token", f"Bearer {access_token}")
        yield client


@pytest.mark.asyncio
async def test_health_check(client):
    """Test health check endpoint"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "Dredge"


@pytest.mark.asyncio
async def test_images_api_list(client):
    """Test images API list endpoint"""
    response = await client.get("/api/v1/images/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # The first image might be different depending on environment
    assert ":" in data[0]["tags"][0]


@pytest.mark.asyncio
async def test_policies_page_renders(client):
    """Test policies page renders"""
    response = await client.get("/policies")
    assert response.status_code == 200
    assert b"Policies" in response.content


@pytest.mark.asyncio
async def test_logs_page_renders(client):
    """Test logs page renders"""
    response = await client.get("/logs")
    assert response.status_code == 200
    assert b"Audit Logs" in response.content


@pytest.mark.asyncio
async def test_purge_image_endpoint(client):
    """Test purge image endpoint"""
    digest = "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
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
async def test_scan_endpoint(client):
    """Test scan endpoint returns image data"""
    # Update path to modular API
    response = await client.post("/api/v1/images/scan")
    # New modular endpoint returns JSON
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
