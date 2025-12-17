from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.routing import RoutingService
from routeros_mcp.infra.routeros.exceptions import RouterOSNetworkError


class _FakeRestClient:
    def __init__(self, *, responses: list[object] | None = None, exc: Exception | None = None) -> None:
        self._responses = list(responses or [])
        self._exc = exc
        self.closed = False
        self.calls: list[str] = []

    async def get(self, path: str, params: dict[str, object] | None = None) -> object:
        del params
        self.calls.append(path)
        if self._exc:
            raise self._exc
        if self._responses:
            return self._responses.pop(0)
        return {}

    async def close(self) -> None:
        self.closed = True


class _FakeSSHClient:
    def __init__(self, *, output: str = "", exc: Exception | None = None) -> None:
        self._output = output
        self._exc = exc
        self.closed = False
        self.commands: list[str] = []

    async def execute(self, command: str) -> str:
        self.commands.append(command)
        if self._exc:
            raise self._exc
        return self._output

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


def test_parse_route_print_output_parses_common_formats_and_ignores_headers() -> None:
    output = """
Flags: X - disabled, A - active, D - dynamic, C - connect, S - static
Columns: DST-ADDRESS, GATEWAY, DISTANCE, ROUTING-TABLE
 # DST-ADDRESS GATEWAY DISTANCE
 0 ADS 0.0.0.0/0 192.168.88.1 main 1
 DAC 192.168.88.0/24 ether1 0
"""

    routes = RoutingService._parse_route_print_output(output)

    assert len(routes) == 2
    assert routes[0]["dst_address"] == "0.0.0.0/0"
    assert routes[0]["gateway"] == "192.168.88.1"
    assert routes[0]["distance"] == 1
    assert routes[0]["dynamic"] is True

    assert routes[1]["dst_address"] == "192.168.88.0/24"
    assert routes[1]["gateway"] == "ether1"
    assert routes[1]["connected"] is True


def test_parse_route_print_output_skips_header_like_lines_and_handles_star_ids() -> None:
    output = """
dst-address gateway distance
*3 ADS 0.0.0.0/0 192.168.88.1 main 1
"""

    routes = RoutingService._parse_route_print_output(output)

    assert len(routes) == 1
    assert routes[0]["id"] == "*3"
    assert routes[0]["gateway"] == "192.168.88.1"


def test_parse_route_print_output_handles_non_int_distance_and_short_lines() -> None:
    output = """
 0 A 10.0.0.0/24 ether1 main x
 1 A 10.0.1.0/24
"""

    routes = RoutingService._parse_route_print_output(output)

    assert len(routes) == 1
    assert routes[0]["dst_address"] == "10.0.0.0/24"
    assert routes[0]["gateway"] == "main"
    assert routes[0]["distance"] == 0


@pytest.mark.asyncio
async def test_get_routing_summary_when_rest_succeeds_counts_routes() -> None:
    rest_client = _FakeRestClient(
        responses=[
            [
                {".id": "*1", "dst-address": "0.0.0.0/0", "gateway": "1.1.1.1", "distance": 1, "static": True},
                {".id": "*2", "dst-address": "10.0.0.0/24", "gateway": "ether1", "distance": 0, "connect": True},
                {".id": "*3", "dst-address": "10.0.1.0/24", "gateway": "10.0.0.2", "distance": 1, "dynamic": True},
            ]
        ]
    )

    service = RoutingService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=None)

    summary = await service.get_routing_summary("dev-1")

    assert summary["total_routes"] == 3
    assert summary["static_routes"] == 1
    assert summary["connected_routes"] == 1
    assert summary["dynamic_routes"] == 1
    assert summary["transport"] == "rest"
    assert rest_client.closed is True


@pytest.mark.asyncio
async def test_get_routing_summary_when_rest_returns_non_list_yields_empty_counts() -> None:
    rest_client = _FakeRestClient(responses=[{"unexpected": True}])

    service = RoutingService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=None)

    summary = await service.get_routing_summary("dev-1")

    assert summary["total_routes"] == 0
    assert summary["routes"] == []
    assert summary["transport"] == "rest"


@pytest.mark.asyncio
async def test_get_routing_summary_when_rest_fails_uses_ssh_fallback() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_output = """
 0 ADS 0.0.0.0/0 192.168.88.1 main 1
 DAC 192.168.88.0/24 ether1 0
"""
    ssh_client = _FakeSSHClient(output=ssh_output)

    service = RoutingService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    summary = await service.get_routing_summary("dev-1")

    assert summary["transport"] == "ssh"
    assert summary["fallback_used"] is True
    assert summary["total_routes"] == 2
    assert rest_client.closed is True
    assert ssh_client.closed is True


@pytest.mark.asyncio
async def test_get_routing_summary_when_both_transports_fail_raises_runtime_error() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_client = _FakeSSHClient(exc=RuntimeError("ssh down"))

    service = RoutingService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    with pytest.raises(RuntimeError, match="Routing summary failed via REST and SSH"):
        await service.get_routing_summary("dev-1")


@pytest.mark.asyncio
async def test_get_route_when_rest_returns_empty_dict_returns_empty() -> None:
    rest_client = _FakeRestClient(responses=[None])

    service = RoutingService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=None)

    route = await service.get_route("dev-1", "*1")

    assert route == {"transport": "rest", "fallback_used": False, "rest_error": None}


@pytest.mark.asyncio
async def test_get_route_when_rest_succeeds_returns_normalized_route() -> None:
    rest_client = _FakeRestClient(
        responses=[
            {
                ".id": "*9",
                "dst-address": "10.0.0.0/24",
                "gateway": "10.0.0.1",
                "distance": 2,
                "scope": 30,
                "target-scope": 10,
                "comment": "test",
                "active": True,
                "dynamic": False,
            }
        ]
    )

    service = RoutingService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=None)

    route = await service.get_route("dev-1", "*9")

    assert route["id"] == "*9"
    assert route["dst_address"] == "10.0.0.0/24"
    assert route["gateway"] == "10.0.0.1"
    assert route["transport"] == "rest"


@pytest.mark.asyncio
async def test_get_route_when_ssh_matches_by_id_returns_route() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_output = """
 0 ADS 0.0.0.0/0 192.168.88.1 main 1
"""
    ssh_client = _FakeSSHClient(output=ssh_output)

    service = RoutingService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    route = await service.get_route("dev-1", "0")

    assert route["gateway"] == "192.168.88.1"
    assert route["transport"] == "ssh"


@pytest.mark.asyncio
async def test_get_route_when_rest_fails_falls_back_to_ssh_by_id_or_index() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_output = """
 0 ADS 0.0.0.0/0 192.168.88.1 main 1
 DAC 192.168.88.0/24 ether1 0
"""
    ssh_client = _FakeSSHClient(output=ssh_output)

    service = RoutingService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    route_by_index = await service.get_route("dev-1", "1")

    assert route_by_index["dst_address"] == "192.168.88.0/24"
    assert route_by_index["gateway"] == "ether1"
    assert route_by_index["transport"] == "ssh"


@pytest.mark.asyncio
async def test_get_route_when_both_transports_fail_raises_runtime_error() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_client = _FakeSSHClient(exc=RuntimeError("ssh down"))

    service = RoutingService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    with pytest.raises(RuntimeError, match="Get route failed via REST and SSH"):
        await service.get_route("dev-1", "*1")


@pytest.mark.asyncio
async def test_get_route_when_ssh_cannot_parse_route_id_returns_empty() -> None:
    rest_client = _FakeRestClient(exc=RouterOSNetworkError("rest down"))
    ssh_output = """
 0 ADS 0.0.0.0/0 192.168.88.1 main 1
"""
    ssh_client = _FakeSSHClient(output=ssh_output)

    service = RoutingService(MagicMock(), _make_settings())
    service.device_service = _StubDeviceService(rest_client=rest_client, ssh_client=ssh_client)

    route = await service.get_route("dev-1", "not-an-int")

    assert route["transport"] == "ssh"
    assert route["fallback_used"] is True
    assert route.get("dst_address", "") == ""
