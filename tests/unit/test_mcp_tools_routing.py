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
