from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import DeviceCreate
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.models import AuditEvent, Base, Snapshot
from routeros_mcp.mcp.errors import MCPError
from routeros_mcp.mcp_resources import device as device_resources
from routeros_mcp.mcp_resources import fleet as fleet_resources

from tests.unit.mcp_tools_test_utils import DummyMCP


class _FakeSystemService:
    async def get_system_overview(self, device_id: str):
        return {"routeros_version": "7.15", "board_name": "rb5009"}


class _FakeHealth:
    def __init__(self, status: str = "healthy", metrics: dict | None = None):
        self.status = status
        self.last_check_timestamp = datetime.now(UTC)
        self.metrics = metrics or {"cpu_usage": 10, "memory_usage_percent": 20, "temperature": 40}


class _FakeHealthService:
    def __init__(self, raise_error: bool = False):
        self.raise_error = raise_error

    async def run_health_check(self, device_id: str):
        if self.raise_error:
            raise RuntimeError("health unavailable")
        return _FakeHealth()


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    class Factory:
        @asynccontextmanager
        async def session(self):
            async with maker() as session:
                yield session
                await session.commit()

    factory = Factory()
    yield factory
    await engine.dispose()


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="lab")


@pytest.fixture
async def seed_devices(session_factory, settings):
    async with session_factory.session() as session:
        service = DeviceService(session, settings)
        await service.register_device(
            DeviceCreate(
                id="dev-1",
                name="router-1",
                management_ip="10.0.0.1",
                management_port=443,
                environment="lab",
            )
        )
        await service.register_device(
            DeviceCreate(
                id="dev-2",
                name="router-2",
                management_ip="10.0.0.2",
                management_port=443,
                environment="lab",
            )
        )


@pytest.fixture
async def seed_snapshot_and_audit(session_factory, seed_devices):
    async with session_factory.session() as session:
        session.add(
            Snapshot(
                id=str(uuid.uuid4()),
                device_id="dev-1",
                timestamp=datetime.now(UTC),
                kind="config",
                data=b"/interface print",
                meta={"size": 18},
            )
        )

        session.add(
            AuditEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(UTC),
                user_sub="tester",
                user_email="tester@example.com",
                user_role="admin",
                device_id="dev-1",
                environment="lab",
                action="READ_SENSITIVE",
                tool_name="system/get-overview",
                tool_tier="fundamental",
                plan_id=None,
                job_id=None,
                result="SUCCESS",
                meta={
                    "summary": "Retrieved device overview",
                    "ip_address": "127.0.0.1",
                    "user_agent": "pytest",
                    "source": "test",
                },
                error_message=None,
            )
        )


@pytest.fixture
async def _setup_device_resources(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    settings,
    seed_devices,
    seed_snapshot_and_audit,
):
    monkeypatch.setattr(
        device_resources, "SystemService", lambda *args, **kwargs: _FakeSystemService()
    )
    monkeypatch.setattr(
        device_resources, "HealthService", lambda *args, **kwargs: _FakeHealthService()
    )

    mcp = DummyMCP()
    device_resources.register_device_resources(mcp, session_factory, settings)
    return mcp


@pytest.mark.asyncio
async def test_device_overview_success(_setup_device_resources):
    mcp = _setup_device_resources
    overview_func = mcp.resources["device://{device_id}/overview"]
    payload = json.loads(await overview_func("dev-1"))
    assert payload["device_id"] == "dev-1"
    assert payload["system"]["routeros_version"] == "7.15"


@pytest.mark.asyncio
async def test_device_overview_health_fallback(
    monkeypatch: pytest.MonkeyPatch, session_factory, settings, seed_devices
):
    monkeypatch.setattr(
        device_resources, "SystemService", lambda *args, **kwargs: _FakeSystemService()
    )
    monkeypatch.setattr(
        device_resources,
        "HealthService",
        lambda *args, **kwargs: _FakeHealthService(raise_error=True),
    )

    mcp = DummyMCP()
    device_resources.register_device_resources(mcp, session_factory, settings)

    overview_func = mcp.resources["device://{device_id}/overview"]
    payload = json.loads(await overview_func("dev-1"))
    assert payload["health"]["status"] == "unknown"
    assert "error" in payload["health"]


@pytest.mark.asyncio
async def test_device_health_success(_setup_device_resources):
    mcp = _setup_device_resources
    health_func = mcp.resources["device://{device_id}/health"]
    payload = json.loads(await health_func("dev-1"))
    assert payload["status"] == "healthy"
    assert payload["checks"]["cpu_ok"] is True


@pytest.mark.asyncio
async def test_device_config_and_logs(_setup_device_resources):
    mcp = _setup_device_resources
    config_func = mcp.resources["device://{device_id}/config"]
    logs_func = mcp.resources["device://{device_id}/logs"]

    config_payload = json.loads(await config_func("dev-1"))
    assert "/interface" in config_payload["config"]
    assert config_payload["_meta"]["snapshot_id"]

    logs = json.loads(await logs_func("dev-1"))
    assert logs["count"] == 1
    assert logs["logs"][0]["message"] == "Retrieved device overview"


@pytest.mark.asyncio
async def test_device_resource_not_found(session_factory, settings):
    mcp = DummyMCP()
    device_resources.register_device_resources(mcp, session_factory, settings)

    overview_func = mcp.resources["device://{device_id}/overview"]
    with pytest.raises(MCPError):
        await overview_func("missing")


@pytest.mark.asyncio
async def test_device_health_not_found(session_factory, settings):
    mcp = DummyMCP()
    device_resources.register_device_resources(mcp, session_factory, settings)

    health_func = mcp.resources["device://{device_id}/health"]
    with pytest.raises(MCPError):
        await health_func("missing")


@pytest.mark.asyncio
async def test_device_overview_generic_error(
    monkeypatch: pytest.MonkeyPatch, session_factory, settings
):
    class BoomDeviceService:
        async def get_device(self, device_id: str):
            raise RuntimeError("explode")

    monkeypatch.setattr(
        device_resources, "DeviceService", lambda *args, **kwargs: BoomDeviceService()
    )
    monkeypatch.setattr(
        device_resources, "SystemService", lambda *args, **kwargs: _FakeSystemService()
    )
    monkeypatch.setattr(
        device_resources, "HealthService", lambda *args, **kwargs: _FakeHealthService()
    )

    mcp = DummyMCP()
    device_resources.register_device_resources(mcp, session_factory, settings)

    overview_func = mcp.resources["device://{device_id}/overview"]
    with pytest.raises(MCPError):
        await overview_func("dev-1")


@pytest.fixture
async def _setup_fleet_resources(
    monkeypatch: pytest.MonkeyPatch, session_factory, settings, seed_devices
):
    class _HealthServiceWithUnreachable(_FakeHealthService):
        async def run_health_check(self, device_id: str):
            if device_id == "dev-2":
                raise RuntimeError("unreachable")
            return _FakeHealth(
                metrics={"cpu_usage": 50, "memory_usage_percent": 60, "temperature": 40}
            )

    monkeypatch.setattr(
        fleet_resources, "DeviceService", lambda *args, **kwargs: DeviceService(*args, **kwargs)
    )
    monkeypatch.setattr(
        fleet_resources, "HealthService", lambda *args, **kwargs: _HealthServiceWithUnreachable()
    )

    mcp = DummyMCP()
    fleet_resources.register_fleet_resources(mcp, session_factory, settings)
    return mcp


@pytest.mark.asyncio
async def test_fleet_health_summary(_setup_fleet_resources):
    mcp = _setup_fleet_resources
    summary_func = mcp.resources["fleet://health-summary"]
    payload = json.loads(await summary_func())
    assert payload["summary"]["total_devices"] == 2
    assert payload["health_distribution"]["unreachable"] == 1


@pytest.mark.asyncio
async def test_fleet_devices_filter(session_factory, settings, seed_devices):
    mcp = DummyMCP()
    fleet_resources.register_fleet_resources(mcp, session_factory, settings)

    devices_func = mcp.resources["fleet://devices/{environment}"]
    payload = json.loads(await devices_func(environment="lab"))
    assert payload["count"] == 2
    device_ids = {d["device_id"] for d in payload["devices"]}
    assert {"dev-1", "dev-2"} == device_ids


@pytest.mark.asyncio
async def test_fleet_health_summary_error(
    monkeypatch: pytest.MonkeyPatch, session_factory, settings
):
    class BoomDeviceService(DeviceService):
        async def list_devices(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(
        fleet_resources, "DeviceService", lambda *args, **kwargs: BoomDeviceService(*args, **kwargs)
    )
    mcp = DummyMCP()
    fleet_resources.register_fleet_resources(mcp, session_factory, settings)

    summary_func = mcp.resources["fleet://health-summary"]
    with pytest.raises(MCPError):
        await summary_func()


@pytest.mark.asyncio
async def test_fleet_devices_error(monkeypatch: pytest.MonkeyPatch, session_factory, settings):
    class BoomDeviceService(DeviceService):
        async def list_devices(self):
            raise RuntimeError("fetch fail")

    monkeypatch.setattr(
        fleet_resources, "DeviceService", lambda *args, **kwargs: BoomDeviceService(*args, **kwargs)
    )
    mcp = DummyMCP()
    fleet_resources.register_fleet_resources(mcp, session_factory, settings)

    devices_func = mcp.resources["fleet://devices/{environment}"]
    with pytest.raises(MCPError):
        await devices_func()
