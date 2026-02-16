"""Tests for registry management"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import init_db
from app.models import RegistryConfig, RegistryType
from sqlmodel import Session, select
from app.core.db import get_session

# Initialize database for tests
init_db()

@pytest.mark.asyncio
async def test_registries_page_renders():
    """Test registries page renders"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/registries")
        assert response.status_code == 200
        assert b"Registry Management" in response.content

@pytest.mark.asyncio
async def test_add_registry_endpoint():
    """Test adding a registry"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "name": "Test Registry",
            "type": "DOCKERHUB",
            "endpoint": "https://hub.docker.com",
            "username": "testuser",
            "password": "testpassword"
        }
        response = await client.post("/registries", data=payload)
        assert response.status_code == 200
        assert b"Test Registry" in response.content
        assert b"DOCKERHUB" in response.content

@pytest.mark.asyncio
async def test_delete_registry_endpoint():
    """Test deleting a registry"""
    # First add a registry to delete
    from app.core.db import engine
    with Session(engine) as session:
        reg = RegistryConfig(
            name="Delete Me",
            type=RegistryType.CUSTOM,
            endpoint="https://delete.me"
        )
        session.add(reg)
        session.commit()
        session.refresh(reg)
        reg_id = reg.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Check it's there
        response = await client.get("/registries")
        assert b"Delete Me" in response.content

        # Delete it
        response = await client.delete(f"/registries/{reg_id}")
        assert response.status_code == 200
        assert response.content == b""

        # Check it's gone
        response = await client.get("/registries")
        assert b"Delete Me" not in response.content
