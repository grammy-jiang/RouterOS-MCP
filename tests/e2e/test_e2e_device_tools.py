from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import device as device_tools

from .e2e_test_utils import DummyMCP, FakeSessionFactory


class _FakeDevice:
    def __init__(
        self,
        device_id: str,
        name: str,
        environment: str,
        tags: dict[str, str],
    ) -> None:
        self.id = device_id
        self.name = name
        self.management_address = "192.0.2.1:443"
        self.environment = environment
        self.status = "healthy"
        self.routeros_version = "7.10"
        self.hardware_model = "RB5009"
        self.tags = tags
        self.allow_advanced_writes = True
        self.allow_professional_workflows = False


class _FakeDeviceService:
    """Fake DeviceService that bypasses the real DB and RouterOS client."""

    last_checked_ids: list[str] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.devices = [
            _FakeDevice("dev-lab-01", "router-lab-01", "lab", {"site": "dc1", "role": "edge"}),
            _FakeDevice("dev-lab-02", "router-lab-02", "lab", {"site": "dc2", "role": "core"}),
        ]

    async def list_devices(self, environment: str | None = None, status: str | None = None):
        result = self.devices
        if environment is not None:
            result = [d for d in result if d.environment == environment]
        if status is not None:
            result = [d for d in result if d.status == status]
        return result

    async def get_device(self, device_id: str):
        for d in self.devices:
            if d.id == device_id:
                return d
        # For connectivity checks we treat unknown IDs as existing but separate devices
        return _FakeDevice(device_id, f"router-{device_id}", "lab", {"site": "dc3"})

    async def check_connectivity(self, device_id: str) -> bool:
        self.__class__.last_checked_ids.append(device_id)
        # Simulate one reachable and one unreachable device
        return device_id != "dev-unreachable"


class TestE2EDeviceTools(unittest.TestCase):
    def _register_tools(self) -> tuple[DummyMCP, Settings]:
        mcp = DummyMCP()
        settings = Settings()
        device_tools.register_device_tools(mcp, settings)
        return mcp, settings

    def test_list_devices_and_tag_filtering(self) -> None:
        async def _run() -> None:
            with (
                patch.object(
                    device_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(device_tools, "DeviceService", _FakeDeviceService),
            ):
                mcp, _ = self._register_tools()
                list_fn = mcp.tools["list_devices"]

                result_all = await list_fn()
                self.assertFalse(result_all["isError"])
                self.assertEqual(2, result_all["_meta"]["total_count"])

                # Filter by environment and tags – should narrow to a single device
                result_filtered = await list_fn(environment="lab", tags={"site": "dc1"})
                self.assertFalse(result_filtered["isError"])
                self.assertEqual(1, result_filtered["_meta"]["total_count"])
                self.assertEqual(
                    "dev-lab-01",
                    result_filtered["_meta"]["devices"][0]["id"],
                )

        asyncio.run(_run())

    def test_check_connectivity_success_and_failure(self) -> None:
        async def _run() -> None:
            _FakeDeviceService.last_checked_ids.clear()
            with (
                patch.object(
                    device_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(device_tools, "DeviceService", _FakeDeviceService),
                patch.object(device_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                check_fn = mcp.tools["check_connectivity"]

                ok = await check_fn("dev-lab-01")
                self.assertFalse(ok["isError"])
                self.assertTrue(ok["_meta"]["reachable"])

                bad = await check_fn("dev-unreachable")
                self.assertTrue(bad["isError"])
                self.assertFalse(bad["_meta"]["reachable"])

                self.assertEqual(
                    ["dev-lab-01", "dev-unreachable"],
                    _FakeDeviceService.last_checked_ids,
                )

        asyncio.run(_run())

    def test_list_devices_error_from_service(self) -> None:
        async def _run() -> None:
            class _ErrorDeviceService:
                def __init__(self, *_args, **_kwargs) -> None:
                    pass

                async def list_devices(
                    self,
                    environment: str | None = None,
                    status: str | None = None,
                ):
                    raise ValueError("list-devices failed in e2e")

            with (
                patch.object(
                    device_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(device_tools, "DeviceService", _ErrorDeviceService),
            ):
                mcp, _ = self._register_tools()
                list_fn = mcp.tools["list_devices"]

                result = await list_fn()
                self.assertTrue(result["isError"])
                self.assertIn("list-devices failed in e2e", result["content"][0]["text"])

        asyncio.run(_run())

    def test_check_connectivity_authorization_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.mcp.errors import AuthorizationError

            def _raise_auth_error(
                *args,
                **kwargs,
            ):
                raise AuthorizationError(
                    "authorization denied in e2e",
                    data={"reason": "test-e2e"},
                )

            with (
                patch.object(
                    device_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(device_tools, "DeviceService", _FakeDeviceService),
                patch.object(device_tools, "check_tool_authorization", _raise_auth_error),
            ):
                mcp, _ = self._register_tools()
                check_fn = mcp.tools["check_connectivity"]

                result = await check_fn("dev-lab-01")
                self.assertTrue(result["isError"])
                self.assertEqual("authorization denied in e2e", result["content"][0]["text"])
                self.assertEqual("test-e2e", result["_meta"]["reason"])

        asyncio.run(_run())
