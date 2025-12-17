"""E2E tests for DHCP MCP tools.

These tests validate the public MCP tool contract (content/isError/_meta)
while mocking external dependencies (DB session factory + domain services).
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.mcp_tools import dhcp as dhcp_tools

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


class _FakeDHCPService:
    """Fake DHCP service for E2E testing."""

    async def get_dhcp_server_status(self, device_id: str):
        return {
            "total_count": 1,
            "servers": [
                {
                    "name": "dhcp1",
                    "interface": "bridge",
                    "lease_time": "10m",
                    "address_pool": "pool1",
                    "disabled": False,
                }
            ],
        }

    async def get_dhcp_leases(self, device_id: str):
        return {
            "total_count": 2,
            "leases": [
                {
                    "address": "192.168.1.10",
                    "mac_address": "00:11:22:33:44:55",
                    "client_id": "1:00:11:22:33:44:55",
                    "host_name": "client1",
                    "server": "dhcp1",
                    "status": "bound",
                },
                {
                    "address": "192.168.1.11",
                    "mac_address": "AA:BB:CC:DD:EE:FF",
                    "client_id": "",
                    "host_name": "client2",
                    "server": "dhcp1",
                    "status": "bound",
                },
            ],
        }


class TestDHCPToolsE2E(unittest.TestCase):
    """E2E tests for DHCP MCP tools."""

    def _register_dhcp_tools(self) -> DummyMCP:
        mcp = DummyMCP()
        settings = make_test_settings()
        dhcp_tools.register_dhcp_tools(mcp, settings)
        return mcp

    def test_get_dhcp_server_status_tool_success(self) -> None:
        """DHCP server status tool returns expected content and metadata."""

        async def _run() -> None:
            with (
                patch.object(dhcp_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(dhcp_tools, "DeviceService", _FakeDeviceService),
                patch.object(dhcp_tools, "DHCPService", lambda *args, **kwargs: _FakeDHCPService()),
                patch.object(dhcp_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_dhcp_tools()
                tool = mcp.tools["get_dhcp_server_status"]

                result = await tool(device_id="dev-lab-01")

                self.assertFalse(result["isError"])
                self.assertEqual(result["content"][0]["text"], "DHCP server 'dhcp1' on bridge")

                meta = result["_meta"]
                self.assertEqual(meta["device_id"], "dev-lab-01")
                self.assertEqual(meta["total_count"], 1)
                self.assertEqual(len(meta["servers"]), 1)
                self.assertEqual(meta["servers"][0]["name"], "dhcp1")
                self.assertEqual(meta["servers"][0]["interface"], "bridge")

        asyncio.run(_run())

    def test_get_dhcp_leases_tool_success(self) -> None:
        """DHCP leases tool returns expected content and metadata."""

        async def _run() -> None:
            with (
                patch.object(dhcp_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(dhcp_tools, "DeviceService", _FakeDeviceService),
                patch.object(dhcp_tools, "DHCPService", lambda *args, **kwargs: _FakeDHCPService()),
                patch.object(dhcp_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_dhcp_tools()
                tool = mcp.tools["get_dhcp_leases"]

                result = await tool(device_id="dev-lab-01")

                self.assertFalse(result["isError"])
                self.assertEqual(result["content"][0]["text"], "2 active DHCP leases")

                meta = result["_meta"]
                self.assertEqual(meta["device_id"], "dev-lab-01")
                self.assertEqual(meta["total_count"], 2)
                self.assertEqual(len(meta["leases"]), 2)
                self.assertEqual(meta["leases"][0]["address"], "192.168.1.10")
                self.assertEqual(meta["leases"][1]["address"], "192.168.1.11")

        asyncio.run(_run())
