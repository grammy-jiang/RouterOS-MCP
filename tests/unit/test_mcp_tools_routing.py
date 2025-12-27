from __future__ import annotations

from types import SimpleNamespace

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp.errors import MCPError
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


@pytest.mark.asyncio
async def test_get_routing_summary_success_formats_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.routing as routing_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubRoutingService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_routing_summary(self, _device_id: str) -> dict[str, object]:
            return {
                "total_routes": 3,
                "static_routes": 1,
                "connected_routes": 1,
                "dynamic_routes": 1,
                "routes": [
                    {"dst_address": "0.0.0.0/0", "gateway": "1.1.1.1", "distance": 1},
                ],
            }

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(routing_tools, "RoutingService", StubRoutingService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["get_routing_summary"](device_id="dev-1")

    assert result["isError"] is False
    assert "Routing table: 3 routes" in result["content"][0]["text"]
    assert result["_meta"]["device_id"] == "dev-1"
    assert result["_meta"]["total_routes"] == 3


@pytest.mark.asyncio
async def test_get_routing_summary_mcp_error_returns_error_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routeros_mcp.mcp_tools.routing as routing_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubRoutingService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_routing_summary(self, _device_id: str) -> dict[str, object]:
            raise MCPError("nope", data={"why": "because"}, code=-32006)

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(routing_tools, "RoutingService", StubRoutingService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["get_routing_summary"](device_id="dev-1")

    assert result["isError"] is True
    assert result["content"][0]["text"] == "nope"
    assert result["_meta"]["why"] == "because"


@pytest.mark.asyncio
async def test_get_routing_summary_unexpected_exception_maps_to_error_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routeros_mcp.mcp_tools.routing as routing_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubRoutingService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_routing_summary(self, _device_id: str) -> dict[str, object]:
            raise ValueError("boom")

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(routing_tools, "RoutingService", StubRoutingService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["get_routing_summary"](device_id="dev-1")

    assert result["isError"] is True
    assert result["content"][0]["text"] == "boom"


@pytest.mark.asyncio
async def test_get_route_success_formats_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.routing as routing_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubRoutingService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_route(self, _device_id: str, _route_id: str) -> dict[str, object] | None:
            return {"dst_address": "0.0.0.0/0", "gateway": "1.1.1.1"}

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(routing_tools, "RoutingService", StubRoutingService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["get_route"](device_id="dev-1", route_id="*3")

    assert result["isError"] is False
    assert result["content"][0]["text"] == "Route: 0.0.0.0/0 via 1.1.1.1"
    assert result["_meta"]["route"]["dst_address"] == "0.0.0.0/0"


@pytest.mark.asyncio
async def test_get_route_not_found_with_available_routes_returns_helpful_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routeros_mcp.mcp_tools.routing as routing_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubRoutingService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_route(self, _device_id: str, _route_id: str) -> None:
            return None

        async def get_routing_summary(self, _device_id: str) -> dict[str, object]:
            return {"total_routes": 2}

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(routing_tools, "RoutingService", StubRoutingService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["get_route"](device_id="dev-1", route_id="*404")

    assert result["isError"] is False
    assert "Use routing/get-summary" in result["content"][0]["text"]
    assert result["_meta"]["found"] is False
    assert result["_meta"]["available_routes"] == 2


@pytest.mark.asyncio
async def test_get_route_not_found_with_no_routes_returns_no_routes_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routeros_mcp.mcp_tools.routing as routing_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubRoutingService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_route(self, _device_id: str, _route_id: str) -> None:
            return None

        async def get_routing_summary(self, _device_id: str) -> dict[str, object]:
            return {"total_routes": 0}

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(routing_tools, "RoutingService", StubRoutingService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["get_route"](device_id="dev-1", route_id="*404")

    assert result["isError"] is False
    assert result["content"][0]["text"] == "No routes found on dev-1"
    assert result["_meta"]["found"] is False


@pytest.mark.asyncio
async def test_get_route_unexpected_exception_maps_to_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.routing as routing_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubRoutingService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_route(self, _device_id: str, _route_id: str) -> dict[str, object] | None:
            raise ValueError("boom")

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(routing_tools, "RoutingService", StubRoutingService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["get_route"](device_id="dev-1", route_id="*1")

    assert result["isError"] is True
    assert result["content"][0]["text"] == "boom"


@pytest.mark.asyncio
async def test_get_route_mcp_error_returns_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.routing as routing_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubRoutingService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_route(self, _device_id: str, _route_id: str) -> dict[str, object] | None:
            raise MCPError("nope", data={"route_id": _route_id}, code=-32006)

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(routing_tools, "RoutingService", StubRoutingService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["get_route"](device_id="dev-1", route_id="*3")

    assert result["isError"] is True
    assert result["content"][0]["text"] == "nope"
    assert result["_meta"]["route_id"] == "*3"


# Tests for plan/apply tools
@pytest.mark.asyncio
async def test_plan_add_static_route_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful static route addition plan."""
    import routeros_mcp.mcp_tools.routing as routing_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = "lab"
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_routing_writes = True
            self.management_ip = "192.168.1.1"

    class FakeDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> FakeDevice:
            return FakeDevice(device_id)

    class FakePlanService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def create_plan(
            self,
            tool_name: str,
            created_by: str,
            device_ids: list[str],
            summary: str,
            changes: dict,
            risk_level: str = "medium",
        ) -> dict:
            return {
                "plan_id": "plan-rt-001",
                "approval_token": "approve-rt-abc123",
                "approval_expires_at": "2025-12-20T16:00:00Z",
            }

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(routing_tools, "PlanService", FakePlanService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["plan_add_static_route"](
        device_ids=["dev-lab-01", "dev-lab-02"],
        dst_address="10.0.0.0/8",
        gateway="192.168.1.254",
        comment="Test route",
    )

    assert result["isError"] is False
    assert "plan created successfully" in result["content"][0]["text"]
    assert result["_meta"]["plan_id"] == "plan-rt-001"
    assert result["_meta"]["approval_token"] == "approve-rt-abc123"
    assert result["_meta"]["device_count"] == 2


@pytest.mark.asyncio
async def test_plan_add_static_route_blocks_default_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test plan blocks default route addition."""
    import routeros_mcp.mcp_tools.routing as routing_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = "lab"
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_routing_writes = True
            self.management_ip = "192.168.1.1"

    class FakeDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> FakeDevice:
            return FakeDevice(device_id)

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["plan_add_static_route"](
        device_ids=["dev-lab-01"],
        dst_address="0.0.0.0/0",
        gateway="192.168.1.254",
    )

    assert result["isError"] is True
    assert "Default route" in result["content"][0]["text"]
    assert "blocked" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_plan_add_static_route_invalid_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test plan rejects invalid destination address."""
    import routeros_mcp.mcp_tools.routing as routing_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = "lab"
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_routing_writes = True
            self.management_ip = "192.168.1.1"

    class FakeDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> FakeDevice:
            return FakeDevice(device_id)

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["plan_add_static_route"](
        device_ids=["dev-lab-01"],
        dst_address="not-an-ip",
        gateway="192.168.1.254",
    )

    assert result["isError"] is True
    assert "Invalid destination address" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_plan_add_static_route_prod_environment_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test plan rejects production environment by default."""
    import routeros_mcp.mcp_tools.routing as routing_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-prod-01") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = "prod"
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_routing_writes = True
            self.management_ip = "192.168.1.1"

    class FakeDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> FakeDevice:
            return FakeDevice(device_id)

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["plan_add_static_route"](
        device_ids=["dev-prod-01"],
        dst_address="10.0.0.0/8",
        gateway="192.168.1.254",
    )

    assert result["isError"] is True
    assert "prod" in result["content"][0]["text"]
    assert "only allowed" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_plan_add_static_route_routing_writes_capability_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test plan requires routing write capability."""
    import routeros_mcp.mcp_tools.routing as routing_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = "lab"
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_routing_writes = False  # Capability disabled
            self.management_ip = "192.168.1.1"

    class FakeDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> FakeDevice:
            return FakeDevice(device_id)

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["plan_add_static_route"](
        device_ids=["dev-lab-01"],
        dst_address="10.0.0.0/8",
        gateway="192.168.1.254",
    )

    assert result["isError"] is True
    assert "routing write capability" in result["content"][0]["text"]
    assert "allow_routing_writes" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_plan_modify_static_route_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful static route modification plan."""
    import routeros_mcp.mcp_tools.routing as routing_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = "lab"
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_routing_writes = True
            self.management_ip = "192.168.1.1"

    class FakeDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> FakeDevice:
            return FakeDevice(device_id)

    class FakePlanService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def create_plan(
            self,
            tool_name: str,
            created_by: str,
            device_ids: list[str],
            summary: str,
            changes: dict,
            risk_level: str = "medium",
        ) -> dict:
            return {
                "plan_id": "plan-rt-002",
                "approval_token": "approve-rt-xyz789",
                "approval_expires_at": "2025-12-20T16:00:00Z",
            }

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(routing_tools, "PlanService", FakePlanService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["plan_modify_static_route"](
        device_ids=["dev-lab-01"],
        route_id="*5",
        gateway="192.168.1.253",
        comment="Updated gateway",
    )

    assert result["isError"] is False
    assert "plan created successfully" in result["content"][0]["text"]
    assert "Route ID: *5" in result["content"][0]["text"]
    assert result["_meta"]["plan_id"] == "plan-rt-002"
    assert result["_meta"]["risk_level"] == "high"  # Modifications are always high risk


@pytest.mark.asyncio
async def test_plan_modify_static_route_no_modifications(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test plan requires at least one modification."""
    import routeros_mcp.mcp_tools.routing as routing_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = "lab"
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_routing_writes = True
            self.management_ip = "192.168.1.1"

    class FakeDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> FakeDevice:
            return FakeDevice(device_id)

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["plan_modify_static_route"](
        device_ids=["dev-lab-01"],
        route_id="*5",
        # No modifications provided
    )

    assert result["isError"] is True
    assert "At least one modification" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_plan_remove_static_route_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful static route removal plan."""
    import routeros_mcp.mcp_tools.routing as routing_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = "lab"
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_routing_writes = True
            self.management_ip = "192.168.1.1"

    class FakeDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> FakeDevice:
            return FakeDevice(device_id)

    class FakePlanService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def create_plan(
            self,
            tool_name: str,
            created_by: str,
            device_ids: list[str],
            summary: str,
            changes: dict,
            risk_level: str = "medium",
        ) -> dict:
            return {
                "plan_id": "plan-rt-003",
                "approval_token": "approve-rt-def456",
                "approval_expires_at": "2025-12-20T16:00:00Z",
            }

    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(routing_tools, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(routing_tools, "PlanService", FakePlanService)
    monkeypatch.setattr(routing_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    routing_tools.register_routing_tools(mcp, settings)

    result = await mcp.tools["plan_remove_static_route"](
        device_ids=["dev-lab-01", "dev-lab-02"],
        route_id="*5",
    )

    assert result["isError"] is False
    assert "plan created successfully" in result["content"][0]["text"]
    assert "WARNING" in result["content"][0]["text"]
    assert "unreachable" in result["content"][0]["text"]
    assert result["_meta"]["plan_id"] == "plan-rt-003"
    assert result["_meta"]["risk_level"] == "high"  # Removals are always high risk
