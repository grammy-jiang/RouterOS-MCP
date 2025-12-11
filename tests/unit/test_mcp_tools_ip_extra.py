from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import ip as ip_module
from unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


class FakeDevice:
    def __init__(self):
        self.environment = "lab"
        self.allow_advanced_writes = True
        self.allow_professional_workflows = True
        self.name = "dev"
        self.routeros_version = "7"


class FakeDeviceService:
    def __init__(self, *_args, **_kwargs):
        self.calls = []

    async def get_device(self, device_id):
        self.calls.append(device_id)
        return FakeDevice()

    async def check_connectivity(self, device_id):
        self.calls.append(("connect", device_id))
        return True

    async def list_devices(self, environment=None):
        return [FakeDevice()]


class FakeIPService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def list_addresses(self, device_id):
        return [{"address": "10.0.0.1/24", "interface": "eth1"}]

    async def get_address(self, device_id, address_id):
        return {"address": "10.0.0.1/24", "interface": "eth1"}

    async def get_arp_table(self, device_id):
        return [{"address": "10.0.0.2", "mac": "aa:bb"}]

    async def add_secondary_address(self, device_id, address, interface, comment, dry_run):
        if dry_run:
            return {
                "planned_changes": {"address": address, "interface": interface},
                "dry_run": True,
            }
        return {"address": address, "interface": interface, "changed": True}

    async def remove_secondary_address(self, device_id, address_id, dry_run):
        if dry_run:
            return {
                "planned_changes": {"address": "10.0.0.1/24", "interface": "eth1"},
                "dry_run": True,
            }
        return {"address": "10.0.0.1/24", "interface": "eth1", "changed": True}


class FakeSession:
    def session(self):
        class Ctx:
            async def __aenter__(self):
                return None

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return Ctx()


class TestMCPToolsIPExtra(unittest.TestCase):
    def _register_tools(self) -> tuple[DummyMCP, Settings]:
        mcp = DummyMCP()
        settings = Settings()
        ip_module.register_ip_tools(mcp, settings)
        return mcp, settings

    def test_list_addresses_tool(self) -> None:
        async def _run() -> None:
            fake_device_service = FakeDeviceService()
            fake_ip_service = FakeIPService()
            with (
                patch.object(ip_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_module, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_module, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["list_ip_addresses"]
                result = await fn("dev1")
                self.assertEqual(1, result["_meta"]["total_count"])

        asyncio.run(_run())

    def test_get_ip_address_tool(self) -> None:
        async def _run() -> None:
            fake_device_service = FakeDeviceService()
            fake_ip_service = FakeIPService()
            with (
                patch.object(ip_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_module, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_module, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["get_ip_address"]
                result = await fn("dev1", "*1")
                self.assertEqual("eth1", result["_meta"]["address"]["interface"])

        asyncio.run(_run())

    def test_get_arp_table_tool(self) -> None:
        async def _run() -> None:
            fake_device_service = FakeDeviceService()
            fake_ip_service = FakeIPService()
            with (
                patch.object(ip_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_module, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_module, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["get_arp_table"]
                result = await fn("dev1")
                self.assertEqual(1, result["_meta"]["total_count"])

        asyncio.run(_run())

    def test_add_secondary_ip_dry_run(self) -> None:
        async def _run() -> None:
            fake_device_service = FakeDeviceService()
            fake_ip_service = FakeIPService()
            with (
                patch.object(ip_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_module, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_module, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["add_secondary_ip_address"]
                result = await fn("dev1", "10.0.0.2/24", "eth1", dry_run=True)
                self.assertTrue(result["_meta"]["dry_run"])

        asyncio.run(_run())

    def test_remove_secondary_ip_apply(self) -> None:
        async def _run() -> None:
            fake_device_service = FakeDeviceService()
            fake_ip_service = FakeIPService()
            with (
                patch.object(ip_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(
                    ip_module, "DeviceService", lambda *args, **kwargs: fake_device_service
                ),
                patch.object(ip_module, "IPService", lambda *args, **kwargs: fake_ip_service),
                patch.object(ip_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["remove_secondary_ip_address"]
                result = await fn("dev1", "*2", dry_run=False)
                self.assertTrue(result["_meta"]["changed"])

        asyncio.run(_run())
