"""Additional smoke tests covering startup and wiring flows."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.system import SystemService
from routeros_mcp.infra.db.session import (
    initialize_session_manager,
    reset_session_manager,
)


pytestmark = pytest.mark.smoke


def test_settings_load_defaults_smoke() -> None:
    """Settings should load with lab defaults without raising."""

    settings = Settings()

    assert settings.environment == "lab"
    assert settings.mcp_transport == "stdio"
    # Encryption key should be populated with insecure default in lab
    assert settings.encryption_key is not None


@pytest.mark.asyncio
async def test_session_factory_in_memory_sqlite_smoke() -> None:
    """In-memory SQLite session factory should initialize and execute simple SQL."""

    reset_session_manager()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:")

    try:
        manager = await initialize_session_manager(settings)
        async with manager.session() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        reset_session_manager()


@pytest.mark.asyncio
async def test_system_service_overview_stubbed_routeros_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """SystemService overview should normalize data when RouterOS calls are stubbed."""

    settings = Settings()
    service = SystemService(session=None, settings=settings)

    class _FakeDevice(SimpleNamespace):
        pass

    async def _fake_get_device(device_id: str) -> _FakeDevice:
        return _FakeDevice(id=device_id, name="Device", system_identity="lab-device")

    async def _fake_overview(_device_id: str):
        return (
            {
                "cpu-load": 12,
                "total-memory": 1024,
                "free-memory": 512,
                "uptime": "1h2m3s",
                "version": "7.15",
                "board-name": "x86",
                "architecture-name": "x86_64",
                "cpu-count": 4,
            },
            "fake-identity",
        )

    service.device_service = SimpleNamespace(get_device=_fake_get_device)
    monkeypatch.setattr(service, "_get_overview_via_rest", _fake_overview)

    overview = await service.get_system_overview("dev-1")

    assert overview["device_id"] == "dev-1"
    assert overview["system_identity"] == "fake-identity"
    assert overview["cpu_count"] == 4
    assert overview["memory_total_bytes"] == 1024
    assert overview["memory_free_bytes"] == 512


@pytest.mark.asyncio
async def test_fastmcp_echo_tool_call_smoke() -> None:
    """FastMCP echo tool should be callable end-to-end without starting transports."""

    from routeros_mcp.mcp.server import RouterOSMCPServer

    server = RouterOSMCPServer(Settings())

    tool = await server.mcp.get_tool("echo")
    result = await tool.fn(message="ping")

    assert result.get("content", [])[0]["text"] == "Echo: ping"
    assert result.get("_meta", {}).get("original_message") == "ping"


@pytest.mark.asyncio
async def test_service_health_tool_call_smoke() -> None:
    """FastMCP service_health tool should respond with a running status."""

    from routeros_mcp.mcp.server import RouterOSMCPServer

    server = RouterOSMCPServer(Settings())

    tool = await server.mcp.get_tool("service_health")
    result = await tool.fn()

    assert result.get("content", [])[0]["text"] == "Service is running"
    assert result.get("_meta", {}).get("environment") == "lab"


def test_config_yaml_file_loads_smoke() -> None:
    """Config file lab.yaml should load without raising."""

    from pathlib import Path

    config_file = Path("config/lab.yaml")
    if config_file.exists():
        settings = Settings(_env_file=str(config_file))
        assert settings.environment == "lab"
        assert settings.database_url is not None


def test_prompt_registration_smoke() -> None:
    """Prompt registration should load without errors."""

    from routeros_mcp.mcp_prompts import register_prompts
    from tests.unit.mcp_tools_test_utils import DummyMCP

    mcp = DummyMCP()
    register_prompts(mcp, Settings())

    # Verify at least one prompt was registered
    assert len(mcp.prompts) > 0


def test_domain_models_instantiate_smoke() -> None:
    """Domain models should instantiate without errors."""

    from routeros_mcp.domain.models import Device, DeviceCreate, HealthCheckResult
    from datetime import UTC, datetime

    # Test DeviceCreate DTO instantiation
    device_create = DeviceCreate(
        id="dev-1",
        name="test-device",
        management_ip="10.0.0.1",
        management_port=443,
        environment="lab",
    )
    assert device_create.id == "dev-1"
    assert device_create.management_ip == "10.0.0.1"

    # Test Device model instantiation
    device = Device(
        id="dev-1",
        name="test-device",
        management_ip="10.0.0.1",
        management_port=443,
        environment="lab",
        status="healthy",
        tags={},
        allow_advanced_writes=False,
        allow_professional_workflows=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert device.id == "dev-1"
    assert device.environment == "lab"

    # Test HealthCheckResult model instantiation
    health = HealthCheckResult(
        device_id="dev-1",
        status="healthy",
        timestamp=datetime.now(UTC),
        cpu_usage_percent=10.5,
        memory_usage_percent=25.0,
    )
    assert health.device_id == "dev-1"
    assert health.status == "healthy"


def test_mcp_error_to_jsonrpc_smoke() -> None:
    """MCPError should map to valid JSON-RPC error format."""

    from routeros_mcp.mcp.errors import DeviceNotFoundError, InvalidRequestError

    error1 = DeviceNotFoundError("Device not found", data={"device_id": "dev-1"})
    jsonrpc1 = error1.to_jsonrpc_error()

    assert jsonrpc1["code"] < 0
    assert jsonrpc1["message"] is not None
    assert jsonrpc1["data"]["device_id"] == "dev-1"

    error2 = InvalidRequestError("Invalid input")
    jsonrpc2 = error2.to_jsonrpc_error()

    assert jsonrpc2["code"] < 0
    assert jsonrpc2["message"] is not None


@pytest.mark.asyncio
async def test_server_async_startup_wiring_smoke() -> None:
    """Server startup should initialize session factory without running transports."""

    from routeros_mcp.mcp.server import RouterOSMCPServer

    server = RouterOSMCPServer(Settings())

    # Initialize session (mimics start() setup without running transports)
    server.session_factory = await initialize_session_manager(server.settings)

    assert server.session_factory is not None
    # Verify session can be created
    async with server.session_factory.session() as session:
        assert session is not None


def test_all_domain_services_instantiate_smoke() -> None:
    """All domain services should instantiate without raising."""

    from routeros_mcp.domain.services import (
        DeviceService,
        SystemService,
        InterfaceService,
        DNSNTPService,
        HealthService,
        RoutingService,
        FirewallLogsService,
        DiagnosticsService,
    )

    # Services accept session=None for smoke testing (they'll fail on use but init is OK)
    services = [
        DeviceService(None, Settings()),
        SystemService(None, Settings()),
        InterfaceService(None, Settings()),
        DNSNTPService(None, Settings()),
        HealthService(None, Settings()),
        RoutingService(None, Settings()),
        FirewallLogsService(None, Settings()),
        DiagnosticsService(None, Settings()),
    ]

    assert all(s is not None for s in services)
    assert len(services) == 8
