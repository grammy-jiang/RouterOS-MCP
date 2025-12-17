from __future__ import annotations

from dataclasses import dataclass

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import system as system_module
from routeros_mcp.domain.services.system import SystemService
from routeros_mcp.infra.routeros.exceptions import (
    RouterOSNetworkError,
    RouterOSServerError,
    RouterOSTimeoutError,
)


@dataclass
class _FakeDevice:
    id: str
    name: str = "dev"
    system_identity: str | None = "dev"


class _FakeRestClient:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        responses: dict[str, object] | None = None,
        raise_on: dict[str, Exception] | None = None,
    ):
        self._error = error
        self._responses = responses or {}
        self._raise_on = raise_on or {}
        self.closed = False
        self.calls: list[str] = []
        self.patch_calls: list[tuple[str, dict]] = []

    async def get(self, path: str):
        self.calls.append(path)
        if path in self._raise_on:
            raise self._raise_on[path]
        if self._error is not None:
            raise self._error
        return self._responses.get(path, {})

    async def patch(self, path: str, payload: dict) -> None:
        self.patch_calls.append((path, payload))
        if self._error is not None:
            raise self._error

    async def close(self) -> None:
        self.closed = True


class _FakeSSHClient:
    def __init__(self, *, outputs: dict[str, str] | None = None, error: Exception | None = None):
        self._outputs = outputs or {}
        self._error = error
        self.closed = False
        self.calls: list[str] = []

    async def execute(self, command: str) -> str:
        self.calls.append(command)
        if self._error is not None:
            raise self._error
        return self._outputs.get(command, "")

    async def close(self) -> None:
        self.closed = True


class _FakeDeviceService:
    def __init__(
        self,
        rest_client: _FakeRestClient | None = None,
        ssh_client: _FakeSSHClient | None = None,
        device: _FakeDevice | None = None,
    ) -> None:
        self._rest_client = rest_client
        self._ssh_client = ssh_client
        self._device = device or _FakeDevice("dev-1")

    async def get_device(self, device_id: str):
        return self._device

    async def get_rest_client(self, device_id: str):
        assert self._rest_client is not None
        return self._rest_client

    async def get_ssh_client(self, device_id: str):
        assert self._ssh_client is not None
        return self._ssh_client


def test_coerce_resource_values_parses_sizes_and_percent() -> None:
    raw = {
        "total-memory": "1,5MiB",
        "free-memory": "512KiB",
        "cpu-count": "2",
        "cpu-load": "5%",
    }

    coerced = SystemService._coerce_resource_values(raw)

    assert coerced["total-memory"] == int(1.5 * 1024**2)
    assert coerced["free-memory"] == 512 * 1024
    assert coerced["cpu-count"] == 2
    assert coerced["cpu-load"] == 5.0


def test_parse_clock_print_output_parses_key_value_lines() -> None:
    output = """
        time: 12:00:00
        date: dec/17/2025
        time-zone-name: UTC
        junk-line-without-colon
        key-only:
    """

    parsed = SystemService._parse_clock_print_output(output)

    assert parsed["time"] == "12:00:00"
    assert parsed["date"] == "dec/17/2025"
    assert parsed["time-zone-name"] == "UTC"
    assert "junk-line-without-colon" not in parsed
    # key-only has no value, should be dropped
    assert "key-only" not in parsed


def test_parse_system_package_print_table_parses_installed_and_available() -> None:
    output = """
        Flags: X - disabled, A - available
        Columns: #, NAME, VERSION, BUILD-TIME, SIZE
        0 wireless 7.20.6 2025-12-04 12:00:39 864.1KiB
        1 XA calea 20.1KiB
        2 A gps 1.2MiB
        # comment line
    """

    parsed = SystemService._parse_system_package_print_table(output)

    assert {p["name"] for p in parsed} == {"wireless", "calea", "gps"}

    installed = next(p for p in parsed if p["name"] == "wireless")
    assert installed["version"] == "7.20.6"
    assert installed["build-time"] == "2025-12-04 12:00:39"
    assert installed["size"] == "864.1KiB"

    available_xa = next(p for p in parsed if p["name"] == "calea")
    assert available_xa["version"] is None
    assert available_xa["build-time"] is None
    assert available_xa["available"] is True
    assert available_xa["disabled"] is True


def test_parse_as_value_blocks_parses_multi_line_and_single_line_records() -> None:
    # This parser is deprecated in production but still supported for backward compatibility.
    # Cover both:
    # - multi-line key=value records separated by blank lines
    # - single-line table-style rows that include multiple key=value pairs and an index token
    output = """
        cpu-load=5
        board-name=hEX

        0 name=\"my router\" version=7.20.6 build-time=2025-12-04 12:00:39
        1 name=other version=7.20.7

        junk-without-equals
        key=value
    """

    blocks = SystemService._parse_as_value_blocks(output)

    assert len(blocks) == 4
    assert blocks[0] == {"cpu-load": "5", "board-name": "hEX"}
    assert blocks[1]["name"] == "my router"
    assert blocks[1]["version"] == "7.20.6"
    assert blocks[1]["build-time"] == "2025-12-04 12:00:39"
    assert blocks[2] == {"name": "other", "version": "7.20.7"}
    assert blocks[3] == {"key": "value"}


def test_normalize_packages_infers_flags_and_installed_status() -> None:
    packages = [
        {
            "name": "wireless",
            "version": "7.20.6",
            "build-time": "2025-12-04 12:00:39",
            "size": "864.1KiB",
            "flags": "XA",
        },
        {"name": "n/a", "flags": "A"},
        {"name": "disabled-explicit", "disabled": "true", "ver": "1", "build_time": "now"},
    ]

    service = SystemService(session=None, settings=Settings())
    normalized = service._normalize_packages(packages)

    wireless = next(p for p in normalized if p["name"] == "wireless")
    assert wireless["installed"] is True
    assert wireless["available"] is True
    assert wireless["disabled"] is True

    na = next(p for p in normalized if p["name"] == "n/a")
    assert na["installed"] is False
    assert na["available"] is True

    disabled_explicit = next(p for p in normalized if p["name"] == "disabled-explicit")
    assert disabled_explicit["disabled"] is True
    assert disabled_explicit["installed"] is True


@pytest.mark.asyncio
async def test_get_system_overview_when_rest_succeeds_and_identity_fetch_fails_uses_device_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rest = _FakeRestClient(
        responses={
            "/rest/system/resource": {
                "cpu-load": 5,
                "cpu-count": 2,
                "total-memory": 1024,
                "free-memory": 512,
                "uptime": "1d",
                "version": "7.20.6",
                "board-name": "hEX",
                "architecture-name": "arm",
            }
        },
        raise_on={"/rest/system/identity": RuntimeError("identity endpoint missing")},
    )

    device = _FakeDevice(id="dev-1", name="dev", system_identity="stored-id")

    monkeypatch.setattr(
        system_module,
        "DeviceService",
        lambda *_a, **_k: _FakeDeviceService(rest_client=rest, ssh_client=_FakeSSHClient(), device=device),
    )

    service = SystemService(session=None, settings=Settings())
    overview = await service.get_system_overview("dev-1")

    assert overview["transport"] == "rest"
    assert overview["fallback_used"] is False
    assert overview["rest_error"] is None
    assert overview["system_identity"] == "stored-id"
    assert rest.closed is True


@pytest.mark.asyncio
async def test_get_system_resource_parses_cpu_memory_and_uptime(monkeypatch: pytest.MonkeyPatch) -> None:
    rest = _FakeRestClient(
        responses={
            "/rest/system/resource": {
                "cpu-load": "10",
                "cpu-count": 4,
                "total-memory": 2000,
                "free-memory": 500,
                "uptime": "1h",
                "version": "7.20.6",
                "board-name": "hEX",
            },
            "/rest/system/identity": {"name": "rest-id"},
        }
    )

    monkeypatch.setattr(
        system_module,
        "DeviceService",
        lambda *_a, **_k: _FakeDeviceService(rest_client=rest, ssh_client=_FakeSSHClient()),
    )

    service = SystemService(session=None, settings=Settings())
    resource = await service.get_system_resource("dev-1")

    assert resource.cpu_usage_percent == 10.0
    assert resource.cpu_count == 4
    assert resource.memory_total_bytes == 2000
    assert resource.memory_free_bytes == 500
    assert resource.memory_used_bytes == 1500
    assert resource.memory_usage_percent == pytest.approx(75.0)
    assert resource.uptime_seconds == 3600
    assert resource.system_identity == "rest-id"
    assert rest.closed is True


@pytest.mark.asyncio
async def test_get_system_packages_when_rest_succeeds_marks_transport_and_normalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rest = _FakeRestClient(
        responses={
            "/rest/system/package": [
                {
                    "name": "system",
                    "version": "7.20.6",
                    "build-time": "2025-12-04 12:00:39",
                    "size": "8.8MiB",
                    "disabled": False,
                }
            ]
        }
    )

    monkeypatch.setattr(
        system_module,
        "DeviceService",
        lambda *_a, **_k: _FakeDeviceService(rest_client=rest, ssh_client=_FakeSSHClient()),
    )

    service = SystemService(session=None, settings=Settings())
    packages = await service.get_system_packages("dev-1")

    assert len(packages) == 1
    pkg = packages[0]
    assert pkg["name"] == "system"
    assert pkg["installed"] is True
    assert pkg["transport"] == "rest"
    assert pkg["fallback_used"] is False
    assert pkg["rest_error"] is None
    assert rest.closed is True


@pytest.mark.asyncio
async def test_update_system_identity_validation_and_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    # Validate guardrails
    monkeypatch.setattr(
        system_module,
        "DeviceService",
        lambda *_a, **_k: _FakeDeviceService(rest_client=_FakeRestClient(), ssh_client=_FakeSSHClient()),
    )

    service = SystemService(session=None, settings=Settings())

    with pytest.raises(ValueError):
        await service.update_system_identity("dev-1", "", dry_run=True)

    with pytest.raises(ValueError):
        await service.update_system_identity("dev-1", "x" * 256, dry_run=True)

    # Happy path variants
    rest = _FakeRestClient(responses={"/rest/system/identity": {"name": "old"}})

    monkeypatch.setattr(
        system_module,
        "DeviceService",
        lambda *_a, **_k: _FakeDeviceService(rest_client=rest, ssh_client=_FakeSSHClient()),
    )

    called: list[tuple[str, str]] = []

    def _dry_run(operation: str, device_id: str, planned_changes: dict) -> dict:
        called.append((operation, device_id))
        return {
            "operation": operation,
            "device_id": device_id,
            "planned_changes": planned_changes,
            "dry_run": True,
        }

    monkeypatch.setattr("routeros_mcp.security.safeguards.create_dry_run_response", _dry_run)

    service = SystemService(session=None, settings=Settings())

    # No change
    no_change = await service.update_system_identity("dev-1", "old", dry_run=False)
    assert no_change["changed"] is False

    # Dry run
    dry = await service.update_system_identity("dev-1", "new", dry_run=True)
    assert dry["dry_run"] is True
    assert called == [("system/set-identity", "dev-1")]

    # Apply
    applied = await service.update_system_identity("dev-1", "new", dry_run=False)
    assert applied["changed"] is True
    assert rest.patch_calls == [("/rest/system/identity", {"name": "new"})]
    assert rest.closed is True


@pytest.mark.asyncio
async def test_get_system_overview_when_rest_times_out_uses_ssh_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    rest = _FakeRestClient(error=RouterOSTimeoutError("timeout"))

    ssh = _FakeSSHClient(
        outputs={
            "/system/resource/print": """
                cpu-load: 5
                cpu-count: 2
                total-memory: 1MiB
                free-memory: 512KiB
                uptime: 1d2h
                version: 7.20.6
                board-name: hEX
                architecture-name: arm
            """,
            "/system/identity/print": "name: ssh-router\n",
        }
    )

    monkeypatch.setattr(
        system_module,
        "DeviceService",
        lambda *_a, **_k: _FakeDeviceService(rest_client=rest, ssh_client=ssh),
    )

    service = SystemService(session=None, settings=Settings())
    overview = await service.get_system_overview("dev-1")

    assert overview["transport"] == "ssh"
    assert overview["fallback_used"] is True
    assert "timeout" in (overview["rest_error"] or "")
    assert overview["cpu_usage_percent"] == 5.0
    assert overview["cpu_count"] == 2
    assert overview["memory_total_bytes"] == 1024**2
    assert overview["memory_free_bytes"] == 512 * 1024
    assert overview["system_identity"] == "ssh-router"


@pytest.mark.asyncio
async def test_get_system_overview_when_rest_and_ssh_fail_raises_runtimeerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rest = _FakeRestClient(error=RouterOSServerError("rest-down", status_code=500))
    ssh = _FakeSSHClient(error=RuntimeError("ssh-down"))

    monkeypatch.setattr(
        system_module,
        "DeviceService",
        lambda *_a, **_k: _FakeDeviceService(rest_client=rest, ssh_client=ssh),
    )

    service = SystemService(session=None, settings=Settings())

    with pytest.raises(RuntimeError) as excinfo:
        await service.get_system_overview("dev-1")

    msg = str(excinfo.value)
    assert "rest_error=" in msg
    assert "ssh_error=" in msg
    assert "rest-down" in msg
    assert "ssh-down" in msg


@pytest.mark.asyncio
async def test_get_system_overview_when_ssh_resource_output_empty_uses_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rest = _FakeRestClient(error=RouterOSServerError("rest-down", status_code=500))
    ssh = _FakeSSHClient(
        outputs={
            # Empty output should cause SSH fallback to raise.
            "/system/resource/print": "\n",
            "/system/identity/print": "name: ssh-router\n",
        }
    )

    monkeypatch.setattr(
        system_module,
        "DeviceService",
        lambda *_a, **_k: _FakeDeviceService(rest_client=rest, ssh_client=ssh),
    )

    service = SystemService(session=None, settings=Settings())

    overview = await service.get_system_overview("dev-1")

    assert overview["transport"] == "ssh"
    assert overview["fallback_used"] is True
    assert "rest-down" in (overview["rest_error"] or "")
    # Defaults applied by _coerce_resource_values
    assert overview["cpu_count"] == 1
    assert overview["cpu_usage_percent"] == 0.0
    assert overview["memory_total_bytes"] == 0
    assert overview["memory_free_bytes"] == 0
    assert overview["system_identity"] == "ssh-router"


@pytest.mark.asyncio
async def test_get_system_clock_when_rest_errors_uses_ssh_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    rest = _FakeRestClient(error=RouterOSNetworkError("net"))
    ssh = _FakeSSHClient(outputs={"/system/clock/print": "time: 12:00:00\ndate: dec/17/2025\n"})

    monkeypatch.setattr(
        system_module,
        "DeviceService",
        lambda *_a, **_k: _FakeDeviceService(rest_client=rest, ssh_client=ssh),
    )

    service = SystemService(session=None, settings=Settings())
    clock = await service.get_system_clock("dev-1")

    assert clock["transport"] == "ssh"
    assert clock["fallback_used"] is True
    assert "net" in (clock["rest_error"] or "")
    assert clock["time"] == "12:00:00"


@pytest.mark.asyncio
async def test_get_system_packages_when_rest_errors_uses_ssh_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    rest = _FakeRestClient(error=RouterOSTimeoutError("timeout"))
    ssh = _FakeSSHClient(
        outputs={
            "/system/package/print": "0 wireless 7.20.6 2025-12-04 12:00:39 864.1KiB\n1 XA calea 20.1KiB\n"
        }
    )

    monkeypatch.setattr(
        system_module,
        "DeviceService",
        lambda *_a, **_k: _FakeDeviceService(rest_client=rest, ssh_client=ssh),
    )

    service = SystemService(session=None, settings=Settings())
    packages = await service.get_system_packages("dev-1")

    assert {p["name"] for p in packages} == {"wireless", "calea"}
    assert all(p["transport"] == "ssh" for p in packages)
    assert all(p["fallback_used"] is True for p in packages)
    assert all("timeout" in (p["rest_error"] or "") for p in packages)
