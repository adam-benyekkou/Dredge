"""Mock tests for Azure Container Registry (ACR) client — Tasks 1.5 & 1.6."""

import pytest
from unittest.mock import MagicMock, patch
from app.models import RegistryConfig, RegistryType
from app.core.registry import ACRRegistryClient, ImageArtifact


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def acr_config():
    return RegistryConfig(
        name="My ACR",
        type=RegistryType.ACR,
        endpoint="myregistry.azurecr.io",
        username="admin",
        password="encrypted_password",
    )


@pytest.fixture
def mock_session():
    """Fake requests.Session returned by create_resilient_session."""
    return MagicMock()


@pytest.fixture
def acr_client(acr_config, mock_session):
    """ACRRegistryClient with mocked OAuth2 exchange and requests session."""
    with (
        patch("app.core.registry.decrypt_secret", return_value="admin_password"),
        patch("app.core.registry.create_resilient_session", return_value=mock_session),
        patch("requests.post") as mock_post,
    ):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "test_acr_token"}
        client = ACRRegistryClient(acr_config)
        # Ensure the client is using our controlled session
        client.session = mock_session
    return client


# ---------------------------------------------------------------------------
# Task 1.5 — Authentication & Retrieval
# ---------------------------------------------------------------------------

class TestACRAuthentication:
    def test_oauth2_token_exchange_sets_bearer_header(self, acr_config, mock_session):
        """ACRRegistryClient exchanges admin credentials for an OAuth2 token and
        sets the Authorization: Bearer header on the session."""
        with (
            patch("app.core.registry.decrypt_secret", return_value="admin_password"),
            patch("app.core.registry.create_resilient_session", return_value=mock_session),
            patch("requests.post") as mock_post,
        ):
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"access_token": "acr_bearer_token"}

            ACRRegistryClient(acr_config)

            # Verify POST was to the correct ACR token endpoint
            assert mock_post.called
            called_url = mock_post.call_args[0][0]
            assert called_url == "https://myregistry.azurecr.io/oauth2/token"

            # Verify service field matches the registry hostname
            call_data = mock_post.call_args[1]["data"]
            assert call_data["grant_type"] == "password"
            assert call_data["service"] == "myregistry.azurecr.io"
            assert call_data["username"] == "admin"
            assert call_data["password"] == "admin_password"

            # Verify token was applied to session headers
            mock_session.headers.update.assert_called_with(
                {"Authorization": "Bearer acr_bearer_token"}
            )

    def test_fallback_to_basic_auth_when_token_exchange_fails(self, acr_config, mock_session):
        """If the OAuth2 token exchange fails (non-200), client falls back to HTTP Basic auth."""
        with (
            patch("app.core.registry.decrypt_secret", return_value="admin_password"),
            patch("app.core.registry.create_resilient_session", return_value=mock_session),
            patch("requests.post") as mock_post,
        ):
            mock_post.return_value.status_code = 401

            client = ACRRegistryClient(acr_config)

            # Basic auth should be set as fallback
            assert mock_session.auth == ("admin", "admin_password")

    def test_endpoint_normalisation_strips_https_scheme(self, mock_session):
        """Endpoints supplied with an https:// prefix are normalised correctly."""
        config = RegistryConfig(
            name="ACR",
            type=RegistryType.ACR,
            endpoint="https://myregistry.azurecr.io",
            username="admin",
            password="pw",
        )
        with (
            patch("app.core.registry.decrypt_secret", return_value="pw"),
            patch("app.core.registry.create_resilient_session", return_value=mock_session),
            patch("requests.post") as mock_post,
        ):
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"access_token": "tok"}
            client = ACRRegistryClient(config)

        assert client.registry == "myregistry.azurecr.io"
        assert client.base_url == "https://myregistry.azurecr.io"


class TestACRListImages:
    def test_list_images_returns_image_artifacts(self, acr_client, mock_session):
        """list_images queries /v2/_catalog and /v2/{repo}/tags/list and returns
        correctly populated ImageArtifact objects."""
        mock_session.get.side_effect = [
            # GET /v2/_catalog
            MagicMock(
                status_code=200,
                json=lambda: {"repositories": ["myapp"]},
                headers={},
            ),
            # GET /v2/myapp/tags/list
            MagicMock(
                status_code=200,
                json=lambda: {"tags": ["v1.0", "latest"]},
                headers={},
            ),
            # GET /v2/myapp/manifests/v1.0
            MagicMock(
                status_code=200,
                json=lambda: {
                    "config": {"size": 1024},
                    "layers": [{"size": 5000}, {"size": 3000}],
                },
                headers={"Docker-Content-Digest": "sha256:abc123"},
            ),
            # GET /v2/myapp/manifests/latest
            MagicMock(
                status_code=200,
                json=lambda: {
                    "config": {"size": 512},
                    "layers": [{"size": 2000}],
                },
                headers={"Docker-Content-Digest": "sha256:def456"},
            ),
        ]

        with patch("app.core.registry.get_cached_images", return_value=None):
            images = acr_client.list_images()

        assert len(images) == 2

        v1 = images[0]
        assert v1.tags == ["myapp:v1.0"]
        assert v1.size_bytes == 9024  # 1024 + 5000 + 3000
        assert v1.digest == "sha256:abc123"
        assert v1.source == "My ACR"

        latest = images[1]
        assert latest.tags == ["myapp:latest"]
        assert latest.size_bytes == 2512  # 512 + 2000
        assert latest.digest == "sha256:def456"

    def test_list_images_uses_cache(self, acr_client):
        """list_images returns cached results without hitting the registry API."""
        cached = [ImageArtifact(tags=["cached:v1"], size_bytes=0, digest="sha256:cache")]
        with patch("app.core.registry.get_cached_images", return_value=cached):
            images = acr_client.list_images()

        assert images is cached

    def test_list_images_untagged_repo_returns_placeholder(self, acr_client, mock_session):
        """Repositories with no tags appear as <none> placeholder artifacts."""
        mock_session.get.side_effect = [
            MagicMock(
                status_code=200,
                json=lambda: {"repositories": ["untagged-image"]},
                headers={},
            ),
            MagicMock(
                status_code=200,
                json=lambda: {"tags": []},
                headers={},
            ),
        ]

        with patch("app.core.registry.get_cached_images", return_value=None):
            images = acr_client.list_images()

        assert len(images) == 1
        assert images[0].tags == ["untagged-image:<none>"]

    def test_list_images_respects_limit(self, acr_client, mock_session):
        """list_images stops collecting artifacts once the limit is reached."""
        mock_session.get.side_effect = [
            MagicMock(
                status_code=200,
                json=lambda: {"repositories": ["repo-a", "repo-b"]},
                headers={},
            ),
            # repo-a: 2 tags
            MagicMock(status_code=200, json=lambda: {"tags": ["v1", "v2"]}, headers={}),
            MagicMock(
                status_code=200,
                json=lambda: {"config": {"size": 0}, "layers": []},
                headers={"Docker-Content-Digest": "sha256:a1"},
            ),
            MagicMock(
                status_code=200,
                json=lambda: {"config": {"size": 0}, "layers": []},
                headers={"Docker-Content-Digest": "sha256:a2"},
            ),
        ]

        with patch("app.core.registry.get_cached_images", return_value=None):
            images = acr_client.list_images(limit=2)

        assert len(images) == 2

    def test_test_connection_success(self, acr_client, mock_session):
        """test_connection returns success when /v2/ responds with HTTP 200."""
        mock_session.get.return_value.status_code = 200

        result = acr_client.test_connection()

        assert result["success"] is True
        assert "myregistry.azurecr.io" in result["message"]

    def test_test_connection_auth_failure(self, acr_client, mock_session):
        """test_connection returns AUTH_ERROR on HTTP 401."""
        mock_session.get.return_value.status_code = 401

        result = acr_client.test_connection()

        assert result["success"] is False
        assert result.get("type") == "AUTH_ERROR"

    def test_test_connection_network_error(self, acr_client, mock_session):
        """test_connection returns NETWORK_ERROR on connection exception."""
        import requests as req
        mock_session.get.side_effect = req.exceptions.ConnectionError("refused")

        result = acr_client.test_connection()

        assert result["success"] is False
        assert result.get("type") == "NETWORK_ERROR"


# ---------------------------------------------------------------------------
# Task 1.6 — Deletion
# ---------------------------------------------------------------------------

class TestACRDeleteImage:
    def test_dry_run_returns_success_without_delete_call(self, acr_client, mock_session):
        """Dry-run returns success and never issues a DELETE request."""
        result = acr_client.delete_image(MagicMock(), "myapp:latest", dry_run=True)

        assert result["success"] is True
        assert result["dry_run"] is True
        assert "DRY RUN" in result["message"]
        mock_session.delete.assert_not_called()

    def test_delete_by_tag_resolves_digest_via_head(self, acr_client, mock_session):
        """repo:tag format: HEAD resolves tag to digest, then DELETE targets digest."""
        mock_session.head.return_value.status_code = 200
        mock_session.head.return_value.headers = {
            "Docker-Content-Digest": "sha256:deadbeef"
        }
        mock_session.delete.return_value.status_code = 202

        result = acr_client.delete_image(MagicMock(), "myapp:latest", dry_run=False)

        assert result["success"] is True
        assert "Successfully deleted" in result["message"]

        # HEAD must target the tag
        head_url = mock_session.head.call_args[0][0]
        assert head_url == "https://myregistry.azurecr.io/v2/myapp/manifests/latest"

        # DELETE must target the resolved digest, NOT the tag
        delete_url = mock_session.delete.call_args[0][0]
        assert delete_url == "https://myregistry.azurecr.io/v2/myapp/manifests/sha256:deadbeef"

    def test_delete_by_digest_skips_head_request(self, acr_client, mock_session):
        """repo@digest format: no HEAD issued, DELETE goes straight to the digest."""
        mock_session.delete.return_value.status_code = 202

        result = acr_client.delete_image(MagicMock(), "myapp@sha256:cafebabe", dry_run=False)

        assert result["success"] is True
        mock_session.head.assert_not_called()

        delete_url = mock_session.delete.call_args[0][0]
        assert delete_url == "https://myregistry.azurecr.io/v2/myapp/manifests/sha256:cafebabe"

    def test_delete_failed_head_returns_error_without_delete(self, acr_client, mock_session):
        """If HEAD returns non-200, delete_image fails without calling DELETE."""
        mock_session.head.return_value.status_code = 404

        result = acr_client.delete_image(MagicMock(), "myapp:ghost", dry_run=False)

        assert result["success"] is False
        assert "Could not resolve tag" in result["message"]
        mock_session.delete.assert_not_called()

    def test_delete_invalid_image_id_returns_error(self, acr_client):
        """A bare image ID with no colon or @ is rejected as invalid."""
        result = acr_client.delete_image(MagicMock(), "justarepo", dry_run=False)

        assert result["success"] is False
        assert "Invalid ACR image identifier" in result["message"]

    def test_delete_adds_audit_log_on_success(self, acr_client, mock_session):
        """A successful deletion adds an AuditLog entry to the DB session."""
        mock_session.head.return_value.status_code = 200
        mock_session.head.return_value.headers = {"Docker-Content-Digest": "sha256:abc"}
        mock_session.delete.return_value.status_code = 202

        db_session = MagicMock()
        acr_client.delete_image(db_session, "myapp:v1", dry_run=False)

        db_session.add.assert_called_once()
        audit_arg = db_session.add.call_args[0][0]
        assert audit_arg.action == "DELETE"
        assert audit_arg.dry_run is False

    def test_delete_registry_http_error_returns_failure(self, acr_client, mock_session):
        """If ACR responds with an error status on DELETE, success=False is returned."""
        mock_session.head.return_value.status_code = 200
        mock_session.head.return_value.headers = {"Docker-Content-Digest": "sha256:xyz"}
        mock_session.delete.return_value.status_code = 403
        mock_session.delete.return_value.text = "Access denied"

        result = acr_client.delete_image(MagicMock(), "myapp:v2", dry_run=False)

        assert result["success"] is False
        assert "403" in result["message"]
