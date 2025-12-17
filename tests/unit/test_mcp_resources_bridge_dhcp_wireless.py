from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp.errors import DeviceNotFoundError, MCPError
from routeros_mcp.mcp_resources import bridge as bridge_resources
from routeros_mcp.mcp_resources import dhcp as dhcp_resources
from routeros_mcp.mcp_resources import wireless as wireless_resources

from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


@dataclass
class _FakeDevice:
    id: str
    name: str = "router-1"
    environment: str = "lab"


@pytest.mark.asyncio
async def test_bridge_resource_success_includes_member_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeDeviceService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def get_device(self, device_id: str) -> _FakeDevice:
            return _FakeDevice(id=device_id)

    class _FakeBridgeService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def list_bridges(self, _device_id: str) -> list[dict[str, Any]]:
            return [{"name": "bridge1"}, {"name": "bridge2"}]

        async def list_bridge_ports(self, _device_id: str) -> list[dict[str, Any]]:
            return [
                {"bridge": "bridge1", "interface": "ether1"},
                {"bridge": "bridge1", "interface": "ether2"},
                {"bridge": "bridge2", "interface": "wlan1"},
            ]

    monkeypatch.setattr(bridge_resources, "DeviceService", _FakeDeviceService)
    monkeypatch.setattr(bridge_resources, "BridgeService", _FakeBridgeService)

    mcp = DummyMCP()
    bridge_resources.register_bridge_resources(mcp, FakeSessionFactory(), Settings(environment="lab"))

    func = mcp.resources["device://{device_id}/bridges"]
    payload = json.loads(await func("dev-1"))

    assert payload["device_id"] == "dev-1"
    assert payload["total_bridges"] == 2
    assert payload["total_ports"] == 3

    b1 = next(b for b in payload["bridges"] if b["name"] == "bridge1")
    assert {p["interface"] for p in b1["member_ports"]} == {"ether1", "ether2"}


@pytest.mark.asyncio
async def test_bridge_resource_device_not_found_maps_to_mcp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeDeviceService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def get_device(self, device_id: str) -> _FakeDevice:
            raise DeviceNotFoundError("missing", data={"device_id": device_id})

    class _FakeBridgeService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def list_bridges(self, _device_id: str) -> list[dict[str, Any]]:
            return []

        async def list_bridge_ports(self, _device_id: str) -> list[dict[str, Any]]:
            return []

    monkeypatch.setattr(bridge_resources, "DeviceService", _FakeDeviceService)
    monkeypatch.setattr(bridge_resources, "BridgeService", _FakeBridgeService)

    mcp = DummyMCP()
    bridge_resources.register_bridge_resources(mcp, FakeSessionFactory(), Settings(environment="lab"))

    func = mcp.resources["device://{device_id}/bridges"]
    with pytest.raises(MCPError) as excinfo:
        await func("missing")

    assert excinfo.value.code == -32002


@pytest.mark.asyncio
async def test_bridge_resource_generic_error_maps_to_mcp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeDeviceService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def get_device(self, device_id: str) -> _FakeDevice:
            return _FakeDevice(id=device_id)

    class _FakeBridgeService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def list_bridges(self, _device_id: str) -> list[dict[str, Any]]:
            raise RuntimeError("boom")

        async def list_bridge_ports(self, _device_id: str) -> list[dict[str, Any]]:
            return []

    monkeypatch.setattr(bridge_resources, "DeviceService", _FakeDeviceService)
    monkeypatch.setattr(bridge_resources, "BridgeService", _FakeBridgeService)

    mcp = DummyMCP()
    bridge_resources.register_bridge_resources(mcp, FakeSessionFactory(), Settings(environment="lab"))

    func = mcp.resources["device://{device_id}/bridges"]
    with pytest.raises(MCPError) as excinfo:
        await func("dev-1")

    assert excinfo.value.code == -32000


@pytest.mark.asyncio
async def test_dhcp_resources_server_and_leases_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeDeviceService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def get_device(self, _device_id: str) -> dict[str, Any]:
            return {"id": "dev-1"}

    class _FakeDHCPService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def get_dhcp_server_status(self, _device_id: str) -> dict[str, Any]:
            return {
                "servers": [{"name": "dhcp1", "interface": "bridge1"}],
                "total_count": 1,
                "transport": "rest",
                "fallback_used": False,
            }

        async def get_dhcp_leases(self, _device_id: str) -> dict[str, Any]:
            return {
                "leases": [{"address": "192.168.1.10", "mac-address": "aa:bb:cc:dd:ee:ff"}],
                "total_count": 1,
                "transport": "rest",
                "fallback_used": False,
            }

    monkeypatch.setattr(dhcp_resources, "DeviceService", _FakeDeviceService)
    monkeypatch.setattr(dhcp_resources, "DHCPService", _FakeDHCPService)

    mcp = DummyMCP()
    dhcp_resources.register_dhcp_resources(mcp, FakeSessionFactory(), Settings(environment="lab"))

    server_func = mcp.resources["device://{device_id}/dhcp-server"]
    leases_func = mcp.resources["device://{device_id}/dhcp-leases"]

    server_payload = json.loads(await server_func("dev-1"))
    assert server_payload["total_count"] == 1
    assert server_payload["servers"][0]["name"] == "dhcp1"

    leases_payload = json.loads(await leases_func("dev-1"))
    assert leases_payload["total_count"] == 1
    assert leases_payload["leases"][0]["address"] == "192.168.1.10"


@pytest.mark.asyncio
async def test_dhcp_resources_propagate_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeDeviceService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def get_device(self, _device_id: str) -> dict[str, Any]:
            return {"id": "dev-1"}

    class _BoomDHCPService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def get_dhcp_server_status(self, _device_id: str) -> dict[str, Any]:
            raise RuntimeError("explode")

        async def get_dhcp_leases(self, _device_id: str) -> dict[str, Any]:
            raise RuntimeError("explode")

    monkeypatch.setattr(dhcp_resources, "DeviceService", _FakeDeviceService)
    monkeypatch.setattr(dhcp_resources, "DHCPService", _BoomDHCPService)

    mcp = DummyMCP()
    dhcp_resources.register_dhcp_resources(mcp, FakeSessionFactory(), Settings(environment="lab"))

    server_func = mcp.resources["device://{device_id}/dhcp-server"]
    leases_func = mcp.resources["device://{device_id}/dhcp-leases"]

    with pytest.raises(RuntimeError, match="explode"):
        await server_func("dev-1")

    with pytest.raises(RuntimeError, match="explode"):
        await leases_func("dev-1")


@pytest.mark.asyncio
async def test_wireless_resources_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeDeviceService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def get_device(self, device_id: str) -> _FakeDevice:
            return _FakeDevice(id=device_id)

    class _FakeWirelessService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, Any]]:
            return [{"name": "wlan1", "ssid": "test"}]

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, Any]]:
            return [{"mac-address": "aa:bb:cc:dd:ee:ff", "interface": "wlan1"}]

    monkeypatch.setattr(wireless_resources, "DeviceService", _FakeDeviceService)
    monkeypatch.setattr(wireless_resources, "WirelessService", _FakeWirelessService)

    mcp = DummyMCP()
    wireless_resources.register_wireless_resources(mcp, FakeSessionFactory(), Settings(environment="lab"))

    cfg_func = mcp.resources["device://{device_id}/wireless"]
    clients_func = mcp.resources["device://{device_id}/wireless/clients"]

    cfg = json.loads(await cfg_func("dev-1"))
    assert cfg["total_interfaces"] == 1

    clients = json.loads(await clients_func("dev-1"))
    assert clients["total_clients"] == 1


@pytest.mark.asyncio
async def test_wireless_resources_map_errors_to_device_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeDeviceService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def get_device(self, device_id: str) -> _FakeDevice:
            return _FakeDevice(id=device_id)

    class _BoomWirelessService:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, Any]]:
            raise RuntimeError("boom")

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, Any]]:
            raise RuntimeError("boom")

    monkeypatch.setattr(wireless_resources, "DeviceService", _FakeDeviceService)
    monkeypatch.setattr(wireless_resources, "WirelessService", _BoomWirelessService)

    mcp = DummyMCP()
    wireless_resources.register_wireless_resources(mcp, FakeSessionFactory(), Settings(environment="lab"))

    cfg_func = mcp.resources["device://{device_id}/wireless"]
    clients_func = mcp.resources["device://{device_id}/wireless/clients"]

    with pytest.raises(DeviceNotFoundError):
        await cfg_func("dev-1")

    with pytest.raises(DeviceNotFoundError):
        await clients_func("dev-1")
