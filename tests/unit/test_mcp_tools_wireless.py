from __future__ import annotations

from types import SimpleNamespace

import pytest

from routeros_mcp.config import Settings
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


@pytest.mark.asyncio
async def test_wireless_interfaces_tool_success_returns_formatted_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools

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

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return [{"id": "*1", "name": "wlan1"}]

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return [{"interface": "wlan1", "mac_address": "AA:BB:CC:DD:EE:FF"}]

        async def detect_capsman(self, _device_id: str) -> bool:
            return False

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_interfaces"](device_id="dev-1")

    assert result["isError"] is False
    assert result["_meta"]["total_count"] == 1


@pytest.mark.asyncio
async def test_wireless_clients_tool_when_service_raises_returns_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools

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

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            raise RuntimeError("boom")

        async def detect_capsman(self, _device_id: str) -> bool:
            return False

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_clients"](device_id="dev-1")

    assert result["isError"] is True
    assert "boom" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_wireless_interfaces_tool_when_mcp_error_returns_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools
    from routeros_mcp.mcp.errors import MCPError

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

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            raise MCPError("denied", data={"reason": "auth"})

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def detect_capsman(self, _device_id: str) -> bool:
            return False

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_interfaces"](device_id="dev-1")

    assert result["isError"] is True
    assert result["_meta"]["reason"] == "auth"


@pytest.mark.asyncio
async def test_wireless_interfaces_tool_when_generic_exception_returns_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools

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

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            raise RuntimeError("boom")

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def detect_capsman(self, _device_id: str) -> bool:
            return False

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_interfaces"](device_id="dev-1")

    assert result["isError"] is True
    assert "boom" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_wireless_clients_tool_when_mcp_error_returns_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools
    from routeros_mcp.mcp.errors import MCPError

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

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            raise MCPError("denied")

        async def detect_capsman(self, _device_id: str) -> bool:
            return False

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_clients"](device_id="dev-1")

    assert result["isError"] is True
    assert result["content"][0]["text"] == "denied"


@pytest.mark.asyncio
async def test_wireless_clients_tool_success_returns_formatted_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools

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

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return [{"interface": "wlan1", "mac_address": "AA:BB:CC:DD:EE:FF"}]

        async def detect_capsman(self, _device_id: str) -> bool:
            return False

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_clients"](device_id="dev-1")

    assert result["isError"] is False
    assert result["_meta"]["total_count"] == 1


@pytest.mark.asyncio
async def test_wireless_interfaces_tool_with_capsman_detected_includes_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that CAPsMAN hint is included when CAPsMAN is detected."""
    import routeros_mcp.mcp_tools.wireless as wireless_tools

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

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return [{"id": "*1", "name": "wlan1"}]

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def detect_capsman(self, _device_id: str) -> bool:
            return True

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_interfaces"](device_id="dev-1")

    assert result["isError"] is False
    assert result["_meta"]["total_count"] == 1
    assert "hints" in result["_meta"]
    assert len(result["_meta"]["hints"]) == 1
    assert result["_meta"]["hints"][0]["code"] == "capsman_detected"
    assert "CAPsMAN" in result["_meta"]["hints"][0]["message"]
    assert "centrally managed" in result["_meta"]["hints"][0]["message"]


@pytest.mark.asyncio
async def test_wireless_interfaces_tool_without_capsman_has_no_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that no CAPsMAN hint is included when CAPsMAN is not detected."""
    import routeros_mcp.mcp_tools.wireless as wireless_tools

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

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return [{"id": "*1", "name": "wlan1"}]

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def detect_capsman(self, _device_id: str) -> bool:
            return False

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_interfaces"](device_id="dev-1")

    assert result["isError"] is False
    assert result["_meta"]["total_count"] == 1
    assert "hints" not in result["_meta"]


@pytest.mark.asyncio
async def test_wireless_clients_tool_with_capsman_detected_includes_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that CAPsMAN hint is included for clients when CAPsMAN is detected."""
    import routeros_mcp.mcp_tools.wireless as wireless_tools

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

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return [{"interface": "wlan1", "mac_address": "AA:BB:CC:DD:EE:FF"}]

        async def detect_capsman(self, _device_id: str) -> bool:
            return True

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_clients"](device_id="dev-1")

    assert result["isError"] is False
    assert result["_meta"]["total_count"] == 1
    assert "hints" in result["_meta"]
    assert len(result["_meta"]["hints"]) == 1
    assert result["_meta"]["hints"][0]["code"] == "capsman_detected"
    assert "CAPsMAN" in result["_meta"]["hints"][0]["message"]
    assert "incomplete" in result["_meta"]["hints"][0]["message"]


@pytest.mark.asyncio
async def test_wireless_clients_tool_without_capsman_has_no_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that no CAPsMAN hint is included for clients when CAPsMAN is not detected."""
    import routeros_mcp.mcp_tools.wireless as wireless_tools

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

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return [{"interface": "wlan1", "mac_address": "AA:BB:CC:DD:EE:FF"}]

        async def detect_capsman(self, _device_id: str) -> bool:
            return False

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_clients"](device_id="dev-1")

    assert result["isError"] is False
    assert result["_meta"]["total_count"] == 1
    assert "hints" not in result["_meta"]
