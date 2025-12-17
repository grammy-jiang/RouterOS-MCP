"""E2E tests for wireless MCP tools."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.mcp_tools import wireless as wireless_tools

from .e2e_test_utils import DummyMCP, FakeSessionFactory, make_test_settings


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


class _FakeWirelessService:
    """Fake wireless service for testing."""

    async def get_wireless_interfaces(self, device_id: str):
        return [
            {
                "id": "*1",
                "name": "wlan1",
                "ssid": "TestNetwork",
                "frequency": "2437",
                "band": "2ghz-b/g/n",
                "channel_width": "20mhz",
                "tx_power": "20",
                "tx_power_mode": "default",
                "mode": "ap-bridge",
                "running": True,
                "disabled": False,
                "comment": "Main AP",
                "mac_address": "aa:bb:cc:dd:ee:01",
                "registered_clients": 2,
                "authenticated_clients": 2,
            },
            {
                "id": "*2",
                "name": "wlan2",
                "ssid": "GuestNetwork",
                "frequency": "5180",
                "band": "5ghz-a/n/ac",
                "channel_width": "40mhz",
                "tx_power": "17",
                "tx_power_mode": "default",
                "mode": "ap-bridge",
                "running": False,
                "disabled": True,
                "comment": "Guest AP",
                "mac_address": "aa:bb:cc:dd:ee:02",
                "registered_clients": 0,
                "authenticated_clients": 0,
            },
        ]

    async def get_wireless_clients(self, device_id: str):
        return [
            {
                "id": "*a",
                "interface": "wlan1",
                "mac_address": "11:22:33:44:55:66",
                "signal_strength": -65,
                "signal_to_noise": 35,
                "tx_rate": "54Mbps",
                "rx_rate": "54Mbps",
                "uptime": "1h23m45s",
                "bytes_sent": 1024000,
                "bytes_received": 1024000,
                "packets_sent": 5000,
                "packets_received": 5000,
            },
            {
                "id": "*b",
                "interface": "wlan1",
                "mac_address": "77:88:99:aa:bb:cc",
                "signal_strength": -72,
                "signal_to_noise": 28,
                "tx_rate": "144.4Mbps",
                "rx_rate": "144.4Mbps",
                "uptime": "45m12s",
                "bytes_sent": 512000,
                "bytes_received": 512000,
                "packets_sent": 2500,
                "packets_received": 2500,
            },
        ]


class TestWirelessTools(unittest.TestCase):
    """E2E tests for wireless MCP tools."""

    def _register_wireless_tools(self) -> DummyMCP:
        """Register wireless tools with mocked dependencies."""
        mcp = DummyMCP()
        settings = make_test_settings()
        wireless_tools.register_wireless_tools(mcp, settings)
        return mcp

    def test_get_wireless_interfaces_success(self) -> None:
        """Test getting wireless interfaces successfully."""

        async def _run() -> None:
            with (
                patch.object(
                    wireless_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(wireless_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    wireless_tools,
                    "WirelessService",
                    lambda *args, **kwargs: _FakeWirelessService(),
                ),
                patch.object(wireless_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_wireless_tools()

                tool = mcp.tools["get_wireless_interfaces"]
                result = await tool(device_id="dev-lab-01")

                # Verify response structure
                self.assertFalse(result["isError"])
                self.assertIn("Found 2 wireless interface(s)", result["content"][0]["text"])

                # Verify metadata
                meta = result["_meta"]
                self.assertEqual(meta["device_id"], "dev-lab-01")
                self.assertEqual(meta["total_count"], 2)
                self.assertEqual(len(meta["interfaces"]), 2)

                # Verify first interface
                interface1 = meta["interfaces"][0]
                self.assertEqual(interface1["name"], "wlan1")
                self.assertEqual(interface1["ssid"], "TestNetwork")
                self.assertEqual(interface1["frequency"], "2437")
                self.assertTrue(interface1["running"])
                self.assertEqual(interface1["registered_clients"], 2)

        asyncio.run(_run())

    def test_get_wireless_clients_success(self) -> None:
        """Test getting wireless clients successfully."""

        async def _run() -> None:
            with (
                patch.object(
                    wireless_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(wireless_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    wireless_tools,
                    "WirelessService",
                    lambda *args, **kwargs: _FakeWirelessService(),
                ),
                patch.object(wireless_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_wireless_tools()

                tool = mcp.tools["get_wireless_clients"]
                result = await tool(device_id="dev-lab-01")

                # Verify response structure
                self.assertFalse(result["isError"])
                self.assertIn("Found 2 connected wireless client(s)", result["content"][0]["text"])

                # Verify metadata
                meta = result["_meta"]
                self.assertEqual(meta["device_id"], "dev-lab-01")
                self.assertEqual(meta["total_count"], 2)
                self.assertEqual(len(meta["clients"]), 2)

                # Verify first client
                client1 = meta["clients"][0]
                self.assertEqual(client1["interface"], "wlan1")
                self.assertEqual(client1["mac_address"], "11:22:33:44:55:66")
                self.assertEqual(client1["signal_strength"], -65)
                self.assertEqual(client1["tx_rate"], "54Mbps")

        asyncio.run(_run())

    def test_get_wireless_interfaces_with_exception(self) -> None:
        """Test error handling when getting wireless interfaces fails."""

        class _FailingWirelessService:
            async def get_wireless_interfaces(self, device_id: str):
                raise RuntimeError("Failed to get wireless interfaces")

        async def _run() -> None:
            with (
                patch.object(
                    wireless_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(wireless_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    wireless_tools,
                    "WirelessService",
                    lambda *args, **kwargs: _FailingWirelessService(),
                ),
                patch.object(wireless_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_wireless_tools()

                tool = mcp.tools["get_wireless_interfaces"]
                result = await tool(device_id="dev-lab-01")

                # Verify error response
                self.assertTrue(result["isError"])
                self.assertIn("Failed to get wireless interfaces", result["content"][0]["text"])

        asyncio.run(_run())

    def test_get_wireless_clients_with_exception(self) -> None:
        """Test error handling when getting wireless clients fails."""

        class _FailingWirelessService:
            async def get_wireless_clients(self, device_id: str):
                raise RuntimeError("Failed to get wireless clients")

        async def _run() -> None:
            with (
                patch.object(
                    wireless_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(wireless_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    wireless_tools,
                    "WirelessService",
                    lambda *args, **kwargs: _FailingWirelessService(),
                ),
                patch.object(wireless_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_wireless_tools()

                tool = mcp.tools["get_wireless_clients"]
                result = await tool(device_id="dev-lab-01")

                # Verify error response
                self.assertTrue(result["isError"])
                self.assertIn("Failed to get wireless clients", result["content"][0]["text"])

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
