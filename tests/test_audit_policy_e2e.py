import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta
from sqlmodel import Session, select

from app.main import app
from app.core.db import engine, init_db
from app.models import AuditLog, CleanupPolicy, ImageStatus, AppSettings
from app.core.auth_jwt import get_current_user

# Initialize DB
init_db()

# Override dependency to skip authentication
async def mocked_get_current_user():
    return "admin"

app.dependency_overrides[get_current_user] = mocked_get_current_user

@pytest.fixture(name="session")
def session_fixture():
    with Session(engine) as session:
        yield session

@pytest.mark.asyncio
async def test_audit_log_pagination(session: Session):
    """Test that audit log pagination works correctly"""
    # Clear existing logs
    session.exec(AuditLog.__table__.delete())
    session.commit()
    
    # Create 60 logs
    for i in range(60):
        log = AuditLog(
            action="DELETE",
            image_id=f"sha256:{i}",
            image_tags=[f"test:{i}"],
            source="Local",
            bytes_freed=1000,
            savings_usd=0.1,
            timestamp=datetime.utcnow() - timedelta(minutes=i)
        )
        session.add(log)
    session.commit()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Test Page 1
        response = await client.get("/logs?page=1&limit=25")
        assert response.status_code == 200
        assert b"Page 1 of 3" in response.content
        assert b"test:0" in response.content
        
        # Test Page 2
        response = await client.get("/logs?page=2&limit=25")
        assert response.status_code == 200
        assert b"Page 2 of 3" in response.content
        assert b"test:25" in response.content

@pytest.mark.asyncio
async def test_audit_log_filters(session: Session):
    """Test that audit log filtering works correctly"""
    # Clear existing logs
    session.exec(AuditLog.__table__.delete())
    session.commit()
    
    # Create logs with different actions and sources
    session.add(AuditLog(action="QUARANTINE", image_id="q1", source="Local", timestamp=datetime.utcnow()))
    session.add(AuditLog(action="DELETE", image_id="d1", source="Docker Hub", timestamp=datetime.utcnow()))
    session.commit()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Filter by Action
        response = await client.get("/logs?action_filter=QUARANTINE")
        assert response.status_code == 200
        assert b"QUARANTINE" in response.content
        assert b"q1" in response.content
        assert b"d1" not in response.content  # The image ID for DELETE log should be hidden
        
        # Filter by Source
        response = await client.get("/logs?source_filter=Docker Hub")
        assert response.status_code == 200
        assert b"Docker Hub" in response.content
        assert b"d1" in response.content
        assert b"q1" not in response.content # The image ID for Local log should be hidden

@pytest.mark.asyncio
async def test_policy_scheduling_update(session: Session):
    """Test that updating policy schedule updates the database and scheduler"""
    # Ensure a policy exists
    policy = session.exec(select(CleanupPolicy)).first()
    if not policy:
        policy = CleanupPolicy(name="Test Policy", enabled=True)
        session.add(policy)
        session.commit()
        session.refresh(policy)
    
    # Mock scheduler
    with patch("app.web.routes.schedule_policy") as mock_schedule:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            form_data = {
                "keep_count": "5",
                "max_age_days": "60",
                "regex_whitelist": "test-.*",
                "enabled": "on",
                "schedule_enabled": "on",
                "schedule_cron": "0 0 * * *"
            }
            response = await client.post("/policies", data=form_data)
            assert response.status_code == 200
            
            # Verify DB update
            session.refresh(policy)
            assert policy.schedule_enabled is True
            assert policy.schedule_cron == "0 0 * * *"
            
            # Verify scheduler call
            mock_schedule.assert_called_once()

@pytest.mark.asyncio
async def test_audit_log_export(session: Session):
    """Test audit log CSV export"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/logs/export")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert b"Timestamp,Action,Source" in response.content
