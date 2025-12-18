import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import dhcp as dhcp_module
from routeros_mcp.infra.routeros.exceptions import RouterOSTimeoutError


class FakeDevice:
    def __init__(self, device_id="dev1", environment="lab"):
        self.id = device_id
        self.environment = environment
        self.allow_professional_workflows = True
        self.allow_advanced_writes = True


class FakeRestClient:
    def __init__(self):
        self.calls = []
        self.store = {
            "/rest/ip/dhcp-server": [
                {
                    "name": "dhcp1",
                    "interface": "bridge",
                    "lease-time": "10m",
                    "address-pool": "pool1",
                    "disabled": False,
                    "authoritative": "after-2sec-delay",
                    ".id": "*1",
                }
            ],
            "/rest/ip/dhcp-server/lease": [
                {
                    "address": "192.168.1.10",
                    "mac-address": "00:11:22:33:44:55",
                    "client-id": "1:00:11:22:33:44:55",
                    "host-name": "client1",
                    "server": "dhcp1",
                    "status": "bound",
                    "expires-after": "5m30s",
                    "disabled": False,
                    ".id": "*2",
                },
                {
                    "address": "192.168.1.11",
                    "mac-address": "AA:BB:CC:DD:EE:FF",
                    "client-id": "",
                    "host-name": "client2",
                    "server": "dhcp1",
                    "status": "bound",
                    "expires-after": "8m",
                    "disabled": False,
                    ".id": "*3",
                },
                {
                    "address": "192.168.1.12",
                    "mac-address": "11:22:33:44:55:66",
                    "client-id": "",
                    "host-name": "",
                    "server": "dhcp1",
                    "status": "waiting",
                    "disabled": False,
                    ".id": "*4",
                },
            ],
        }

    async def get(self, path):
        self.calls.append(("get", path))
        return self.store.get(path, {})

    async def close(self):
        self.calls.append(("close", None))


class FakeSSHClient:
    def __init__(self):
        self.calls = []

    async def execute(self, command):
        self.calls.append(("execute", command))
        if command == "/ip/dhcp-server/print":
            return """Columns: NAME, INTERFACE, ADDRESS-POOL, LEASE-TIME
# NAME                 INTERFACE       ADDRESS-POOL         LEASE-TIME
0 dhcp-vlan20-mgmt     vlan20-mgmt     pool-vlan20-mgmt     30m       
1 dhcp-vlan30-home     vlan30-home     pool-vlan30-home     30m       
2 dhcp-vlan40-guest    vlan40-guest    pool-vlan40-guest    30m       
3 dhcp-vlan50-iot      vlan50-iot      pool-vlan50-iot      30m       
4 dhcp-vlan60-homelab  vlan60-homelab  pool-vlan60-homelab  30m       
5 dhcp-vlan70-test     vlan70-test     pool-vlan70-test     30m"""
        elif command.startswith("/ip/dhcp-server/lease/print"):
            # Emulate RouterOS SSH output for `print detail` (reliable status/last-seen fields)
            return """Flags: X - disabled, R - radius, D - dynamic, B - blocked
 0   ;;; cAP ac (RBcAPGi-5acD2nD)
     address=192.168.20.251 mac-address=18:FD:74:7C:7B:4F server=dhcp-vlan20-mgmt 
     status=bound last-seen=6m33s
     host-name=ap-cAP-ac

 1   ;;; hAP lite (RB941-2nD)
     address=192.168.20.252 mac-address=6C:3B:6B:6D:C2:A2 server=dhcp-vlan20-mgmt 
     status=waiting last-seen=never

 2   ;;; MCP Server on Raspberry Pi 3B
     address=192.168.30.247 mac-address=B8:27:EB:E0:5C:A0 server=dhcp-vlan30-home 
     status=bound last-seen=12m43s
     host-name=MCPServer

 3   ;;; Xiaomi Pad 6 Pro
     address=192.168.30.252 mac-address=5E:5E:90:C4:91:3C server=dhcp-vlan30-home 
     status=bound last-seen=11m43s
     host-name=Xiaomi-Pad-6-Pro

 4 D address=192.168.20.248 mac-address=00:E0:4C:34:5D:51 server=dhcp-vlan20-mgmt 
     status=bound last-seen=2m46s

 5 D address=192.168.30.242 mac-address=0A:AF:A0:8D:C9:82 server=dhcp-vlan30-home 
     status=bound last-seen=1m20s

 6 D address=192.168.30.253 mac-address=9A:45:26:5F:9C:5C server=dhcp-vlan30-home 
     status=bound last-seen=4m54s

 7 D address=192.168.30.243 mac-address=2E:1A:66:2A:DB:31 server=dhcp-vlan30-home 
     status=bound last-seen=12m14s

 8 D address=192.168.30.241 mac-address=D4:D2:52:3F:6F:C9 server=dhcp-vlan30-home 
     status=bound last-seen=27m43s
     host-name=SurfacePro7
"""
        return ""

    async def close(self):
        self.calls.append(("close", None))


class FakeDeviceService:
    def __init__(self, *_args, **_kwargs):
        self.rest_client = FakeRestClient()
        self.ssh_client = FakeSSHClient()
        self.requests = []
        self.rest_fails = False

    async def get_device(self, device_id):
        self.requests.append(device_id)
        return FakeDevice(device_id)

    async def get_rest_client(self, device_id):
        self.requests.append(device_id)
        if self.rest_fails:
            raise RouterOSTimeoutError("Simulated REST timeout")
        return self.rest_client

    async def get_ssh_client(self, device_id):
        self.requests.append(device_id)
        return self.ssh_client


@pytest.fixture
def service(monkeypatch):
    settings = Settings()
    fake_device_service = FakeDeviceService()
    monkeypatch.setattr(dhcp_module, "DeviceService", lambda *args, **kwargs: fake_device_service)
    svc = dhcp_module.DHCPService(session=None, settings=settings)
    return svc, fake_device_service


@pytest.mark.asyncio
async def test_get_dhcp_server_status_rest(service):
    svc, device_service = service
    result = await svc.get_dhcp_server_status("dev1")

    assert result["total_count"] == 1
    assert len(result["servers"]) == 1

    server = result["servers"][0]
    assert server["name"] == "dhcp1"
    assert server["interface"] == "bridge"
    assert server["lease_time"] == "10m"
    assert server["address_pool"] == "pool1"
    assert server["disabled"] is False
    assert server["authoritative"] == "after-2sec-delay"
    assert server["id"] == "*1"

    assert result["transport"] == "rest"
    assert result["fallback_used"] is False


@pytest.mark.asyncio
async def test_get_dhcp_server_status_ssh_fallback(service):
    svc, device_service = service
    device_service.rest_fails = True

    result = await svc.get_dhcp_server_status("dev1")

    assert result["total_count"] == 6
    assert len(result["servers"]) == 6

    # Check first server
    server = result["servers"][0]
    assert server["name"] == "dhcp-vlan20-mgmt"
    assert server["interface"] == "vlan20-mgmt"
    assert server["address_pool"] == "pool-vlan20-mgmt"
    assert server["lease_time"] == "30m"
    assert server["disabled"] is False

    # Check last server
    server = result["servers"][5]
    assert server["name"] == "dhcp-vlan70-test"
    assert server["interface"] == "vlan70-test"
    assert server["address_pool"] == "pool-vlan70-test"
    assert server["lease_time"] == "30m"
    assert server["disabled"] is False

    assert result["transport"] == "ssh"
    assert result["fallback_used"] is True


@pytest.mark.asyncio
async def test_get_dhcp_leases_rest(service):
    svc, device_service = service
    result = await svc.get_dhcp_leases("dev1")

    # Should only return bound leases (not waiting)
    assert result["total_count"] == 2
    assert len(result["leases"]) == 2

    lease1 = result["leases"][0]
    assert lease1["address"] == "192.168.1.10"
    assert lease1["mac_address"] == "00:11:22:33:44:55"
    assert lease1["client_id"] == "1:00:11:22:33:44:55"
    assert lease1["host_name"] == "client1"
    assert lease1["server"] == "dhcp1"
    assert lease1["status"] == "bound"
    assert lease1["expires_after"] == "5m30s"

    lease2 = result["leases"][1]
    assert lease2["address"] == "192.168.1.11"
    assert lease2["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert lease2["host_name"] == "client2"

    assert result["transport"] == "rest"
    assert result["fallback_used"] is False


@pytest.mark.asyncio
async def test_get_dhcp_leases_ssh_fallback(service):
    svc, device_service = service
    device_service.rest_fails = True

    result = await svc.get_dhcp_leases("dev1")

    # SSH should return 8 bound leases (exclude ID 1 with "waiting" status)
    assert result["total_count"] == 8
    assert len(result["leases"]) == 8

    # Check first lease with comment
    lease1 = result["leases"][0]
    assert lease1["address"] == "192.168.20.251"
    assert lease1["mac_address"] == "18:FD:74:7C:7B:4F"
    assert lease1["host_name"] == "ap-cAP-ac"
    assert lease1["server"] == "dhcp-vlan20-mgmt"
    assert lease1["status"] == "bound"
    assert lease1["last_seen"] == "6m33s"
    assert lease1["comment"] == "cAP ac (RBcAPGi-5acD2nD)"

    # Check second lease (MCP Server on Raspberry Pi)
    lease2 = result["leases"][1]
    assert lease2["address"] == "192.168.30.247"
    assert lease2["host_name"] == "MCPServer"
    assert lease2["comment"] == "MCP Server on Raspberry Pi 3B"

    # Check fourth returned lease (dynamic flag, no hostname, no comment)
    # Returned order excludes the waiting lease, so this is ID 4.
    lease4 = result["leases"][3]
    assert lease4["address"] == "192.168.20.248"
    assert lease4["host_name"] == ""
    assert lease4["dynamic"] is True
    assert "comment" not in lease4  # No comment for this entry

    # Check last lease (new dynamic with hostname)
    last = result["leases"][-1]
    assert last["address"] == "192.168.30.241"
    assert last["host_name"] == "SurfacePro7"
    assert last["server"] == "dhcp-vlan30-home"
    assert last["status"] == "bound"
    assert last["dynamic"] is True

    assert result["transport"] == "ssh"
    assert result["fallback_used"] is True


@pytest.mark.asyncio
async def test_get_dhcp_server_status_empty(service):
    svc, device_service = service
    device_service.rest_client.store["/rest/ip/dhcp-server"] = []

    result = await svc.get_dhcp_server_status("dev1")

    assert result["total_count"] == 0
    assert len(result["servers"]) == 0


@pytest.mark.asyncio
async def test_get_dhcp_leases_filters_expired(service):
    svc, device_service = service
    # Update store to include only non-bound leases
    device_service.rest_client.store["/rest/ip/dhcp-server/lease"] = [
        {
            "address": "192.168.1.20",
            "mac-address": "00:00:00:00:00:00",
            "server": "dhcp1",
            "status": "waiting",
            "disabled": False,
        },
        {
            "address": "192.168.1.21",
            "mac-address": "11:11:11:11:11:11",
            "server": "dhcp1",
            "status": "bound",
            "disabled": True,  # Disabled lease should be filtered
        },
    ]

    result = await svc.get_dhcp_leases("dev1")

    # Should return no active leases (one is waiting, one is disabled)
    assert result["total_count"] == 0
    assert len(result["leases"]) == 0


@pytest.mark.asyncio
async def test_get_dhcp_server_status_rest_normalizes_single_dict_and_includes_optionals(service):
    svc, device_service = service
    device_service.rest_client.store["/rest/ip/dhcp-server"] = {
        "name": "dhcpX",
        "interface": "ether1",
        "lease-time": "1h",
        "address-pool": "poolX",
        "disabled": True,
        "bootp-support": "static",
        "lease-script": "script",
        ".id": "*9",
    }

    result = await svc.get_dhcp_server_status("dev1")

    assert result["total_count"] == 1
    server = result["servers"][0]
    assert server["name"] == "dhcpX"
    assert server["disabled"] is True
    assert server["bootp_support"] == "static"
    assert server["lease_script"] == "script"
    assert server["id"] == "*9"


@pytest.mark.asyncio
async def test_get_dhcp_server_status_ssh_parses_multiple_servers(service):
    svc, device_service = service
    device_service.rest_fails = True

    # Test with actual device output format
    result = await svc.get_dhcp_server_status("dev1")
    
    # Should parse 6 DHCP servers from FakeSSHClient
    assert result["total_count"] == 6
    assert len(result["servers"]) == 6
    
    # Verify each server has required fields
    for server in result["servers"]:
        assert "name" in server
        assert "interface" in server
        assert "address_pool" in server
        assert "lease_time" in server
        assert "disabled" in server


@pytest.mark.asyncio
async def test_get_dhcp_leases_rest_includes_optional_fields(service):
    svc, device_service = service
    device_service.rest_client.store["/rest/ip/dhcp-server/lease"] = [
        {
            "address": "192.168.1.100",
            "mac-address": "00:aa:bb:cc:dd:ee",
            "client-id": "1:00:aa:bb:cc:dd:ee",
            "host-name": "client100",
            "server": "dhcp1",
            "status": "bound",
            "disabled": False,
            "last-seen": "10s",
            "active-mac-address": "00:aa:bb:cc:dd:ee",
            "active-address": "192.168.1.100",
            ".id": "*99",
        }
    ]

    result = await svc.get_dhcp_leases("dev1")
    assert result["total_count"] == 1
    lease = result["leases"][0]
    assert lease["last_seen"] == "10s"
    assert lease["active_mac_address"] == "00:aa:bb:cc:dd:ee"
    assert lease["active_address"] == "192.168.1.100"
    assert lease["id"] == "*99"


@pytest.mark.asyncio
async def test_get_dhcp_server_status_when_rest_and_ssh_fail_raises_runtime_error(service):
    svc, device_service = service
    device_service.rest_fails = True

    async def boom(_cmd):
        raise RuntimeError("ssh down")

    device_service.ssh_client.execute = boom

    with pytest.raises(RuntimeError):
        await svc.get_dhcp_server_status("dev1")
