from __future__ import annotations

from types import SimpleNamespace

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp.errors import MCPError
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


@pytest.mark.asyncio
async def test_ping_tool_success_formats_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.diagnostics as diagnostics_tools

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

    class StubDiagnosticsService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def ping(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {
                "packets_sent": 4,
                "packets_received": 4,
                "packet_loss_percent": 0.0,
                "min_rtt_ms": 1.0,
                "avg_rtt_ms": 2.0,
                "max_rtt_ms": 3.0,
                "responses": [1.0, 2.0, 3.0, 2.0],
            }

    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsService", StubDiagnosticsService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    result = await mcp.tools["ping"](device_id="dev-1", target="8.8.8.8")

    assert result["isError"] is False
    assert "Ping to 8.8.8.8" in result["content"][0]["text"]
    assert result["_meta"]["packets_sent"] == 4


@pytest.mark.asyncio
async def test_ping_tool_maps_unexpected_exception_to_mcp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.diagnostics as diagnostics_tools

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

    class StubDiagnosticsService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def ping(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            raise ValueError("boom")

    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsService", StubDiagnosticsService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    with pytest.raises(MCPError):
        await mcp.tools["ping"](device_id="dev-1", target="8.8.8.8")


@pytest.mark.asyncio
async def test_traceroute_tool_success_formats_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.diagnostics as diagnostics_tools

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

    class StubDiagnosticsService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def traceroute(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {"hops": [{"hop": 1}, {"hop": 2}]}

    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsService", StubDiagnosticsService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    result = await mcp.tools["traceroute"](device_id="dev-1", target="1.1.1.1")

    assert result["isError"] is False
    assert "Traceroute to 1.1.1.1" in result["content"][0]["text"]
    assert len(result["_meta"]["hops"]) == 2


@pytest.mark.asyncio
async def test_ping_tool_reraises_mcp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.diagnostics as diagnostics_tools

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

    class StubDiagnosticsService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def ping(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {}

    def _deny(*_args: object, **_kwargs: object) -> None:
        raise MCPError("denied")

    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsService", StubDiagnosticsService)
    monkeypatch.setattr(diagnostics_tools, "check_tool_authorization", _deny)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    with pytest.raises(MCPError, match="denied"):
        await mcp.tools["ping"](device_id="dev-1", target="8.8.8.8")


@pytest.mark.asyncio
async def test_traceroute_tool_maps_unexpected_exception_to_mcp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.diagnostics as diagnostics_tools

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

    class StubDiagnosticsService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def traceroute(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError("boom")

    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsService", StubDiagnosticsService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    with pytest.raises(MCPError):
        await mcp.tools["traceroute"](device_id="dev-1", target="1.1.1.1")


@pytest.mark.asyncio
async def test_traceroute_tool_reraises_mcp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.diagnostics as diagnostics_tools

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

    class StubDiagnosticsService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def traceroute(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {}

    def _deny(*_args: object, **_kwargs: object) -> None:
        raise MCPError("denied")

    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsService", StubDiagnosticsService)
    monkeypatch.setattr(diagnostics_tools, "check_tool_authorization", _deny)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    with pytest.raises(MCPError, match="denied"):
        await mcp.tools["traceroute"](device_id="dev-1", target="1.1.1.1")
