"""Unit tests for CAPsMAN MCP tools."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from routeros_mcp.config import Settings
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


@pytest.mark.asyncio
async def test_get_capsman_remote_caps_tool_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_capsman_remote_caps tool returns formatted result."""
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

        async def get_capsman_remote_caps(self, _device_id: str) -> list[dict[str, object]]:
            return [
                {
                    "id": "*1",
                    "name": "cap-ap-1",
                    "address": "192.168.1.10",
                    "identity": "CAP-Office-AP",
                    "state": "authorized",
                },
                {
                    "id": "*2",
                    "name": "cap-ap-2",
                    "address": "192.168.1.11",
                    "identity": "CAP-Lobby-AP",
                    "state": "provisioning",
                },
            ]

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_capsman_remote_caps"](device_id="dev-1")

    assert result["isError"] is False
    assert result["_meta"]["total_count"] == 2
    assert len(result["_meta"]["remote_caps"]) == 2
    assert result["_meta"]["remote_caps"][0]["name"] == "cap-ap-1"
    assert result["_meta"]["remote_caps"][1]["name"] == "cap-ap-2"
    assert "Found 2 remote CAP device(s)" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_get_capsman_remote_caps_tool_when_not_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_capsman_remote_caps tool when CAPsMAN not present."""
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

        async def get_capsman_remote_caps(self, _device_id: str) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_capsman_remote_caps"](device_id="dev-1")

    assert result["isError"] is False
    assert result["_meta"]["total_count"] == 0
    assert len(result["_meta"]["remote_caps"]) == 0
    assert "No remote CAPs found" in result["content"][0]["text"]
    assert "not be a CAPsMAN controller" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_get_capsman_registrations_tool_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_capsman_registrations tool returns formatted result."""
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

        async def get_capsman_registrations(self, _device_id: str) -> list[dict[str, object]]:
            return [
                {
                    "id": "*a",
                    "interface": "cap-ap-1",
                    "mac_address": "11:22:33:44:55:66",
                    "ssid": "CorpWiFi",
                },
                {
                    "id": "*b",
                    "interface": "cap-ap-1",
                    "mac_address": "77:88:99:aa:bb:cc",
                    "ssid": "CorpWiFi",
                },
                {
                    "id": "*c",
                    "interface": "cap-ap-2",
                    "mac_address": "aa:bb:cc:dd:ee:ff",
                    "ssid": "GuestWiFi",
                },
            ]

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_capsman_registrations"](device_id="dev-1")

    assert result["isError"] is False
    assert result["_meta"]["total_count"] == 3
    assert len(result["_meta"]["registrations"]) == 3
    assert result["_meta"]["registrations"][0]["mac_address"] == "11:22:33:44:55:66"
    assert result["_meta"]["registrations"][2]["ssid"] == "GuestWiFi"
    assert "Found 3 active CAPsMAN registration(s)" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_get_capsman_registrations_tool_when_not_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_capsman_registrations tool when CAPsMAN not present."""
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

        async def get_capsman_registrations(self, _device_id: str) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_capsman_registrations"](device_id="dev-1")

    assert result["isError"] is False
    assert result["_meta"]["total_count"] == 0
    assert len(result["_meta"]["registrations"]) == 0
    assert "No CAPsMAN registrations found" in result["content"][0]["text"]
    assert "not be a CAPsMAN controller" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_get_capsman_tools_when_service_raises_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CAPsMAN tools when service raises exception."""
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

        async def get_capsman_remote_caps(self, _device_id: str) -> list[dict[str, object]]:
            raise RuntimeError("Network error")

        async def get_capsman_registrations(self, _device_id: str) -> list[dict[str, object]]:
            raise RuntimeError("Connection failed")

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    # Test remote-caps error handling
    result1 = await mcp.tools["get_capsman_remote_caps"](device_id="dev-1")
    assert result1["isError"] is True
    assert "Network error" in result1["content"][0]["text"]

    # Test registrations error handling
    result2 = await mcp.tools["get_capsman_registrations"](device_id="dev-1")
    assert result2["isError"] is True
    assert "Connection failed" in result2["content"][0]["text"]
