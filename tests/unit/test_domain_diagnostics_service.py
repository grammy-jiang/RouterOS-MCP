from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.diagnostics import (
    MAX_PING_COUNT,
    MAX_TRACEROUTE_COUNT,
    MAX_TRACEROUTE_HOPS,
    DiagnosticsService,
)
from routeros_mcp.infra.routeros.exceptions import RouterOSSSHError, RouterOSTimeoutError
from routeros_mcp.mcp.errors import AuthenticationError, ValidationError


class _FakeRestClient:
    def __init__(
        self,
        *,
        ping_data: Any | None = None,
        trace_data: Any | None = None,
        post_exc: Exception | None = None,
    ) -> None:
        self._ping_data = ping_data
        self._trace_data = trace_data
        self._post_exc = post_exc
        self.calls: list[tuple[str, str, Any]] = []

    async def post(self, path: str, payload: dict[str, Any]) -> Any:
        self.calls.append(("post", path, payload))
        if self._post_exc is not None:
            raise self._post_exc
        if path == "/rest/tool/ping":
            return self._ping_data
        if path == "/rest/tool/traceroute":
            return self._trace_data
        return None

    async def close(self) -> None:
        self.calls.append(("close", "", None))


class _FakeSSHClient:
    def __init__(
        self, *, outputs: dict[str, str] | None = None, exc: Exception | None = None
    ) -> None:
        self._outputs = outputs or {}
        self._exc = exc
        self.calls: list[tuple[str, str]] = []

    async def execute(self, command: str) -> str:
        self.calls.append(("execute", command))
        if self._exc is not None:
            raise self._exc
        # Return first matching output by prefix to tolerate dynamic args.
        for prefix, output in self._outputs.items():
            if command.startswith(prefix):
                return output
        return ""

    async def close(self) -> None:
        self.calls.append(("close", ""))


class _FakeDeviceService:
    def __init__(
        self,
        *,
        rest_client: _FakeRestClient | None = None,
        ssh_client: _FakeSSHClient | None = None,
        rest_exc: Exception | None = None,
    ) -> None:
        self._rest_client = rest_client
        self._ssh_client = ssh_client
        self._rest_exc = rest_exc
        self.device = SimpleNamespace(id="dev-1", name="router-1", environment="lab")

    async def get_device(self, device_id: str) -> Any:
        return self.device

    async def get_rest_client(self, device_id: str) -> _FakeRestClient:
        if self._rest_exc is not None:
            raise self._rest_exc
        assert self._rest_client is not None
        return self._rest_client

    async def get_ssh_client(self, device_id: str) -> _FakeSSHClient:
        assert self._ssh_client is not None
        return self._ssh_client


def test_parse_rest_ping_result_counts_and_rtts() -> None:
    data = [
        {"status": "echo reply", "time": "10ms"},
        {"status": "timeout"},
        {"status": "echo reply", "time": 5},
    ]
    parsed = DiagnosticsService._parse_rest_ping_result("8.8.8.8", data)

    assert parsed["host"] == "8.8.8.8"
    assert parsed["packets_sent"] == 3
    assert parsed["packets_received"] == 2
    assert parsed["packet_loss_percent"] == pytest.approx(33.333, abs=0.01)
    assert parsed["min_rtt_ms"] == 5.0
    assert parsed["max_rtt_ms"] == 10.0


@pytest.mark.parametrize(
    "value,expected",
    [
        ("5ms", 5.0),
        ("6.2ms", 6.2),
        ("5ms945us", 5.945),
        ("945us", 0.945),
        ("", 0.0),
        ("not-a-number", 0.0),
    ],
)
def test_parse_rtt_ms(value: str, expected: float) -> None:
    assert DiagnosticsService._parse_rtt_ms(value) == pytest.approx(expected)


def test_parse_ssh_ping_output_summary_format() -> None:
    output = """  SEQ HOST                                     SIZE TTL TIME       STATUS
    0 8.8.8.8                                    56  56  10ms      echo reply
    1 8.8.8.8                                    56  56  timeout
    sent=2 received=1 packet-loss=50% min-rtt=10ms avg-rtt=10ms max-rtt=10ms
    """

    parsed = DiagnosticsService._parse_ssh_ping_output("8.8.8.8", output)
    assert parsed["packets_sent"] == 2
    assert parsed["packets_received"] == 1
    assert parsed["packet_loss_percent"] == 50.0
    assert parsed["min_rtt_ms"] == 10.0


def test_parse_ssh_ping_output_fallback_lines_and_timeouts() -> None:
    output = """ 0 1.1.1.1 56 64 time=5ms
    1 1.1.1.1 56 64 timeout
    2 1.1.1.1 56 64 5ms945us
    """

    parsed = DiagnosticsService._parse_ssh_ping_output("1.1.1.1", output)
    assert parsed["packets_sent"] == 3
    assert parsed["packets_received"] == 2
    assert parsed["packet_loss_percent"] == pytest.approx(33.333, abs=0.01)
    assert parsed["max_rtt_ms"] == pytest.approx(5.945)


def test_parse_rest_traceroute() -> None:
    data = [
        {"hop": 1, "address": "192.0.2.1", "time": "1ms"},
        {"hop": 2, "address": "198.51.100.1", "time": "5ms"},
        {"hop": 3, "address": "*"},
    ]

    hops = DiagnosticsService._parse_rest_traceroute(data)
    assert hops == [
        {"hop": 1, "address": "192.0.2.1", "rtt_ms": 1.0},
        {"hop": 2, "address": "198.51.100.1", "rtt_ms": 5.0},
        {"hop": 3, "address": "*", "rtt_ms": 0.0},
    ]


def test_parse_ssh_traceroute_output_with_timeout_and_headers() -> None:
    output = """ # ADDRESS
    1 192.0.2.1  1ms
    2 198.51.100.1 timeout
    3 203.0.113.1  10ms
    """

    hops = DiagnosticsService._parse_ssh_traceroute_output(output)
    assert hops == [
        {"hop": 1, "address": "192.0.2.1", "rtt_ms": 1.0},
        {"hop": 2, "address": "198.51.100.1", "rtt_ms": 0.0},
        {"hop": 3, "address": "203.0.113.1", "rtt_ms": 10.0},
    ]


@pytest.mark.asyncio
async def test_ping_validates_count_limits() -> None:
    service = DiagnosticsService(session=None, settings=Settings())
    service.device_service = _FakeDeviceService(
        rest_exc=RouterOSTimeoutError("no rest"), ssh_client=_FakeSSHClient()
    )

    with pytest.raises(ValidationError):
        await service.ping("dev-1", "8.8.8.8", count=MAX_PING_COUNT + 1)

    with pytest.raises(ValidationError):
        await service.ping("dev-1", "8.8.8.8", count=0)


@pytest.mark.asyncio
async def test_ping_rest_success_sets_transport_metadata() -> None:
    rest = _FakeRestClient(
        ping_data=[
            {"status": "echo reply", "time": "10ms"},
            {"status": "echo reply", "time": "5ms"},
        ]
    )
    device_service = _FakeDeviceService(rest_client=rest, ssh_client=_FakeSSHClient())

    service = DiagnosticsService(session=None, settings=Settings())
    service.device_service = device_service

    result = await service.ping("dev-1", "8.8.8.8", count=2)

    assert result["transport"] == "rest"
    assert result["fallback_used"] is False
    assert result["rest_error"] is None
    assert result["packets_sent"] == 2
    assert result["packets_received"] == 2
    assert any(call[0] == "close" for call in rest.calls)


@pytest.mark.asyncio
async def test_ping_rest_failure_falls_back_to_ssh() -> None:
    rest_exc = AuthenticationError("bad token")
    ssh_output = "sent=1 received=1 packet-loss=0% min-rtt=10ms avg-rtt=10ms max-rtt=10ms"
    ssh = _FakeSSHClient(outputs={"/tool/ping": ssh_output})

    device_service = _FakeDeviceService(rest_exc=rest_exc, ssh_client=ssh)

    service = DiagnosticsService(session=None, settings=Settings())
    service.device_service = device_service

    result = await service.ping("dev-1", "8.8.8.8", count=1)

    assert result["transport"] == "ssh"
    assert result["fallback_used"] is True
    assert "bad token" in (result["rest_error"] or "")
    assert result["packets_received"] == 1


@pytest.mark.asyncio
async def test_ping_ssh_failure_propagates() -> None:
    device_service = _FakeDeviceService(
        rest_exc=RouterOSTimeoutError("rest timeout"),
        ssh_client=_FakeSSHClient(exc=RouterOSSSHError("ssh down")),
    )

    service = DiagnosticsService(session=None, settings=Settings())
    service.device_service = device_service

    with pytest.raises(RouterOSSSHError):
        await service.ping("dev-1", "8.8.8.8", count=1)


@pytest.mark.asyncio
async def test_traceroute_validates_count_limits() -> None:
    service = DiagnosticsService(session=None, settings=Settings())
    service.device_service = _FakeDeviceService(
        rest_exc=RouterOSTimeoutError("no rest"), ssh_client=_FakeSSHClient()
    )

    with pytest.raises(ValidationError):
        await service.traceroute("dev-1", "8.8.8.8", count=MAX_TRACEROUTE_COUNT + 1)

    with pytest.raises(ValidationError):
        await service.traceroute("dev-1", "8.8.8.8", count=0)


@pytest.mark.asyncio
async def test_traceroute_validates_max_hops_limits() -> None:
    """Test traceroute validates max_hops is within 1-64 range."""
    from routeros_mcp.domain.services.diagnostics import MAX_TRACEROUTE_HOPS
    
    service = DiagnosticsService(session=None, settings=Settings())
    service.device_service = _FakeDeviceService(
        rest_exc=RouterOSTimeoutError("no rest"), ssh_client=_FakeSSHClient()
    )

    # max_hops too high
    with pytest.raises(ValidationError, match="max_hops cannot exceed"):
        await service.traceroute("dev-1", "8.8.8.8", count=1, max_hops=MAX_TRACEROUTE_HOPS + 1)

    # max_hops too low
    with pytest.raises(ValidationError, match="max_hops must be at least 1"):
        await service.traceroute("dev-1", "8.8.8.8", count=1, max_hops=0)

    # Valid max_hops should not raise
    rest = _FakeRestClient(trace_data=[{"hop": 1, "address": "192.0.2.1", "time": "1ms"}])
    service.device_service = _FakeDeviceService(rest_client=rest, ssh_client=_FakeSSHClient())
    
    # Should work with min value
    result = await service.traceroute("dev-1", "8.8.8.8", count=1, max_hops=1)
    assert result is not None
    
    # Should work with max value
    result = await service.traceroute("dev-1", "8.8.8.8", count=1, max_hops=MAX_TRACEROUTE_HOPS)
    assert result is not None


@pytest.mark.asyncio
async def test_traceroute_rest_success_sets_transport_metadata() -> None:
    rest = _FakeRestClient(trace_data=[{"hop": 1, "address": "192.0.2.1", "time": "1ms"}])
    device_service = _FakeDeviceService(rest_client=rest, ssh_client=_FakeSSHClient())

    service = DiagnosticsService(session=None, settings=Settings())
    service.device_service = device_service

    result = await service.traceroute("dev-1", "8.8.8.8", count=1)

    assert result["transport"] == "rest"
    assert result["fallback_used"] is False
    assert result["rest_error"] is None
    assert result["hops"][0]["hop"] == 1
    assert any(call[0] == "close" for call in rest.calls)


@pytest.mark.asyncio
async def test_traceroute_rest_failure_falls_back_to_ssh() -> None:
    ssh_output = """ 1 192.0.2.1  1ms
    2 198.51.100.1 timeout
    """
    ssh = _FakeSSHClient(outputs={"/tool/traceroute": ssh_output})

    device_service = _FakeDeviceService(
        rest_exc=RouterOSTimeoutError("rest timeout"), ssh_client=ssh
    )

    service = DiagnosticsService(session=None, settings=Settings())
    service.device_service = device_service

    result = await service.traceroute("dev-1", "8.8.8.8", count=1)

    assert result["transport"] == "ssh"
    assert result["fallback_used"] is True
    assert "rest timeout" in (result["rest_error"] or "")
    assert result["hops"][1]["rtt_ms"] == 0.0
