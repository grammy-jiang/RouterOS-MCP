from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import ip as ip_tools
from unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


class _FakeDeviceService:
    def __init__(self, *_args, **_kwargs) -> None:
        self.device = SimpleNamespace(
            id="dev-1",
            name="router-1",
            environment="lab",
            allow_advanced_writes=True,
            allow_professional_workflows=True,
        )

    async def get_device(self, device_id: str):
        return self.device


class _FakeIPService:
    def __init__(self, *_args, **_kwargs) -> None:
        self.raise_in: str | None = None

    async def list_addresses(self, device_id: str):
        if self.raise_in == "list":
            raise ValueError("boom")
        return [
            {"id": "*1", "address": "10.0.0.2/24", "interface": "ether1", "network": "10.0.0.0"}
        ]

    async def get_address(self, device_id: str, address_id: str):
        return {
            "id": address_id,
            "address": "10.0.0.2/24",
            "interface": "ether1",
            "network": "10.0.0.0",
        }

    async def get_arp_table(self, device_id: str):
        return [
            {
                "address": "10.0.0.3",
                "mac_address": "00:11:22:33:44:55",
                "interface": "ether1",
                "status": "complete",
            }
        ]

    async def add_secondary_address(
        self, device_id: str, address: str, interface: str, comment: str, dry_run: bool
    ):
        return {
            "changed": not dry_run,
            "dry_run": dry_run,
            "address": address,
            "interface": interface,
            "planned_changes": {"address": address, "interface": interface},
        }

    async def remove_secondary_address(self, device_id: str, address_id: str, dry_run: bool):
        return {
            "changed": not dry_run,
            "dry_run": dry_run,
            "address_id": address_id,
            "address": "10.0.0.2/24",
            "interface": "ether1",
            "planned_changes": {
                "address_id": address_id,
                "address": "10.0.0.2/24",
                "interface": "ether1",
            },
        }


class TestMCPToolsIP(unittest.TestCase):
    def _register_tools(
        self, fake_device_service: _FakeDeviceService, fake_ip_service: _FakeIPService
    ) -> DummyMCP:
        mcp = DummyMCP()
        settings = Settings()
        ip_tools.register_ip_tools(mcp, settings)
        return mcp

    def test_list_ip_addresses_success(self) -> None:
        async def _run() -> None:
            fake_device_service = _FakeDeviceService()
            fake_ip_service = _FakeIPService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, fake_ip_service)
                result = await mcp.tools["list_ip_addresses"]("dev-1")
                self.assertEqual(1, result["_meta"]["total_count"])
                self.assertEqual("10.0.0.2/24", result["_meta"]["addresses"][0]["address"])

        asyncio.run(_run())

    def test_get_ip_address_success(self) -> None:
        async def _run() -> None:
            fake_device_service = _FakeDeviceService()
            fake_ip_service = _FakeIPService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, fake_ip_service)
                result = await mcp.tools["get_ip_address"]("dev-1", "*1")
                self.assertEqual("*1", result["_meta"]["address"]["id"])

        asyncio.run(_run())

    def test_get_arp_table_success(self) -> None:
        async def _run() -> None:
            fake_device_service = _FakeDeviceService()
            fake_ip_service = _FakeIPService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, fake_ip_service)
                result = await mcp.tools["get_arp_table"]("dev-1")
                self.assertEqual(
                    "00:11:22:33:44:55",
                    result["_meta"]["arp_entries"][0]["mac_address"],
                )

        asyncio.run(_run())

    def test_add_secondary_ip_dry_run(self) -> None:
        async def _run() -> None:
            fake_device_service = _FakeDeviceService()
            fake_ip_service = _FakeIPService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, fake_ip_service)
                result = await mcp.tools["add_secondary_ip_address"](
                    "dev-1",
                    "10.0.0.5/24",
                    "ether1",
                    dry_run=True,
                )
                self.assertTrue(result["_meta"]["dry_run"])
                self.assertIn("planned_changes", result["_meta"])

        asyncio.run(_run())

    def test_add_secondary_ip_apply(self) -> None:
        async def _run() -> None:
            fake_device_service = _FakeDeviceService()
            fake_ip_service = _FakeIPService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, fake_ip_service)
                result = await mcp.tools["add_secondary_ip_address"](
                    "dev-1",
                    "10.0.0.6/24",
                    "ether1",
                    dry_run=False,
                )
                self.assertFalse(result["_meta"]["dry_run"])
                self.assertTrue(result["_meta"]["changed"])

        asyncio.run(_run())

    def test_remove_secondary_ip_apply(self) -> None:
        async def _run() -> None:
            fake_device_service = _FakeDeviceService()
            fake_ip_service = _FakeIPService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, fake_ip_service)
                result = await mcp.tools["remove_secondary_ip_address"](
                    "dev-1",
                    "*1",
                    dry_run=False,
                )
                self.assertFalse(result["_meta"]["dry_run"])
                self.assertTrue(result["_meta"]["changed"])

        asyncio.run(_run())

    def test_remove_secondary_ip_dry_run(self) -> None:
        async def _run() -> None:
            fake_device_service = _FakeDeviceService()
            fake_ip_service = _FakeIPService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, fake_ip_service)
                result = await mcp.tools["remove_secondary_ip_address"](
                    "dev-1",
                    "*1",
                    dry_run=True,
                )
                self.assertTrue(result["_meta"]["dry_run"])
                self.assertIn("planned_changes", result["_meta"])

        asyncio.run(_run())

    def test_list_ip_addresses_error_path(self) -> None:
        async def _run() -> None:
            fake_device_service = _FakeDeviceService()
            fake_ip_service = _FakeIPService()
            fake_ip_service.raise_in = "list"
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, fake_ip_service)
                result = await mcp.tools["list_ip_addresses"]("dev-1")
                self.assertTrue(result["isError"])

        asyncio.run(_run())

    def test_list_ip_addresses_mcp_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.mcp.errors import MCPError

            class BoomService(_FakeIPService):
                async def list_addresses(self, *_args, **_kwargs):
                    raise MCPError("mcp fail", data={"field": "address"})

            fake_device_service = _FakeDeviceService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", BoomService),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, _FakeIPService())
                result = await mcp.tools["list_ip_addresses"]("dev-1")
                self.assertTrue(result["isError"])
                self.assertEqual("address", result["_meta"]["field"])

        asyncio.run(_run())

    def test_get_ip_address_mcp_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.mcp.errors import MCPError

            class BoomService(_FakeIPService):
                async def get_address(self, *_args, **_kwargs):
                    raise MCPError("bad", data={"id": "*1"})

            fake_device_service = _FakeDeviceService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", BoomService),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, _FakeIPService())
                result = await mcp.tools["get_ip_address"]("dev-1", "*1")
                self.assertTrue(result["isError"])
                self.assertEqual("*1", result["_meta"]["id"])

        asyncio.run(_run())

    def test_get_arp_table_generic_error(self) -> None:
        async def _run() -> None:
            class BoomService(_FakeIPService):
                async def get_arp_table(self, *_args, **_kwargs):
                    raise RuntimeError("arp fail")

            fake_device_service = _FakeDeviceService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", BoomService),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, _FakeIPService())
                result = await mcp.tools["get_arp_table"]("dev-1")
                self.assertTrue(result["isError"])
                self.assertEqual("RuntimeError", result["_meta"]["original_error"])

        asyncio.run(_run())

    def test_add_secondary_ip_mcp_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.mcp.errors import MCPError

            class BoomService(_FakeIPService):
                async def add_secondary_address(self, *_args, **_kwargs):
                    raise MCPError("no add", data={"attempt": True})

            fake_device_service = _FakeDeviceService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", BoomService),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, _FakeIPService())
                result = await mcp.tools["add_secondary_ip_address"](
                    "dev-1",
                    "10.0.0.7/24",
                    "ether1",
                )
                self.assertTrue(result["isError"])
                self.assertTrue(result["_meta"]["attempt"])

        asyncio.run(_run())

    def test_remove_secondary_ip_generic_error(self) -> None:
        async def _run() -> None:
            class BoomService(_FakeIPService):
                async def remove_secondary_address(self, *_args, **_kwargs):
                    raise RuntimeError("remove fail")

            fake_device_service = _FakeDeviceService()
            with (
                patch.object(ip_tools, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_tools, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_tools, "IPService", BoomService),
                patch.object(ip_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_device_service, _FakeIPService())
                result = await mcp.tools["remove_secondary_ip_address"]("dev-1", "*9")
                self.assertTrue(result["isError"])
                self.assertEqual("RuntimeError", result["_meta"]["original_error"])

        asyncio.run(_run())
