from __future__ import annotations

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import diagnostics as diagnostics_module
from routeros_mcp.domain.services.diagnostics import DiagnosticsService
from routeros_mcp.mcp.errors import ValidationError


class _FakeRestClient:
    def __init__(self, ping_payload: list[dict], trace_payload: list[dict]):
        self.ping_payload = ping_payload
        self.trace_payload = trace_payload
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    async def post(self, path: str, payload: dict):
        self.calls.append((path, payload))
        if path.endswith("ping"):
            return self.ping_payload
        return self.trace_payload

    async def close(self):
        self.closed = True


class _FakeDeviceService:
    def __init__(self, client: _FakeRestClient) -> None:
        self.client = client

    async def get_device(self, device_id: str):
        return {"id": device_id}

    async def get_rest_client(self, device_id: str):
        return self.client


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch):
    client = _FakeRestClient(
        ping_payload=[
            {"status": "echo reply", "time": "10ms"},
            {"status": "timeout", "time": "0ms"},
        ],
        trace_payload=[
            {"hop": 1, "address": "10.0.0.1", "time": "5ms"},
            {"hop": 2, "address": "8.8.8.8", "time": "10ms"},
        ],
    )
    monkeypatch.setattr(
        diagnostics_module, "DeviceService", lambda *args, **kwargs: _FakeDeviceService(client)
    )
    return client


@pytest.mark.asyncio
async def test_ping_success_and_limits(fake_env):
    client = fake_env
    service = DiagnosticsService(session=None, settings=Settings())

    result = await service.ping("dev-1", "8.8.8.8", count=2)
    assert result["packets_sent"] == 2
    assert result["packets_received"] == 2
    assert result["max_rtt_ms"] == 10.0
    assert client.closed is True

    with pytest.raises(ValidationError):
        await service.ping("dev-1", "8.8.8.8", count=0)

    with pytest.raises(ValidationError):
        await service.ping("dev-1", "8.8.8.8", count=diagnostics_module.MAX_PING_COUNT + 1)


@pytest.mark.asyncio
async def test_traceroute_success_and_limits(fake_env):
    service = DiagnosticsService(session=None, settings=Settings())

    result = await service.traceroute("dev-1", "8.8.8.8", count=2)
    assert len(result["hops"]) == 2
    assert result["hops"][0]["rtt_ms"] == 5.0

    with pytest.raises(ValidationError):
        await service.traceroute("dev-1", "8.8.8.8", count=0)

    with pytest.raises(ValidationError):
        await service.traceroute(
            "dev-1", "8.8.8.8", count=diagnostics_module.MAX_TRACEROUTE_COUNT + 1
        )
