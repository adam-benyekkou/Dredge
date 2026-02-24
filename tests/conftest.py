"""
Global pytest configuration.

Cloud-provider SDKs (boto3, google-cloud, azure) are runtime dependencies
but may not be installed in the lightweight test environment. We mock them
at the sys.modules level *before* any test module imports app code, so that
import-time references to these libraries resolve to MagicMocks instead of
raising ModuleNotFoundError.
"""

import sys
from unittest.mock import MagicMock


def _mock_module(name: str) -> MagicMock:
    """Create and register a MagicMock for a module path and all sub-paths."""
    mock = MagicMock()
    sys.modules[name] = mock
    return mock


# ---------------------------------------------------------------------------
# AWS / boto3
# ---------------------------------------------------------------------------
_mock_module("boto3")
_mock_module("botocore")
_mock_module("botocore.exceptions")

# Make ClientError importable as a real exception class so isinstance checks work
class _ClientError(Exception):
    def __init__(self, error_response=None, operation_name=""):
        self.response = error_response or {"Error": {"Code": "Unknown", "Message": "Unknown"}}
        super().__init__(str(self.response))

sys.modules["botocore.exceptions"].ClientError = _ClientError

# ---------------------------------------------------------------------------
# Google Cloud / google-auth
# ---------------------------------------------------------------------------
_mock_module("google")
_mock_module("google.auth")
_mock_module("google.oauth2")
_mock_module("google.oauth2.service_account")
_mock_module("google.cloud")
_mock_module("google.cloud.artifactregistry_v1")

# ---------------------------------------------------------------------------
# Azure SDK
# ---------------------------------------------------------------------------
_mock_module("azure")
_mock_module("azure.identity")
_mock_module("azure.containerregistry")
