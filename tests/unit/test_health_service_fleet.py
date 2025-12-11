from __future__ import annotations

from datetime import UTC, datetime

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import HealthCheckResult, HealthSummary
from routeros_mcp.domain.services import health as health_module


class _FakeDevice:
    def __init__(self, device_id: str) -> None:
        self.id = device_id
        self.routeros_version = "7.15"
        self.hardware_model = "rb5009"


class _FakeDeviceService:
    def __init__(self, devices: list[_FakeDevice]) -> None:
        self.devices = devices

    async def list_devices(self, environment: str | None = None):
        return self.devices

    async def get_device(self, device_id: str):
        return next(d for d in self.devices if d.id == device_id)

    async def get_rest_client(self, device_id: str):
        raise RuntimeError("should not be called in fleet test")


@pytest.mark.asyncio
async def test_get_fleet_health_counts(monkeypatch: pytest.MonkeyPatch):
    devices = [_FakeDevice("dev-1"), _FakeDevice("dev-2"), _FakeDevice("dev-3")]
    service = health_module.HealthService(session=None, settings=Settings())
    service.device_service = _FakeDeviceService(devices)

    async def fake_run_health_check(device_id: str):
        status_map = {
            "dev-1": HealthCheckResult(
                device_id=device_id,
                status="healthy",
                issues=[],
                warnings=[],
                timestamp=datetime.now(UTC),
            ),
            "dev-2": HealthCheckResult(
                device_id=device_id,
                status="degraded",
                issues=["cpu"],
                warnings=[],
                timestamp=datetime.now(UTC),
            ),
            "dev-3": HealthCheckResult(
                device_id=device_id,
                status="unreachable",
                issues=["down"],
                warnings=[],
                timestamp=datetime.now(UTC),
            ),
        }
        return status_map[device_id]

    monkeypatch.setattr(service, "run_health_check", fake_run_health_check)

    summary: HealthSummary = await service.get_fleet_health(environment="lab")

    assert summary.total_devices == 3
    assert summary.healthy_count == 1
    assert summary.degraded_count == 1
    assert summary.unreachable_count == 1
    assert summary.overall_status == "degraded"
