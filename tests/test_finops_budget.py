import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta
from sqlmodel import Session, select

from app.main import app
from app.core.db import engine, init_db
from app.models import AppSettings
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
async def test_update_budget_settings(session: Session):
    """Test updating monthly budget in settings"""
    # Create default settings if not exists
    if not session.get(AppSettings, 1):
        session.add(AppSettings(id=1))
        session.commit()
        
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        form_data = {
            "section": "finops",
            "provider_name": "Custom",
            "custom_price_per_gb": "0.15",
            "currency_symbol": "$",
            "monthly_budget": "50.00"
        }
        response = await client.post("/settings", data=form_data)
        assert response.status_code == 200
        
        # Verify DB
        session.expire_all()
        settings = session.get(AppSettings, 1)
        assert settings.monthly_budget == 50.0
        assert settings.custom_price_per_gb == 0.15

@pytest.mark.asyncio
async def test_budget_logic(session: Session):
    """Test budget alert logic (direct function call)"""
    from app.core.finops import check_budget
    
    # Setup settings
    settings = session.get(AppSettings, 1)
    if not settings:
        settings = AppSettings(id=1)
        session.add(settings)
    
    settings.monthly_budget = 10.0 # Low budget
    settings.last_budget_alert_at = None
    settings.custom_price_per_gb = 1.0 # High price
    session.add(settings)
    session.commit()
    
    # Mock Registry Client to return high usage
    with patch("app.core.registry.RegistryClientFactory.get_client") as mock_get_client:
        mock_client = MagicMock()
        # 20 GB * $1.0 = $20 > $10 budget
        mock_image = MagicMock()
        mock_image.size_bytes = 20 * (1024**3) 
        mock_image.source = "Local"
        mock_client.list_images.return_value = [mock_image]
        mock_client.list_volumes.return_value = []
        mock_get_client.return_value = mock_client
        
        # Mock Notification
        with patch("app.core.notify.send_notification") as mock_notify:
            await check_budget(session)
            
            # Should trigger notification
            mock_notify.assert_called_once()
            args = mock_notify.call_args[1]
            assert "Budget Exceeded" in args['title']
            
            # Check timestamp updated
            session.refresh(settings)
            assert settings.last_budget_alert_at is not None
            assert settings.last_budget_alert_at.date() == datetime.utcnow().date()
            
            # Run again - should NOT trigger (already sent today)
            mock_notify.reset_mock()
            await check_budget(session)
            mock_notify.assert_not_called()
