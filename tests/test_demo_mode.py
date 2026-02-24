import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_demo_no_login():
    """Verify that the login page redirects to dashboard in demo mode"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/auth/login")
        assert response.status_code == 302
        assert response.headers["location"] == "/"

@pytest.mark.asyncio
async def test_demo_scan_mocked():
    """Verify that scanning returns the demo mode message"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/scan")
        assert response.status_code == 200
        # Check HX-Trigger header for the toast message
        assert "Scan complete (Demo Mode)" in response.headers["HX-Trigger"]

@pytest.mark.asyncio
async def test_demo_destructive_action_mocked():
    """Verify that a destructive action returns the demo mode simulation message"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Try to delete a volume
        response = await client.delete("/volumes/some-volume")
        assert response.status_code == 200
        assert "Action simulated in Demo Mode" in response.headers["HX-Trigger"]

@pytest.mark.asyncio
async def test_demo_settings_mocked():
    """Verify that settings updates are simulated"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        form_data = {"section": "finops", "provider_name": "AWS"}
        response = await client.post("/settings", data=form_data)
        assert response.status_code == 200
        assert "Action simulated in Demo Mode" in response.headers["HX-Trigger"]
