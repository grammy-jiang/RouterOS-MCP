from __future__ import annotations

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import firewall_logs as firewall_logs_module
from routeros_mcp.infra.routeros.exceptions import RouterOSTimeoutError
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


class _FakeSSHClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def execute(self, command: str) -> str:
        self.calls.append(("execute", command))
        if command == "/ip/firewall/filter/print":
            return """ #   CHAIN      ACTION    PROTOCOL  DST-PORT  COMMENT
 *1  input      accept    tcp       22        ssh"""
        elif command == "/ip/firewall/nat/print":
            return """ #    CHAIN     ACTION     IN-INTERFACE  OUT-INTERFACE  TO-ADDRESSES  COMMENT
 *a   dstnat    dst-nat    ether2        ether1         192.0.2.10    http"""
        elif command == "/ip/firewall/address-list/print":
            return """ #    LIST         ADDRESS       COMMENT  TIMEOUT
 *x   mcp-managed  192.0.2.1     seed     1d
 *y   other        198.51.100.2  other    """
        elif command == "/log/print":
            return """ #   TIME      TOPICS          MESSAGE
 *l1 00:00:01  info,system     started
 *l2 00:00:02  warning,firewall drop"""
        elif command == "/system/logging/print":
            return """ #  TOPICS           ACTION    PREFIX
 0  info,warning     memory    sys
 1  firewall         disk      fw"""
        return ""

    async def close(self):
        self.calls.append(("close", None))


class _FakeDeviceService:
    def __init__(self, client: _FakeRestClient) -> None:
        self.client = client
        self.ssh_client = _FakeSSHClient()
        self.rest_fails = False

    async def get_device(self, device_id: str):
        return {"id": device_id}

    async def get_rest_client(self, device_id: str):
        if self.rest_fails:
            raise RouterOSTimeoutError("Simulated REST timeout")
        return self.client

    async def get_ssh_client(self, device_id: str):
        return self.ssh_client


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
async def test_get_recent_logs_message_filter(fake_env):
    client, _ = fake_env
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())

    logs, total = await service.get_recent_logs("dev-1", limit=10, message="drop")

    assert total == 2  # underlying store size
    assert len(logs) == 1
    assert logs[0]["message"] == "drop"


@pytest.mark.asyncio
async def test_get_logging_config(fake_env):
    client, _ = fake_env
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())

    config = await service.get_logging_config("dev-1")
    assert config[0]["topics"] == ["info", "warning"]
    assert config[1]["action"] == "disk"

    assert ("close", None, None) in client.calls


@pytest.mark.asyncio
async def test_list_filter_rules_via_ssh_fallback(fake_env):
    """Test list_filter_rules via SSH fallback when REST fails."""
    _, device_service = fake_env
    device_service.rest_fails = True
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())

    filter_rules = await service.list_filter_rules("dev-1")
    assert len(filter_rules) == 1
    assert filter_rules[0]["chain"] == "input"
    assert filter_rules[0]["action"] == "accept"
    assert filter_rules[0]["transport"] == "ssh"
    assert filter_rules[0]["fallback_used"] is True


@pytest.mark.asyncio
async def test_list_nat_rules_via_ssh_fallback(fake_env):
    """Test list_nat_rules via SSH fallback when REST fails."""
    _, device_service = fake_env
    device_service.rest_fails = True
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())

    nat_rules = await service.list_nat_rules("dev-1")
    assert len(nat_rules) == 1
    assert nat_rules[0]["chain"] == "dstnat"
    assert nat_rules[0]["action"] == "dst-nat"
    assert nat_rules[0]["transport"] == "ssh"
    assert nat_rules[0]["fallback_used"] is True


@pytest.mark.asyncio
async def test_list_address_lists_via_ssh_fallback(fake_env):
    """Test list_address_lists via SSH fallback when REST fails."""
    _, device_service = fake_env
    device_service.rest_fails = True
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())

    address_lists = await service.list_address_lists("dev-1")
    assert len(address_lists) == 2
    assert address_lists[0]["list"] == "mcp-managed"
    assert address_lists[0]["address"] == "192.0.2.1"
    assert address_lists[0]["transport"] == "ssh"
    assert address_lists[0]["fallback_used"] is True


@pytest.mark.asyncio
async def test_get_recent_logs_via_ssh_fallback(fake_env):
    """Test get_recent_logs via SSH fallback when REST fails."""
    _, device_service = fake_env
    device_service.rest_fails = True
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())

    logs, total = await service.get_recent_logs("dev-1", limit=10)
    assert total == 2
    assert logs[0]["message"] == "started"
    assert logs[0]["transport"] == "ssh"
    assert logs[0]["fallback_used"] is True


@pytest.mark.asyncio
async def test_get_logging_config_via_ssh_fallback(fake_env):
    """Test get_logging_config via SSH fallback when REST fails."""
    _, device_service = fake_env
    device_service.rest_fails = True
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())

    config = await service.get_logging_config("dev-1")
    assert len(config) == 2
    assert config[0]["topics"] == ["info", "warning"]
    assert config[0]["action"] == "memory"
    assert config[0]["transport"] == "ssh"
    assert config[0]["fallback_used"] is True


@pytest.mark.asyncio
async def test_list_address_lists_ssh_fallback_empty(fake_env):
    """Test list_address_lists via SSH when list is empty."""
    client, device_service = fake_env
    
    old_execute = device_service.ssh_client.execute
    
    async def execute_empty(command):
        if command == "/ip/firewall/address-list/print":
            return """ #    LIST         ADDRESS       COMMENT  TIMEOUT"""
        return await old_execute(command)
    
    device_service.ssh_client.execute = execute_empty
    device_service.rest_fails = True
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())
    
    lists = await service.list_address_lists("dev-1")
    assert len(lists) == 0


@pytest.mark.asyncio
async def test_get_recent_logs_with_topic_filter(fake_env):
    """Test get_recent_logs with topic filtering."""
    client, device_service = fake_env
    service = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())
    
    logs, total = await service.get_recent_logs("dev-1", limit=10, topics=["firewall"])
    
    assert isinstance(logs, list)
    assert isinstance(total, int)


def test_parse_firewall_filter_print_output_multiline_with_comments():
    """Ensure multiline CLI output with comments and flags is parsed richly."""
    sample_output = """
Flags: X - disabled, D - dynamic, I - invalid, r - runtime
 0  D ;;; special dummy rule to show fasttrack counters
      chain=forward action=passthrough
 1  D ;;; special dummy rule to show slowpath counters
      chain=forward action=passthrough
 2    chain=input action=accept connection-state=established,related
 3    ;;; fasttrack established/related
      chain=forward action=fasttrack-connection connection-state=established,related
 4    chain=forward action=accept connection-state=established,related
 5    chain=forward action=drop connection-state=invalid
 6    chain=input action=accept protocol=icmp
 7    ;;; input: drop from RFC1918 block
      chain=input action=drop src-address=10.0.0.0/8 in-interface=ether1 comment="[DoS] drop rfc1918"
"""

    parsed = firewall_logs_module.FirewallLogsService._parse_firewall_filter_print_output(
        sample_output
    )

    assert len(parsed) == 8

    # Rule 0: disabled with comment
    r0 = parsed[0]
    assert r0["id"] == "0"
    assert r0["disabled"] is True
    assert r0["chain"] == "forward"
    assert r0["action"] == "passthrough"
    assert "fasttrack counters" in r0["comment"]

    # Rule 6: ICMP accept
    r6 = parsed[6]
    assert r6["chain"] == "input"
    assert r6["action"] == "accept"
    assert r6["protocol"] == "icmp"

    # Rule 7: has src-address, interface, and comment from continuation line
    r7 = parsed[7]
    assert r7["chain"] == "input"
    assert r7["action"] == "drop"
    assert r7["src_address"] == "10.0.0.0/8"
    assert r7["comment"] == "[DoS] drop rfc1918"
    assert r7.get("extras", {}).get("in-interface") == "ether1"


def test_parse_log_print_output_date_time_and_time_only():
    sample = """
2025-12-11 22:52:33 system,info installed system-7.20.6
00:00:01 system,clock,critical,info ntp change time Dec/11/2025 22:53:07 => Dec/11/2025 22:54:02
*l1 00:00:02 info,system started services
"""

    parsed = firewall_logs_module.FirewallLogsService._parse_log_print_output(sample, limit=10)

    # Date + time preserved and used as id/time
    first = parsed[0]
    assert first["time"] == "2025-12-11 22:52:33"
    assert first["topics"] == ["system", "info"]
    assert first["message"] == "installed system-7.20.6"

    # Time-only retains full message (no truncation on spaces)
    second = parsed[1]
    assert second["time"] == "00:00:01"
    assert "ntp change time" in second["message"]
    assert second["topics"] == ["system", "clock", "critical", "info"]

    # Id + time variant keeps message and topics
    third = parsed[2]
    assert third["id"] == "*l1"
    assert third["time"] == "00:00:02"
    assert third["message"] == "started services"
    assert third["topics"] == ["info", "system"]


def test_filter_logs_time_window():
    svc = firewall_logs_module.FirewallLogsService(session=None, settings=Settings())

    entries = [
        {"time": "2025-12-11 22:52:33", "message": "a"},
        {"time": "2025-12-12 00:00:00", "message": "b"},
        {"time": "2025-12-13 00:00:00", "message": "c"},
    ]

    filtered = svc._filter_logs(entries, "2025-12-12 00:00:00", "2025-12-12 23:59:59", None, 10)

    assert len(filtered) == 1
    assert filtered[0]["message"] == "b"
