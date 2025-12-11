import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import ip as ip_module
from routeros_mcp.security import safeguards


class FakeDevice:
    def __init__(self, device_id="dev1"):
        self.id = device_id
        self.management_address = "10.0.0.1"


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


class FakeDeviceService:
    def __init__(self, *_args, **_kwargs):
        self.client = FakeRestClient()
        self.devices = {}
        self.requests = []

    async def get_device(self, device_id):
        self.requests.append(device_id)
        return FakeDevice(device_id)

    async def get_rest_client(self, device_id):
        self.requests.append(device_id)
        return self.client


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


@pytest.mark.asyncio
async def test_get_address(service):
    svc, _ = service
    addr = await svc.get_address("dev1", "*1")
    assert addr["id"] == "*1"
    assert addr["network"] == "10.0.0.0"


@pytest.mark.asyncio
async def test_get_arp_table(service):
    svc, _ = service
    arp = await svc.get_arp_table("dev1")
    assert arp[0]["mac_address"] == "00:11:22:33:44:55"


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
