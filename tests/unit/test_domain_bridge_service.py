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

    def __init__(
        self, rest_client: _FakeRestClient, ssh_client: _FakeSSHClient | None = None
    ) -> None:
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
    assert any(
        call[0] == "get" and call[1] == "/rest/interface/bridge/port" for call in client.calls
    )
    assert any(call[0] == "close" for call in client.calls)


@pytest.mark.asyncio
async def test_list_bridges_ssh_fallback(monkeypatch: pytest.MonkeyPatch):
    """Test bridge listing falls back to SSH when REST fails."""
    # Create SSH client with actual RouterOS multi-line output
    ssh_output = """Flags: D - dynamic; X - disabled, R - running 
 0  R name="bridge-lan" mtu=auto actual-mtu=1500 l2mtu=1514 arp=enabled arp-timeout=auto mac-address=78:9A:18:A2:F3:D3 protocol-mode=rstp fast-forward=yes igmp-snooping=yes 
      multicast-router=temporary-query multicast-querier=no startup-query-count=2 last-member-query-count=2 last-member-interval=1s membership-interval=4m20s querier-interval=4m15s query-interval=2m5s 
      query-response-interval=10s startup-query-interval=31s250ms igmp-version=2 mld-version=1 auto-mac=yes ageing-time=5m priority=0x8000 max-message-age=20s forward-delay=15s transmit-hold-count=6 
      vlan-filtering=yes ether-type=0x8100 pvid=1 frame-types=admit-all ingress-filtering=yes dhcp-snooping=no port-cost-mode=long mvrp=no max-learned-entries=auto 

 1  R ;;; Dedicated Loopback for Router-ID
      name="lo-router-id" mtu=auto actual-mtu=1500 l2mtu=65535 arp=enabled arp-timeout=auto mac-address=F2:7A:43:BA:E3:35 protocol-mode=rstp fast-forward=yes igmp-snooping=no auto-mac=yes 
      ageing-time=5m priority=0x8000 max-message-age=20s forward-delay=15s transmit-hold-count=6 vlan-filtering=no dhcp-snooping=no port-cost-mode=long mvrp=no max-learned-entries=auto
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
    assert bridges[0]["name"] == "bridge-lan"
    assert bridges[0]["mac_address"] == "78:9A:18:A2:F3:D3"
    assert bridges[0]["protocol_mode"] == "rstp"
    assert bridges[0]["running"] is True
    assert bridges[0]["vlan_filtering"] is True
    assert bridges[0]["transport"] == "ssh"
    assert bridges[0]["fallback_used"] is True

    assert bridges[1]["name"] == "lo-router-id"
    assert bridges[1]["mac_address"] == "F2:7A:43:BA:E3:35"
    assert bridges[1]["running"] is True
    assert bridges[1]["vlan_filtering"] is False

    # Verify SSH client was called
    assert any("/interface/bridge/print" in call for call in ssh_client.calls)


@pytest.mark.asyncio
async def test_list_bridge_ports_ssh_fallback(monkeypatch: pytest.MonkeyPatch):
    """Test bridge port listing falls back to SSH when REST fails."""
    # Create SSH client with actual RouterOS output from core-RB5009
    ssh_output = """Flags: I - INACTIVE; D - DYNAMIC; H - HW-OFFLOAD
Columns: INTERFACE, BRIDGE, HW, HORIZON, TRUSTED, FAST-LEAVE, BPDU-GUARD, EDGE, POINT-TO-POINT, PVID, FRAME-TYPES
 #     INTERFACE  BRIDGE      HW   HORIZON  TRUSTED  FAST-LEAVE  BPDU-GUARD  EDGE  POINT-TO-POINT  PVID  FRAME-TYPES
 0   H ether2     bridge-lan  yes  none     no       no          yes         auto  auto              20  admit-all  
 1 I H ether3     bridge-lan  yes  none     no       no          yes         auto  auto              30  admit-all  
 2 I H ether4     bridge-lan  yes  none     no       no          yes         auto  auto              60  admit-all  
;;; Uplink to ap-hAP-lite (trunk: VLAN20 untagged, 50 tagged)
 3 I H ether5     bridge-lan  yes  none     no       no          no          auto  auto              20  admit-all  
 4 I H ether6     bridge-lan  yes  none     no       no          yes         auto  auto              60  admit-all  
 5 I H ether7     bridge-lan  yes  none     no       no          yes         auto  auto              70  admit-all  
;;; Uplink to ap-cAP-ac (trunk: VLAN20 untagged, 30/40 tagged)
 6   H ether8     bridge-lan  yes  none     no       no          no          auto  auto              20  admit-all  
 7  D  cap3       bridge-lan       none     no       no          no          yes   no                30  admit-all  
 8 ID  cap4       bridge-lan       none     no       no          no          yes   no                40  admit-all  
 9  D  cap1       bridge-lan       none     no       no          no          yes   no                30  admit-all  
10 ID  cap2       bridge-lan       none     no       no          no          yes   no                40  admit-all  
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

    # Verify we got 11 ports
    assert len(ports) == 11

    # Port 0: ether2 - active, HW column=yes, PVID 20
    assert ports[0]["interface"] == "ether2"
    assert ports[0]["bridge"] == "bridge-lan"
    assert ports[0]["hw"] is True  # HW column = yes
    assert ports[0]["hw_offload_flag"] is True  # H flag present
    assert ports[0]["disabled"] is False  # No I flag
    assert ports[0]["pvid"] == 20
    assert ports[0]["transport"] == "ssh"
    assert ports[0]["fallback_used"] is True

    # Port 1: ether3 - inactive (I flag), HW column=yes, PVID 30
    assert ports[1]["interface"] == "ether3"
    assert ports[1]["bridge"] == "bridge-lan"
    assert ports[1]["hw"] is True  # HW column = yes
    assert ports[1]["disabled"] is True  # Has I flag
    assert ports[1]["pvid"] == 30

    # Port 7: cap3 - dynamic (D flag), HW column empty/no, PVID 30
    assert ports[7]["interface"] == "cap3"
    assert ports[7]["bridge"] == "bridge-lan"
    assert ports[7]["disabled"] is False  # D flag = dynamic, not inactive
    assert ports[7]["dynamic"] is True  # D flag present
    assert ports[7]["hw"] is False  # HW column empty
    assert ports[7]["pvid"] == 30

    # Port 8: cap4 - inactive and dynamic (ID flags), PVID 40
    assert ports[8]["interface"] == "cap4"
    assert ports[8]["disabled"] is True  # I flag = inactive
    assert ports[8]["dynamic"] is True  # D flag = dynamic
    assert ports[8]["pvid"] == 40

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
    # Test with actual RouterOS output format with flags and multiple columns
    output = """Flags: I - INACTIVE; D - DYNAMIC; H - HW-OFFLOAD
Columns: INTERFACE, BRIDGE, HW, HORIZON, TRUSTED, FAST-LEAVE, BPDU-GUARD, EDGE, POINT-TO-POINT, PVID, FRAME-TYPES
 #     INTERFACE  BRIDGE      HW   HORIZON  TRUSTED  FAST-LEAVE  BPDU-GUARD  EDGE  POINT-TO-POINT  PVID  FRAME-TYPES
 0   H ether2     bridge-lan  yes  none     no       no          yes         auto  auto              20  admit-all
 1 I H ether3     bridge-lan  yes  none     no       no          yes         auto  auto              30  admit-all
 2 I H ether4     bridge-lan  yes  none     no       no          yes         auto  auto              60  admit-all
 3  D  cap1       bridge-lan       none     no       no          no          yes   no                30  admit-all
 4 ID  cap2       bridge-lan       none     no       no          no          yes   no                40  admit-all
"""

    ports = bridge_module.BridgeService._parse_bridge_port_print_output(output)

    assert len(ports) == 5

    # Port 0: ether2 - HW column=yes, PVID 20, hw_offload_flag from H in margin
    assert ports[0]["interface"] == "ether2"
    assert ports[0]["bridge"] == "bridge-lan"
    assert ports[0]["hw"] is True  # HW column = yes
    assert ports[0]["hw_offload_flag"] is True  # H flag present in margin
    assert ports[0]["disabled"] is False  # No I flag
    assert ports[0]["pvid"] == 20

    # Port 1: ether3 - inactive (I flag), HW column=yes, PVID 30
    assert ports[1]["interface"] == "ether3"
    assert ports[1]["disabled"] is True  # I flag = inactive
    assert ports[1]["hw"] is True  # HW column = yes
    assert ports[1]["pvid"] == 30
    assert ports[1]["horizon"] == "none"
    assert ports[1]["edge"] == "auto"

    # Port 3: cap1 - dynamic (D flag), HW column empty, PVID 30, edge=yes
    assert ports[3]["interface"] == "cap1"
    assert ports[3]["disabled"] is False  # D flag = dynamic, not inactive
    assert ports[3]["dynamic"] is True  # D flag present
    assert ports[3]["hw"] is False  # HW column empty (no)
    assert ports[3]["pvid"] == 30
    assert ports[3]["edge"] == "yes"
    assert ports[3]["point_to_point"] == "no"

    # Port 4: cap2 - inactive and dynamic (I D or ID flags), PVID 40
    assert ports[4]["interface"] == "cap2"
    assert ports[4]["disabled"] is True  # I flag = inactive
    assert ports[4]["dynamic"] is True  # D flag = dynamic
    assert ports[4]["pvid"] == 40
