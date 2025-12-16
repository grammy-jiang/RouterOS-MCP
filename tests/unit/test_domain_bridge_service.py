"""Unit tests for bridge service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import bridge as bridge_module
from routeros_mcp.infra.routeros.exceptions import RouterOSTimeoutError


class _FakeRestClient:
    """Fake REST client for testing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, dict | None]] = []
        self.store = {
            "/rest/interface/bridge": [
                {
                    ".id": "*1",
                    "name": "bridge1",
                    "mtu": 1500,
                    "actual-mtu": 1500,
                    "l2mtu": 1514,
                    "mac-address": "78:9A:18:A2:F3:D4",
                    "arp": "enabled",
                    "arp-timeout": "auto",
                    "disabled": False,
                    "running": True,
                    "auto-mac": True,
                    "ageing-time": "5m",
                    "priority": "0x8000",
                    "protocol-mode": "rstp",
                    "fast-forward": True,
                    "vlan-filtering": False,
                    "comment": "Main bridge",
                },
                {
                    ".id": "*2",
                    "name": "bridge2",
                    "mtu": 1500,
                    "actual-mtu": 1500,
                    "l2mtu": 1514,
                    "mac-address": "78:9A:18:A2:F3:D5",
                    "disabled": True,
                    "running": False,
                    "protocol-mode": "stp",
                    "vlan-filtering": True,
                    "comment": "",
                },
            ],
            "/rest/interface/bridge/port": [
                {
                    ".id": "*1",
                    "interface": "ether2",
                    "bridge": "bridge1",
                    "disabled": False,
                    "hw": True,
                    "pvid": 1,
                    "priority": "0x80",
                    "path-cost": 10,
                    "horizon": "none",
                    "edge": "auto",
                    "point-to-point": "auto",
                    "learn": "auto",
                    "trusted": False,
                    "frame-types": "admit-all",
                    "ingress-filtering": False,
                    "tag-stacking": False,
                    "comment": "LAN port",
                },
                {
                    ".id": "*2",
                    "interface": "ether3",
                    "bridge": "bridge1",
                    "disabled": False,
                    "hw": True,
                    "pvid": 10,
                    "priority": "0x80",
                    "path-cost": 10,
                    "comment": "",
                },
                {
                    ".id": "*3",
                    "interface": "ether4",
                    "bridge": "bridge2",
                    "disabled": True,
                    "hw": False,
                    "pvid": 1,
                    "comment": "",
                },
            ],
        }

    async def get(self, path: str, params: dict | None = None):
        self.calls.append(("get", path, params))
        return self.store.get(path, {})

    async def close(self):
        self.calls.append(("close", None, None))


class _FakeSSHClient:
    """Fake SSH client for testing."""

    def __init__(self, output: str = "") -> None:
        self.calls: list[tuple[str]] = []
        self.output = output

    async def execute(self, command: str):
        self.calls.append((command,))
        return self.output

    async def close(self):
        self.calls.append(("close",))


class _FakeDeviceService:
    """Fake device service for testing."""

    def __init__(self, rest_client: _FakeRestClient, ssh_client: _FakeSSHClient | None = None) -> None:
        self.rest_client = rest_client
        self.ssh_client = ssh_client
        self.device = SimpleNamespace(
            id="dev-1",
            name="router-1",
            environment="lab",
            routeros_version="7.15",
            hardware_model="rb5009",
            system_identity="router-1",
        )

    async def get_device(self, device_id: str):
        return self.device

    async def get_rest_client(self, device_id: str):
        return self.rest_client

    async def get_ssh_client(self, device_id: str):
        if self.ssh_client is None:
            raise RuntimeError("SSH client not configured")
        return self.ssh_client


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch):
    """Set up fake environment for testing."""
    rest_client = _FakeRestClient()
    device_service = _FakeDeviceService(rest_client)

    monkeypatch.setattr(bridge_module, "DeviceService", lambda *args, **kwargs: device_service)

    return rest_client, device_service


@pytest.mark.asyncio
async def test_list_bridges_via_rest(fake_env):
    """Test listing bridges via REST API."""
    client, _ = fake_env
    service = bridge_module.BridgeService(session=None, settings=Settings())

    bridges = await service.list_bridges("dev-1")

    # Check we got the right number of bridges
    assert len(bridges) == 2

    # Check first bridge details
    assert bridges[0]["name"] == "bridge1"
    assert bridges[0]["mac_address"] == "78:9A:18:A2:F3:D4"
    assert bridges[0]["protocol_mode"] == "rstp"
    assert bridges[0]["running"] is True
    assert bridges[0]["disabled"] is False
    assert bridges[0]["vlan_filtering"] is False
    assert bridges[0]["comment"] == "Main bridge"
    assert bridges[0]["transport"] == "rest"
    assert bridges[0]["fallback_used"] is False

    # Check second bridge details
    assert bridges[1]["name"] == "bridge2"
    assert bridges[1]["protocol_mode"] == "stp"
    assert bridges[1]["running"] is False
    assert bridges[1]["disabled"] is True
    assert bridges[1]["vlan_filtering"] is True

    # Verify REST client was called
    assert any(call[0] == "get" and call[1] == "/rest/interface/bridge" for call in client.calls)
    assert any(call[0] == "close" for call in client.calls)


@pytest.mark.asyncio
async def test_list_bridge_ports_via_rest(fake_env):
    """Test listing bridge ports via REST API."""
    client, _ = fake_env
    service = bridge_module.BridgeService(session=None, settings=Settings())

    ports = await service.list_bridge_ports("dev-1")

    # Check we got the right number of ports
    assert len(ports) == 3

    # Check first port details
    assert ports[0]["interface"] == "ether2"
    assert ports[0]["bridge"] == "bridge1"
    assert ports[0]["disabled"] is False
    assert ports[0]["hw"] is True
    assert ports[0]["pvid"] == 1
    assert ports[0]["priority"] == "0x80"
    assert ports[0]["path_cost"] == 10
    assert ports[0]["comment"] == "LAN port"
    assert ports[0]["transport"] == "rest"
    assert ports[0]["fallback_used"] is False

    # Check second port details (VLAN 10)
    assert ports[1]["interface"] == "ether3"
    assert ports[1]["bridge"] == "bridge1"
    assert ports[1]["pvid"] == 10

    # Check third port details (disabled)
    assert ports[2]["interface"] == "ether4"
    assert ports[2]["bridge"] == "bridge2"
    assert ports[2]["disabled"] is True
    assert ports[2]["hw"] is False

    # Verify REST client was called
    assert any(call[0] == "get" and call[1] == "/rest/interface/bridge/port" for call in client.calls)
    assert any(call[0] == "close" for call in client.calls)


@pytest.mark.asyncio
async def test_list_bridges_ssh_fallback(monkeypatch: pytest.MonkeyPatch):
    """Test bridge listing falls back to SSH when REST fails."""
    # Create SSH client with sample output
    ssh_output = """Flags: R - RUNNING; D - DISABLED
Columns: NAME, MTU, ACTUAL-MTU, MAC-ADDRESS, PROTOCOL-MODE
 #     NAME       MTU   ACTUAL-MTU  MAC-ADDRESS        PROTOCOL-MODE
 0  R  bridge1    auto  1500        78:9A:18:A2:F3:D4  rstp
 1     bridge2    1500  1500        78:9A:18:A2:F3:D5  stp
"""
    ssh_client = _FakeSSHClient(ssh_output)

    # Create REST client that will fail
    failing_rest_client = _FakeRestClient()

    # Create device service with both clients
    device_service = _FakeDeviceService(failing_rest_client, ssh_client)

    monkeypatch.setattr(bridge_module, "DeviceService", lambda *args, **kwargs: device_service)

    # Mock the REST method to raise timeout error
    async def failing_rest(*args, **kwargs):
        raise RouterOSTimeoutError("Timeout")

    service = bridge_module.BridgeService(session=None, settings=Settings())
    monkeypatch.setattr(service, "_list_bridges_via_rest", failing_rest)

    # Call should fall back to SSH
    bridges = await service.list_bridges("dev-1")

    # Verify we got bridges from SSH
    assert len(bridges) == 2
    assert bridges[0]["name"] == "bridge1"
    assert bridges[0]["running"] is True
    assert bridges[0]["transport"] == "ssh"
    assert bridges[0]["fallback_used"] is True

    assert bridges[1]["name"] == "bridge2"
    assert bridges[1]["running"] is False

    # Verify SSH client was called
    assert any("/interface/bridge/print" in call for call in ssh_client.calls)


@pytest.mark.asyncio
async def test_list_bridge_ports_ssh_fallback(monkeypatch: pytest.MonkeyPatch):
    """Test bridge port listing falls back to SSH when REST fails."""
    # Create SSH client with sample output
    ssh_output = """Flags: H - HW-OFFLOAD; I - INACTIVE; D - DISABLED
Columns: INTERFACE, BRIDGE, HW, PVID, PRIORITY, PATH-COST
 #     INTERFACE  BRIDGE    HW  PVID  PRIORITY  PATH-COST
 0  H  ether2     bridge1   yes 1     0x80      10
 1  H  ether3     bridge1   yes 10    0x80      10
 2     ether4     bridge2   no  1     0x80      10
"""
    ssh_client = _FakeSSHClient(ssh_output)

    # Create REST client that will fail
    failing_rest_client = _FakeRestClient()

    # Create device service with both clients
    device_service = _FakeDeviceService(failing_rest_client, ssh_client)

    monkeypatch.setattr(bridge_module, "DeviceService", lambda *args, **kwargs: device_service)

    # Mock the REST method to raise timeout error
    async def failing_rest(*args, **kwargs):
        raise RouterOSTimeoutError("Timeout")

    service = bridge_module.BridgeService(session=None, settings=Settings())
    monkeypatch.setattr(service, "_list_bridge_ports_via_rest", failing_rest)

    # Call should fall back to SSH
    ports = await service.list_bridge_ports("dev-1")

    # Verify we got ports from SSH
    assert len(ports) == 3
    assert ports[0]["interface"] == "ether2"
    assert ports[0]["bridge"] == "bridge1"
    assert ports[0]["hw"] is True
    assert ports[0]["pvid"] == 1
    assert ports[0]["transport"] == "ssh"
    assert ports[0]["fallback_used"] is True

    assert ports[1]["interface"] == "ether3"
    assert ports[1]["pvid"] == 10

    assert ports[2]["interface"] == "ether4"
    assert ports[2]["bridge"] == "bridge2"
    assert ports[2]["disabled"] is False  # D flag not set, so disabled is False
    assert ports[2]["hw"] is False

    # Verify SSH client was called
    assert any("/interface/bridge/port/print" in call for call in ssh_client.calls)


@pytest.mark.asyncio
async def test_parse_bridge_output_various_formats():
    """Test parsing bridge output with various RouterOS formats."""
    # Test with different flag combinations
    output = """Flags: R - RUNNING; D - DISABLED
 #     NAME       MTU   ACTUAL-MTU  MAC-ADDRESS        PROTOCOL-MODE
 0  R  bridge1    auto  1500        78:9A:18:A2:F3:D4  rstp
 1  D  bridge2    1500  1500        78:9A:18:A2:F3:D5  stp
 2     bridge3    auto  1500        78:9A:18:A2:F3:D6  none
"""

    bridges = bridge_module.BridgeService._parse_bridge_print_output(output)

    assert len(bridges) == 3
    assert bridges[0]["running"] is True
    assert bridges[0]["disabled"] is False
    assert bridges[1]["running"] is False
    assert bridges[1]["disabled"] is True
    assert bridges[2]["running"] is False
    assert bridges[2]["disabled"] is False


@pytest.mark.asyncio
async def test_parse_bridge_port_output_various_formats():
    """Test parsing bridge port output with various RouterOS formats."""
    # Test with different flag combinations
    output = """Flags: H - HW-OFFLOAD; I - INACTIVE; D - DISABLED
 #     INTERFACE  BRIDGE    HW  PVID  PRIORITY  PATH-COST
 0  H  ether2     bridge1   yes 1     0x80      10
 1  D  ether3     bridge1   no  100   0x90      20
 2  HI ether4     bridge2   yes 1     0x80      10
"""

    ports = bridge_module.BridgeService._parse_bridge_port_print_output(output)

    assert len(ports) == 3
    assert ports[0]["disabled"] is False
    assert ports[0]["hw"] is True
    assert ports[0]["pvid"] == 1
    assert ports[1]["disabled"] is True
    assert ports[1]["hw"] is False
    assert ports[1]["pvid"] == 100
    assert ports[2]["disabled"] is False  # D flag not set
