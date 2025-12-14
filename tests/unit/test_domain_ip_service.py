import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import ip as ip_module
from routeros_mcp.infra.routeros.exceptions import RouterOSTimeoutError
from routeros_mcp.security import safeguards


class FakeDevice:
    def __init__(self, device_id="dev1"):
        self.id = device_id
        self.management_ip = "10.0.0.1"
        self.management_port = 443


class FakeRestClient:
    def __init__(self):
        self.calls = []
        self.store = {
            "/rest/ip/address": [
                {
                    ".id": "*1",
                    "address": "10.0.0.2/24",
                    "network": "10.0.0.0",
                    "interface": "ether1",
                }
            ],
            "/rest/ip/address/*1": {
                ".id": "*1",
                "address": "10.0.0.2/24",
                "network": "10.0.0.0",
                "interface": "ether1",
            },
            "/rest/ip/arp": [
                {
                    "address": "10.0.0.3",
                    "mac-address": "00:11:22:33:44:55",
                    "interface": "ether1",
                    "status": "complete",
                }
            ],
        }

    async def get(self, path):
        self.calls.append(("get", path))
        return self.store.get(path, {})

    async def put(self, path, payload):
        self.calls.append(("put", path, payload))
        return {".id": "*2", **payload}

    async def delete(self, path):
        self.calls.append(("delete", path))
        return {}

    async def close(self):
        self.calls.append(("close", None))


class FakeSSHClient:
    def __init__(self):
        self.calls = []

    async def execute(self, command):
        self.calls.append(("execute", command))
        if command == "/ip/address/print":
            return """Flags: D - disabled, X - invalid
 #    ADDRESS            NETWORK         INTERFACE
 *1   10.0.0.2/24        10.0.0.0/24     ether1
 *2   10.0.0.5/24        10.0.0.0/24     ether2"""
        elif command == "/ip/arp/print":
            return """Flags: D - DYNAMIC; C - COMPLETE
Columns: ADDRESS, MAC-ADDRESS, INTERFACE, STATUS
#    ADDRESS         MAC-ADDRESS        INTERFACE    STATUS   
0 DC 10.0.0.3        00:11:22:33:44:55  ether1       reachable"""
        return ""

    async def close(self):
        self.calls.append(("close", None))


class FakeDeviceService:
    def __init__(self, *_args, **_kwargs):
        self.client = FakeRestClient()
        self.ssh_client = FakeSSHClient()
        self.devices = {}
        self.requests = []
        self.rest_fails = False  # Flag to make REST fail for testing fallback

    async def get_device(self, device_id):
        self.requests.append(device_id)
        return FakeDevice(device_id)

    async def get_rest_client(self, device_id):
        self.requests.append(device_id)
        if self.rest_fails:
            # Return a client that will raise timeout
            raise RouterOSTimeoutError("Simulated REST timeout")
        return self.client

    async def get_ssh_client(self, device_id):
        self.requests.append(device_id)
        return self.ssh_client


@pytest.fixture
def service(monkeypatch):
    settings = Settings()
    fake_device_service = FakeDeviceService()

    # patch safeguards to no-op
    monkeypatch.setattr(ip_module, "DeviceService", lambda *args, **kwargs: fake_device_service)
    monkeypatch.setattr(safeguards, "validate_ip_address_format", lambda addr: None)
    monkeypatch.setattr(safeguards, "check_ip_overlap", lambda addr, existing, iface: None)
    monkeypatch.setattr(safeguards, "check_management_ip_protection", lambda mgmt, addr: None)
    monkeypatch.setattr(
        safeguards,
        "create_dry_run_response",
        lambda operation, device_id, planned_changes: {
            "operation": operation,
            "device_id": device_id,
            "planned_changes": planned_changes,
            "dry_run": True,
        },
    )
    svc = ip_module.IPService(session=None, settings=settings)
    return svc, fake_device_service


@pytest.mark.asyncio
async def test_list_addresses(service):
    svc, dev = service
    addrs = await svc.list_addresses("dev1")
    assert addrs and addrs[0]["address"] == "10.0.0.2/24"
    assert addrs[0]["transport"] == "rest"
    assert addrs[0]["fallback_used"] is False


@pytest.mark.asyncio
async def test_get_address(service):
    svc, _ = service
    addr = await svc.get_address("dev1", "*1")
    assert addr["id"] == "*1"
    assert addr["network"] == "10.0.0.0"
    assert addr["transport"] == "rest"
    assert addr["fallback_used"] is False


@pytest.mark.asyncio
async def test_get_address_not_found_raises_error(service):
    """Test that get_address raises ValueError when address ID is not found via SSH."""
    svc, dev_svc = service
    
    # Make REST fail to trigger SSH fallback
    dev_svc.rest_fails = True
    
    # The fake SSH client only has *1 and *2 in its output, so *999 should raise ValueError
    # which then gets wrapped in RuntimeError by get_address
    with pytest.raises(RuntimeError, match="Get address failed via REST and SSH"):
        await svc.get_address("dev1", "*999")


@pytest.mark.asyncio
async def test_get_arp_table(service):
    svc, _ = service
    arp = await svc.get_arp_table("dev1")
    assert arp[0]["mac_address"] == "00:11:22:33:44:55"
    assert arp[0]["transport"] == "rest"
    assert arp[0]["fallback_used"] is False


@pytest.mark.asyncio
async def test_list_addresses_via_ssh_fallback(service):
    """Test SSH fallback when REST times out for list_addresses."""
    svc, dev = service
    dev.rest_fails = True  # Make REST fail

    addrs = await svc.list_addresses("dev1")
    assert addrs and addrs[0]["address"] == "10.0.0.2/24"
    assert addrs[0]["transport"] == "ssh"
    assert addrs[0]["fallback_used"] is True
    assert addrs[0]["rest_error"] is not None


@pytest.mark.asyncio
async def test_get_address_via_ssh_fallback(service):
    """Test SSH fallback when REST times out for get_address."""
    svc, dev = service
    dev.rest_fails = True  # Make REST fail

    addr = await svc.get_address("dev1", "*1")
    assert addr["address"] == "10.0.0.2/24"
    assert addr["transport"] == "ssh"
    assert addr["fallback_used"] is True
    assert addr["rest_error"] is not None


@pytest.mark.asyncio
async def test_get_arp_table_via_ssh_fallback(service):
    """Test SSH fallback when REST times out for get_arp_table."""
    svc, dev = service
    dev.rest_fails = True  # Make REST fail

    arp = await svc.get_arp_table("dev1")
    assert arp[0]["address"] == "10.0.0.3"
    assert arp[0]["transport"] == "ssh"
    assert arp[0]["fallback_used"] is True
    assert arp[0]["rest_error"] is not None


@pytest.mark.asyncio
async def test_parse_ip_address_print_output():
    """Test parsing of /ip/address/print output."""
    output = """Flags: D - disabled, X - invalid
 #    ADDRESS            NETWORK         INTERFACE
 *1   10.0.0.2/24        10.0.0.0/24     ether1
 *2 D 10.0.0.5/24        10.0.0.0/24     ether2"""

    result = ip_module.IPService._parse_ip_address_print_output(output)
    assert len(result) == 2
    assert result[0]["address"] == "10.0.0.2/24"
    assert result[0]["disabled"] is False
    assert result[1]["address"] == "10.0.0.5/24"
    assert result[1]["disabled"] is True


@pytest.mark.asyncio
async def test_parse_arp_table_print_output():
    """Test parsing of /ip/arp/print output with actual RouterOS format."""
    output = """Flags: D - DYNAMIC; C - COMPLETE
Columns: ADDRESS, MAC-ADDRESS, INTERFACE, STATUS
#    ADDRESS         MAC-ADDRESS        INTERFACE    STATUS   
0 DC 192.168.20.251  18:FD:74:7C:7B:4F  vlan20-mgmt  stale    
1 DC 192.168.20.248  00:E0:4C:34:5D:51  vlan20-mgmt  reachable
2 DC 192.168.1.1     98:03:8E:D0:38:9F  ether1       delay    
3 DC 192.168.30.242  0A:AF:A0:8D:C9:82  vlan30-home  reachable"""

    result = ip_module.IPService._parse_arp_table_print_output(output)
    assert len(result) == 4
    assert result[0]["address"] == "192.168.20.251"
    assert result[0]["mac_address"] == "18:FD:74:7C:7B:4F"
    assert result[0]["interface"] == "vlan20-mgmt"
    assert result[0]["status"] == "stale"
    assert result[1]["address"] == "192.168.20.248"
    assert result[1]["mac_address"] == "00:E0:4C:34:5D:51"
    assert result[1]["interface"] == "vlan20-mgmt"
    assert result[1]["status"] == "reachable"
    assert result[2]["address"] == "192.168.1.1"
    assert result[2]["interface"] == "ether1"
    assert result[3]["address"] == "192.168.30.242"
    assert result[3]["status"] == "reachable"


@pytest.mark.asyncio
async def test_add_secondary_address_dry_run(service):
    svc, _ = service
    result = await svc.add_secondary_address("dev1", "10.0.0.5/24", "ether1", dry_run=True)
    assert result["dry_run"] is True
    assert result["planned_changes"]["address"] == "10.0.0.5/24"


@pytest.mark.asyncio
async def test_add_secondary_address_apply(service):
    svc, dev = service
    result = await svc.add_secondary_address("dev1", "10.0.0.6/24", "ether1", dry_run=False)
    assert result["changed"] is True
    assert any(call[0] == "put" for call in dev.client.calls)


@pytest.mark.asyncio
async def test_remove_secondary_address_dry_run(service):
    svc, _ = service
    result = await svc.remove_secondary_address("dev1", "*1", dry_run=True)
    assert result["dry_run"] is True
    assert result["planned_changes"]["address_id"] == "*1"


@pytest.mark.asyncio
async def test_remove_secondary_address_apply(service):
    svc, dev = service
    result = await svc.remove_secondary_address("dev1", "*1", dry_run=False)
    assert result["changed"] is True
    assert any(call[0] == "delete" for call in dev.client.calls)
