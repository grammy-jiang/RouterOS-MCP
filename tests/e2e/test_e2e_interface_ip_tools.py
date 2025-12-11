from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import interface as interface_tools
from routeros_mcp.mcp_tools import ip as ip_tools

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


class _FakeInterfaceService:
    async def list_interfaces(self, device_id: str):
        return [
            {
                "id": "*1",
                "name": "ether1",
                "type": "ether",
                "running": True,
                "disabled": False,
                "comment": "WAN",
                "mtu": 1500,
                "mac_address": "00:11:22:33:44:55",
            },
            {
                "id": "*2",
                "name": "bridge1",
                "type": "bridge",
                "running": True,
                "disabled": False,
                "comment": "LAN",
                "mtu": 1500,
                "mac_address": "00:11:22:33:44:66",
            },
        ]

    async def get_interface(self, device_id: str, interface_id: str):
        return {
            "id": interface_id,
            "name": "ether1",
            "type": "ether",
            "running": True,
            "disabled": False,
            "comment": "WAN",
            "mtu": 1500,
            "mac_address": "00:11:22:33:44:55",
            "last_link_up_time": "2025-01-01T00:00:00Z",
        }

    async def get_interface_stats(self, device_id: str, interface_names: list[str] | None = None):
        stats = [
            {
                "name": "ether1",
                "rx_bits_per_second": 1000,
                "tx_bits_per_second": 2000,
                "rx_packets_per_second": 10,
                "tx_packets_per_second": 20,
            },
            {
                "name": "bridge1",
                "rx_bits_per_second": 500,
                "tx_bits_per_second": 750,
                "rx_packets_per_second": 5,
                "tx_packets_per_second": 7,
            },
        ]
        if interface_names:
            return [s for s in stats if s["name"] in interface_names]
        return stats


class _FakeIPService:
    async def list_addresses(self, device_id: str):
        return [
            {
                "id": "*1",
                "address": "192.0.2.1/24",
                "network": "192.0.2.0",
                "interface": "ether1",
                "disabled": False,
                "comment": "WAN IP",
                "dynamic": False,
                "invalid": False,
            }
        ]

    async def get_address(self, device_id: str, address_id: str):
        return {
            "id": address_id,
            "address": "192.0.2.1/24",
            "network": "192.0.2.0",
            "interface": "ether1",
            "disabled": False,
            "comment": "WAN IP",
            "dynamic": False,
            "invalid": False,
        }

    async def get_arp_table(self, device_id: str):
        return [
            {
                "address": "192.0.2.10",
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "interface": "ether1",
                "status": "reachable",
                "comment": "host-1",
            }
        ]


class TestE2EInterfaceIPTools(unittest.TestCase):
    def _register_interface_tools(self) -> DummyMCP:
        mcp = DummyMCP()
        settings = Settings()
        interface_tools.register_interface_tools(mcp, settings)
        return mcp

    def _register_ip_tools(self) -> DummyMCP:
        mcp = DummyMCP()
        settings = Settings()
        ip_tools.register_ip_tools(mcp, settings)
        return mcp

    def test_interface_tools_end_to_end(self) -> None:
        async def _run() -> None:
            with (
                patch.object(
                    interface_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(interface_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    interface_tools,
                    "InterfaceService",
                    lambda *args, **kwargs: _FakeInterfaceService(),
                ),
                patch.object(interface_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_interface_tools()

                list_fn = mcp.tools["list_interfaces"]
                result = await list_fn("dev-lab-01")
                self.assertFalse(result["isError"])
                self.assertEqual(2, result["_meta"]["total_count"])

                get_fn = mcp.tools["get_interface"]
                detail = await get_fn("dev-lab-01", "*1")
                self.assertEqual("ether1", detail["_meta"]["interface"]["name"])

                stats_fn = mcp.tools["get_interface_stats"]
                stats_all = await stats_fn("dev-lab-01")
                self.assertEqual(2, len(stats_all["_meta"]["stats"]))

                stats_filtered = await stats_fn("dev-lab-01", ["ether1"])
                self.assertEqual(1, len(stats_filtered["_meta"]["stats"]))
                self.assertEqual("ether1", stats_filtered["_meta"]["stats"][0]["name"])

        asyncio.run(_run())

    def test_ip_tools_end_to_end(self) -> None:
        async def _run() -> None:
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(ip_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    ip_tools,
                    "IPService",
                    lambda *args, **kwargs: _FakeIPService(),
                ),
                patch.object(ip_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_ip_tools()

                list_fn = mcp.tools["list_ip_addresses"]
                addresses = await list_fn("dev-lab-01")
                self.assertFalse(addresses["isError"])
                self.assertEqual(1, addresses["_meta"]["total_count"])

                get_fn = mcp.tools["get_ip_address"]
                addr = await get_fn("dev-lab-01", "*1")
                self.assertEqual("192.0.2.1/24", addr["_meta"]["address"]["address"])

                arp_fn = mcp.tools["get_arp_table"]
                arp = await arp_fn("dev-lab-01")
                self.assertEqual(1, arp["_meta"]["total_count"])
                self.assertEqual(
                    "192.0.2.10",
                    arp["_meta"]["arp_entries"][0]["address"],
                )

        asyncio.run(_run())

    def test_interface_tools_error_from_service(self) -> None:
        async def _run() -> None:
            class _ErrorInterfaceService:
                async def list_interfaces(self, device_id: str):
                    raise ValueError("interface list failed in e2e")

            with (
                patch.object(
                    interface_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(interface_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    interface_tools,
                    "InterfaceService",
                    lambda *args, **kwargs: _ErrorInterfaceService(),
                ),
                patch.object(interface_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_interface_tools()
                list_fn = mcp.tools["list_interfaces"]

                result = await list_fn("dev-lab-01")
                self.assertTrue(result["isError"])
                self.assertIn("interface list failed in e2e", result["content"][0]["text"])

        asyncio.run(_run())

    def test_ip_tools_routeros_network_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.infra.routeros.exceptions import RouterOSNetworkError

            class _ErrorIPService:
                async def get_arp_table(self, device_id: str):
                    raise RouterOSNetworkError("router unreachable in e2e")

            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(ip_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    ip_tools,
                    "IPService",
                    lambda *args, **kwargs: _ErrorIPService(),
                ),
                patch.object(ip_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_ip_tools()
                arp_fn = mcp.tools["get_arp_table"]

                result = await arp_fn("dev-lab-01")
                self.assertTrue(result["isError"])
                # Mapped via map_exception_to_error to DeviceUnreachableError
                self.assertEqual("router unreachable in e2e", result["content"][0]["text"])
                self.assertEqual("RouterOSNetworkError", result["_meta"]["original_error"])

        asyncio.run(_run())
