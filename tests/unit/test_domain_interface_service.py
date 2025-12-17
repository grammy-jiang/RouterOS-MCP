from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.interface import InterfaceService
from routeros_mcp.infra.routeros.exceptions import RouterOSNetworkError


class _FakeRestClient:
    def __init__(self, *, responses: list[object] | None = None, exc: Exception | None = None) -> None:
        self._responses = list(responses or [])
        self._exc = exc
        self.closed = False
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    async def get(self, path: str, params: dict[str, object] | None = None) -> object:
        self.calls.append((path, params))
        if self._exc:
            raise self._exc
        if self._responses:
            return self._responses.pop(0)
        return {}

    async def close(self) -> None:
        self.closed = True


class _FakeSSHClient:
    def __init__(
        self,
        *,
        outputs: dict[str, str] | None = None,
        exc_for: set[str] | None = None,
    ) -> None:
        self._outputs = outputs or {}
        self._exc_for = exc_for or set()
        self.closed = False
        self.commands: list[str] = []

    async def execute(self, command: str) -> str:
        self.commands.append(command)
        if command in self._exc_for:
            raise RuntimeError(f"ssh failed for {command}")
        return self._outputs.get(command, "")

    async def close(self) -> None:
        self.closed = True


class _StubDeviceService:
    def __init__(self, *, rest_client: _FakeRestClient | None, ssh_client: _FakeSSHClient | None) -> None:
        self._rest_client = rest_client
        self._ssh_client = ssh_client

    async def get_device(self, _device_id: str) -> object:
        return SimpleNamespace()

    async def get_rest_client(self, _device_id: str) -> _FakeRestClient:
        assert self._rest_client is not None
        return self._rest_client

    async def get_ssh_client(self, _device_id: str) -> _FakeSSHClient:
        assert self._ssh_client is not None
        return self._ssh_client


def _make_settings() -> Settings:
    return Settings(database_url="sqlite+aiosqlite:///:memory:")


def test_parse_interface_print_output_parses_flags_and_fields() -> None:
    output = """
Flags: D - DYNAMIC; R - RUNNING; S - SLAVE
 #   NAME    TYPE   ACTUAL-MTU  L2MTU  MAX-L2MTU  MAC-ADDRESS
 0  R  ether1 ether      1500   1514       9796  78:9A:18:A2:F3:D2
 1  RS ether2 ether      1500   1514       9796  78:9A:18:A2:F3:D3
 2  D  ether3 ether      1600   1514       9796  78:9A:18:A2:F3:D4
"""

    interfaces = InterfaceService._parse_interface_print_output(output)

    assert [i["name"] for i in interfaces] == ["ether1", "ether2", "ether3"]
    assert interfaces[0]["running"] is True
    assert interfaces[0]["disabled"] is False
    assert interfaces[1]["running"] is True
    assert interfaces[2]["disabled"] is True
    assert interfaces[2]["mtu"] == 1600


def test_parse_interface_print_output_skips_bad_lines_and_handles_errors() -> None:
    output = """
Flags: D - DYNAMIC; R - RUNNING; S - SLAVE
this is not a data line
 0 R
 1  R  ether1 ether 1500 1514 9796 78:9A:18:A2:F3:D2
"""

    interfaces = InterfaceService._parse_interface_print_output(output)

    assert len(interfaces) == 1
    assert interfaces[0]["name"] == "ether1"


def test_parse_monitor_traffic_output_handles_units_and_spaces() -> None:
    output = """
       rx-packets-per-second:     3 707
          rx-bits-per-second:  38.2Mbps
       tx-packets-per-second:       462
          tx-bits-per-second: 393.3kbps
"""

    stats = InterfaceService._parse_monitor_traffic_output(output)

    assert stats["rx_packets_per_second"] == 3707
    assert stats["rx_bits_per_second"] == 38_200_000
    assert stats["tx_packets_per_second"] == 462
    assert stats["tx_bits_per_second"] == 393_300


def test_parse_monitor_traffic_output_handles_gbps_and_invalid_values() -> None:
    output = """
this line has no colon
rx-bits-per-second: 1.5Gbps
tx-bits-per-second: not-a-number
rx-packets-per-second: 10
tx-packets-per-second: 20
"""

    stats = InterfaceService._parse_monitor_traffic_output(output)

    assert stats["rx_bits_per_second"] == 1_500_000_000
    assert stats["tx_bits_per_second"] == 0


@pytest.mark.asyncio
async def test_get_interface_stats_via_ssh_skips_empty_name_and_filtered_names() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_client = _FakeSSHClient(
        outputs={
            "/interface/print": "ignored",
            "/interface/monitor-traffic ether1 once": "rx-bits-per-second: 1bps\n",
        }
    )

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)
    service._parse_interface_print_output = MagicMock(
        return_value=[
            {"name": ""},
            {"name": "ether2"},
            {"name": "ether1"},
        ]
    )

    stats = await service._get_interface_stats_via_ssh("dev-1", ["ether1"])

    assert stats == [
        {
            "rx_bits_per_second": 1,
            "tx_bits_per_second": 0,
            "rx_packets_per_second": 0,
            "tx_packets_per_second": 0,
            "name": "ether1",
        }
    ]


@pytest.mark.asyncio
async def test_list_interfaces_when_rest_succeeds_sets_transport_metadata() -> None:
    rest_client = _FakeRestClient(
        responses=[
            [
                {
                    ".id": "*1",
                    "name": "ether1",
                    "type": "ether",
                    "running": True,
                    "disabled": False,
                    "comment": "uplink",
                    "mtu": 1500,
                    "l2mtu": 1514,
                    "max-l2mtu": 9796,
                    "mac-address": "AA:BB:CC:DD:EE:FF",
                }
            ]
        ]
    )

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=None)

    interfaces = await service.list_interfaces("dev-1")

    assert interfaces[0]["id"] == "*1"
    assert interfaces[0]["name"] == "ether1"
    assert interfaces[0]["transport"] == "rest"
    assert interfaces[0]["fallback_used"] is False
    assert interfaces[0]["rest_error"] is None
    assert rest_client.closed is True


@pytest.mark.asyncio
async def test_list_interfaces_when_rest_fails_uses_ssh_fallback() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_output = """
Flags: D - DYNAMIC; R - RUNNING; S - SLAVE
 # NAME TYPE ACTUAL-MTU L2MTU MAX-L2MTU MAC-ADDRESS
 0  R ether1 ether 1500 1514 9796 78:9A:18:A2:F3:D2
"""
    ssh_client = _FakeSSHClient(outputs={"/interface/print": ssh_output})

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    interfaces = await service.list_interfaces("dev-1")

    assert interfaces[0]["name"] == "ether1"
    assert interfaces[0]["transport"] == "ssh"
    assert interfaces[0]["fallback_used"] is True
    assert "rest down" in (interfaces[0]["rest_error"] or "")
    assert rest_client.closed is True
    assert ssh_client.closed is True


@pytest.mark.asyncio
async def test_list_interfaces_when_both_transports_fail_raises_runtime_error() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_client = _FakeSSHClient(exc_for={"/interface/print"})

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    with pytest.raises(RuntimeError, match="Interface listing failed via REST and SSH"):
        await service.list_interfaces("dev-1")


@pytest.mark.asyncio
async def test_get_interface_when_rest_returns_value_sets_metadata() -> None:
    rest_client = _FakeRestClient(
        responses=[
            {
                ".id": "*2",
                "name": "ether2",
                "type": "ether",
                "running": True,
                "disabled": False,
                "comment": "",
                "mtu": 1500,
                "l2mtu": 1514,
                "max-l2mtu": 9796,
                "mac-address": "AA:AA:AA:AA:AA:AA",
                "last-link-up-time": "jan/01/2025 00:00:00",
            }
        ]
    )

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=None)

    interface = await service.get_interface("dev-1", "*2")

    assert interface["id"] == "*2"
    assert interface["name"] == "ether2"
    assert interface["transport"] == "rest"
    assert interface["fallback_used"] is False


@pytest.mark.asyncio
async def test_get_interface_when_rest_fails_falls_back_to_ssh_and_can_return_empty() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_output = """
Flags: D - DYNAMIC; R - RUNNING; S - SLAVE
 # NAME TYPE ACTUAL-MTU L2MTU MAX-L2MTU MAC-ADDRESS
 0  R ether1 ether 1500 1514 9796 78:9A:18:A2:F3:D2
"""
    ssh_client = _FakeSSHClient(outputs={"/interface/print": ssh_output})

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    interface = await service.get_interface("dev-1", "*999")

    assert interface["transport"] == "ssh"
    assert interface["fallback_used"] is True
    assert interface.get("id") in {None, "", "*999"}


@pytest.mark.asyncio
async def test_get_interface_when_both_transports_fail_raises_runtime_error() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_client = _FakeSSHClient(exc_for={"/interface/print"})

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    with pytest.raises(RuntimeError, match="Get interface failed via REST and SSH"):
        await service.get_interface("dev-1", "*1")


@pytest.mark.asyncio
async def test_get_interface_when_ssh_finds_interface_by_id_returns_details() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_output = """
Flags: D - DYNAMIC; R - RUNNING; S - SLAVE
 # NAME TYPE ACTUAL-MTU L2MTU MAX-L2MTU MAC-ADDRESS
 0  R ether1 ether 1500 1514 9796 78:9A:18:A2:F3:D2
"""
    ssh_client = _FakeSSHClient(outputs={"/interface/print": ssh_output})

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    interface = await service.get_interface("dev-1", "0")

    assert interface["name"] == "ether1"
    assert interface["transport"] == "ssh"
    assert interface["fallback_used"] is True


@pytest.mark.asyncio
async def test_get_interface_stats_via_rest_issues_one_shot_monitor_requests() -> None:
    rest_client = _FakeRestClient(
        responses=[
            {
                "name": "ether1",
                "rx-bits-per-second": 123,
                "tx-bits-per-second": 456,
                "rx-packets-per-second": 7,
                "tx-packets-per-second": 8,
            }
        ]
    )

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=None)

    stats = await service.get_interface_stats("dev-1", ["ether1"])

    assert stats[0]["name"] == "ether1"
    assert stats[0]["rx_bits_per_second"] == 123
    assert stats[0]["transport"] == "rest"
    assert rest_client.calls[0][0] == "/rest/interface/monitor-traffic"


@pytest.mark.asyncio
async def test_get_interface_stats_via_rest_filters_out_unexpected_interface_name() -> None:
    rest_client = _FakeRestClient(
        responses=[
            {
                "name": "ether2",
                "rx-bits-per-second": 1,
            }
        ]
    )

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=None)

    stats = await service._get_interface_stats_via_rest("dev-1", ["ether1"])

    assert stats == []


@pytest.mark.asyncio
async def test_get_interface_stats_when_rest_fails_uses_ssh_and_falls_back_to_zeros() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_interfaces = """
Flags: D - DYNAMIC; R - RUNNING; S - SLAVE
 # NAME TYPE ACTUAL-MTU L2MTU MAX-L2MTU MAC-ADDRESS
 0  R ether1 ether 1500 1514 9796 78:9A:18:A2:F3:D2
 1  R ether2 ether 1500 1514 9796 78:9A:18:A2:F3:D3
"""
    ssh_monitor_ok = """
rx-packets-per-second: 1
rx-bits-per-second: 1kbps
tx-packets-per-second: 2
tx-bits-per-second: 2bps
"""

    ssh_client = _FakeSSHClient(
        outputs={
            "/interface/print": ssh_interfaces,
            "/interface/monitor-traffic ether1 once": ssh_monitor_ok,
        },
        exc_for={"/interface/monitor-traffic ether2 once"},
    )

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    stats = await service.get_interface_stats("dev-1")

    names = {s["name"] for s in stats}
    assert names == {"ether1", "ether2"}

    ether2 = next(s for s in stats if s["name"] == "ether2")
    assert ether2["rx_bits_per_second"] == 0
    assert ether2["transport"] == "ssh"


@pytest.mark.asyncio
async def test_get_interface_stats_when_both_transports_fail_raises_runtime_error() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_client = _FakeSSHClient(exc_for={"/interface/print"})

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    with pytest.raises(RuntimeError, match="Interface stats failed via REST and SSH"):
        await service.get_interface_stats("dev-1")


@pytest.mark.asyncio
async def test_get_interface_stats_via_rest_when_no_interface_names_uses_list_interfaces_and_list_response() -> None:
    rest_client = _FakeRestClient(
        responses=[
            [
                {"name": "ether1", "rx-bits-per-second": 1},
                "not-a-dict",
            ]
        ]
    )

    service = InterfaceService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=None)
    service.list_interfaces = AsyncMock(return_value=[{"name": "ether1"}])

    stats = await service._get_interface_stats_via_rest("dev-1", None)

    assert stats == [
        {
            "name": "ether1",
            "rx_bits_per_second": 1,
            "tx_bits_per_second": 0,
            "rx_packets_per_second": 0,
            "tx_packets_per_second": 0,
        }
    ]
