from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp.errors import MCPError
from routeros_mcp.mcp_tools import device as device_tools
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


class _FakeDeviceService:
    def __init__(self, reachable: bool = True, raise_error: bool = False) -> None:
        self.reachable = reachable
        self.raise_error = raise_error
        self.device = SimpleNamespace(
            id="dev-1",
            name="router-1",
            environment="lab",
            routeros_version="7.15",
            management_ip="10.0.0.1",
            management_port=443,
            status="healthy",
            hardware_model="rb5009",
            allow_advanced_writes=True,
            allow_professional_workflows=True,
            tags={"role": "edge"},
        )

    async def list_devices(self, environment: str | None = None):
        devices = [
            self.device,
            SimpleNamespace(
                id="dev-2",
                name="router-2",
                environment="lab",
                routeros_version="7.14",
                management_ip="10.0.0.2",
                management_port=443,
                status="warning",
                hardware_model="rb4011",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                tags={"role": "core"},
            ),
        ]
        if environment:
            devices = [d for d in devices if d.environment == environment]
        return devices

    async def get_device(self, device_id: str):
        if self.raise_error:
            raise MCPError(code=-32000, message="not found", data={"device_id": device_id})
        return self.device

    async def check_connectivity(self, device_id: str):
        if self.raise_error:
            raise ValueError("connectivity error")
        return self.reachable, {
            "failure_reason": None if self.reachable else "timeout",
            "transport": "rest" if self.reachable else "ssh",
            "fallback_used": not self.reachable,
            "attempted_transports": ["rest"] if self.reachable else ["rest", "ssh"],
        }


class TestMCPToolsDevice(unittest.TestCase):
    def _register_tools(self, fake_service: _FakeDeviceService) -> DummyMCP:
        mcp = DummyMCP()
        settings = Settings()
        device_tools.register_device_tools(mcp, settings)
        return mcp

    def test_list_devices_filters_by_tags(self) -> None:
        async def _run() -> None:
            fake_service = _FakeDeviceService()
            with (
                patch.object(
                    device_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(device_tools, "DeviceService", lambda *args, **kwargs: fake_service),
                patch.object(
                    device_tools, "check_tool_authorization", lambda *args, **kwargs: None
                ),
            ):
                mcp = self._register_tools(fake_service)
                result = await mcp.tools["list_devices"](tags={"role": "edge"})
                self.assertEqual(1, result["_meta"]["total_count"])
                self.assertEqual("dev-1", result["_meta"]["devices"][0]["id"])

        asyncio.run(_run())

    def test_check_connectivity_success(self) -> None:
        async def _run() -> None:
            fake_service = _FakeDeviceService()
            with (
                patch.object(
                    device_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(device_tools, "DeviceService", lambda *args, **kwargs: fake_service),
                patch.object(
                    device_tools, "check_tool_authorization", lambda *args, **kwargs: None
                ),
            ):
                mcp = self._register_tools(fake_service)
                result = await mcp.tools["check_connectivity"]("dev-1")
                self.assertTrue(result["_meta"]["reachable"])
                self.assertFalse(result["isError"])
                self.assertIsNone(result["_meta"]["failure_reason"])
                self.assertEqual("rest", result["_meta"]["transport"])

        asyncio.run(_run())

    def test_check_connectivity_unreachable(self) -> None:
        async def _run() -> None:
            fake_service = _FakeDeviceService(reachable=False)
            with (
                patch.object(
                    device_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(device_tools, "DeviceService", lambda *args, **kwargs: fake_service),
                patch.object(
                    device_tools, "check_tool_authorization", lambda *args, **kwargs: None
                ),
            ):
                mcp = self._register_tools(fake_service)
                result = await mcp.tools["check_connectivity"]("dev-1")
                self.assertTrue(result["isError"])
                self.assertFalse(result["_meta"]["reachable"])
                self.assertEqual("timeout", result["_meta"]["failure_reason"])
                self.assertEqual("ssh", result["_meta"]["transport"])

        asyncio.run(_run())

    def test_check_connectivity_exception(self) -> None:
        async def _run() -> None:
            fake_service = _FakeDeviceService(raise_error=True)
            with (
                patch.object(
                    device_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(device_tools, "DeviceService", lambda *args, **kwargs: fake_service),
                patch.object(
                    device_tools, "check_tool_authorization", lambda *args, **kwargs: None
                ),
            ):
                mcp = self._register_tools(fake_service)
                result = await mcp.tools["check_connectivity"]("dev-unknown")
                self.assertTrue(result["isError"])
                self.assertEqual("dev-unknown", result["_meta"]["device_id"])

        asyncio.run(_run())
