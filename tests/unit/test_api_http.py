from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from routeros_mcp.api.http import create_http_app, get_current_user
from routeros_mcp.config import Settings


@pytest.fixture
def settings():
    return Settings(oidc_enabled=False, debug=True)


def test_health_and_metrics(monkeypatch, settings):
    # Stub metrics text
    monkeypatch.setattr("routeros_mcp.api.http.get_metrics_text", lambda: "metrics-ok")
    app = create_http_app(settings)
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "metrics-ok" in resp.text


@pytest.mark.asyncio
async def test_get_current_user_when_oidc_disabled(settings):
    # Should bypass validation and return anonymous context
    user = await get_current_user(request=SimpleNamespace(headers={}), settings=settings)
    assert user["role"] == "admin"


class TestLoginEndpoint:
    """Tests for OAuth 2.1 login endpoint."""

    def test_login_when_oidc_disabled(self):
        """Test login endpoint returns 501 when OIDC is disabled."""
        settings = Settings(oidc_enabled=False, debug=True)
        app = create_http_app(settings)

        # Override the get_settings dependency to use our test settings
        from routeros_mcp.api.http import get_settings

        app.dependency_overrides[get_settings] = lambda: settings

        client = TestClient(app)

        resp = client.get("/api/auth/login")
        assert resp.status_code == 501
        assert "not enabled" in resp.json()["detail"]

    def test_login_when_oidc_enabled_but_missing_config(self):
        """Test login endpoint returns 500 when OIDC config is incomplete."""
        # Config passes validation but missing redirect_uri at runtime
        # (redirect_uri is not required in Settings, only checked in login endpoint)
        settings = Settings(
            oidc_enabled=True,
            oidc_issuer="https://auth.example.com",
            oidc_client_id="test-client",
            # redirect_uri is None
            debug=True,
        )
        app = create_http_app(settings)

        # Override the get_settings dependency to use our test settings
        from routeros_mcp.api.http import get_settings

        app.dependency_overrides[get_settings] = lambda: settings

        client = TestClient(app)

        resp = client.get("/api/auth/login")
        assert resp.status_code == 500
        assert "not properly configured" in resp.json()["detail"]

    def test_login_when_oidc_properly_configured(self):
        """Test login endpoint returns authorization URL when properly configured."""
        settings = Settings(
            oidc_enabled=True,
            oidc_issuer="https://auth.example.com",
            oidc_client_id="test-client-id",
            oidc_redirect_uri="http://localhost:8080/api/auth/callback",
            oidc_scopes="openid profile email",
            debug=True,
        )
        app = create_http_app(settings)

        # Override the get_settings dependency to use our test settings
        from routeros_mcp.api.http import get_settings

        app.dependency_overrides[get_settings] = lambda: settings

        client = TestClient(app)

        resp = client.get("/api/auth/login")
        assert resp.status_code == 200

        data = resp.json()
        assert "authorization_url" in data
        assert "state" in data
        assert "message" in data

        # Verify the authorization URL is properly formed
        auth_url = data["authorization_url"]
        assert auth_url.startswith("https://auth.example.com/authorize?")
        assert "response_type=code" in auth_url
        assert "client_id=test-client-id" in auth_url
        assert "redirect_uri=http" in auth_url
        assert "scope=openid" in auth_url
        assert "state=" in auth_url
        assert "code_challenge=" in auth_url
        assert "code_challenge_method=S256" in auth_url

    def test_login_returns_state_for_csrf_verification(self):
        """Test that login endpoint returns state parameter for CSRF protection."""
        from urllib.parse import urlparse, parse_qs

        settings = Settings(
            oidc_enabled=True,
            oidc_issuer="https://auth.example.com",
            oidc_client_id="test-client-id",
            oidc_redirect_uri="http://localhost:8080/api/auth/callback",
            debug=True,
        )
        app = create_http_app(settings)

        # Override the get_settings dependency to use our test settings
        from routeros_mcp.api.http import get_settings

        app.dependency_overrides[get_settings] = lambda: settings

        client = TestClient(app)

        resp = client.get("/api/auth/login")
        assert resp.status_code == 200

        data = resp.json()
        returned_state = data["state"]

        # Parse state from URL
        parsed = urlparse(data["authorization_url"])
        params = parse_qs(parsed.query)
        url_state = params["state"][0]

        # Returned state should match state in URL
        assert returned_state == url_state
        assert len(returned_state) >= 32  # Should be cryptographically secure
