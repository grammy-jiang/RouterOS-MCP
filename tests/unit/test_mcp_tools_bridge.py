"""Unit tests for bridge MCP tools."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

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
                patch.object(
                    bridge_tools, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(
                    bridge_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(
                    bridge_tools, "BridgeService", lambda *args, **kwargs: fake_bridge_service
                ),
                patch.object(
                    bridge_tools, "check_tool_authorization", lambda *args, **kwargs: None
                ),
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
                patch.object(
                    bridge_tools, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(
                    bridge_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(
                    bridge_tools, "BridgeService", lambda *args, **kwargs: fake_bridge_service
                ),
                patch.object(
                    bridge_tools, "check_tool_authorization", lambda *args, **kwargs: None
                ),
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
                patch.object(
                    bridge_tools, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(
                    bridge_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(
                    bridge_tools, "BridgeService", lambda *args, **kwargs: fake_bridge_service
                ),
                patch.object(
                    bridge_tools, "check_tool_authorization", lambda *args, **kwargs: None
                ),
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

    def test_plan_add_bridge_port_registered(self) -> None:
        """Test that plan_add_bridge_port tool is registered."""
        mcp = DummyMCP()
        settings = Settings()
        bridge_tools.register_bridge_tools(mcp, settings)
        
        self.assertIn("plan_add_bridge_port", mcp.tools)
        self.assertIn("plan_remove_bridge_port", mcp.tools)
        self.assertIn("plan_modify_bridge_settings", mcp.tools)
        self.assertIn("apply_bridge_plan", mcp.tools)


class TestBridgePlanService(unittest.TestCase):
    """Tests for BridgePlanService."""
    
    def test_validate_bridge_params_add_port_success(self) -> None:
        """Test successful bridge parameter validation for add port."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        result = service.validate_bridge_params(
            bridge_name="bridge-lan",
            interface="ether2",
            settings=None,
            operation="add_bridge_port"
        )
        
        self.assertTrue(result["valid"])
        self.assertEqual(result["bridge_name"], "bridge-lan")
        self.assertEqual(result["interface"], "ether2")
    
    def test_validate_bridge_params_modify_settings_success(self) -> None:
        """Test successful bridge parameter validation for modify settings."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        result = service.validate_bridge_params(
            bridge_name="bridge-lan",
            interface=None,
            settings={"protocol_mode": "rstp", "vlan_filtering": True},
            operation="modify_bridge_settings"
        )
        
        self.assertTrue(result["valid"])
        self.assertEqual(result["bridge_name"], "bridge-lan")
    
    def test_validate_bridge_params_empty_bridge_name(self) -> None:
        """Test bridge parameter validation with empty bridge name."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        with self.assertRaises(ValueError) as context:
            service.validate_bridge_params(
                bridge_name="",
                interface="ether2",
                settings=None,
                operation="add_bridge_port"
            )
        
        self.assertIn("Bridge name cannot be empty", str(context.exception))
    
    def test_validate_bridge_params_missing_interface_for_add(self) -> None:
        """Test bridge parameter validation with missing interface for add port."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        with self.assertRaises(ValueError) as context:
            service.validate_bridge_params(
                bridge_name="bridge-lan",
                interface="",
                settings=None,
                operation="add_bridge_port"
            )
        
        self.assertIn("Interface name is required", str(context.exception))
    
    def test_validate_bridge_params_invalid_protocol_mode(self) -> None:
        """Test bridge parameter validation with invalid protocol mode."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        with self.assertRaises(ValueError) as context:
            service.validate_bridge_params(
                bridge_name="bridge-lan",
                interface=None,
                settings={"protocol_mode": "invalid"},
                operation="modify_bridge_settings"
            )
        
        self.assertIn("Invalid protocol_mode", str(context.exception))
    
    def test_check_interface_available_success(self) -> None:
        """Test interface availability check with available interface."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        existing_ports = [
            {"interface": "ether1", "bridge": "bridge-lan"},
        ]
        
        result = service.check_interface_available(
            interface="ether2",
            existing_ports=existing_ports
        )
        
        self.assertTrue(result["available"])
    
    def test_check_interface_available_already_bridged(self) -> None:
        """Test interface availability check with already bridged interface."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        existing_ports = [
            {"interface": "ether2", "bridge": "bridge-lan"},
        ]
        
        with self.assertRaises(ValueError) as context:
            service.check_interface_available(
                interface="ether2",
                existing_ports=existing_ports
            )
        
        self.assertIn("already a member", str(context.exception))
        self.assertIn("bridge-lan", str(context.exception))
    
    def test_check_stp_safety_production_bridge(self) -> None:
        """Test STP safety check blocks changes on production bridge."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        with self.assertRaises(ValueError) as context:
            service.check_stp_safety(
                bridge_name="bridge-lan",
                settings={"protocol_mode": "rstp"},
                device_environment="prod"
            )
        
        self.assertIn("STP/protocol changes are blocked", str(context.exception))
        self.assertIn("production bridge", str(context.exception))
    
    def test_check_stp_safety_lab_environment(self) -> None:
        """Test STP safety check allows changes on lab bridge."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        result = service.check_stp_safety(
            bridge_name="bridge-lan",
            settings={"protocol_mode": "rstp"},
            device_environment="lab"
        )
        
        self.assertTrue(result["safe"])
        self.assertTrue(result["is_stp_change"])
    
    def test_check_stp_safety_non_stp_change(self) -> None:
        """Test STP safety check with non-STP change."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        result = service.check_stp_safety(
            bridge_name="bridge-lan",
            settings={"ageing_time": "10m"},
            device_environment="prod"
        )
        
        self.assertTrue(result["safe"])
        self.assertFalse(result["is_stp_change"])
    
    def test_assess_risk_production(self) -> None:
        """Test risk assessment for production environment."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        risk = service.assess_risk(
            operation="add_bridge_port",
            device_environment="prod",
            is_stp_change=False,
            is_vlan_filtering_change=False
        )
        
        self.assertEqual(risk, "high")
    
    def test_assess_risk_stp_change(self) -> None:
        """Test risk assessment for STP change."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        risk = service.assess_risk(
            operation="modify_bridge_settings",
            device_environment="lab",
            is_stp_change=True,
            is_vlan_filtering_change=False
        )
        
        self.assertEqual(risk, "high")
    
    def test_assess_risk_vlan_filtering_change(self) -> None:
        """Test risk assessment for VLAN filtering change."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        risk = service.assess_risk(
            operation="modify_bridge_settings",
            device_environment="lab",
            is_stp_change=False,
            is_vlan_filtering_change=True
        )
        
        self.assertEqual(risk, "high")
    
    def test_assess_risk_port_removal(self) -> None:
        """Test risk assessment for port removal."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        risk = service.assess_risk(
            operation="remove_bridge_port",
            device_environment="lab",
            is_stp_change=False,
            is_vlan_filtering_change=False
        )
        
        self.assertEqual(risk, "high")
    
    def test_assess_risk_medium(self) -> None:
        """Test risk assessment for medium risk operation."""
        from routeros_mcp.domain.services.bridge import BridgePlanService
        
        service = BridgePlanService()
        
        risk = service.assess_risk(
            operation="add_bridge_port",
            device_environment="lab",
            is_stp_change=False,
            is_vlan_filtering_change=False
        )
        
        self.assertEqual(risk, "medium")


if __name__ == "__main__":
    unittest.main()
