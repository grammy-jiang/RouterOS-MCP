from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import dns_ntp as dns_ntp_tools
from routeros_mcp.mcp_tools import firewall_logs as firewall_logs_tools
from routeros_mcp.mcp_tools import firewall_write as firewall_write_tools
from routeros_mcp.mcp_tools import interface as interface_tools
from routeros_mcp.mcp_tools import routing as routing_tools
from routeros_mcp.mcp_tools import system as system_tools
from unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


class _FakeDeviceService:
    def __init__(self) -> None:
        self.device = SimpleNamespace(
            id="dev-1",
            name="router-1",
            environment="lab",
            allow_advanced_writes=True,
            allow_professional_workflows=True,
        )

    async def get_device(self, device_id: str):
        return self.device

    async def get_rest_client(self, _device_id: str):
        return _FakeRestClient()


class _FakeRestClient:
    def __init__(self) -> None:
        self.closed = False

    async def get(self, _path: str):
        return {"time": "12:00:00", "date": "2025-12-13", "time-zone-name": "UTC", "time-zone-autodetect": True, "gmt-offset": "+00:00", "dst-active": False}

    async def close(self):
        self.closed = True


class _FakeInterfaceService:
    def __init__(self) -> None:
        self.raise_in: str | None = None

    async def list_interfaces(self, device_id: str):
        if self.raise_in == "list":
            raise ValueError("failed list")
        return [
            {"id": "*1", "name": "ether1", "type": "ether", "running": True, "disabled": False},
            {"id": "*2", "name": "bridge1", "type": "bridge", "running": True, "disabled": False},
        ]

    async def get_interface(self, device_id: str, interface_id: str):
        return {"id": interface_id, "name": "ether1", "type": "ether", "running": True}

    async def get_interface_stats(self, device_id: str, interface_names: list[str] | None = None):
        stats = [
            {"name": "ether1", "rx_bps": 1000, "tx_bps": 2000},
            {"name": "bridge1", "rx_bps": 500, "tx_bps": 750},
        ]
        if interface_names:
            return [s for s in stats if s["name"] in interface_names]
        return stats


class _FakeRoutingService:
    def __init__(self) -> None:
        self.raise_in: str | None = None

    async def get_routing_summary(self, device_id: str):
        if self.raise_in == "summary":
            raise ValueError("boom")
        return {
            "total_routes": 3,
            "static_routes": 1,
            "connected_routes": 1,
            "dynamic_routes": 1,
            "routes": [
                {"id": "*1", "dst_address": "0.0.0.0/0", "gateway": "10.0.0.1"},
                {"id": "*2", "dst_address": "10.0.0.0/24", "gateway": "bridge"},
                {"id": "*3", "dst_address": "10.0.1.0/24", "gateway": "ether1"},
            ],
        }

    async def get_route(self, device_id: str, route_id: str):
        if self.raise_in == "route":
            raise ValueError("not found")
        return {"id": route_id, "dst_address": "0.0.0.0/0", "gateway": "10.0.0.1"}


class _FakeSystemService:
    def __init__(self) -> None:
        self.identity = "old-id"

    async def get_system_overview(self, device_id: str):
        return {
            "device_name": "router-1",
            "system_identity": self.identity,
            "routeros_version": "7.10",
            "hardware_model": "CCR",
            "cpu_usage_percent": 12.5,
            "cpu_count": 4,
            "memory_usage_percent": 45.5,
            "memory_used_bytes": 512 * 1024 * 1024,
            "memory_total_bytes": 1024 * 1024 * 1024,
            "uptime_formatted": "1d1h",
        }

    async def get_system_packages(self, device_id: str):
        return [{"name": "routeros", "version": "7.10"}]

    async def get_system_clock(self, device_id: str):
        return {
            "time": "12:00:00",
            "date": "2025-12-13",
            "time-zone-name": "UTC",
            "time_zone_name": "UTC",
            "time-zone-autodetect": True,
            "gmt-offset": "+00:00",
            "dst-active": False,
            "transport": "rest",
            "fallback_used": False,
            "rest_error": None,
        }

    async def update_system_identity(self, device_id: str, identity: str, dry_run: bool):
        if dry_run:
            return {
                "changed": False,
                "dry_run": True,
                "planned_changes": {"old_identity": self.identity, "new_identity": identity},
            }
        changed = identity != self.identity
        old = self.identity
        self.identity = identity
        return {"changed": changed, "old_identity": old, "new_identity": self.identity}


class _FakeFirewallLogsService:
    async def list_filter_rules(self, device_id: str):
        return [{"id": "*1", "chain": "input", "action": "accept"}]

    async def list_nat_rules(self, device_id: str):
        return [{"id": "*2", "chain": "srcnat", "action": "masquerade"}]

    async def list_address_lists(self, device_id: str, list_name: str | None):
        entries = [{"id": "*3", "list": "mcp-managed", "address": "10.0.0.1", "comment": "test"}]
        if list_name:
            return [e for e in entries if e["list"] == list_name]
        return entries

    async def get_recent_logs(
        self,
        device_id: str,
        limit: int,
        topics: list[str] | None,
        start_time: str | None = None,
        end_time: str | None = None,
        message: str | None = None,
    ):
        entries = [
            {"id": "1", "time": "jan/01", "topics": ["system"], "message": "started"},
            {"id": "2", "time": "jan/01", "topics": ["firewall"], "message": "allow"},
        ]
        return entries[:limit], len(entries)

    async def get_logging_config(self, device_id: str):
        return [{"id": "*1", "topics": ["system"], "action": "memory"}]


class _FakeFirewallService:
    async def update_address_list_entry(
        self,
        device_id: str,
        list_name: str,
        address: str,
        action: str,
        comment: str,
        timeout: str,
        dry_run: bool,
    ):
        if dry_run:
            return {
                "changed": False,
                "dry_run": True,
                "planned_changes": {"action": action, "address": address, "list_name": list_name},
            }
        return {"changed": True, "action": action, "address": address, "list_name": list_name}


class _FakeDNSNTPService:
    async def get_dns_status(self, device_id: str):
        return {
            "dns_servers": ["1.1.1.1", "8.8.8.8"],
            "allow_remote_requests": True,
            "cache_size": 2048,
            "cache_used": 512,
        }

    async def get_dns_cache(self, device_id: str, limit: int):
        entries = [
            {"name": "example.com", "type": "A", "data": "1.1.1.1", "ttl": 100},
            {"name": "ipv6.test", "type": "AAAA", "data": "2001::1", "ttl": 200},
        ]
        return entries[:limit], len(entries)

    async def get_ntp_status(self, device_id: str):
        return {
            "status": "synchronized",
            "ntp_servers": ["time.nist.gov"],
            "stratum": 2,
            "offset_ms": 0.123,
        }

    async def update_dns_servers(self, device_id: str, dns_servers: list[str], dry_run: bool):
        if dry_run:
            return {
                "changed": False,
                "dry_run": True,
                "planned_changes": {"old_servers": ["1.1.1.1"], "new_servers": dns_servers},
            }
        return {"changed": True, "new_servers": dns_servers}

    async def flush_dns_cache(self, device_id: str):
        return {"entries_flushed": 2}

    async def update_ntp_servers(
        self, device_id: str, ntp_servers: list[str], enabled: bool, dry_run: bool
    ):
        if dry_run:
            return {
                "changed": False,
                "dry_run": True,
                "planned_changes": {"old_servers": ["time.old"], "new_servers": ntp_servers},
            }
        return {"changed": True, "new_servers": ntp_servers}


class TestMCPToolsNetworking(unittest.TestCase):
    def _interface_patches(
        self, device_service: _FakeDeviceService, interface_service: _FakeInterfaceService
    ):
        return (
            patch.object(interface_tools, "get_session_factory", return_value=FakeSessionFactory()),
            patch.object(interface_tools, "DeviceService", lambda *_a, **_k: device_service),
            patch.object(interface_tools, "InterfaceService", lambda *_a, **_k: interface_service),
            patch.object(interface_tools, "check_tool_authorization", lambda **_k: None),
        )

    def _routing_patches(
        self, device_service: _FakeDeviceService, routing_service: _FakeRoutingService
    ):
        return (
            patch.object(routing_tools, "get_session_factory", return_value=FakeSessionFactory()),
            patch.object(routing_tools, "DeviceService", lambda *_a, **_k: device_service),
            patch.object(routing_tools, "RoutingService", lambda *_a, **_k: routing_service),
            patch.object(routing_tools, "check_tool_authorization", lambda **_k: None),
        )

    def _system_patches(
        self,
        device_service: _FakeDeviceService,
        system_service: _FakeSystemService,
    ):
        return (
            patch.object(system_tools, "get_session_factory", return_value=FakeSessionFactory()),
            patch.object(system_tools, "DeviceService", lambda *_a, **_k: device_service),
            patch.object(system_tools, "SystemService", lambda *_a, **_k: system_service),
            patch.object(system_tools, "check_tool_authorization", lambda **_k: None),
        )

    def _firewall_logs_patches(
        self,
        device_service: _FakeDeviceService,
        logs_service: _FakeFirewallLogsService,
    ):
        return (
            patch.object(
                firewall_logs_tools, "get_session_factory", return_value=FakeSessionFactory()
            ),
            patch.object(firewall_logs_tools, "DeviceService", lambda *_a, **_k: device_service),
            patch.object(
                firewall_logs_tools, "FirewallLogsService", lambda *_a, **_k: logs_service
            ),
            patch.object(firewall_logs_tools, "check_tool_authorization", lambda **_k: None),
        )

    def _firewall_write_patches(
        self,
        device_service: _FakeDeviceService,
        fw_service: _FakeFirewallService,
    ):
        return (
            patch.object(
                firewall_write_tools, "get_session_factory", return_value=FakeSessionFactory()
            ),
            patch.object(firewall_write_tools, "DeviceService", lambda *_a, **_k: device_service),
            patch.object(firewall_write_tools, "FirewallService", lambda *_a, **_k: fw_service),
            patch.object(firewall_write_tools, "check_tool_authorization", lambda **_k: None),
        )

    def _dns_ntp_patches(
        self,
        device_service: _FakeDeviceService,
        dns_service: _FakeDNSNTPService,
    ):
        return (
            patch.object(dns_ntp_tools, "get_session_factory", return_value=FakeSessionFactory()),
            patch.object(dns_ntp_tools, "DeviceService", lambda *_a, **_k: device_service),
            patch.object(dns_ntp_tools, "DNSNTPService", lambda *_a, **_k: dns_service),
            patch.object(dns_ntp_tools, "check_tool_authorization", lambda **_k: None),
        )

    def test_interface_tools_success(self) -> None:
        async def _run() -> None:
            device_service = _FakeDeviceService()
            interface_service = _FakeInterfaceService()
            patches = self._interface_patches(device_service, interface_service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp = DummyMCP()
                interface_tools.register_interface_tools(mcp, Settings())
                result = await mcp.tools["list_interfaces"]("dev-1")
                self.assertTrue(result["content"][0]["text"].startswith("Found 2 interface"))
                self.assertEqual(2, result["_meta"]["total_count"])

                detail = await mcp.tools["get_interface"]("dev-1", "*1")
                self.assertEqual("ether1", detail["_meta"]["interface"]["name"])

                stats_all = await mcp.tools["get_interface_stats"]("dev-1")
                self.assertEqual(2, len(stats_all["_meta"]["stats"]))
                self.assertIn("all interfaces", stats_all["content"][0]["text"])

                stats_filtered = await mcp.tools["get_interface_stats"]("dev-1", ["ether1"])
                self.assertEqual("ether1", stats_filtered["_meta"]["stats"][0]["name"])

        asyncio.run(_run())

    def test_interface_tools_error_path(self) -> None:
        async def _run() -> None:
            device_service = _FakeDeviceService()
            interface_service = _FakeInterfaceService()
            patches = self._interface_patches(device_service, interface_service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp = DummyMCP()
                interface_tools.register_interface_tools(mcp, Settings())
                interface_service.raise_in = "list"
                result = await mcp.tools["list_interfaces"]("dev-1")
                self.assertTrue(result["isError"])

        asyncio.run(_run())

    def test_interface_stats_error_path(self) -> None:
        async def _run() -> None:
            device_service = _FakeDeviceService()
            interface_service = _FakeInterfaceService()
            patches = self._interface_patches(device_service, interface_service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp = DummyMCP()
                interface_tools.register_interface_tools(mcp, Settings())

                async def boom(*_args, **_kwargs):
                    raise ValueError("stats fail")

                interface_service.get_interface_stats = boom  # type: ignore[assignment]
                result = await mcp.tools["get_interface_stats"]("dev-1", ["ether1"])
                self.assertTrue(result["isError"])

        asyncio.run(_run())

    def test_routing_tools_success(self) -> None:
        async def _run() -> None:
            device_service = _FakeDeviceService()
            routing_service = _FakeRoutingService()
            patches = self._routing_patches(device_service, routing_service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp = DummyMCP()
                routing_tools.register_routing_tools(mcp, Settings())
                summary = await mcp.tools["get_routing_summary"]("dev-1")
                self.assertEqual(3, summary["_meta"]["total_routes"])
                self.assertIn("Routing table", summary["content"][0]["text"])

                route = await mcp.tools["get_route"]("dev-1", "*1")
                self.assertEqual("10.0.0.1", route["_meta"]["route"]["gateway"])

        asyncio.run(_run())

    def test_routing_tools_error_path(self) -> None:
        async def _run() -> None:
            device_service = _FakeDeviceService()
            routing_service = _FakeRoutingService()
            patches = self._routing_patches(device_service, routing_service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp = DummyMCP()
                routing_tools.register_routing_tools(mcp, Settings())
                routing_service.raise_in = "route"
                result = await mcp.tools["get_route"]("dev-1", "*missing")
                self.assertTrue(result["isError"])

        asyncio.run(_run())

    def test_system_tools_overview_packages_clock_identity(self) -> None:
        async def _run() -> None:
            device_service = _FakeDeviceService()
            system_service = _FakeSystemService()
            patches = self._system_patches(device_service, system_service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp = DummyMCP()
                system_tools.register_system_tools(mcp, Settings())

                overview = await mcp.tools["get_system_overview"]("dev-1")
                self.assertIn("Device: router-1", overview["content"][0]["text"])
                self.assertEqual("7.10", overview["_meta"]["routeros_version"])

                packages = await mcp.tools["get_system_packages"]("dev-1")
                self.assertEqual(1, packages["_meta"]["total_count"])

                clock = await mcp.tools["get_system_clock"]("dev-1")
                self.assertEqual("UTC", clock["_meta"]["time_zone_name"])

                rest_client = await device_service.get_rest_client("dev-1")
                await rest_client.close()
                self.assertTrue(rest_client.closed)

                dry_run = await mcp.tools["set_system_identity"]("dev-1", "new-id", dry_run=True)
                self.assertTrue(dry_run["_meta"]["dry_run"])
                self.assertEqual("new-id", dry_run["_meta"]["planned_changes"]["new_identity"])

                applied = await mcp.tools["set_system_identity"]("dev-1", "new-id", dry_run=False)
                self.assertTrue(applied["_meta"]["changed"])
                self.assertEqual("new-id", applied["_meta"]["new_identity"])

        asyncio.run(_run())

    def test_firewall_logs_tools(self) -> None:
        async def _run() -> None:
            device_service = _FakeDeviceService()
            logs_service = _FakeFirewallLogsService()
            patches = self._firewall_logs_patches(device_service, logs_service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp = DummyMCP()
                firewall_logs_tools.register_firewall_logs_tools(mcp, Settings())

                filt = await mcp.tools["list_firewall_filter_rules"]("dev-1")
                self.assertEqual(1, filt["_meta"]["total_count"])

                nat = await mcp.tools["list_firewall_nat_rules"]("dev-1")
                self.assertEqual("srcnat", nat["_meta"]["nat_rules"][0]["chain"])

                addr = await mcp.tools["list_firewall_address_lists"](
                    "dev-1", list_name="mcp-managed"
                )
                self.assertEqual(1, addr["_meta"]["total_count"])

                logs = await mcp.tools["get_recent_logs"]("dev-1", limit=1, topics=["system"])
                self.assertEqual(2, logs["_meta"]["total_count"])
                self.assertIn("topics", logs["_meta"]["log_entries"][0])

                config = await mcp.tools["get_logging_config"]("dev-1")
                self.assertEqual(1, config["_meta"]["total_count"])

        asyncio.run(_run())

    def test_firewall_write_tools(self) -> None:
        async def _run() -> None:
            device_service = _FakeDeviceService()
            fw_service = _FakeFirewallService()
            patches = self._firewall_write_patches(device_service, fw_service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp = DummyMCP()
                firewall_write_tools.register_firewall_write_tools(mcp, Settings())

                dry = await mcp.tools["update_firewall_address_list"](
                    "dev-1", "mcp-list", "10.0.0.1", action="add", dry_run=True
                )
                self.assertTrue(dry["_meta"]["dry_run"])
                self.assertEqual("add", dry["_meta"]["planned_changes"]["action"])

                applied = await mcp.tools["update_firewall_address_list"](
                    "dev-1", "mcp-list", "10.0.0.1", action="remove", dry_run=False
                )
                self.assertTrue(applied["_meta"]["changed"])
                text = applied["content"][0]["text"]
                self.assertTrue(text.startswith("Removed") or text.startswith("Added"))

        asyncio.run(_run())

    def test_firewall_write_tools_error(self) -> None:
        async def _run() -> None:
            device_service = _FakeDeviceService()
            fw_service = _FakeFirewallService()
            patches = self._firewall_write_patches(device_service, fw_service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp = DummyMCP()
                firewall_write_tools.register_firewall_write_tools(mcp, Settings())

                async def boom(*_args, **_kwargs):
                    from routeros_mcp.mcp.errors import MCPError

                    raise MCPError("fail", data={"detail": "nope"})

                fw_service.update_address_list_entry = boom  # type: ignore[assignment]
                result = await mcp.tools["update_firewall_address_list"](
                    "dev-1", "mcp", "1.1.1.1", action="add"
                )
                self.assertTrue(result["isError"])
                self.assertEqual("nope", result["_meta"]["detail"])

        asyncio.run(_run())

    def test_dns_ntp_tools_read_and_write(self) -> None:
        async def _run() -> None:
            device_service = _FakeDeviceService()
            dns_service = _FakeDNSNTPService()
            patches = self._dns_ntp_patches(device_service, dns_service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp = DummyMCP()
                dns_ntp_tools.register_dns_ntp_tools(mcp, Settings())

                dns_status = await mcp.tools["get_dns_status"]("dev-1")
                self.assertIn("1.1.1.1", dns_status["content"][0]["text"])

                cache = await mcp.tools["get_dns_cache"]("dev-1", limit=1)
                self.assertEqual(1, cache["_meta"]["returned_count"])

                ntp_status = await mcp.tools["get_ntp_status"]("dev-1")
                self.assertEqual("synchronized", ntp_status["_meta"]["status"])

                dns_dry = await mcp.tools["update_dns_servers"]("dev-1", ["9.9.9.9"], dry_run=True)
                self.assertEqual(["9.9.9.9"], dns_dry["_meta"]["planned_changes"]["new_servers"])

                ntp_dry = await mcp.tools["update_ntp_servers"](
                    "dev-1", ["pool.ntp.org"], enabled=True, dry_run=True
                )
                self.assertEqual(
                    ["pool.ntp.org"], ntp_dry["_meta"]["planned_changes"]["new_servers"]
                )

                flush = await mcp.tools["flush_dns_cache"]("dev-1")
                self.assertEqual(2, flush["_meta"]["entries_flushed"])

        asyncio.run(_run())
