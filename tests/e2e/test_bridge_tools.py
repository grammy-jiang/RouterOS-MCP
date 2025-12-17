"""E2E tests for bridge tools."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.mcp_tools import bridge as bridge_tools

from .e2e_test_utils import DummyMCP, FakeSessionFactory, make_test_settings


class _FakeDeviceService:
    """Fake device service for E2E testing."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.id = "dev-lab-01"
        self.name = "router-lab-01"
        self.environment = "lab"
        self.allow_advanced_writes = True
        self.allow_professional_workflows = False

    async def get_device(self, device_id: str):
        return self


class _FakeBridgeService:
    """Fake bridge service for E2E testing."""

    async def list_bridges(self, device_id: str):
        """Return sample bridge data."""
        return [
            {
                "id": "*1",
                "name": "bridge1",
                "mtu": 1500,
                "actual_mtu": 1500,
                "l2mtu": 1514,
                "mac_address": "78:9A:18:A2:F3:D4",
                "arp": "enabled",
                "arp_timeout": "auto",
                "disabled": False,
                "running": True,
                "auto_mac": True,
                "ageing_time": "5m",
                "priority": "0x8000",
                "protocol_mode": "rstp",
                "fast_forward": True,
                "vlan_filtering": False,
                "comment": "Main LAN bridge",
                "transport": "rest",
                "fallback_used": False,
                "rest_error": None,
            },
            {
                "id": "*2",
                "name": "bridge-vlan",
                "mtu": 1500,
                "actual_mtu": 1500,
                "l2mtu": 1514,
                "mac_address": "78:9A:18:A2:F3:D5",
                "disabled": False,
                "running": True,
                "protocol_mode": "rstp",
                "vlan_filtering": True,
                "comment": "VLAN bridge",
                "transport": "rest",
                "fallback_used": False,
                "rest_error": None,
            },
        ]

    async def list_bridge_ports(self, device_id: str):
        """Return sample bridge port data."""
        return [
            {
                "id": "*1",
                "interface": "ether2",
                "bridge": "bridge1",
                "disabled": False,
                "hw": True,
                "pvid": 1,
                "priority": "0x80",
                "path_cost": 10,
                "horizon": "none",
                "edge": "auto",
                "point_to_point": "auto",
                "learn": "auto",
                "trusted": False,
                "frame_types": "admit-all",
                "ingress_filtering": False,
                "tag_stacking": False,
                "comment": "LAN port 1",
                "transport": "rest",
                "fallback_used": False,
                "rest_error": None,
            },
            {
                "id": "*2",
                "interface": "ether3",
                "bridge": "bridge1",
                "disabled": False,
                "hw": True,
                "pvid": 1,
                "priority": "0x80",
                "path_cost": 10,
                "comment": "LAN port 2",
                "transport": "rest",
                "fallback_used": False,
                "rest_error": None,
            },
            {
                "id": "*3",
                "interface": "ether4",
                "bridge": "bridge-vlan",
                "disabled": False,
                "hw": True,
                "pvid": 10,
                "priority": "0x80",
                "path_cost": 10,
                "frame_types": "admit-only-vlan-tagged",
                "ingress_filtering": True,
                "comment": "VLAN trunk",
                "transport": "rest",
                "fallback_used": False,
                "rest_error": None,
            },
        ]


class TestBridgeToolsE2E(unittest.TestCase):
    """E2E tests for bridge tools."""

    def _register_bridge_tools(self) -> DummyMCP:
        """Register bridge tools with mocked dependencies."""
        mcp = DummyMCP()
        settings = make_test_settings()
        bridge_tools.register_bridge_tools(mcp, settings)
        return mcp

    def test_list_bridges_e2e(self) -> None:
        """Test end-to-end bridge listing workflow (MCP tool contract)."""

        async def _run() -> None:
            with (
                patch.object(
                    bridge_tools, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(bridge_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    bridge_tools,
                    "BridgeService",
                    lambda *args, **kwargs: _FakeBridgeService(),
                ),
                patch.object(bridge_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_bridge_tools()

                tool = mcp.tools["list_bridges"]
                result = await tool(device_id="dev-lab-01")

                self.assertFalse(result["isError"], "Tool execution should not error")
                self.assertEqual(result["content"][0]["text"], "Found 2 bridge(s) on router-lab-01")

                meta = result["_meta"]
                self.assertEqual(meta["device_id"], "dev-lab-01")
                self.assertEqual(meta["total_count"], 2)
                self.assertEqual(len(meta["bridges"]), 2)

                bridges = meta["bridges"]
                self.assertEqual(bridges[0]["name"], "bridge1")
                self.assertEqual(bridges[0]["protocol_mode"], "rstp")
                self.assertFalse(bridges[0]["vlan_filtering"])
                self.assertEqual(bridges[0]["comment"], "Main LAN bridge")

                self.assertEqual(bridges[1]["name"], "bridge-vlan")
                self.assertTrue(bridges[1]["vlan_filtering"])
                self.assertEqual(bridges[1]["comment"], "VLAN bridge")

        asyncio.run(_run())

    def test_list_bridge_ports_e2e(self) -> None:
        """Test end-to-end bridge port listing workflow (MCP tool contract)."""

        async def _run() -> None:
            with (
                patch.object(
                    bridge_tools, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(bridge_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    bridge_tools,
                    "BridgeService",
                    lambda *args, **kwargs: _FakeBridgeService(),
                ),
                patch.object(bridge_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_bridge_tools()

                tool = mcp.tools["list_bridge_ports"]
                result = await tool(device_id="dev-lab-01")

                self.assertFalse(result["isError"], "Tool execution should not error")
                self.assertEqual(
                    result["content"][0]["text"], "Found 3 bridge port(s) on router-lab-01"
                )

                meta = result["_meta"]
                self.assertEqual(meta["device_id"], "dev-lab-01")
                self.assertEqual(meta["total_count"], 3)
                self.assertEqual(len(meta["bridge_ports"]), 3)

                ports = meta["bridge_ports"]
                self.assertEqual(ports[0]["interface"], "ether2")
                self.assertEqual(ports[0]["bridge"], "bridge1")
                self.assertEqual(ports[0]["pvid"], 1)
                self.assertTrue(ports[0]["hw"])
                self.assertEqual(ports[0]["comment"], "LAN port 1")

                self.assertEqual(ports[1]["interface"], "ether3")
                self.assertEqual(ports[1]["bridge"], "bridge1")
                self.assertEqual(ports[1]["pvid"], 1)

                # VLAN trunk port
                self.assertEqual(ports[2]["interface"], "ether4")
                self.assertEqual(ports[2]["bridge"], "bridge-vlan")
                self.assertEqual(ports[2]["pvid"], 10)
                self.assertEqual(ports[2]["frame_types"], "admit-only-vlan-tagged")
                self.assertTrue(ports[2]["ingress_filtering"])

        asyncio.run(_run())

    def test_bridge_tools_combined_workflow(self) -> None:
        """Test combined workflow: list bridges then list ports."""

        async def _run() -> None:
            with (
                patch.object(
                    bridge_tools, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(bridge_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    bridge_tools,
                    "BridgeService",
                    lambda *args, **kwargs: _FakeBridgeService(),
                ),
                patch.object(bridge_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_bridge_tools()

                list_bridges_tool = mcp.tools["list_bridges"]
                list_ports_tool = mcp.tools["list_bridge_ports"]

                bridges_result = await list_bridges_tool(device_id="dev-lab-01")
                self.assertFalse(bridges_result["isError"])
                bridges = bridges_result["_meta"]["bridges"]

                ports_result = await list_ports_tool(device_id="dev-lab-01")
                self.assertFalse(ports_result["isError"])
                ports = ports_result["_meta"]["bridge_ports"]

                bridge_names = {b["name"] for b in bridges}
                self.assertEqual(bridge_names, {"bridge1", "bridge-vlan"})

                for port in ports:
                    self.assertIn(port["bridge"], bridge_names)

                bridge1_ports = [p for p in ports if p["bridge"] == "bridge1"]
                bridge_vlan_ports = [p for p in ports if p["bridge"] == "bridge-vlan"]

                self.assertEqual(len(bridge1_ports), 2)
                self.assertEqual(len(bridge_vlan_ports), 1)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
