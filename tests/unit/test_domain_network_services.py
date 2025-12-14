from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import firewall as firewall_module
from routeros_mcp.domain.services import health as health_module
from routeros_mcp.domain.services import interface as interface_module
from routeros_mcp.domain.services import routing as routing_module
from routeros_mcp.domain.services import system as system_module
from routeros_mcp.infra.routeros.exceptions import RouterOSTimeoutError
from routeros_mcp.security import safeguards


class _FakeRestClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, dict | None]] = []
        self.store = {
            "/rest/interface": [
                {
                    ".id": "*1",
                    "name": "ether1",
                    "type": "ether",
                    "running": True,
                    "mtu": 1500,
                    "mac-address": "aa:bb",
                },
                {
                    ".id": "*2",
                    "name": "ether2",
                    "type": "ether",
                    "running": False,
                    "disabled": True,
                    "mtu": 1500,
                    "mac-address": "cc:dd",
                },
            ],
            "/rest/interface/*1": {
                ".id": "*1",
                "name": "ether1",
                "type": "ether",
                "running": True,
                "mtu": 1500,
                "mac-address": "aa:bb",
                "last-link-up-time": "2025-01-01",
            },
            "/rest/interface/monitor-traffic": [
                {
                    "name": "ether1",
                    "rx-bits-per-second": 100,
                    "tx-bits-per-second": 200,
                    "rx-packets-per-second": 1,
                    "tx-packets-per-second": 2,
                },
                {
                    "name": "ether2",
                    "rx-bits-per-second": 0,
                    "tx-bits-per-second": 0,
                    "rx-packets-per-second": 0,
                    "tx-packets-per-second": 0,
                },
            ],
            "/rest/ip/firewall/address-list": [
                {".id": "*a", "list": "mcp-managed", "address": "192.0.2.1", "comment": "seed"},
                {".id": "*b", "list": "other", "address": "198.51.100.1", "comment": "other"},
            ],
            "/rest/ip/route": [
                {".id": "*r1", "dst-address": "0.0.0.0/0", "gateway": "10.0.0.1", "static": True},
                {
                    ".id": "*r2",
                    "dst-address": "10.0.0.0/24",
                    "gateway": "10.0.0.1",
                    "connect": True,
                },
                {
                    ".id": "*r3",
                    "dst-address": "203.0.113.0/24",
                    "gateway": "10.0.0.2",
                    "dynamic": True,
                },
            ],
            "/rest/ip/route/*r1": {
                ".id": "*r1",
                "dst-address": "0.0.0.0/0",
                "gateway": "10.0.0.1",
                "distance": 1,
                "comment": "default",
            },
            "/rest/system/resource": {
                "cpu-load": 10,
                "cpu-count": 4,
                "total-memory": 1024,
                "free-memory": 512,
                "uptime": "1h2m3s",
                "version": "7.15",
                "board-name": "rb5009",
                "architecture-name": "arm",
            },
            "/rest/system/identity": {"name": "router-1"},
            "/rest/system/package": [
                {
                    "name": "routeros",
                    "version": "7.15",
                    "build-time": "2025-01-01",
                    "disabled": False,
                },
            ],
        }

    async def get(self, path: str, params: dict | None = None):
        self.calls.append(("get", path, params))

        # Simulate monitor-traffic per-interface filtering
        if path == "/rest/interface/monitor-traffic":
            data = self.store.get(path, [])
            if params and params.get("interface"):
                iface = params["interface"]
                if isinstance(data, list):
                    filtered = [item for item in data if item.get("name") == iface]
                    if filtered:
                        return filtered
                return []
            return data

        return self.store.get(path, {})

    async def put(self, path: str, payload: dict):
        self.calls.append(("put", path, payload))
        return {".id": "*new", **payload}

    async def delete(self, path: str):
        self.calls.append(("delete", path, None))
        return {}

    async def patch(self, path: str, payload: dict):
        self.calls.append(("patch", path, payload))
        return {}

    async def close(self):
        self.calls.append(("close", None, None))


class _FakeDeviceService:
    def __init__(self, client: _FakeRestClient) -> None:
        self.client = client
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
        return self.client

    async def list_devices(self, environment: str | None = None):
        return [self.device]


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch):
    client = _FakeRestClient()
    device_service = _FakeDeviceService(client)

    monkeypatch.setattr(interface_module, "DeviceService", lambda *args, **kwargs: device_service)
    monkeypatch.setattr(firewall_module, "DeviceService", lambda *args, **kwargs: device_service)
    monkeypatch.setattr(routing_module, "DeviceService", lambda *args, **kwargs: device_service)
    monkeypatch.setattr(system_module, "DeviceService", lambda *args, **kwargs: device_service)
    monkeypatch.setattr(health_module, "DeviceService", lambda *args, **kwargs: device_service)

    return client, device_service


@pytest.mark.asyncio
async def test_interface_service_operations(fake_env):
    client, _ = fake_env
    service = interface_module.InterfaceService(session=None, settings=Settings())

    interfaces = await service.list_interfaces("dev-1")
    assert len(interfaces) == 2
    assert interfaces[0]["name"] == "ether1"

    detail = await service.get_interface("dev-1", "*1")
    assert detail["mac_address"] == "aa:bb"

    stats = await service.get_interface_stats("dev-1", ["ether1"])
    assert stats[0]["rx_bits_per_second"] == 100
    assert any(call[0] == "close" for call in client.calls)


@pytest.mark.asyncio
async def test_firewall_service_add_remove(fake_env, monkeypatch: pytest.MonkeyPatch):
    client, _ = fake_env
    settings = Settings()

    monkeypatch.setattr(safeguards, "validate_mcp_owned_list", lambda name: None)
    monkeypatch.setattr(safeguards, "validate_ip_address_format", lambda addr: None)
    monkeypatch.setattr(
        safeguards,
        "create_dry_run_response",
        lambda operation, device_id, planned_changes: {
            "operation": operation,
            "planned_changes": planned_changes,
            "device_id": device_id,
            "dry_run": True,
        },
    )

    service = firewall_module.FirewallService(session=None, settings=settings)

    add_result = await service.update_address_list_entry(
        "dev-1", "mcp-managed", "203.0.113.10", action="add", comment="test"
    )
    assert add_result["changed"] is True
    assert any(call[0] == "put" for call in client.calls)

    remove_missing = await service.update_address_list_entry(
        "dev-1", "mcp-managed", "192.0.2.99", action="remove"
    )
    assert remove_missing["changed"] is False

    remove_dry_run = await service.update_address_list_entry(
        "dev-1", "mcp-managed", "192.0.2.1", action="remove", dry_run=True
    )
    assert remove_dry_run["dry_run"] is True

    with pytest.raises(ValueError):
        await service.update_address_list_entry(
            "dev-1", "mcp-managed", "192.0.2.1", action="invalid"
        )


@pytest.mark.asyncio
async def test_routing_service_summary(fake_env):
    client, _ = fake_env
    service = routing_module.RoutingService(session=None, settings=Settings())

    summary = await service.get_routing_summary("dev-1")
    assert summary["total_routes"] == 3
    assert summary["static_routes"] == 1
    assert summary["dynamic_routes"] == 1

    route = await service.get_route("dev-1", "*r1")
    assert route["gateway"] == "10.0.0.1"
    assert any(call[0] == "close" for call in client.calls)


@pytest.mark.asyncio
async def test_system_service_overview_and_identity(fake_env, monkeypatch: pytest.MonkeyPatch):
    client, _ = fake_env
    settings = Settings()
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

    service = system_module.SystemService(session=None, settings=settings)

    overview = await service.get_system_overview("dev-1")
    assert overview["cpu_usage_percent"] == 10.0
    assert overview["memory_used_bytes"] == 512

    resource = await service.get_system_resource("dev-1")
    assert resource.cpu_usage_percent == 10.0
    assert resource.system_identity == "router-1"

    packages = await service.get_system_packages("dev-1")
    assert packages[0]["name"] == "routeros"

    identity_dry_run = await service.update_system_identity("dev-1", "router-new", dry_run=True)
    assert identity_dry_run["dry_run"] is True
    assert identity_dry_run["planned_changes"]["new_identity"] == "router-new"

    identity_no_change = await service.update_system_identity("dev-1", "router-1", dry_run=False)
    assert identity_no_change["changed"] is False
    assert any(call[0] == "close" for call in client.calls)


@pytest.mark.asyncio
async def test_system_service_overview_rest_fallback(fake_env, monkeypatch: pytest.MonkeyPatch):
    _client, device_service = fake_env
    settings = Settings()
    service = system_module.SystemService(session=None, settings=settings)
    service.device_service = device_service

    # Force REST path to fail and SSH path to succeed
    monkeypatch.setattr(
        service,
        "_get_overview_via_rest",
        AsyncMock(side_effect=RouterOSTimeoutError("rest timeout")),
    )

    ssh_resource = {
        "cpu-load": 5,
        "cpu-count": 2,
        "total-memory": 100,
        "free-memory": 60,
        "uptime": "5s",
        "version": "7.1",
        "board-name": "rb",
        "architecture-name": "arm",
    }

    monkeypatch.setattr(
        service,
        "_get_overview_via_ssh",
        AsyncMock(return_value=(ssh_resource, "router-ssh")),
    )

    overview = await service.get_system_overview("dev-1")

    assert overview["transport"] == "ssh"
    assert overview["fallback_used"] is True
    assert "rest timeout" in (overview.get("rest_error") or "")
    # Ensure metrics parsed from SSH output
    assert overview["cpu_usage_percent"] == 5.0
    assert overview["memory_used_bytes"] == 40


@pytest.mark.asyncio
async def test_coerce_resource_values_parses_units():
    data = {
        "total-memory": "1024.0MiB",
        "free-memory": "859.7MiB",
        "cpu-load": "12%",
        "cpu-count": "4",
    }

    coerced = system_module.SystemService._coerce_resource_values(data)

    assert coerced["total-memory"] == 1024 * 1024 * 1024
    assert coerced["free-memory"] == int(859.7 * 1024 * 1024)
    assert coerced["cpu-load"] == 12.0
    assert coerced["cpu-count"] == 4


@pytest.mark.asyncio
async def test_parse_resource_plain_format():
    output = """
        uptime: 1d2h57m53s
        version: 7.20.6 (stable)
        total-memory: 1024.0MiB
        free-memory: 859.7MiB
        cpu-count: 4
        cpu-load: 0%
        architecture-name: arm64
        board-name: RB5009UPr+S+
    """

    parsed = system_module.SystemService._parse_ssh_resource_output(output)
    coerced = system_module.SystemService._coerce_resource_values(parsed)

    assert parsed["version"] == "7.20.6 (stable)"
    assert coerced["total-memory"] == 1024 * 1024 * 1024
    assert coerced["free-memory"] == int(859.7 * 1024 * 1024)
    assert coerced["cpu-count"] == 4
    assert coerced["cpu-load"] == 0.0


@pytest.mark.asyncio
async def test_system_overview_ssh_plain_fallback(monkeypatch: pytest.MonkeyPatch):
    settings = Settings()
    service = system_module.SystemService(session=None, settings=settings)

    device = SimpleNamespace(id="dev-plain", name="router-plain", system_identity=None)

    resource_plain = """
        uptime: 1d2h57m53s
        version: 7.20.6 (stable)
        total-memory: 1024.0MiB
        free-memory: 859.7MiB
        cpu-count: 4
        cpu-load: 0%
        architecture-name: arm64
        board-name: RB5009UPr+S+
    """

    identity_plain = "name: core-RB5009"

    class FakeSSHClient:
        async def execute(self, cmd):
            if cmd == "/system/resource/print":
                return resource_plain
            if cmd == "/system/identity/print":
                return identity_plain
            raise AssertionError(f"Unexpected command: {cmd}")

        async def close(self):
            return None

    service.device_service = SimpleNamespace(
        get_device=AsyncMock(return_value=device),
        get_ssh_client=AsyncMock(return_value=FakeSSHClient()),
    )

    monkeypatch.setattr(
        service,
        "_get_overview_via_rest",
        AsyncMock(side_effect=RouterOSTimeoutError("rest timeout")),
    )

    overview = await service.get_system_overview("dev-plain")

    assert overview["transport"] == "ssh"
    assert overview["fallback_used"] is True
    assert overview["system_identity"] == "core-RB5009"
    assert overview["routeros_version"] == "7.20.6 (stable)"
    assert overview["hardware_model"] == "RB5009UPr+S+"
    assert overview["architecture"] == "arm64"
    assert overview["cpu_count"] == 4
    assert overview["memory_total_bytes"] == 1024 * 1024 * 1024
    assert overview["memory_free_bytes"] == int(859.7 * 1024 * 1024)
    assert overview["cpu_usage_percent"] == 0.0
    assert overview["uptime_seconds"] == system_module.parse_routeros_uptime("1d2h57m53s")


@pytest.mark.asyncio
async def test_system_service_packages_rest_fallback(fake_env, monkeypatch: pytest.MonkeyPatch):
    _client, device_service = fake_env
    service = system_module.SystemService(session=None, settings=Settings())
    service.device_service = device_service

    monkeypatch.setattr(
        service,
        "_get_packages_via_rest",
        AsyncMock(side_effect=RouterOSTimeoutError("rest timeout")),
    )

    ssh_packages = [
        {
            "name": "routeros",
            "version": "7.1",
            "build_time": "2024-01-01",
            "disabled": False,
        }
    ]

    monkeypatch.setattr(
        service,
        "_get_packages_via_ssh",
        AsyncMock(return_value=ssh_packages),
    )

    packages = await service.get_system_packages("dev-1")

    assert packages[0]["transport"] == "ssh"
    assert packages[0]["fallback_used"] is True
    assert "rest timeout" in (packages[0].get("rest_error") or "")


@pytest.mark.asyncio
async def test_system_service_packages_ssh_table_output_parsing(monkeypatch: pytest.MonkeyPatch):
    """Ensure SSH fallback parses table-style `/system/package/print` output.

    RouterOS returns table format for package listings. The service should
    parse and return both installed and available packages.
    """

    settings = Settings()
    service = system_module.SystemService(session=None, settings=settings)

    device = SimpleNamespace(id="dev-lab-01", name="Router Lab 01", system_identity="core")

    table_output = """
Flags: X - DISABLED; A - AVAILABLE
Columns: NAME, VERSION, BUILD-TIME, SIZE
 #    NAME            VERSION  BUILD-TIME           SIZE
 0    wireless        7.20.6   2025-12-04 12:00:39  864.1KiB
 1    routeros        7.20.6   2025-12-04 12:00:39  12.6MiB
 2    container       7.20.6   2025-12-04 12:00:39  208.1KiB
 3    rose-storage    7.20.6   2025-12-04 12:00:39  3140.1KiB
 4    zerotier        7.20.6   2025-12-04 12:00:39  836.1KiB
 5 XA calea                                         20.1KiB
"""

    class FakeSSHClient:
        async def execute(self, cmd):
            if cmd == "/system/package/print":
                return table_output
            raise AssertionError(f"Unexpected command: {cmd}")

        async def close(self):
            return None

    service.device_service = SimpleNamespace(
        get_device=AsyncMock(return_value=device),
        get_ssh_client=AsyncMock(return_value=FakeSSHClient()),
        get_rest_client=AsyncMock(side_effect=RouterOSTimeoutError("rest timeout")),
    )

    packages = await service.get_system_packages("dev-lab-01")

    # Includes installed + available packages (do not drop information)
    assert len(packages) == 6

    installed = [p for p in packages if p.get("installed")]
    available = [p for p in packages if (p.get("available") and not p.get("installed"))]

    assert len(installed) == 5
    assert len(available) == 1

    installed_names = {p["name"] for p in installed}
    assert {"routeros", "wireless", "container", "rose-storage", "zerotier"}.issubset(installed_names)
    assert all(p["version"] == "7.20.6" for p in installed)
    assert all(p["build_time"] == "2025-12-04 12:00:39" for p in installed)
    assert all(p.get("size") for p in installed)

    assert available[0]["name"] == "calea"
    assert available[0]["version"] in {None, ""}
    assert available[0]["build_time"] in {None, ""}
    assert available[0].get("size")


@pytest.mark.asyncio
async def test_system_service_packages_ssh_plain_print_fallback_when_as_value_empty():
    """Test that package listing uses standard print format.

    RouterOS returns standard table format for /system/package/print.
    The SSH path should parse installed and available packages from the table output.
    """

    settings = Settings()
    service = system_module.SystemService(session=None, settings=settings)

    device = SimpleNamespace(id="dev-lab-01", name="Router Lab 01", system_identity="core")

    table_output = """
Flags: X - DISABLED; A - AVAILABLE
Columns: NAME, VERSION, BUILD-TIME, SIZE
 #    NAME            VERSION  BUILD-TIME           SIZE
 0    wireless        7.20.6   2025-12-04 12:00:39  864.1KiB
 1    routeros        7.20.6   2025-12-04 12:00:39  12.6MiB
 2    container       7.20.6   2025-12-04 12:00:39  208.1KiB
 3    rose-storage    7.20.6   2025-12-04 12:00:39  3140.1KiB
 4    zerotier        7.20.6   2025-12-04 12:00:39  836.1KiB
 5 XA calea                                         20.1KiB
"""

    class FakeSSHClient:
        def __init__(self) -> None:
            self.commands: list[str] = []

        async def execute(self, cmd):
            self.commands.append(cmd)
            # Simulate standard table output
            if cmd == "/system/package/print":
                return table_output
            raise AssertionError(f"Unexpected command: {cmd}")

        async def close(self):
            return None

    fake_ssh = FakeSSHClient()
    service.device_service = SimpleNamespace(
        get_device=AsyncMock(return_value=device),
        get_ssh_client=AsyncMock(return_value=fake_ssh),
    )

    packages = await service._get_packages_via_ssh("dev-lab-01")

    assert "/system/package/print" in fake_ssh.commands
    assert len(packages) == 6
    installed = [p for p in packages if p.get("installed")]
    available = [p for p in packages if (p.get("available") and not p.get("installed"))]
    assert len(installed) == 5
    assert len(available) == 1
    names = {p["name"] for p in installed}
    assert {"routeros", "wireless", "container", "rose-storage", "zerotier"}.issubset(names)


def test_parse_as_value_blocks_single_line_multi_kv():
    output = "0 name=routeros version=7.20.6 build-time=2025-12-04 12:00:39 disabled=false\n"
    blocks = system_module.SystemService._parse_as_value_blocks(output)
    assert len(blocks) == 1
    assert blocks[0]["name"] == "routeros"
    assert blocks[0]["version"] == "7.20.6"
    assert blocks[0]["build-time"] == "2025-12-04 12:00:39"


@pytest.mark.asyncio
async def test_system_service_clock_rest_fallback(fake_env, monkeypatch: pytest.MonkeyPatch):
    _client, device_service = fake_env
    service = system_module.SystemService(session=None, settings=Settings())
    service.device_service = device_service

    monkeypatch.setattr(
        service,
        "_get_clock_via_rest",
        AsyncMock(side_effect=RouterOSTimeoutError("rest timeout")),
    )

    ssh_clock = {"time": "12:00:00", "date": "2025-12-13", "time-zone-name": "UTC", "gmt-offset": "+00:00", "dst-active": False}

    monkeypatch.setattr(
        service,
        "_get_clock_via_ssh",
        AsyncMock(return_value=ssh_clock),
    )

    clock = await service.get_system_clock("dev-1")

    assert clock["transport"] == "ssh"
    assert clock["fallback_used"] is True
    assert "rest timeout" in (clock.get("rest_error") or "")


@pytest.mark.asyncio
async def test_health_service_run_health_check(fake_env, monkeypatch: pytest.MonkeyPatch):
    _, device_service = fake_env
    settings = Settings()
    service = health_module.HealthService(session=None, settings=settings)
    service.device_service = device_service

    store_mock = AsyncMock()
    monkeypatch.setattr(service, "_store_health_check", store_mock)

    healthy = await service.run_health_check("dev-1")
    assert healthy.status == "healthy"
    store_mock.assert_awaited()

    async def _fail_client(device_id: str):
        raise RuntimeError("unreachable")

    service.device_service.get_rest_client = _fail_client  # type: ignore[assignment]
    unhealthy = await service.run_health_check("dev-1")
    assert unhealthy.status == "unreachable"
