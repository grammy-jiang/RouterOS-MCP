from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import dns_ntp as dns_ntp_module
from routeros_mcp.domain.services.dns_ntp import DNSNTPService
from routeros_mcp.infra.routeros.exceptions import RouterOSTimeoutError


class _FakeRestClient:
    def __init__(self, *, get_exc: Exception | None = None, data: dict[str, Any] | None = None) -> None:
        self._get_exc = get_exc
        self._data = data or {}
        self.calls: list[tuple[str, str, Any]] = []

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append(("get", path, params))
        if self._get_exc is not None:
            raise self._get_exc
        return self._data.get(path, {})

    async def post(self, path: str, payload: dict[str, Any]) -> Any:
        self.calls.append(("post", path, payload))
        return {}

    async def patch(self, path: str, payload: dict[str, Any]) -> Any:
        self.calls.append(("patch", path, payload))
        return {}

    async def close(self) -> None:
        self.calls.append(("close", "", None))


class _FakeSSHClient:
    def __init__(self, *, outputs: dict[str, str], exc: Exception | None = None) -> None:
        self._outputs = outputs
        self._exc = exc
        self.calls: list[tuple[str, str]] = []

    async def execute(self, command: str) -> str:
        self.calls.append(("execute", command))
        if self._exc is not None:
            raise self._exc
        return self._outputs.get(command, "")

    async def close(self) -> None:
        self.calls.append(("close", ""))


class _FakeDeviceService:
    def __init__(
        self,
        *,
        rest_client: _FakeRestClient | None = None,
        ssh_client: _FakeSSHClient | None = None,
    ) -> None:
        self._rest_client = rest_client
        self._ssh_client = ssh_client
        self.device = SimpleNamespace(id="dev-1", name="router-1", environment="lab")

    async def get_device(self, _device_id: str) -> Any:
        return self.device

    async def get_rest_client(self, _device_id: str) -> _FakeRestClient:
        assert self._rest_client is not None
        return self._rest_client

    async def get_ssh_client(self, _device_id: str) -> _FakeSSHClient:
        assert self._ssh_client is not None
        return self._ssh_client


def test_parse_bool_and_duration_helpers_cover_edge_cases() -> None:
    assert dns_ntp_module._parse_bool(True) is True
    assert dns_ntp_module._parse_bool(False) is False
    assert dns_ntp_module._parse_bool(None) is False
    assert dns_ntp_module._parse_bool(" yes ") is True
    assert dns_ntp_module._parse_bool("enabled") is True
    assert dns_ntp_module._parse_bool("no") is False

    assert dns_ntp_module._parse_duration_to_ms(None) == 0.0
    assert dns_ntp_module._parse_duration_to_ms(12) == 12.0
    assert dns_ntp_module._parse_duration_to_ms("") == 0.0
    assert dns_ntp_module._parse_duration_to_ms("10ms") == 10.0
    assert dns_ntp_module._parse_duration_to_ms("100us") == 0.1
    assert dns_ntp_module._parse_duration_to_ms("2s") == 2000.0
    assert dns_ntp_module._parse_duration_to_ms("-1.5s") == -1500.0
    assert dns_ntp_module._parse_duration_to_ms("not-a-duration") == 0.0

    # Hit the suffix-only branches (regex doesn't match these shapes).
    assert dns_ntp_module._parse_duration_to_ms("ms") == 0.0
    assert dns_ntp_module._parse_duration_to_ms("1.5us") == 0.0015
    assert dns_ntp_module._parse_duration_to_ms("s") == 0.0


@pytest.mark.asyncio
async def test_get_dns_cache_validates_limit() -> None:
    from routeros_mcp.mcp.errors import ValidationError

    service = DNSNTPService(session=None, settings=Settings(environment="lab"))
    service.device_service = _FakeDeviceService(
        rest_client=_FakeRestClient(data={}),
        ssh_client=_FakeSSHClient(outputs={}),
    )

    with pytest.raises(ValidationError):
        await service.get_dns_cache("dev-1", limit=dns_ntp_module.MAX_DNS_CACHE_ENTRIES + 1)


@pytest.mark.asyncio
async def test_get_dns_cache_when_rest_succeeds_normalizes_and_respects_limit() -> None:
    rest = _FakeRestClient(
        data={
            "/rest/ip/dns/cache": [
                {"name": "example.com", "type": "A", "data": "93.184.216.34", "ttl": 100},
                {"name": "example.net", "type": "AAAA", "data": "2001:db8::1", "ttl": 200},
                "not-a-dict",
                {"name": "ignored-by-limit"},
            ]
        }
    )

    service = DNSNTPService(session=None, settings=Settings(environment="lab"))
    service.device_service = _FakeDeviceService(rest_client=rest, ssh_client=_FakeSSHClient(outputs={}))

    cache, total = await service.get_dns_cache("dev-1", limit=2)

    assert total == 4
    assert [row["name"] for row in cache] == ["example.com", "example.net"]
    assert all(row["transport"] == "rest" for row in cache)
    assert all(row["fallback_used"] is False for row in cache)


@pytest.mark.asyncio
async def test_get_dns_cache_when_rest_and_ssh_fail_raises_runtimeerror() -> None:
    rest = _FakeRestClient(get_exc=RouterOSTimeoutError("rest timeout"))
    ssh = _FakeSSHClient(outputs={}, exc=RuntimeError("ssh down"))

    service = DNSNTPService(session=None, settings=Settings(environment="lab"))
    service.device_service = _FakeDeviceService(rest_client=rest, ssh_client=ssh)

    with pytest.raises(RuntimeError) as excinfo:
        await service.get_dns_cache("dev-1", limit=10)

    msg = str(excinfo.value)
    assert "rest_error=" in msg
    assert "ssh_error=" in msg


@pytest.mark.asyncio
async def test_get_dns_status_when_rest_times_out_uses_ssh_fallback() -> None:
    rest = _FakeRestClient(get_exc=RouterOSTimeoutError("rest timeout"))

    # Real RouterOS output format with aligned columns and multiline servers
    ssh_output = """       servers: 1.1.1.1
                1.0.0.1
 dynamic-servers: 8.8.8.8
     allow-remote: yes
     cache-size: 2048KiB
     cache-used: 12KiB
         max-udp: not-an-int
   doh-max-conc: 10"""

    ssh = _FakeSSHClient(outputs={"/ip/dns/print": ssh_output})

    service = DNSNTPService(session=None, settings=Settings(environment="lab"))
    service.device_service = _FakeDeviceService(rest_client=rest, ssh_client=ssh)

    status = await service.get_dns_status("dev-1")

    assert status["transport"] == "ssh"
    assert status["fallback_used"] is True
    assert "rest timeout" in (status["rest_error"] or "")
    assert status["dns_servers"] == ["1.1.1.1", "1.0.0.1"]
    assert status["dynamic_servers"] == ["8.8.8.8"]


@pytest.mark.asyncio
async def test_get_dns_status_rest_handles_unexpected_server_types_and_extra_optionals() -> None:
    """Cover REST DNS status branches for non-str/list servers and extra optional fields."""
    rest = _FakeRestClient(
        data={
            "/rest/ip/dns": {
                "servers": 123,
                "dynamic-servers": None,
                "allow-remote-requests": False,
                "cache-size": 2048,
                "cache-used": 0,
                "cache-max-ttl": "1d",
                "address-list-extra-time": "1h",
                "vrf": "main",
                "mdns-repeat-ifaces": "bridge",
            }
        }
    )

    service = DNSNTPService(session=None, settings=Settings(environment="lab"))
    service.device_service = _FakeDeviceService(rest_client=rest, ssh_client=_FakeSSHClient(outputs={}))

    status = await service.get_dns_status("dev-1")

    assert status["transport"] == "rest"
    assert status["dns_servers"] == []
    assert status["dynamic_servers"] == []
    assert status["cache_max_ttl"] == "1d"
    assert status["address_list_extra_time"] == "1h"
    assert status["vrf"] == "main"
    assert status["mdns_repeat_ifaces"] == "bridge"


@pytest.mark.asyncio
async def test_get_dns_cache_when_rest_times_out_uses_ssh_fallback() -> None:
    rest = _FakeRestClient(get_exc=RouterOSTimeoutError("rest timeout"))

    # Real RouterOS DNS cache output using key=value detail format
    # This is what `/ip/dns/cache/print as-value` returns
    ssh_output = """name=staticcdn.duckduckgo.com type=CNAME data=external-content.duckduckgo.com. ttl=23h53m27s

name=api.githubcopilot.com type=CNAME data=glb-db52c2cf8be544.github.com. ttl=59m47s

name=alive.github.com type=CNAME data=live.github.com. ttl=57m21s

type=NS data=a.root-servers.net. ttl=2d12h36m6s

type=NS data=b.root-servers.net. ttl=2d12h36m6s

name=sg-vip001.taboola.com type=A data=141.226.229.48 ttl=4h12m43s

name=teams.microsoft.com type=CNAME data=teams.office.com. ttl=2d21h57m56s

"""

    ssh = _FakeSSHClient(
        outputs={
            "/ip/dns/cache/print as-value without-paging": ssh_output,
        }
    )

    service = DNSNTPService(session=None, settings=Settings(environment="lab"))
    service.device_service = _FakeDeviceService(rest_client=rest, ssh_client=ssh)

    cache, total = await service.get_dns_cache("dev-1", limit=10)

    assert total == 7
    assert cache[0]["transport"] == "ssh"
    assert cache[0]["fallback_used"] is True
    assert cache[0]["name"] == "staticcdn.duckduckgo.com"
    assert cache[0]["type"] == "CNAME"
    assert cache[0]["data"] == "external-content.duckduckgo.com."
    assert cache[1]["name"] == "api.githubcopilot.com"
    assert cache[2]["type"] == "CNAME"
    assert cache[3]["type"] == "NS"
    assert cache[3]["name"] == ""  # NS record with empty name
    assert cache[5]["name"] == "sg-vip001.taboola.com"
    assert cache[5]["type"] == "A"
    assert cache[5]["data"] == "141.226.229.48"


@pytest.mark.asyncio
async def test_get_ntp_status_when_rest_times_out_uses_ssh_fallback() -> None:
    rest = _FakeRestClient(get_exc=RouterOSTimeoutError("rest timeout"))

    # Real RouterOS output format with multi-line servers, status field, and synced metrics
    ssh_output = """         enabled: yes              
            mode: unicast          
         servers: 0.au.pool.ntp.org
                  1.au.pool.ntp.org
                  2.au.pool.ntp.org
             vrf: main                   
      freq-drift: 2.773 PPM        
          status: synchronized     
   synced-server: 0.au.pool.ntp.org
  synced-stratum: 1                
   system-offset: 5.945 ms"""

    ssh = _FakeSSHClient(outputs={"/system/ntp/client/print": ssh_output})

    service = DNSNTPService(session=None, settings=Settings(environment="lab"))
    service.device_service = _FakeDeviceService(rest_client=rest, ssh_client=ssh)

    ntp = await service.get_ntp_status("dev-1")

    assert ntp["transport"] == "ssh"
    assert ntp["fallback_used"] is True
    assert ntp["enabled"] is True
    assert ntp["mode"] == "unicast"
    assert ntp["ntp_servers"] == ["0.au.pool.ntp.org", "1.au.pool.ntp.org", "2.au.pool.ntp.org"]
    assert ntp["status"] == "synchronized"
    assert ntp["stratum"] == 1
    assert ntp["synced_server"] == "0.au.pool.ntp.org"
    assert ntp["synced_stratum"] == 1
    assert ntp["system_offset_ms"] == pytest.approx(5.945)
    assert ntp["offset_ms"] == pytest.approx(5.945)
    assert "raw_fields" in ntp


@pytest.mark.asyncio
async def test_get_ntp_status_ssh_uses_table_servers_and_parses_offsets_and_dynamic_servers() -> None:
    rest = _FakeRestClient(get_exc=RouterOSTimeoutError("rest timeout"))

    # Real RouterOS output with empty servers list, dynamic servers, and table rows
    ssh_output = """         enabled: yes              
            mode: unicast          
         servers:                  
   dynamic-servers: 2.au.pool.ntp.org
             vrf: main                   
      freq-drift: 1.234 PPM        
          status: enabled          
   synced-server: 0.au.pool.ntp.org
  synced-stratum: 2                
   system-offset: 10.5 ms         
    last-offset: 8.234 ms         

0   time.cloudflare.com  unicast  true
1   time.google.com      unicast  false"""

    ssh = _FakeSSHClient(outputs={"/system/ntp/client/print": ssh_output})

    service = DNSNTPService(session=None, settings=Settings(environment="lab"))
    service.device_service = _FakeDeviceService(rest_client=rest, ssh_client=ssh)

    ntp = await service.get_ntp_status("dev-1")

    assert ntp["transport"] == "ssh"
    assert ntp["enabled"] is True
    # Parser captures both rows from table when no configured servers
    assert ntp["ntp_servers"] == ["time.cloudflare.com", "time.google.com"]
    assert ntp["dynamic_servers"] == ["2.au.pool.ntp.org"]
    assert ntp["synced_server"] == "0.au.pool.ntp.org"
    # Table row with "true" overrides the "status: enabled" text field
    assert ntp["status"] == "synchronized"
    assert ntp["stratum"] == 2
    assert ntp["system_offset_ms"] == pytest.approx(10.5)
    assert ntp["last_offset_ms"] == pytest.approx(8.234)
    assert ntp["offset_ms"] == pytest.approx(8.234)  # last_offset takes precedence


@pytest.mark.asyncio
async def test_get_ntp_status_ssh_with_multiline_servers_and_synchronized_status() -> None:
    """Test parsing of actual RouterOS output with continuation-line servers and 'synchronized' status."""
    rest = _FakeRestClient(get_exc=RouterOSTimeoutError("rest timeout"))

    # Actual RouterOS output format with multi-line servers and synchronized status
    ssh_output = """         enabled: yes              
            mode: unicast          
         servers: 0.au.pool.ntp.org
                  1.au.pool.ntp.org
                  2.au.pool.ntp.org
                  3.au.pool.ntp.org
             vrf: main                   
      freq-drift: 2.773 PPM        
          status: synchronized     
   synced-server: 0.au.pool.ntp.org
  synced-stratum: 1                
   system-offset: 2.132 ms         
""".strip()

    ssh = _FakeSSHClient(outputs={"/system/ntp/client/print": ssh_output})

    service = DNSNTPService(session=None, settings=Settings(environment="lab"))
    service.device_service = _FakeDeviceService(rest_client=rest, ssh_client=ssh)

    ntp = await service.get_ntp_status("dev-1")

    assert ntp["transport"] == "ssh"
    assert ntp["fallback_used"] is True
    assert ntp["enabled"] is True
    assert ntp["mode"] == "unicast"
    assert ntp["ntp_servers"] == [
        "0.au.pool.ntp.org",
        "1.au.pool.ntp.org",
        "2.au.pool.ntp.org",
        "3.au.pool.ntp.org",
    ]
    assert ntp["status"] == "synchronized"
    assert ntp["synced_server"] == "0.au.pool.ntp.org"
    assert ntp["synced_stratum"] == 1
    assert ntp["stratum"] == 1
    assert ntp["system_offset_ms"] == pytest.approx(2.132)
    assert ntp["offset_ms"] == pytest.approx(2.132)


@pytest.mark.asyncio
async def test_update_dns_servers_auto_invalidates_cache_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    rest = _FakeRestClient(
        data={
            "/rest/ip/dns": {"servers": "8.8.8.8"},
        }
    )

    settings = Settings(environment="lab")
    settings.mcp_resource_cache_auto_invalidate = True

    service = DNSNTPService(session=None, settings=settings)
    service.device_service = _FakeDeviceService(rest_client=rest, ssh_client=_FakeSSHClient(outputs={}))

    invalidate = AsyncMock()
    monkeypatch.setattr(service, "_invalidate_dns_cache", invalidate)

    # Monkeypatch safeguards validators/dry-run helper to keep the test focused.
    monkeypatch.setattr("routeros_mcp.security.safeguards.validate_dns_servers", lambda _s: None)

    result = await service.update_dns_servers("dev-1", ["9.9.9.9"], dry_run=False)

    assert result["changed"] is True
    assert any(call[0] == "patch" and call[1] == "/rest/ip/dns" for call in rest.calls)
    invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_flush_dns_cache_auto_invalidates_cache_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    rest = _FakeRestClient(
        data={
            "/rest/ip/dns/cache": [{"name": "example.com"}, {"name": "example.net"}],
        }
    )

    settings = Settings(environment="lab")
    settings.mcp_resource_cache_auto_invalidate = True

    service = DNSNTPService(session=None, settings=settings)
    service.device_service = _FakeDeviceService(rest_client=rest, ssh_client=_FakeSSHClient(outputs={}))

    invalidate = AsyncMock()
    monkeypatch.setattr(service, "_invalidate_dns_cache", invalidate)

    result = await service.flush_dns_cache("dev-1")

    assert result["changed"] is True
    assert result["entries_flushed"] == 2
    assert any(call[0] == "post" and call[1] == "/rest/ip/dns/cache/flush" for call in rest.calls)
    invalidate.assert_awaited_once()
