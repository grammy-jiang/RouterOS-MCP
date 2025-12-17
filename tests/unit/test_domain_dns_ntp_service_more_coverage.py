from __future__ import annotations

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import dns_ntp as dns_ntp_module
from routeros_mcp.domain.services.dns_ntp import DNSNTPService


class _FakeRestClient:
    def __init__(self, data: dict[str, object] | None = None, *, raise_on: set[str] | None = None):
        self.data = data or {}
        self.raise_on = raise_on or set()
        self.calls: list[tuple[str, dict | None]] = []
        self.closed = False

    async def get(self, path: str):
        self.calls.append((path, None))
        if path in self.raise_on:
            raise RuntimeError(f"boom: {path}")
        return self.data.get(path, {})

    async def post(self, path: str, payload: dict):
        self.calls.append((path, payload))
        return {}

    async def patch(self, path: str, payload: dict):
        self.calls.append((path, payload))
        return {}

    async def close(self) -> None:
        self.closed = True


class _FakeDeviceService:
    def __init__(self, client: _FakeRestClient):
        self.client = client

    async def get_device(self, device_id: str):
        return {"id": device_id, "environment": "lab"}

    async def get_rest_client(self, device_id: str):
        return self.client


@pytest.fixture
def patch_safeguards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("routeros_mcp.security.safeguards.validate_dns_servers", lambda _servers: None)
    monkeypatch.setattr("routeros_mcp.security.safeguards.validate_ntp_servers", lambda _servers: None)
    monkeypatch.setattr(
        "routeros_mcp.security.safeguards.create_dry_run_response",
        lambda operation, device_id, planned_changes: {
            "operation": operation,
            "device_id": device_id,
            "planned_changes": planned_changes,
            "dry_run": True,
        },
    )


@pytest.mark.asyncio
async def test_get_dns_status_rest_includes_optional_fields(
    monkeypatch: pytest.MonkeyPatch,
    patch_safeguards: None,
) -> None:
    client = _FakeRestClient(
        data={
            "/rest/ip/dns": {
                "servers": "8.8.8.8,1.1.1.1",
                "dynamic-servers": "10.0.0.1",
                "allow-remote-requests": True,
                "cache-size": 4096,
                "cache-used": 100,
                "use-doh-server": "https://dns.example/doh",
                "verify-doh-cert": True,
                "doh-max-server-connections": 10,
                "doh-max-concurrent-queries": 50,
                "doh-timeout": "2s",
                "max-udp-packet-size": 4096,
                "query-server-timeout": "1s",
                "query-total-timeout": "5s",
                "max-concurrent-queries": 200,
                "max-concurrent-tcp-sessions": 25,
            }
        }
    )

    monkeypatch.setattr(
        dns_ntp_module, "DeviceService", lambda *_a, **_k: _FakeDeviceService(client)
    )

    service = DNSNTPService(session=None, settings=Settings())
    status = await service.get_dns_status("dev-1")

    assert status["dns_servers"] == ["8.8.8.8", "1.1.1.1"]
    assert status["dynamic_servers"] == ["10.0.0.1"]

    # Optional fields should be surfaced when present
    assert status["use_doh_server"] == "https://dns.example/doh"
    assert status["verify_doh_cert"] is True
    assert status["doh_max_server_connections"] == 10
    assert status["doh_max_concurrent_queries"] == 50
    assert status["doh_timeout"] == "2s"
    assert status["max_udp_packet_size"] == 4096
    assert status["query_server_timeout"] == "1s"
    assert status["query_total_timeout"] == "5s"
    assert status["max_concurrent_queries"] == 200
    assert status["max_concurrent_tcp_sessions"] == 25


@pytest.mark.asyncio
async def test_get_dns_status_rest_servers_as_list(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRestClient(
        data={
            "/rest/ip/dns": {
                "servers": ["8.8.8.8", "1.1.1.1"],
                "dynamic-servers": ["10.0.0.1"],
                "allow-remote-requests": "yes",
            }
        }
    )

    monkeypatch.setattr(dns_ntp_module, "DeviceService", lambda *_a, **_k: _FakeDeviceService(client))

    service = DNSNTPService(session=None, settings=Settings())
    status = await service.get_dns_status("dev-1")

    assert status["dns_servers"] == ["8.8.8.8", "1.1.1.1"]
    assert status["dynamic_servers"] == ["10.0.0.1"]
    assert status["allow_remote_requests"] == "yes"


@pytest.mark.asyncio
async def test_get_ntp_status_rest_monitor_as_list_and_servers_as_list(
    monkeypatch: pytest.MonkeyPatch,
    patch_safeguards: None,
) -> None:
    client = _FakeRestClient(
        data={
            "/rest/system/ntp/client": {
                "servers": ["0.pool.ntp.org", "1.pool.ntp.org"],
                "dynamic-servers": ["2.pool.ntp.org"],
                "enabled": True,
                "mode": "unicast",
                "vrf": "main",
            },
            "/rest/system/ntp/client/monitor": [
                {
                    "synced": "yes",
                    "stratum": "3",
                    "offset": "5ms945us",
                    "server": "0.pool.ntp.org",
                    "synced-stratum": "4",
                }
            ],
        }
    )

    monkeypatch.setattr(
        dns_ntp_module, "DeviceService", lambda *_a, **_k: _FakeDeviceService(client)
    )

    service = DNSNTPService(session=None, settings=Settings())
    status = await service.get_ntp_status("dev-1")

    assert status["ntp_servers"] == ["0.pool.ntp.org", "1.pool.ntp.org"]
    assert status["dynamic_servers"] == ["2.pool.ntp.org"]
    assert status["status"] == "synchronized"
    assert status["stratum"] == 3
    assert status["offset_ms"] == pytest.approx(5.945, rel=1e-6)
    assert status["synced_server"] == "0.pool.ntp.org"
    assert status["synced_stratum"] == 4
    assert status["vrf"] == "main"


@pytest.mark.asyncio
async def test_flush_dns_cache_handles_cache_read_error_and_cache_not_initialized(
    monkeypatch: pytest.MonkeyPatch,
    patch_safeguards: None,
) -> None:
    client = _FakeRestClient(data={}, raise_on={"/rest/ip/dns/cache"})

    monkeypatch.setattr(
        dns_ntp_module, "DeviceService", lambda *_a, **_k: _FakeDeviceService(client)
    )

    # Make cache invalidation enabled, but simulate that the cache isn't initialized.
    monkeypatch.setattr(
        "routeros_mcp.infra.observability.resource_cache.get_cache",
        lambda: (_ for _ in ()).throw(RuntimeError("not initialized")),
    )

    settings = Settings()
    settings.mcp_resource_cache_auto_invalidate = True

    service = DNSNTPService(session=None, settings=settings)
    result = await service.flush_dns_cache("dev-1")

    assert result["changed"] is True
    assert result["entries_flushed"] == 0
    assert any(path == "/rest/ip/dns/cache/flush" for path, _ in client.calls)


@pytest.mark.asyncio
async def test_invalidate_dns_cache_records_metrics_when_entries_invalidated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeCache:
        async def invalidate(self, _key: str, _device_id: str) -> bool:
            return True

    monkeypatch.setattr("routeros_mcp.infra.observability.resource_cache.get_cache", lambda: _FakeCache())

    called: list[tuple[str, str]] = []

    def _record(component: str, reason: str) -> None:
        called.append((component, reason))

    monkeypatch.setattr(dns_ntp_module.metrics, "record_cache_invalidation", _record)

    monkeypatch.setattr(dns_ntp_module, "DeviceService", lambda *_a, **_k: object())

    service = DNSNTPService(session=None, settings=Settings())
    await service._invalidate_dns_cache("dev-1")

    assert called == [("dns_ntp", "config_update")]


@pytest.mark.asyncio
async def test_invalidate_ntp_cache_does_not_raise_when_cache_not_initialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "routeros_mcp.infra.observability.resource_cache.get_cache",
        lambda: (_ for _ in ()).throw(RuntimeError("not initialized")),
    )

    monkeypatch.setattr(dns_ntp_module, "DeviceService", lambda *_a, **_k: object())

    service = DNSNTPService(session=None, settings=Settings())
    await service._invalidate_ntp_cache("dev-1")


@pytest.mark.asyncio
async def test_get_ntp_status_rest_when_monitor_missing_uses_enabled_state_and_defaults(
    monkeypatch: pytest.MonkeyPatch,
    patch_safeguards: None,
) -> None:
    client = _FakeRestClient(
        data={
            "/rest/system/ntp/client": {
                "servers": "0.pool.ntp.org",
                "enabled": False,
                "mode": "unicast",
            }
        },
        raise_on={"/rest/system/ntp/client/monitor": RuntimeError("monitor not supported")},
    )

    monkeypatch.setattr(
        dns_ntp_module, "DeviceService", lambda *_a, **_k: _FakeDeviceService(client)
    )

    service = DNSNTPService(session=None, settings=Settings())
    status = await service.get_ntp_status("dev-1")

    assert status["enabled"] is False
    assert status["status"] == "disabled"
    assert status["stratum"] == 0
    assert status["offset_ms"] == 0.0


@pytest.mark.asyncio
async def test_update_ntp_servers_no_change_dry_run_apply_and_invalidate(
    monkeypatch: pytest.MonkeyPatch,
    patch_safeguards: None,
) -> None:
    client = _FakeRestClient(
        data={
            "/rest/system/ntp/client": {"servers": "0.pool.ntp.org", "enabled": True},
        }
    )

    monkeypatch.setattr(
        dns_ntp_module, "DeviceService", lambda *_a, **_k: _FakeDeviceService(client)
    )

    settings = Settings()
    settings.mcp_resource_cache_auto_invalidate = True

    service = DNSNTPService(session=None, settings=settings)

    invalidated: list[str] = []

    async def _invalidate(device_id: str) -> None:
        invalidated.append(device_id)

    monkeypatch.setattr(service, "_invalidate_ntp_cache", _invalidate)

    # No change
    no_change = await service.update_ntp_servers(
        "dev-1",
        ["0.pool.ntp.org"],
        enabled=True,
        dry_run=False,
    )
    assert no_change["changed"] is False

    # Dry run
    dry = await service.update_ntp_servers(
        "dev-1",
        ["time.example.com"],
        enabled=False,
        dry_run=True,
    )
    assert dry["dry_run"] is True

    # Apply
    applied = await service.update_ntp_servers(
        "dev-1",
        ["time.example.com"],
        enabled=False,
        dry_run=False,
    )
    assert applied["changed"] is True

    assert any(
        path == "/rest/system/ntp/client"
        and payload is not None
        and payload.get("servers") == "time.example.com"
        and payload.get("enabled") == "no"
        for path, payload in client.calls
    )
    assert invalidated == ["dev-1"]
