from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import health as health_module

if TYPE_CHECKING:
    from routeros_mcp.domain.models import HealthCheckResult


class _FakeDevice:
    def __init__(self, device_id: str):
        self.id = device_id
        self.routeros_version = "7.15"
        self.hardware_model = "rb5009"


class _FakeRestClient:
    def __init__(self, resource_payload: dict):
        self.resource_payload = resource_payload
        self.closed = False

    async def get(self, path: str):
        return self.resource_payload

    async def close(self):
        self.closed = True


class _FakeDeviceService:
    def __init__(self, client: _FakeRestClient, device: _FakeDevice):
        self.client = client
        self.device = device

    async def get_device(self, device_id: str):
        return self.device

    async def get_rest_client(self, device_id: str):
        return self.client

    async def list_devices(self, environment: str | None = None):
        return [self.device]


@pytest.mark.asyncio
async def test_run_health_check_with_issues(monkeypatch: pytest.MonkeyPatch):
    resource_payload = {
        "cpu-load": 95,
        "total-memory": 100,
        "free-memory": 5,
        "uptime": "1h",
    }
    client = _FakeRestClient(resource_payload)
    device = _FakeDevice("dev-issue")

    service = health_module.HealthService(session=None, settings=Settings())
    service.device_service = _FakeDeviceService(client, device)

    store_mock = AsyncMock()
    monkeypatch.setattr(service, "_store_health_check", store_mock)

    result: HealthCheckResult = await service.run_health_check("dev-issue")
    assert result.status == "degraded"
    assert any("CPU" in issue for issue in result.issues) or any(
        "memory" in issue.lower() for issue in result.issues
    )
    assert client.closed is True


@pytest.mark.asyncio
async def test_run_health_check_memory_warning(monkeypatch: pytest.MonkeyPatch):
    resource_payload = {
        "cpu-load": 10,
        "total-memory": 100,
        "free-memory": 10,
        "uptime": "1h",
    }
    client = _FakeRestClient(resource_payload)
    device = _FakeDevice("dev-mem")

    service = health_module.HealthService(session=None, settings=Settings())
    service.device_service = _FakeDeviceService(client, device)

    store_mock = AsyncMock()
    monkeypatch.setattr(service, "_store_health_check", store_mock)

    result: HealthCheckResult = await service.run_health_check("dev-mem")
    assert result.status == "degraded"
    assert any("memory" in msg.lower() for msg in (result.issues + result.warnings))


@pytest.mark.asyncio
async def test_run_health_check_unreachable(monkeypatch: pytest.MonkeyPatch):
    device = _FakeDevice("dev-down")

    service = health_module.HealthService(session=None, settings=Settings())

    async def _fail_get_rest_client(_device_id):
        raise RuntimeError("boom")

    service.device_service = _FakeDeviceService(None, device)
    service.device_service.get_rest_client = _fail_get_rest_client  # type: ignore

    store_mock = AsyncMock()
    monkeypatch.setattr(service, "_store_health_check", store_mock)

    result = await service.run_health_check("dev-down")
    assert result.status == "unreachable"
    assert "Device unreachable" in result.issues[0]
