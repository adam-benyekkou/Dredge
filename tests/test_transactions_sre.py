import pytest
from unittest.mock import MagicMock, patch
from fastapi import Response
from sqlmodel import Session
from app.web.routes import purge_image
from app.models import ImageArtifact

@pytest.mark.asyncio
async def test_purge_image_transactional_rollback():
    """
    Verify that purge_image rolls back the session if an error occurs.
    """
    mock_session = MagicMock(spec=Session)
    mock_response = MagicMock(spec=Response)
    digest = "sha256:123"
    
    # Mock image lookup
    mock_image = ImageArtifact(digest=digest, size_bytes=100, source="Local")
    mock_session.exec.return_value.first.return_value = mock_image
    
    # Mock registry client to succeed
    mock_client = MagicMock()
    mock_client.delete_image.return_value = {"success": True}
    
    # Mock commit to FAIL
    mock_session.commit.side_effect = Exception("DB Error")
    
    with patch("app.core.registry.RegistryClientFactory.get_client", return_value=mock_client):
        response = await purge_image(digest, mock_response, mock_session)
        
        # Verify rollback was called
        mock_session.rollback.assert_called_once()
        # Verify error response
        assert response.status_code == 500
        assert b"Purge failed" in response.body

@pytest.mark.asyncio
async def test_purge_image_registry_failure_no_db_delete():
    """
    Verify that if registry deletion fails, the image is NOT deleted from DB.
    """
    mock_session = MagicMock(spec=Session)
    mock_response = MagicMock(spec=Response)
    digest = "sha256:123"
    
    mock_image = ImageArtifact(digest=digest, size_bytes=100, source="Local")
    mock_session.exec.return_value.first.return_value = mock_image
    
    # Mock registry client to FAIL
    mock_client = MagicMock()
    mock_client.delete_image.return_value = {"success": False, "message": "API Error"}
    
    with patch("app.core.registry.RegistryClientFactory.get_client", return_value=mock_client):
        await purge_image(digest, mock_response, mock_session)
        
        # session.delete(image) should NOT have been called
        # Wait, I need to check if delete was called
        assert not any(call[0][0] == mock_image for call in mock_session.delete.call_args_list)
        # Verify rollback (to clear client-added audit logs)
        mock_session.rollback.assert_called_once()
