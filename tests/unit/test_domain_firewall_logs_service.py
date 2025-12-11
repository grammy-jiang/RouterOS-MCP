from __future__ import annotations

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import firewall_logs as firewall_logs_module
from routeros_mcp.mcp.errors import ValidationError


class _FakeRestClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, dict | None]] = []
        self.store = {
            "/rest/ip/firewall/filter": [
                {
                    ".id": "*1",
                    "chain": "input",
                    "action": "accept",
                    "protocol": "tcp",
                    "dst-port": "22",
                    "src-address": "198.51.100.10",
                    "comment": "ssh",
                    "disabled": False,
                }
            ],
            "/rest/ip/firewall/nat": [
                {
                    ".id": "*a",
                    "chain": "dstnat",
                    "action": "dst-nat",
                    "out-interface": "ether1",
                    "in-interface": "ether2",
                    "to-addresses": "192.0.2.10",
                    "to-ports": "8080",
                    "comment": "http",
                    "disabled": False,
                }
            ],
            "/rest/ip/firewall/address-list": [
                {
                    ".id": "*x",
                    "list": "mcp-managed",
                    "address": "192.0.2.1",
                    "comment": "seed",
                    "timeout": "1d",
                },
                {".id": "*y", "list": "other", "address": "198.51.100.2", "comment": "other"},
            ],
            "/rest/log": [
                {".id": "*l1", "time": "00:00:01", "topics": "info,system", "message": "started"},
                {
                    ".id": "*l2",
                    "time": "00:00:02",
                    "topics": ["warning", "firewall"],
                    "message": "drop",
                },
            ],
            "/rest/system/logging": [
                {"topics": "info,warning", "action": "memory", "prefix": "sys"},
                {"topics": ["firewall"], "action": "disk", "prefix": "fw"},
            ],
        }

    async def get(self, path: str):
        self.calls.append(("get", path, None))
        return self.store.get(path, {})

    async def close(self):
        self.calls.append(("close", None, None))


class _FakeDeviceService:
    def __init__(self, client: _FakeRestClient) -> None:
        self.client = client

    async def get_device(self, device_id: str):
        return {"id": device_id}

    async def get_rest_client(self, device_id: str):
        return self.client


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch):
    client = _FakeRestClient()
    device_service = _FakeDeviceService(client)

    monkeypatch.setattr(
        firewall_logs_module, "DeviceService", lambda *args, **kwargs: device_service
    )

    return client, device_service


@pytest.mark.asyncio
async def test_list_firewall_collections(fake_env):
    client, _ = fake_env
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())

    filter_rules = await service.list_filter_rules("dev-1")
    assert filter_rules[0]["id"] == "*1"
    assert filter_rules[0]["dst_port"] == "22"

    nat_rules = await service.list_nat_rules("dev-1")
    assert nat_rules[0]["to_addresses"] == "192.0.2.10"

    address_lists = await service.list_address_lists("dev-1")
    assert {entry["id"] for entry in address_lists} == {"*x", "*y"}

    filtered_lists = await service.list_address_lists("dev-1", list_name="mcp-managed")
    assert len(filtered_lists) == 1
    assert filtered_lists[0]["address"] == "192.0.2.1"

    assert ("close", None, None) in client.calls


@pytest.mark.asyncio
async def test_get_recent_logs_and_limit(fake_env):
    client, _ = fake_env
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())

    logs, total = await service.get_recent_logs("dev-1", limit=2, topics=["firewall"])
    assert total == 2
    # Only one log due to limit and topics filter should match the second entry
    assert len(logs) == 1
    assert logs[0]["topics"] == ["warning", "firewall"]

    # Exceeding limit should raise validation error
    with pytest.raises(ValidationError):
        await service.get_recent_logs("dev-1", limit=firewall_logs_module.MAX_LOG_ENTRIES + 1)

    assert ("close", None, None) in client.calls


@pytest.mark.asyncio
async def test_get_logging_config(fake_env):
    client, _ = fake_env
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())

    config = await service.get_logging_config("dev-1")
    assert config[0]["topics"] == ["info", "warning"]
    assert config[1]["action"] == "disk"

    assert ("close", None, None) in client.calls
