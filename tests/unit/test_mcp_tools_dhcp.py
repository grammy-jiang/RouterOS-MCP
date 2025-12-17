from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import dhcp as dhcp_module
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


if __name__ == "__main__":
    unittest.main()
