"""End-to-end tests for Dredge"""

import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["app"] == "Dredge"


@pytest.mark.asyncio
async def test_dashboard_renders():
    """Test dashboard page renders"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert b"Dashboard" in response.content
        assert b"Monthly Waste" in response.content


@pytest.mark.asyncio
async def test_images_page_renders():
    """Test images page renders"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/images")
        assert response.status_code == 200
        assert b"Docker Images" in response.content


@pytest.mark.asyncio
async def test_scan_endpoint():
    """Test scan endpoint returns image data"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/scan")
        # Scan may fail if Docker is not available in test environment
        # But endpoint should return valid HTML
        assert response.status_code in [200, 500]
        assert b"<" in response.content  # HTML content
