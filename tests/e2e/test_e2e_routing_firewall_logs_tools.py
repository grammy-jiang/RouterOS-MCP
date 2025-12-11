from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import firewall_logs as firewall_logs_tools
from routeros_mcp.mcp_tools import routing as routing_tools

from .e2e_test_utils import DummyMCP, FakeSessionFactory


class _FakeDeviceService:
    def __init__(self, *_args, **_kwargs) -> None:
        self.id = "dev-lab-01"
        self.name = "router-lab-01"
        self.environment = "lab"
        self.allow_advanced_writes = True
        self.allow_professional_workflows = False

    async def get_device(self, device_id: str):
        return self


class _FakeRoutingService:
    async def get_routing_summary(self, device_id: str):
        return {
            "total_routes": 3,
            "static_routes": 1,
            "connected_routes": 1,
            "dynamic_routes": 1,
            "routes": [
                {
                    "id": "*1",
                    "dst_address": "0.0.0.0/0",
                    "gateway": "192.0.2.254",
                    "distance": 1,
                    "comment": "default",
                }
            ],
        }

    async def get_route(self, device_id: str, route_id: str):
        return {
            "id": route_id,
            "dst_address": "0.0.0.0/0",
            "gateway": "192.0.2.254",
            "distance": 1,
            "scope": 30,
            "target_scope": 10,
            "comment": "default",
            "active": True,
            "dynamic": False,
        }


class _FakeFirewallLogsService:
    async def list_filter_rules(self, device_id: str):
        return [
            {
                "id": "*1",
                "chain": "input",
                "action": "accept",
                "protocol": "tcp",
                "dst_port": "22",
                "src_address": "",
                "dst_address": "",
                "comment": "allow ssh",
                "disabled": False,
            }
        ]

    async def list_nat_rules(self, device_id: str):
        return [
            {
                "id": "*2",
                "chain": "srcnat",
                "action": "masquerade",
                "out_interface": "ether1",
                "in_interface": "",
                "to_addresses": "",
                "to_ports": "",
                "comment": "masquerade",
                "disabled": False,
            }
        ]

    async def list_address_lists(self, device_id: str, list_name: str | None):
        entries = [
            {
                "id": "*3",
                "list_name": "mcp-managed",
                "address": "192.0.2.10",
                "comment": "host",
                "timeout": "1d",
            }
        ]
        if list_name:
            return [e for e in entries if e["list_name"] == list_name]
        return entries

    async def get_recent_logs(self, device_id: str, limit: int, topics: list[str] | None):
        entries = [
            {
                "id": "1",
                "time": "jan/01 00:00:00",
                "topics": ["system"],
                "message": "system started",
            },
            {
                "id": "2",
                "time": "jan/01 00:00:01",
                "topics": ["firewall"],
                "message": "accept",
            },
        ]
        return entries[:limit], len(entries)

    async def get_logging_config(self, device_id: str):
        return [
            {
                "topics": ["system"],
                "action": "memory",
                "prefix": "",
            }
        ]


class TestE2ERoutingFirewallLogsTools(unittest.TestCase):
    def _register_routing_tools(self) -> DummyMCP:
        mcp = DummyMCP()
        settings = Settings()
        routing_tools.register_routing_tools(mcp, settings)
        return mcp

    def _register_firewall_logs_tools(self) -> DummyMCP:
        mcp = DummyMCP()
        settings = Settings()
        firewall_logs_tools.register_firewall_logs_tools(mcp, settings)
        return mcp

    def test_routing_tools_end_to_end(self) -> None:
        async def _run() -> None:
            with (
                patch.object(
                    routing_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(routing_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    routing_tools,
                    "RoutingService",
                    lambda *args, **kwargs: _FakeRoutingService(),
                ),
                patch.object(routing_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_routing_tools()

                summary = await mcp.tools["get_routing_summary"]("dev-lab-01")
                self.assertFalse(summary["isError"])
                self.assertEqual(3, summary["_meta"]["total_routes"])
                self.assertEqual(
                    "0.0.0.0/0",
                    summary["_meta"]["routes"][0]["dst_address"],
                )

                route = await mcp.tools["get_route"]("dev-lab-01", "*1")
                self.assertEqual(
                    "192.0.2.254",
                    route["_meta"]["route"]["gateway"],
                )

        asyncio.run(_run())

    def test_firewall_logs_tools_end_to_end(self) -> None:
        async def _run() -> None:
            with (
                patch.object(
                    firewall_logs_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(firewall_logs_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    firewall_logs_tools,
                    "FirewallLogsService",
                    lambda *args, **kwargs: _FakeFirewallLogsService(),
                ),
                patch.object(
                    firewall_logs_tools,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_firewall_logs_tools()

                filt = await mcp.tools["list_firewall_filter_rules"]("dev-lab-01")
                self.assertEqual(1, filt["_meta"]["total_count"])

                nat = await mcp.tools["list_firewall_nat_rules"]("dev-lab-01")
                self.assertEqual(
                    "srcnat",
                    nat["_meta"]["nat_rules"][0]["chain"],
                )

                addr = await mcp.tools["list_firewall_address_lists"](
                    "dev-lab-01",
                    list_name="mcp-managed",
                )
                self.assertEqual(1, addr["_meta"]["total_count"])

                logs = await mcp.tools["get_recent_logs"](
                    "dev-lab-01",
                    limit=1,
                    topics=["system"],
                )
                self.assertEqual(2, logs["_meta"]["total_count"])
                self.assertIn("system", logs["_meta"]["log_entries"][0]["topics"])

                config = await mcp.tools["get_logging_config"]("dev-lab-01")
                self.assertEqual(1, config["_meta"]["total_count"])
                self.assertEqual(
                    ["system"],
                    config["_meta"]["logging_actions"][0]["topics"],
                )

        asyncio.run(_run())

    def test_routing_tools_route_not_found(self) -> None:
        async def _run() -> None:
            from routeros_mcp.infra.routeros.exceptions import RouterOSNotFoundError

            class _ErrorRoutingService:
                async def get_route(self, device_id: str, route_id: str):
                    raise RouterOSNotFoundError("route missing in e2e")

            with (
                patch.object(
                    routing_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(routing_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    routing_tools,
                    "RoutingService",
                    lambda *args, **kwargs: _ErrorRoutingService(),
                ),
                patch.object(routing_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_routing_tools()
                route_fn = mcp.tools["get_route"]

                result = await route_fn("dev-lab-01", "*missing")
                self.assertTrue(result["isError"])
                self.assertEqual("route missing in e2e", result["content"][0]["text"])
                self.assertEqual("RouterOSNotFoundError", result["_meta"]["original_error"])

        asyncio.run(_run())

    def test_firewall_logs_tools_recent_logs_error(self) -> None:
        async def _run() -> None:
            class _ErrorFirewallLogsService:
                async def get_recent_logs(
                    self,
                    device_id: str,
                    limit: int,
                    topics: list[str] | None,
                ):
                    raise ValueError("recent-logs failed in e2e")

            with (
                patch.object(
                    firewall_logs_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(firewall_logs_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    firewall_logs_tools,
                    "FirewallLogsService",
                    lambda *args, **kwargs: _ErrorFirewallLogsService(),
                ),
                patch.object(
                    firewall_logs_tools,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_firewall_logs_tools()
                logs_fn = mcp.tools["get_recent_logs"]

                result = await logs_fn("dev-lab-01", limit=10, topics=None)
                self.assertTrue(result["isError"])
                self.assertIn("recent-logs failed in e2e", result["content"][0]["text"])

        asyncio.run(_run())
