from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import dhcp as dhcp_module
from routeros_mcp.mcp.errors import ValidationError
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


class FakeDevice:
    def __init__(self, device_id: str = "dev1", environment: str = "lab") -> None:
        self.id = device_id
        self.environment = environment
        self.allow_professional_workflows = True
        self.allow_advanced_writes = True


class FakeDeviceService:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def get_device(self, device_id: str) -> FakeDevice:
        return FakeDevice(device_id=device_id, environment="lab")


class FakeDHCPService:
    async def get_dhcp_server_status(self, device_id: str):
        return {
            "servers": [
                {
                    "name": "dhcp1",
                    "interface": "bridge",
                    "lease_time": "10m",
                    "address_pool": "pool1",
                    "disabled": False,
                }
            ],
            "total_count": 1,
        }

    async def get_dhcp_leases(self, device_id: str):
        return {
            "leases": [
                {
                    "address": "192.168.1.10",
                    "mac_address": "00:11:22:33:44:55",
                    "client_id": "1:00:11:22:33:44:55",
                    "host_name": "client1",
                    "server": "dhcp1",
                    "status": "bound",
                }
            ],
            "total_count": 1,
        }


class FakeDHCPServiceMany:
    async def get_dhcp_server_status(self, device_id: str):
        return {
            "servers": [
                {"name": "dhcp1", "interface": "bridge", "lease_time": "10m", "address_pool": "pool1", "disabled": False},
                {"name": "dhcp2", "interface": "ether2", "lease_time": "10m", "address_pool": "pool2", "disabled": False},
            ],
            "total_count": 2,
        }

    async def get_dhcp_leases(self, device_id: str):
        return {
            "leases": [
                {"address": "192.168.1.10", "host_name": "a", "status": "bound"},
                {"address": "192.168.1.11", "host_name": "b", "status": "bound"},
            ],
            "total_count": 2,
        }


class TestMCPToolsDHCP(unittest.TestCase):
    def _register_tools(self) -> DummyMCP:
        mcp = DummyMCP()
        settings = Settings()
        dhcp_module.register_dhcp_tools(mcp, settings)
        return mcp

    def test_dhcp_tools_registered(self) -> None:
        mcp = self._register_tools()
        self.assertIn("get_dhcp_server_status", mcp.tools)
        self.assertIn("get_dhcp_leases", mcp.tools)

    @patch.object(dhcp_module, "DeviceService")
    @patch.object(dhcp_module, "DHCPService")
    @patch.object(dhcp_module, "get_session_factory")
    def test_get_dhcp_server_status(
        self, mock_session_factory, mock_dhcp_service_cls, mock_device_service_cls
    ) -> None:
        mock_session_factory.return_value = FakeSessionFactory()
        mock_device_service_cls.return_value = FakeDeviceService()
        mock_dhcp_service_cls.return_value = FakeDHCPService()

        mcp = self._register_tools()
        tool_func = mcp.tools["get_dhcp_server_status"]
        result = asyncio.run(tool_func(device_id="dev1"))

        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("_meta", result)
        self.assertFalse(result.get("isError", False))

        meta = result["_meta"]
        self.assertEqual(meta["device_id"], "dev1")
        self.assertIn("servers", meta)
        self.assertEqual(meta["total_count"], 1)

    @patch.object(dhcp_module, "DeviceService")
    @patch.object(dhcp_module, "DHCPService")
    @patch.object(dhcp_module, "get_session_factory")
    def test_get_dhcp_leases(
        self, mock_session_factory, mock_dhcp_service_cls, mock_device_service_cls
    ) -> None:
        mock_session_factory.return_value = FakeSessionFactory()
        mock_device_service_cls.return_value = FakeDeviceService()
        mock_dhcp_service_cls.return_value = FakeDHCPService()

        mcp = self._register_tools()
        tool_func = mcp.tools["get_dhcp_leases"]
        result = asyncio.run(tool_func(device_id="dev1"))

        self.assertIsInstance(result, dict)
        self.assertIn("content", result)
        self.assertIn("_meta", result)
        self.assertFalse(result.get("isError", False))

        meta = result["_meta"]
        self.assertEqual(meta["device_id"], "dev1")
        self.assertIn("leases", meta)
        self.assertEqual(meta["total_count"], 1)

    @patch.object(dhcp_module, "DeviceService")
    @patch.object(dhcp_module, "DHCPService")
    @patch.object(dhcp_module, "get_session_factory")
    def test_get_dhcp_server_status_no_servers(
        self, mock_session_factory, mock_dhcp_service_cls, mock_device_service_cls
    ) -> None:
        mock_session_factory.return_value = FakeSessionFactory()
        mock_device_service_cls.return_value = FakeDeviceService()

        fake_dhcp_service = FakeDHCPService()

        async def empty_server_status(device_id):
            return {"servers": [], "total_count": 0}

        fake_dhcp_service.get_dhcp_server_status = empty_server_status
        mock_dhcp_service_cls.return_value = fake_dhcp_service

        mcp = self._register_tools()
        tool_func = mcp.tools["get_dhcp_server_status"]
        result = asyncio.run(tool_func(device_id="dev1"))

        self.assertIsInstance(result, dict)
        content_text = result["content"][0]["text"]
        self.assertIn("No DHCP servers", content_text)

    @patch.object(dhcp_module, "DeviceService")
    @patch.object(dhcp_module, "DHCPService")
    @patch.object(dhcp_module, "get_session_factory")
    def test_get_dhcp_leases_no_leases(
        self, mock_session_factory, mock_dhcp_service_cls, mock_device_service_cls
    ) -> None:
        mock_session_factory.return_value = FakeSessionFactory()
        mock_device_service_cls.return_value = FakeDeviceService()

        fake_dhcp_service = FakeDHCPService()

        async def empty_leases(device_id):
            return {"leases": [], "total_count": 0}

        fake_dhcp_service.get_dhcp_leases = empty_leases
        mock_dhcp_service_cls.return_value = fake_dhcp_service

        mcp = self._register_tools()
        tool_func = mcp.tools["get_dhcp_leases"]
        result = asyncio.run(tool_func(device_id="dev1"))

        self.assertIsInstance(result, dict)
        content_text = result["content"][0]["text"]
        self.assertIn("No active DHCP leases", content_text)

    @patch.object(dhcp_module, "DeviceService")
    @patch.object(dhcp_module, "DHCPService")
    @patch.object(dhcp_module, "get_session_factory")
    def test_get_dhcp_server_status_multiple_servers_formats_list(
        self, mock_session_factory, mock_dhcp_service_cls, mock_device_service_cls
    ) -> None:
        mock_session_factory.return_value = FakeSessionFactory()
        mock_device_service_cls.return_value = FakeDeviceService()
        mock_dhcp_service_cls.return_value = FakeDHCPServiceMany()

        mcp = self._register_tools()
        tool_func = mcp.tools["get_dhcp_server_status"]
        result = asyncio.run(tool_func(device_id="dev1"))

        content_text = result["content"][0]["text"]
        self.assertIn("2 DHCP servers", content_text)
        self.assertIn("dhcp1", content_text)
        self.assertIn("dhcp2", content_text)

    @patch.object(dhcp_module, "DeviceService")
    @patch.object(dhcp_module, "DHCPService")
    @patch.object(dhcp_module, "get_session_factory")
    def test_get_dhcp_leases_multiple_leases_formats_count(
        self, mock_session_factory, mock_dhcp_service_cls, mock_device_service_cls
    ) -> None:
        mock_session_factory.return_value = FakeSessionFactory()
        mock_device_service_cls.return_value = FakeDeviceService()
        mock_dhcp_service_cls.return_value = FakeDHCPServiceMany()

        mcp = self._register_tools()
        tool_func = mcp.tools["get_dhcp_leases"]
        result = asyncio.run(tool_func(device_id="dev1"))

        content_text = result["content"][0]["text"]
        self.assertIn("2 active DHCP leases", content_text)

    @patch.object(dhcp_module, "DeviceService")
    @patch.object(dhcp_module, "DHCPService")
    @patch.object(dhcp_module, "get_session_factory")
    def test_get_dhcp_server_status_handles_mcp_error(
        self, mock_session_factory, mock_dhcp_service_cls, mock_device_service_cls
    ) -> None:
        mock_session_factory.return_value = FakeSessionFactory()
        mock_device_service_cls.return_value = FakeDeviceService()

        class _Boom:
            async def get_dhcp_server_status(self, device_id: str):
                raise ValidationError("bad", data={"device_id": device_id})

        mock_dhcp_service_cls.return_value = _Boom()

        mcp = self._register_tools()
        tool_func = mcp.tools["get_dhcp_server_status"]
        result = asyncio.run(tool_func(device_id="dev1"))

        self.assertTrue(result.get("isError", False))
        self.assertIn("bad", result["content"][0]["text"])
        self.assertEqual(result.get("_meta"), {"device_id": "dev1"})

    @patch.object(dhcp_module, "DeviceService")
    @patch.object(dhcp_module, "DHCPService")
    @patch.object(dhcp_module, "get_session_factory")
    def test_get_dhcp_leases_handles_generic_error_via_mapper(
        self, mock_session_factory, mock_dhcp_service_cls, mock_device_service_cls
    ) -> None:
        mock_session_factory.return_value = FakeSessionFactory()
        mock_device_service_cls.return_value = FakeDeviceService()

        class _Boom:
            async def get_dhcp_leases(self, device_id: str):
                raise ValueError("nope")

        mock_dhcp_service_cls.return_value = _Boom()

        mcp = self._register_tools()
        tool_func = mcp.tools["get_dhcp_leases"]
        result = asyncio.run(tool_func(device_id="dev1"))

        self.assertTrue(result.get("isError", False))
        self.assertIn("nope", result["content"][0]["text"])

    # Tests for DHCP Plan/Apply Tools

    @patch.object(dhcp_module, "DeviceService")
    @patch.object(dhcp_module, "DHCPPlanService")
    @patch.object(dhcp_module, "PlanService")
    @patch.object(dhcp_module, "get_session_factory")
    def test_plan_create_dhcp_pool_success(
        self, mock_session_factory, mock_plan_service_cls, mock_dhcp_plan_service_cls, mock_device_service_cls
    ) -> None:
        """Test successful DHCP pool creation plan."""
        mock_session_factory.return_value = FakeSessionFactory()
        
        # Mock device service to return lab device with DHCP writes enabled
        fake_device = FakeDevice(device_id="dev1", environment="lab")
        fake_device.allow_dhcp_writes = True
        fake_device.name = "router-lab-01"  # Add name attribute
        fake_device_service = FakeDeviceService()
        
        async def mock_get_device(device_id):
            return fake_device
        
        fake_device_service.get_device = mock_get_device
        mock_device_service_cls.return_value = fake_device_service
        
        # Mock DHCP plan service
        fake_dhcp_plan = dhcp_module.DHCPPlanService()
        mock_dhcp_plan_service_cls.return_value = fake_dhcp_plan
        
        # Mock plan service
        fake_plan_service = unittest.mock.MagicMock()
        
        async def mock_create_plan(*args, **kwargs):
            return {
                "plan_id": "plan-dhcp-001",
                "approval_token": "approve-test-abc",
                "approval_expires_at": "2025-12-15T12:00:00Z",
            }
        
        fake_plan_service.create_plan = mock_create_plan
        mock_plan_service_cls.return_value = fake_plan_service
        
        mcp = self._register_tools()
        tool_func = mcp.tools["plan_create_dhcp_pool"]
        result = asyncio.run(tool_func(
            device_ids=["dev1"],
            pool_name="test-pool",
            address_range="192.168.1.100-192.168.1.200",
            gateway="192.168.1.1",
            dns_servers=["8.8.8.8"]
        ))
        
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("isError", False), f"Test failed with error: {result.get('content', '')}")
        self.assertIn("_meta", result)
        self.assertEqual(result["_meta"]["plan_id"], "plan-dhcp-001")
        self.assertEqual(result["_meta"]["approval_token"], "approve-test-abc")

    @patch.object(dhcp_module, "DeviceService")
    @patch.object(dhcp_module, "DHCPPlanService")
    @patch.object(dhcp_module, "get_session_factory")
    def test_plan_create_dhcp_pool_validation_error(
        self, mock_session_factory, mock_dhcp_plan_service_cls, mock_device_service_cls
    ) -> None:
        """Test DHCP pool creation plan with validation error."""
        mock_session_factory.return_value = FakeSessionFactory()
        mock_device_service_cls.return_value = FakeDeviceService()
        
        # Mock DHCP plan service to raise validation error
        fake_dhcp_plan = unittest.mock.MagicMock()
        fake_dhcp_plan.validate_pool_params.side_effect = ValueError("Invalid address range")
        mock_dhcp_plan_service_cls.return_value = fake_dhcp_plan
        
        mcp = self._register_tools()
        tool_func = mcp.tools["plan_create_dhcp_pool"]
        result = asyncio.run(tool_func(
            device_ids=["dev1"],
            pool_name="test-pool",
            address_range="invalid-range",
            gateway="",
            dns_servers=None
        ))
        
        self.assertTrue(result.get("isError", False))
        self.assertIn("Invalid address range", result["content"][0]["text"])

    @patch.object(dhcp_module, "DeviceService")
    @patch.object(dhcp_module, "get_session_factory")
    def test_plan_create_dhcp_pool_missing_capability(
        self, mock_session_factory, mock_device_service_cls
    ) -> None:
        """Test DHCP pool creation plan fails without DHCP write capability."""
        mock_session_factory.return_value = FakeSessionFactory()
        
        # Mock device service to return device without DHCP writes
        fake_device = FakeDevice(device_id="dev1", environment="lab")
        fake_device.allow_dhcp_writes = False
        fake_device_service = FakeDeviceService()
        
        async def mock_get_device(device_id):
            return fake_device
        
        fake_device_service.get_device = mock_get_device
        mock_device_service_cls.return_value = fake_device_service
        
        mcp = self._register_tools()
        tool_func = mcp.tools["plan_create_dhcp_pool"]
        result = asyncio.run(tool_func(
            device_ids=["dev1"],
            pool_name="test-pool",
            address_range="192.168.1.100-192.168.1.200",
            gateway="",
            dns_servers=None
        ))
        
        self.assertTrue(result.get("isError", False))
        self.assertIn("does not have DHCP write capability", result["content"][0]["text"])


class TestDHCPPlanService(unittest.TestCase):
    """Tests for DHCPPlanService."""
    
    def test_validate_pool_params_success(self) -> None:
        """Test successful pool parameter validation."""
        service = dhcp_module.DHCPPlanService()
        
        result = service.validate_pool_params(
            pool_name="test-pool",
            address_range="192.168.1.100-192.168.1.200",
            gateway="192.168.1.1",
            dns_servers=["8.8.8.8", "8.8.4.4"]
        )
        
        self.assertTrue(result["valid"])
        self.assertEqual(result["pool_name"], "test-pool")
        self.assertEqual(result["address_range"], "192.168.1.100-192.168.1.200")
    
    def test_validate_pool_params_invalid_range(self) -> None:
        """Test pool parameter validation with invalid range."""
        service = dhcp_module.DHCPPlanService()
        
        with self.assertRaises(ValueError) as context:
            service.validate_pool_params(
                pool_name="test-pool",
                address_range="192.168.1.200-192.168.1.100",  # Start > End
                gateway=None,
                dns_servers=None
            )
        
        self.assertIn("start IP", str(context.exception))
    
    def test_validate_pool_params_gateway_not_in_subnet(self) -> None:
        """Test pool parameter validation with gateway not in subnet."""
        service = dhcp_module.DHCPPlanService()
        
        with self.assertRaises(ValueError) as context:
            service.validate_pool_params(
                pool_name="test-pool",
                address_range="192.168.1.100-192.168.1.200",
                gateway="10.0.0.1",  # Different subnet
                dns_servers=None
            )
        
        self.assertIn("Gateway", str(context.exception))
        self.assertIn("same subnet", str(context.exception))
    
    def test_check_pool_overlap_no_overlap(self) -> None:
        """Test pool overlap detection with no overlap."""
        service = dhcp_module.DHCPPlanService()
        
        existing_pools = [
            {"name": "pool1", "address_range": "192.168.1.50-192.168.1.99"},
        ]
        
        result = service.check_pool_overlap(
            new_range="192.168.1.100-192.168.1.200",
            existing_pools=existing_pools
        )
        
        self.assertFalse(result["overlap_detected"])
    
    def test_check_pool_overlap_with_overlap(self) -> None:
        """Test pool overlap detection with overlap."""
        service = dhcp_module.DHCPPlanService()
        
        existing_pools = [
            {"name": "pool1", "address_range": "192.168.1.50-192.168.1.150"},
        ]
        
        with self.assertRaises(ValueError) as context:
            service.check_pool_overlap(
                new_range="192.168.1.100-192.168.1.200",
                existing_pools=existing_pools
            )
        
        self.assertIn("overlaps", str(context.exception))
        self.assertIn("pool1", str(context.exception))
    
    def test_assess_risk_production(self) -> None:
        """Test risk assessment for production environment."""
        service = dhcp_module.DHCPPlanService()
        
        risk = service.assess_risk(
            operation="create_dhcp_pool",
            device_environment="prod",
            affects_production=False
        )
        
        self.assertEqual(risk, "high")
    
    def test_assess_risk_pool_removal(self) -> None:
        """Test risk assessment for pool removal."""
        service = dhcp_module.DHCPPlanService()
        
        risk = service.assess_risk(
            operation="remove_dhcp_pool",
            device_environment="lab",
            affects_production=False
        )
        
        self.assertEqual(risk, "high")
    
    def test_assess_risk_medium(self) -> None:
        """Test risk assessment for medium risk operation."""
        service = dhcp_module.DHCPPlanService()
        
        risk = service.assess_risk(
            operation="create_dhcp_pool",
            device_environment="lab",
            affects_production=False
        )
        
        self.assertEqual(risk, "medium")


if __name__ == "__main__":
    unittest.main()
