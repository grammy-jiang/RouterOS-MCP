import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import dns_ntp as dns_ntp_module
from routeros_mcp.mcp.errors import ValidationError


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
            "/rest/ip/dns": {
                "servers": "1.1.1.1,2.2.2.2",
                "allow-remote-requests": True,
                "cache-size": 2048,
                "cache-used": 128,
            },
            "/rest/system/ntp/client": {
                "servers": "0.pool.ntp.org,1.pool.ntp.org",
                "enabled": True,
                "mode": "unicast",
            },
            "/rest/system/ntp/client/monitor": {"synced": True, "stratum": 2, "offset": 1.5},
            "/rest/ip/dns/cache": [
                {"name": "example.com", "type": "A", "data": "93.184.216.34", "ttl": 60}
            ],
        }

    async def get(self, path):
        self.calls.append(("get", path))
        return self.store.get(path, {})

    async def patch(self, path, payload):
        self.calls.append(("patch", path, payload))
        self.store[path] = payload
        return payload

    async def post(self, path, payload):
        self.calls.append(("post", path, payload))
        return {}

    async def close(self):
        self.calls.append(("close", None))


class FakeDeviceService:
    def __init__(self, *_args, **_kwargs):
        self.rest_client = FakeRestClient()
        self.requests = []

    async def get_device(self, device_id):
        self.requests.append(device_id)
        return FakeDevice(device_id)

    async def get_rest_client(self, device_id):
        self.requests.append(device_id)
        return self.rest_client


@pytest.fixture
def service(monkeypatch):
    settings = Settings()
    fake_device_service = FakeDeviceService()
    monkeypatch.setattr(
        dns_ntp_module, "DeviceService", lambda *args, **kwargs: fake_device_service
    )
    svc = dns_ntp_module.DNSNTPService(session=None, settings=settings)
    return svc, fake_device_service


@pytest.mark.asyncio
async def test_get_dns_status(service):
    svc, device_service = service
    result = await svc.get_dns_status("dev1")
    assert result["dns_servers"] == ["1.1.1.1", "2.2.2.2"]
    assert device_service.requests


@pytest.mark.asyncio
async def test_get_dns_cache(service):
    svc, device_service = service
    entries, total = await svc.get_dns_cache("dev1", limit=10)
    assert len(entries) == 1
    assert total == 1


@pytest.mark.asyncio
async def test_get_dns_cache_limit_error(service):
    svc, _ = service
    with pytest.raises(ValidationError):
        await svc.get_dns_cache("dev1", limit=dns_ntp_module.MAX_DNS_CACHE_ENTRIES + 1)


@pytest.mark.asyncio
async def test_update_dns_servers(service):
    svc, device_service = service
    result = await svc.update_dns_servers("dev1", ["9.9.9.9"], dry_run=True)
    assert result["dry_run"] is True

    result_apply = await svc.update_dns_servers("dev1", ["8.8.8.8"], dry_run=False)
    assert result_apply["changed"] is True
    assert device_service.rest_client.calls


@pytest.mark.asyncio
async def test_flush_dns_cache(service):
    svc, device_service = service
    result = await svc.flush_dns_cache("dev1")
    assert result["changed"] is True
    # ensure flush called
    assert any(call[0] == "post" for call in device_service.rest_client.calls)


@pytest.mark.asyncio
async def test_update_ntp_servers(service):
    svc, device_service = service
    result_dry = await svc.update_ntp_servers("dev1", ["time.google.com"], dry_run=True)
    assert result_dry["dry_run"]

    result_apply = await svc.update_ntp_servers("dev1", ["time.cloudflare.com"], enabled=True)
    assert result_apply["changed"]
    assert any(call[0] == "patch" for call in device_service.rest_client.calls)
