"""Smoke tests for Settings validators and warnings."""

from __future__ import annotations

import pytest

from routeros_mcp.config import Settings


pytestmark = pytest.mark.smoke


def test_oidc_enabled_missing_fields_raises_smoke() -> None:
    with pytest.raises(ValueError):
        Settings(oidc_enabled=True)


def test_http_in_prod_without_oidc_warns_smoke() -> None:
    with pytest.warns(UserWarning):
        Settings(
            environment="prod",
            mcp_transport="http",
            oidc_enabled=False,
            encryption_key="dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcyEh",  # base64 encoded test key
        )
