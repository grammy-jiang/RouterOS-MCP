"""E2E tests for bridge tools."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import bridge as bridge_tools

from .e2e_test_utils import DummyMCP, FakeSessionFactory


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

    def setUp(self):
        """Set up test fixtures."""
        self.mcp = DummyMCP()
        self.session_factory = FakeSessionFactory()
        self.settings = Settings(environment="lab")

    @patch("routeros_mcp.domain.services.device.DeviceService")
    @patch("routeros_mcp.domain.services.bridge.BridgeService")
    @patch("routeros_mcp.infra.db.session.get_session_factory")
    async def test_list_bridges_e2e(self, mock_get_session_factory, mock_bridge_service, mock_device_service):
        """Test end-to-end bridge listing workflow."""
        # Set up mocks
        mock_get_session_factory.return_value = self.session_factory
        mock_device_service.return_value = _FakeDeviceService()
        mock_bridge_service.return_value = _FakeBridgeService()

        # Register tools
        bridge_tools.register_bridge_tools(self.mcp, self.settings)

        # Find the list_bridges tool
        list_bridges_tool = None
        for tool in self.mcp.tools:
            if tool.name == "list_bridges":
                list_bridges_tool = tool
                break

        self.assertIsNotNone(list_bridges_tool, "list_bridges tool should be registered")

        # Execute the tool
        result = await list_bridges_tool.fn(device_id="dev-lab-01")

        # Verify result structure
        self.assertFalse(result["is_error"], "Tool execution should not error")
        self.assertEqual(result["content"], "Found 2 bridge(s) on router-lab-01")

        # Verify metadata
        meta = result["meta"]
        self.assertEqual(meta["device_id"], "dev-lab-01")
        self.assertEqual(meta["total_count"], 2)
        self.assertEqual(len(meta["bridges"]), 2)

        # Verify bridge details
        bridges = meta["bridges"]
        self.assertEqual(bridges[0]["name"], "bridge1")
        self.assertEqual(bridges[0]["protocol_mode"], "rstp")
        self.assertFalse(bridges[0]["vlan_filtering"])
        self.assertEqual(bridges[0]["comment"], "Main LAN bridge")

        self.assertEqual(bridges[1]["name"], "bridge-vlan")
        self.assertTrue(bridges[1]["vlan_filtering"])
        self.assertEqual(bridges[1]["comment"], "VLAN bridge")

    @patch("routeros_mcp.domain.services.device.DeviceService")
    @patch("routeros_mcp.domain.services.bridge.BridgeService")
    @patch("routeros_mcp.infra.db.session.get_session_factory")
    async def test_list_bridge_ports_e2e(
        self, mock_get_session_factory, mock_bridge_service, mock_device_service
    ):
        """Test end-to-end bridge port listing workflow."""
        # Set up mocks
        mock_get_session_factory.return_value = self.session_factory
        mock_device_service.return_value = _FakeDeviceService()
        mock_bridge_service.return_value = _FakeBridgeService()

        # Register tools
        bridge_tools.register_bridge_tools(self.mcp, self.settings)

        # Find the list_bridge_ports tool
        list_ports_tool = None
        for tool in self.mcp.tools:
            if tool.name == "list_bridge_ports":
                list_ports_tool = tool
                break

        self.assertIsNotNone(list_ports_tool, "list_bridge_ports tool should be registered")

        # Execute the tool
        result = await list_ports_tool.fn(device_id="dev-lab-01")

        # Verify result structure
        self.assertFalse(result["is_error"], "Tool execution should not error")
        self.assertEqual(result["content"], "Found 3 bridge port(s) on router-lab-01")

        # Verify metadata
        meta = result["meta"]
        self.assertEqual(meta["device_id"], "dev-lab-01")
        self.assertEqual(meta["total_count"], 3)
        self.assertEqual(len(meta["bridge_ports"]), 3)

        # Verify port details
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

    @patch("routeros_mcp.domain.services.device.DeviceService")
    @patch("routeros_mcp.domain.services.bridge.BridgeService")
    @patch("routeros_mcp.infra.db.session.get_session_factory")
    async def test_bridge_tools_combined_workflow(
        self, mock_get_session_factory, mock_bridge_service, mock_device_service
    ):
        """Test combined workflow: list bridges then list ports."""
        # Set up mocks
        mock_get_session_factory.return_value = self.session_factory
        mock_device_service.return_value = _FakeDeviceService()
        mock_bridge_service.return_value = _FakeBridgeService()

        # Register tools
        bridge_tools.register_bridge_tools(self.mcp, self.settings)

        # Find tools
        list_bridges_tool = None
        list_ports_tool = None
        for tool in self.mcp.tools:
            if tool.name == "list_bridges":
                list_bridges_tool = tool
            elif tool.name == "list_bridge_ports":
                list_ports_tool = tool

        self.assertIsNotNone(list_bridges_tool)
        self.assertIsNotNone(list_ports_tool)

        # First, list bridges
        bridges_result = await list_bridges_tool.fn(device_id="dev-lab-01")
        self.assertFalse(bridges_result["is_error"])
        bridges = bridges_result["meta"]["bridges"]

        # Then, list ports
        ports_result = await list_ports_tool.fn(device_id="dev-lab-01")
        self.assertFalse(ports_result["is_error"])
        ports = ports_result["meta"]["bridge_ports"]

        # Verify we can correlate bridges and ports
        bridge_names = {b["name"] for b in bridges}
        self.assertEqual(bridge_names, {"bridge1", "bridge-vlan"})

        # All ports should belong to one of the bridges
        for port in ports:
            self.assertIn(port["bridge"], bridge_names)

        # Verify port distribution
        bridge1_ports = [p for p in ports if p["bridge"] == "bridge1"]
        bridge_vlan_ports = [p for p in ports if p["bridge"] == "bridge-vlan"]

        self.assertEqual(len(bridge1_ports), 2)
        self.assertEqual(len(bridge_vlan_ports), 1)


if __name__ == "__main__":
    unittest.main()
