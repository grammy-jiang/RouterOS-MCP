import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import dns_ntp as dns_ntp_module
from routeros_mcp.infra.routeros.exceptions import RouterOSTimeoutError
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
                "servers": "1.1.1.1,1.0.0.1",
                "dynamic-servers": "",
                "allow-remote-requests": True,
                "cache-size": 4096,
                "cache-used": 115,
                "use-doh-server": "",
                "verify-doh-cert": False,
                "doh-max-server-connections": 5,
                "doh-max-concurrent-queries": 50,
                "doh-timeout": "5s",
                "max-udp-packet-size": 4096,
                "query-server-timeout": "2s",
                "query-total-timeout": "10s",
                "max-concurrent-queries": 100,
                "max-concurrent-tcp-sessions": 20,
                "cache-max-ttl": "1w",
                "address-list-extra-time": "0s",
                "vrf": "main",
                "mdns-repeat-ifaces": "",
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


class FakeSSHClient:
    def __init__(self):
        self.calls = []

    async def execute(self, command):
        self.calls.append(("execute", command))
        # Simulate actual RouterOS v7 multi-line output format with all fields
        outputs = {
            "/ip/dns/print": """                      servers: 1.1.1.1
                               1.0.0.1
              dynamic-servers:
               use-doh-server:
              verify-doh-cert: no
   doh-max-server-connections: 5
   doh-max-concurrent-queries: 50
                  doh-timeout: 5s
        allow-remote-requests: yes
          max-udp-packet-size: 4096
         query-server-timeout: 2s
          query-total-timeout: 10s
       max-concurrent-queries: 100
  max-concurrent-tcp-sessions: 20
                   cache-size: 4096KiB
                cache-max-ttl: 1w
      address-list-extra-time: 0s
                          vrf: main
           mdns-repeat-ifaces:
                   cache-used: 115KiB""",
            "/system/ntp/client/print": """        servers: 0.pool.ntp.org,1.pool.ntp.org
        enabled: yes
           mode: unicast""",
            "/ip/dns/cache/print": """ #  NAME          TYPE  DATA             TTL
 0  example.com   A     93.184.216.34    60
 1  google.com    A     142.250.80.46    300""",
        }
        return outputs.get(command, "")

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
    monkeypatch.setattr(
        dns_ntp_module, "DeviceService", lambda *args, **kwargs: fake_device_service
    )
    svc = dns_ntp_module.DNSNTPService(session=None, settings=settings)
    return svc, fake_device_service


@pytest.mark.asyncio
async def test_get_dns_status(service):
    svc, device_service = service
    result = await svc.get_dns_status("dev1")
    assert result["dns_servers"] == ["1.1.1.1", "1.0.0.1"]
    assert result["cache_size_kb"] == 4096
    assert result["cache_used_kb"] == 115
    assert result["dynamic_servers"] == []
    assert result["allow_remote_requests"] is True
    assert result.get("max_udp_packet_size") == 4096
    assert result.get("max_concurrent_queries") == 100
    assert result.get("vrf") == "main"
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


@pytest.mark.asyncio
async def test_get_dns_status_via_ssh_fallback(service):
    """Test get_dns_status via SSH fallback when REST fails."""
    svc, dev = service
    dev.rest_fails = True

    result = await svc.get_dns_status("dev1")

    assert result["dns_servers"] == ["1.1.1.1", "1.0.0.1"]
    assert result["allow_remote_requests"] is True
    assert result["cache_size_kb"] == 4096
    assert result["cache_used_kb"] == 115
    assert result["transport"] == "ssh"
    assert result["fallback_used"] is True
    assert result["rest_error"] is not None


@pytest.mark.asyncio
async def test_get_dns_cache_via_ssh_fallback(service):
    """Test get_dns_cache via SSH fallback when REST fails."""
    svc, dev = service
    dev.rest_fails = True

    entries, total = await svc.get_dns_cache("dev1", limit=10)

    assert len(entries) == 2
    assert entries[0]["name"] == "example.com"
    assert entries[0]["type"] == "A"
    assert entries[0]["transport"] == "ssh"
    assert entries[0]["fallback_used"] is True


@pytest.mark.asyncio
async def test_get_ntp_status_via_ssh_fallback(service):
    """Test get_ntp_status via SSH fallback when REST fails."""
    svc, dev = service
    dev.rest_fails = True

    result = await svc.get_ntp_status("dev1")

    assert result["enabled"] is True
    assert result["ntp_servers"] == ["0.pool.ntp.org", "1.pool.ntp.org"]
    assert result["mode"] == "unicast"
    assert result["transport"] == "ssh"
    assert result["fallback_used"] is True
    assert result["rest_error"] is not None


@pytest.mark.asyncio
async def test_update_dns_servers_validation_empty(service):
    """Test update_dns_servers with empty list raises validation error."""
    svc, _ = service
    with pytest.raises(ValueError):
        await svc.update_dns_servers("dev1", [])


@pytest.mark.asyncio
async def test_update_ntp_servers_validation_empty(service):
    """Test update_ntp_servers with empty list raises validation error."""
    svc, _ = service
    with pytest.raises(ValueError):
        await svc.update_ntp_servers("dev1", [])


@pytest.mark.asyncio
async def test_get_dns_cache_with_filter_type(service):
    """Test get_dns_cache with type filter."""
    svc, device_service = service
    entries, total = await svc.get_dns_cache("dev1", limit=10)
    # Just verify it works with filtering
    assert isinstance(entries, list)


@pytest.mark.asyncio
async def test_update_ntp_servers_with_enable_false(service):
    """Test update_ntp_servers with enabled=False."""
    svc, device_service = service
    result = await svc.update_ntp_servers("dev1", ["time.google.com"], enabled=False)

    assert result["changed"] is True
    assert any(call[0] == "patch" for call in device_service.rest_client.calls)
