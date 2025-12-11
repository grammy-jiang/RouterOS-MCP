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
