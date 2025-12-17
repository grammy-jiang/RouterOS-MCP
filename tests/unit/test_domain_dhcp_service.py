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
            return """ #   NAME   INTERFACE  LEASE-TIME  ADDRESS-POOL
 0   dhcp1  bridge     10m         pool1"""
        elif command == "/ip/dhcp-server/lease/print":
            return """Flags: X - disabled, R - radius, D - dynamic, B - blocked
 #   ADDRESS        MAC-ADDRESS        CLIENT-ID          HOST-NAME    SERVER
 0 D 192.168.1.10   00:11:22:33:44:55  1:00:11:22:33:44:55 client1     dhcp1
 1 D 192.168.1.11   AA:BB:CC:DD:EE:FF                     client2     dhcp1
 2 X 192.168.1.12   11:22:33:44:55:66                                 dhcp1"""
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

    assert result["total_count"] == 1
    assert len(result["servers"]) == 1

    server = result["servers"][0]
    assert server["name"] == "dhcp1"
    assert server["interface"] == "bridge"
    assert server["lease_time"] == "10m"
    assert server["address_pool"] == "pool1"
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

    # SSH should return 2 active leases (D flag, not X)
    assert result["total_count"] == 2
    assert len(result["leases"]) == 2

    lease1 = result["leases"][0]
    assert lease1["address"] == "192.168.1.10"
    assert lease1["mac_address"] == "00:11:22:33:44:55"
    assert lease1["host_name"] == "client1"
    assert lease1["status"] == "bound"

    lease2 = result["leases"][1]
    assert lease2["address"] == "192.168.1.11"
    assert lease2["mac_address"] == "AA:BB:CC:DD:EE:FF"

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
