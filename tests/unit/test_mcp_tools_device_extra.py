from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import device as device_module
from unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


class FakeDevice:
    def __init__(self, env="lab"):
        self.id = "dev-1"
        self.environment = env
        self.allow_advanced_writes = True
        self.allow_professional_workflows = True
        self.name = "dev"
        self.status = "up"
        self.routeros_version = "7"
        self.hardware_model = "hEX"
        self.tags = {"site": "lab"}
        self.management_address = "10.0.0.1"


class FakeDeviceService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def list_devices(self, environment=None):
        return [FakeDevice(env=environment or "lab"), FakeDevice(env="prod")]

    async def get_device(self, device_id):
        return FakeDevice()

    async def check_connectivity(self, device_id):
        return True


class FakeSession:
    def session(self):
        class Ctx:
            async def __aenter__(self):
                return None

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return Ctx()


class TestMCPToolsDeviceExtra(unittest.TestCase):
    def _register_tools(self) -> tuple[DummyMCP, Settings]:
        mcp = DummyMCP()
        settings = Settings()
        device_module.register_device_tools(mcp, settings)
        return mcp, settings

    def test_list_devices_tool_filters(self) -> None:
        async def _run() -> None:
            with (
                patch.object(
                    device_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(device_module, "DeviceService", FakeDeviceService),
                patch.object(device_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["list_devices"]
                result = await fn(environment="lab", tags={"site": "lab"})
                self.assertGreaterEqual(result["_meta"]["total_count"], 1)

        asyncio.run(_run())

    def test_check_connectivity_tool(self) -> None:
        async def _run() -> None:
            with (
                patch.object(
                    device_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(device_module, "DeviceService", FakeDeviceService),
                patch.object(device_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["check_connectivity"]
                result = await fn("dev1")
                self.assertTrue(result["_meta"]["reachable"])

        asyncio.run(_run())
