"""Smoke tests for MCP resources and tool registration."""

from __future__ import annotations

import json
from typing import Any

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp_resources import plan as plan_resources
from routeros_mcp.mcp_tools import device as device_tools

from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
async def test_plan_resources_render_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan resources should format JSON content using patched services."""

    # Patch PlanService and JobService to return predictable data without touching a DB
    class _FakePlanService:
        def __init__(self, _session: Any) -> None:
            pass

        async def get_plan(self, plan_id: str) -> dict[str, Any]:
            return {
                "plan_id": plan_id,
                "tool_name": "tool",
                "status": "approved",
                "created_by": "tester",
                "approved_by": "approver",
                "device_ids": ["dev-1", "dev-2"],
                "summary": "example",
                "changes": {"dns": ["1.1.1.1"]},
                "created_at": "2025-01-01T00:00:00Z",
                "approved_at": "2025-01-02T00:00:00Z",
                "updated_at": "2025-01-03T00:00:00Z",
            }

    class _FakeJobService:
        def __init__(self, _session: Any) -> None:
            pass

        async def list_jobs(self, plan_id: str, limit: int = 100) -> list[dict[str, Any]]:
            return [
                {"job_id": "job-1", "plan_id": plan_id, "status": "success"},
                {"job_id": "job-2", "plan_id": plan_id, "status": "failed"},
            ]

    monkeypatch.setattr(plan_resources, "PlanService", _FakePlanService)
    monkeypatch.setattr(plan_resources, "JobService", _FakeJobService)

    mcp = DummyMCP()
    settings = Settings()
    plan_resources.register_plan_resources(mcp, FakeSessionFactory(), settings)

    # Call the resource implementations directly
    summary_func = mcp.resources["plan://{plan_id}/summary"]
    details_func = mcp.resources["plan://{plan_id}/details"]
    execution_func = mcp.resources["plan://{plan_id}/execution-log"]

    summary = await summary_func("plan-123")
    details = await details_func("plan-123")
    execution = await execution_func("plan-123")

    assert json.loads(summary)["plan_id"] == "plan-123"
    assert json.loads(details)["changes"]["dns"] == ["1.1.1.1"]
    exec_payload = json.loads(execution)
    assert exec_payload["execution_summary"]["total_jobs"] == 2


def test_device_tools_register_without_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registering device tools should succeed when session factory is patched."""

    monkeypatch.setattr(device_tools, "get_session_factory", lambda _url: FakeSessionFactory())

    mcp = DummyMCP()
    settings = Settings()

    device_tools.register_device_tools(mcp, settings)

    assert "list_devices" in mcp.tools
    assert "check_connectivity" in mcp.tools


@pytest.mark.asyncio
async def test_device_overview_resource_renders_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Device overview resource should serialize JSON when services are stubbed."""

    from types import SimpleNamespace

    from routeros_mcp.mcp_resources import device as device_resources

    class _FakeDeviceService:
        def __init__(self, _session: Any, _settings: Settings) -> None:
            pass

        async def get_device(self, device_id: str) -> SimpleNamespace:
            return SimpleNamespace(
                id=device_id,
                name="device-name",
                environment="lab",
                management_ip="10.0.0.1",
                management_port=443,
                tags=["lab"],
                system_identity="identity",
            )

    class _FakeSystemService:
        def __init__(self, _session: Any, _settings: Settings) -> None:
            pass

        async def get_system_overview(self, device_id: str) -> dict[str, Any]:
            return {
                "device_id": device_id,
                "routeros_version": "7.15",
                "cpu_count": 4,
                "cpu_usage_percent": 12.5,
            }

    class _FakeHealth:
        def __init__(self) -> None:
            self.status = "healthy"
            self.last_check_timestamp = None
            self.metrics = {"cpu_usage": 10, "memory_usage_percent": 20}

    class _FakeHealthService:
        def __init__(self, _session: Any, _settings: Settings) -> None:
            pass

        async def run_health_check(self, _device_id: str) -> _FakeHealth:
            return _FakeHealth()

    monkeypatch.setattr(device_resources, "DeviceService", _FakeDeviceService)
    monkeypatch.setattr(device_resources, "SystemService", _FakeSystemService)
    monkeypatch.setattr(device_resources, "HealthService", _FakeHealthService)

    mcp = DummyMCP()
    settings = Settings()
    device_resources.register_device_resources(mcp, FakeSessionFactory(), settings)

    overview_func = mcp.resources["device://{device_id}/overview"]
    payload = await overview_func("dev-123")
    data = json.loads(payload)

    assert data["device_id"] == "dev-123"
    assert data["system"]["routeros_version"] == "7.15"
    assert data["health"]["status"] == "healthy"
