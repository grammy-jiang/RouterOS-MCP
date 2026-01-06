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


@pytest.mark.asyncio
async def test_traceroute_streaming_yields_progress_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test traceroute with stream_progress=True yields progress messages."""
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
            return {
                "hops": [
                    {"hop": 1, "address": "192.168.1.1", "rtt_ms": 1.5},
                    {"hop": 2, "address": "10.0.0.1", "rtt_ms": 12.3},
                    {"hop": 3, "address": "8.8.8.8", "rtt_ms": 25.7},
                ],
                "target": "8.8.8.8",
            }

    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsService", StubDiagnosticsService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    # Call traceroute with stream_progress=True
    result_generator = await mcp.tools["traceroute"](
        device_id="dev-1", 
        target="8.8.8.8",
        stream_progress=True,
    )

    # Collect all yielded events
    events = []
    async for event in result_generator:
        events.append(event)

    # Verify we got progress events
    progress_events = [e for e in events if e.get("type") == "progress"]
    assert len(progress_events) >= 3, "Should have at least 3 progress events (starting + 3 hops)"

    # Verify starting message
    assert any("Starting traceroute" in e.get("message", "") for e in progress_events)

    # Verify hop progress messages
    hop_progress = [e for e in progress_events if "Hop" in e.get("message", "")]
    assert len(hop_progress) == 3, "Should have 3 hop progress messages"

    # Verify final result
    final_result = events[-1]
    assert "content" in final_result
    assert "isError" in final_result
    assert final_result["isError"] is False
    assert "_meta" in final_result
    assert final_result["_meta"]["total_hops"] == 3
    assert final_result["_meta"]["reached_target"] is True


@pytest.mark.asyncio
async def test_traceroute_non_streaming_returns_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test traceroute with stream_progress=False returns dict immediately."""
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
            return {
                "hops": [
                    {"hop": 1, "address": "192.168.1.1", "rtt_ms": 1.5},
                    {"hop": 2, "address": "10.0.0.1", "rtt_ms": 12.3},
                ],
                "target": "8.8.8.8",
            }

    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsService", StubDiagnosticsService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    # Call traceroute with stream_progress=False (default)
    result = await mcp.tools["traceroute"](device_id="dev-1", target="8.8.8.8")

    # Should return dict immediately, not async generator
    assert isinstance(result, dict)
    assert result["isError"] is False
    assert "Traceroute to 8.8.8.8" in result["content"][0]["text"]
    assert len(result["_meta"]["hops"]) == 2


@pytest.mark.asyncio
async def test_traceroute_streaming_handles_timeout_hops(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test traceroute streaming handles hops with timeouts (*)."""
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
            return {
                "hops": [
                    {"hop": 1, "address": "192.168.1.1", "rtt_ms": 1.5},
                    {"hop": 2, "address": "*", "rtt_ms": 0.0},  # Timeout hop
                    {"hop": 3, "address": "8.8.8.8", "rtt_ms": 25.7},
                ],
                "target": "8.8.8.8",
            }

    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsService", StubDiagnosticsService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    result_generator = await mcp.tools["traceroute"](
        device_id="dev-1",
        target="8.8.8.8",
        stream_progress=True,
    )

    events = []
    async for event in result_generator:
        events.append(event)

    # Verify timeout hop is handled
    progress_events = [e for e in events if e.get("type") == "progress"]
    timeout_messages = [e for e in progress_events if "timeout" in e.get("message", "").lower()]
    assert len(timeout_messages) >= 1, "Should have at least one timeout message"

    # Verify data field has null for timeout hop
    timeout_data = [e.get("data", {}) for e in timeout_messages]
    assert any(d.get("ip") is None for d in timeout_data)


@pytest.mark.asyncio
async def test_traceroute_streaming_unreachable_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test traceroute streaming when target is unreachable."""
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
            return {
                "hops": [
                    {"hop": 1, "address": "192.168.1.1", "rtt_ms": 1.5},
                    {"hop": 2, "address": "*", "rtt_ms": 0.0},
                    {"hop": 3, "address": "*", "rtt_ms": 0.0},
                ],
                "target": "10.255.255.1",
            }

    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsService", StubDiagnosticsService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    result_generator = await mcp.tools["traceroute"](
        device_id="dev-1",
        target="10.255.255.1",
        stream_progress=True,
    )

    events = []
    async for event in result_generator:
        events.append(event)

    # Verify final result shows target not reached
    final_result = events[-1]
    assert final_result["_meta"]["reached_target"] is False
    assert "not reached" in final_result["content"][0]["text"]


@pytest.mark.asyncio
async def test_traceroute_tool_validates_max_hops_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test traceroute tool validates max_hops parameter through service layer."""
    import routeros_mcp.mcp_tools.diagnostics as diagnostics_tools
    from routeros_mcp.domain.services.diagnostics import MAX_TRACEROUTE_HOPS
    from routeros_mcp.mcp.errors import ValidationError

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class ValidatingDiagnosticsService:
        """Mock service that validates max_hops like the real one."""
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def traceroute(self, *_args: object, max_hops: int = 30, **_kwargs: object) -> dict[str, object]:
            # Replicate real validation logic
            if max_hops > MAX_TRACEROUTE_HOPS:
                raise ValidationError(
                    f"Traceroute max_hops cannot exceed {MAX_TRACEROUTE_HOPS}",
                    data={"requested_max_hops": max_hops, "max_hops": MAX_TRACEROUTE_HOPS},
                )
            if max_hops < 1:
                raise ValidationError(
                    "Traceroute max_hops must be at least 1",
                    data={"requested_max_hops": max_hops},
                )
            # Valid case - return dummy result
            return {
                "hops": [],
                "target": "8.8.8.8",
            }

    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsService", ValidatingDiagnosticsService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    # Test with max_hops=0 (too low) - should raise ValidationError
    with pytest.raises(ValidationError, match="max_hops must be at least 1"):
        await mcp.tools["traceroute"](device_id="dev-1", target="8.8.8.8", max_hops=0)

    # Test with max_hops=65 (too high) - should raise ValidationError
    with pytest.raises(ValidationError, match="max_hops cannot exceed 64"):
        await mcp.tools["traceroute"](device_id="dev-1", target="8.8.8.8", max_hops=65)

    # Test with max_hops=-1 (negative) - should raise ValidationError
    with pytest.raises(ValidationError, match="max_hops must be at least 1"):
        await mcp.tools["traceroute"](device_id="dev-1", target="8.8.8.8", max_hops=-1)
