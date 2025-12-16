"""Unit tests for bridge MCP tools."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import bridge as bridge_tools

from .mcp_tools_test_utils import DummyMCP, FakeSessionFactory


class _FakeDeviceService:
    """Fake device service for testing."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.id = "dev-lab-01"
        self.name = "router-lab-01"
        self.environment = "lab"
        self.allow_advanced_writes = True
        self.allow_professional_workflows = False

    async def get_device(self, device_id: str):
        return self


class _FakeBridgeService:
    """Fake bridge service for testing."""

    async def list_bridges(self, device_id: str):
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
                "comment": "Main bridge",
                "transport": "rest",
                "fallback_used": False,
            },
            {
                "id": "*2",
                "name": "bridge2",
                "mtu": 1500,
                "actual_mtu": 1500,
                "l2mtu": 1514,
                "mac_address": "78:9A:18:A2:F3:D5",
                "disabled": True,
                "running": False,
                "protocol_mode": "stp",
                "vlan_filtering": True,
                "comment": "",
                "transport": "rest",
                "fallback_used": False,
            },
        ]

    async def list_bridge_ports(self, device_id: str):
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
                "comment": "LAN port",
                "transport": "rest",
                "fallback_used": False,
            },
            {
                "id": "*2",
                "interface": "ether3",
                "bridge": "bridge1",
                "disabled": False,
                "hw": True,
                "pvid": 10,
                "priority": "0x80",
                "path_cost": 10,
                "comment": "",
                "transport": "rest",
                "fallback_used": False,
            },
        ]


class TestBridgeTools(unittest.TestCase):
    """Test bridge MCP tools."""

    def test_list_bridges_tool(self):
        """Test list_bridges tool."""
        async def _run():
            fake_device_service = _FakeDeviceService()
            fake_bridge_service = _FakeBridgeService()

            with (
                patch.object(bridge_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(bridge_tools, "DeviceService", lambda *args, **kwargs: fake_device_service),
                patch.object(bridge_tools, "BridgeService", lambda *args, **kwargs: fake_bridge_service),
                patch.object(bridge_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = DummyMCP()
                settings = Settings(environment="lab")
                bridge_tools.register_bridge_tools(mcp, settings)

                # Get the tool
                list_bridges_tool = mcp.tools.get("list_bridges")
                assert list_bridges_tool is not None

                # Call the tool
                result = await list_bridges_tool(device_id="dev-lab-01")

                # Verify result
                assert result["content"][0]["text"] == "Found 2 bridge(s) on router-lab-01"
                assert result["isError"] is False
                assert result["_meta"]["device_id"] == "dev-lab-01"
                assert result["_meta"]["total_count"] == 2
                assert len(result["_meta"]["bridges"]) == 2

                # Verify bridge data
                bridges = result["_meta"]["bridges"]
                assert bridges[0]["name"] == "bridge1"
                assert bridges[0]["protocol_mode"] == "rstp"
                assert bridges[0]["vlan_filtering"] is False
                assert bridges[1]["name"] == "bridge2"
                assert bridges[1]["protocol_mode"] == "stp"
                assert bridges[1]["vlan_filtering"] is True

        asyncio.run(_run())

    def test_list_bridge_ports_tool(self):
        """Test list_bridge_ports tool."""
        async def _run():
            fake_device_service = _FakeDeviceService()
            fake_bridge_service = _FakeBridgeService()

            with (
                patch.object(bridge_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(bridge_tools, "DeviceService", lambda *args, **kwargs: fake_device_service),
                patch.object(bridge_tools, "BridgeService", lambda *args, **kwargs: fake_bridge_service),
                patch.object(bridge_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = DummyMCP()
                settings = Settings(environment="lab")
                bridge_tools.register_bridge_tools(mcp, settings)

                # Get the tool
                list_ports_tool = mcp.tools.get("list_bridge_ports")
                assert list_ports_tool is not None

                # Call the tool
                result = await list_ports_tool(device_id="dev-lab-01")

                # Verify result
                assert result["content"][0]["text"] == "Found 2 bridge port(s) on router-lab-01"
                assert result["isError"] is False
                assert result["_meta"]["device_id"] == "dev-lab-01"
                assert result["_meta"]["total_count"] == 2
                assert len(result["_meta"]["bridge_ports"]) == 2

                # Verify port data
                ports = result["_meta"]["bridge_ports"]
                assert ports[0]["interface"] == "ether2"
                assert ports[0]["bridge"] == "bridge1"
                assert ports[0]["pvid"] == 1
                assert ports[0]["hw"] is True
                assert ports[1]["interface"] == "ether3"
                assert ports[1]["pvid"] == 10

        asyncio.run(_run())

    def test_bridge_tools_registration(self):
        """Test that bridge tools are registered correctly."""
        mcp = DummyMCP()
        settings = Settings(environment="lab")
        bridge_tools.register_bridge_tools(mcp, settings)

        # Check that tools were registered
        assert "list_bridges" in mcp.tools
        assert "list_bridge_ports" in mcp.tools

    def test_list_bridges_error_handling(self):
        """Test list_bridges tool error handling."""
        async def _run():
            fake_device_service = _FakeDeviceService()

            class FailingBridgeService:
                async def list_bridges(self, device_id: str):
                    raise RuntimeError("Bridge listing failed")

            fake_bridge_service = FailingBridgeService()

            with (
                patch.object(bridge_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(bridge_tools, "DeviceService", lambda *args, **kwargs: fake_device_service),
                patch.object(bridge_tools, "BridgeService", lambda *args, **kwargs: fake_bridge_service),
                patch.object(bridge_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = DummyMCP()
                settings = Settings(environment="lab")
                bridge_tools.register_bridge_tools(mcp, settings)

                # Get the tool
                list_bridges_tool = mcp.tools.get("list_bridges")
                assert list_bridges_tool is not None

                # Call the tool (should handle error gracefully)
                result = await list_bridges_tool(device_id="dev-lab-01")

                # Verify error response
                assert result["isError"] is True
                assert "Bridge listing failed" in result["content"][0]["text"]

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()

