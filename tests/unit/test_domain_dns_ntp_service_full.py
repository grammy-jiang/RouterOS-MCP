from __future__ import annotations

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import dns_ntp as dns_ntp_module
from routeros_mcp.domain.services.dns_ntp import DNSNTPService
from routeros_mcp.mcp.errors import ValidationError


class _FakeRestClient:
    def __init__(self):
        self.closed = False
        self.calls: list[tuple[str, dict | None]] = []
        self.data = {
            "/rest/ip/dns": {
                "servers": "8.8.8.8,1.1.1.1",
                "allow-remote-requests": True,
                "cache-size": 2048,
                "cache-used": 123,
            },
            "/rest/ip/dns/cache": [
                {"name": "example.com", "type": "A", "data": "93.184.216.34", "ttl": 100},
                {"name": "example.net", "type": "AAAA", "data": "2001:db8::1", "ttl": 50},
            ],
            "/rest/system/ntp/client": {
                "servers": "0.pool.ntp.org,1.pool.ntp.org",
                "enabled": True,
                "mode": "unicast",
            },
            "/rest/system/ntp/client/monitor": {"synced": True, "stratum": 2, "offset": 1.5},
        }

    async def get(self, path: str):
        self.calls.append((path, None))
        if path == "/rest/ip/dns/cache/flush":
            return {}
        return self.data.get(path, {})

    async def post(self, path: str, payload: dict):
        self.calls.append((path, payload))
        return {}

    async def patch(self, path: str, payload: dict):
        self.calls.append((path, payload))
        return {}

    async def close(self):
        self.closed = True


class _FakeDeviceService:
    def __init__(self, client: _FakeRestClient):
        self.client = client

    async def get_device(self, device_id: str):
        return {"id": device_id, "environment": "lab"}

    async def get_rest_client(self, device_id: str):
        return self.client


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch):
    client = _FakeRestClient()
    monkeypatch.setattr(
        dns_ntp_module, "DeviceService", lambda *args, **kwargs: _FakeDeviceService(client)
    )

    # Safeguard validators live in routeros_mcp.security.safeguards
    monkeypatch.setattr(
        "routeros_mcp.security.safeguards.validate_dns_servers", lambda servers: None
    )
    monkeypatch.setattr(
        "routeros_mcp.security.safeguards.validate_ntp_servers", lambda servers: None
    )
    monkeypatch.setattr(
        "routeros_mcp.security.safeguards.create_dry_run_response",
        lambda operation, device_id, planned_changes: {
            "operation": operation,
            "device_id": device_id,
            "planned_changes": planned_changes,
            "dry_run": True,
        },
    )

    return client


@pytest.mark.asyncio
async def test_get_dns_and_cache(fake_env):
    client = fake_env
    service = DNSNTPService(session=None, settings=Settings())

    status = await service.get_dns_status("dev-1")
    assert status["dns_servers"] == ["8.8.8.8", "1.1.1.1"]

    cache, total = await service.get_dns_cache("dev-1", limit=1)
    assert total == 2
    assert len(cache) == 1

    with pytest.raises(ValidationError):
        await service.get_dns_cache("dev-1", limit=dns_ntp_module.MAX_DNS_CACHE_ENTRIES + 1)

    assert client.closed is True


@pytest.mark.asyncio
async def test_get_ntp_status_with_monitor(fake_env):
    client = fake_env
    service = DNSNTPService(session=None, settings=Settings())

    ntp = await service.get_ntp_status("dev-1")
    assert ntp["status"] == "synchronized"
    assert ntp["ntp_servers"] == ["0.pool.ntp.org", "1.pool.ntp.org"]
    assert client.closed is True


@pytest.mark.asyncio
async def test_get_ntp_status_without_monitor(fake_env):
    client = fake_env
    client.data.pop("/rest/system/ntp/client/monitor", None)
    service = DNSNTPService(session=None, settings=Settings())

    ntp = await service.get_ntp_status("dev-1")
    # When monitor endpoint is missing we fall back to client status; ensure it's one of expected
    # reported states (may be "not_synchronized" when monitor data is absent).
    assert ntp["status"] in ("enabled", "disabled", "not_synchronized")


@pytest.mark.asyncio
async def test_update_dns_servers_paths(fake_env):
    client = fake_env
    service = DNSNTPService(session=None, settings=Settings())

    # No change
    result = await service.update_dns_servers("dev-1", ["8.8.8.8", "1.1.1.1"], dry_run=False)
    assert result["changed"] is False

    # Dry run
    result = await service.update_dns_servers("dev-1", ["9.9.9.9"], dry_run=True)
    assert result["dry_run"] is True

    # Apply change
    result = await service.update_dns_servers("dev-1", ["9.9.9.9"], dry_run=False)
    assert result["changed"] is True
    assert any(
        call[0] == "/rest/ip/dns" and call[1] == {"servers": "9.9.9.9"} for call in client.calls
    )


@pytest.mark.asyncio
async def test_flush_dns_cache(fake_env):
    client = fake_env
    service = DNSNTPService(session=None, settings=Settings())

    result = await service.flush_dns_cache("dev-1")
    assert result["entries_flushed"] == 2
    assert any(call[0] == "/rest/ip/dns/cache/flush" for call in client.calls)


@pytest.mark.asyncio
async def test_update_ntp_servers_paths(fake_env):
    client = fake_env
    service = DNSNTPService(session=None, settings=Settings())

    # No change
    result = await service.update_ntp_servers(
        "dev-1", ["0.pool.ntp.org", "1.pool.ntp.org"], enabled=True
    )
    assert result["changed"] is False

    # Dry run
    result = await service.update_ntp_servers(
        "dev-1", ["time.example.com"], enabled=False, dry_run=True
    )
    assert result["dry_run"] is True

    # Apply change
    result = await service.update_ntp_servers(
        "dev-1", ["time.example.com"], enabled=True, dry_run=False
    )
    assert result["changed"] is True
    assert any(
        call[0] == "/rest/system/ntp/client"
        and isinstance(call[1], dict)
        and call[1].get("servers") == "time.example.com"
        for call in client.calls
    )
