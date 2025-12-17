from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import system as system_module
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


class FakeDevice:
    def __init__(self):
        self.environment = "lab"
        self.allow_advanced_writes = True
        self.allow_professional_workflows = True


class FakeDeviceService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def get_device(self, device_id):
        return FakeDevice()

    async def get_rest_client(self, device_id):
        class Client:
            async def get(self, path):
                return {"time": "12:00:00", "date": "2025-12-13", "time-zone-name": "UTC", "time-zone-autodetect": True, "gmt-offset": "+00:00", "dst-active": False}

            async def close(self):
                return None

        return Client()


class FakeSystemService:
    def __init__(self, *_args, **_kwargs):
        self.identity = "dev"

    async def get_system_overview(self, device_id):
        return {
            "device_name": "dev",
            "system_identity": "dev",
            "routeros_version": "7",
            "hardware_model": "hEX",
            "cpu_usage_percent": 1.0,
            "cpu_count": 1,
            "memory_usage_percent": 2.0,
            "memory_used_bytes": 1024,
            "memory_total_bytes": 2048,
            "uptime_formatted": "1d",
        }

    async def get_system_packages(self, device_id):
        return [{"name": "system", "version": "7"}]

    async def get_system_clock(self, device_id):
        return {
            "time": "12:00:00",
            "date": "2025-12-13",
            "time-zone-name": "UTC",
            "time-zone-autodetect": True,
            "gmt-offset": "+00:00",
            "dst-active": False,
            "transport": "rest",
            "fallback_used": False,
            "rest_error": None,
        }

    async def update_system_identity(self, device_id, identity, dry_run=False):
        if dry_run:
            return {
                "changed": False,
                "dry_run": True,
                "planned_changes": {"old_identity": self.identity, "new_identity": identity},
            }
        if identity == self.identity:
            return {"changed": False, "old_identity": self.identity, "new_identity": self.identity}
        old = self.identity
        self.identity = identity
        return {"changed": True, "old_identity": old, "new_identity": identity}


class FakeSession:
    def session(self):
        class Ctx:
            async def __aenter__(self):
                return None

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return Ctx()


class TestMCPToolsSystemExtra(unittest.TestCase):
    def _register_tools(self) -> tuple[DummyMCP, Settings]:
        mcp = DummyMCP()
        settings = Settings()
        system_module.register_system_tools(mcp, settings)
        return mcp, settings

    def _common_patches(self, system_service: FakeSystemService | None = None):
        if system_service is None:
            system_service = FakeSystemService()
        return (
            patch.object(system_module, "get_session_factory", return_value=FakeSessionFactory()),
            patch.object(system_module, "DeviceService", FakeDeviceService),
            patch.object(system_module, "SystemService", lambda *_a, **_k: system_service),
            patch.object(system_module, "check_tool_authorization", lambda **_kwargs: None),
        )

    def test_get_system_info_tool(self) -> None:
        async def _run() -> None:
            system_service = FakeSystemService()
            patch_session, patch_device, patch_system, patch_auth = self._common_patches(
                system_service
            )
            with patch_session, patch_device, patch_system, patch_auth:
                mcp, _ = self._register_tools()
                fn = mcp.tools["get_system_overview"]
                result = await fn("dev1")
                self.assertEqual("7", result["_meta"]["routeros_version"])

        asyncio.run(_run())

    def test_get_resources_tool(self) -> None:
        async def _run() -> None:
            system_service = FakeSystemService()
            patch_session, patch_device, patch_system, patch_auth = self._common_patches(
                system_service
            )
            with patch_session, patch_device, patch_system, patch_auth:
                mcp, _ = self._register_tools()
                fn = mcp.tools["get_system_packages"]
                result = await fn("dev1")
                self.assertIn("packages", result["_meta"])

        asyncio.run(_run())

    def test_get_ip_route_tool(self) -> None:
        async def _run() -> None:
            system_service = FakeSystemService()
            patch_session, patch_device, patch_system, patch_auth = self._common_patches(
                system_service
            )
            with patch_session, patch_device, patch_system, patch_auth:
                mcp, _ = self._register_tools()
                fn = mcp.tools["get_system_clock"]
                result = await fn("dev1")
                self.assertIn("time", result["_meta"])

        asyncio.run(_run())

    def test_set_system_identity_variants(self) -> None:
        async def _run() -> None:
            system_service = FakeSystemService()
            patch_session, patch_device, patch_system, patch_auth = self._common_patches(
                system_service
            )
            with patch_session, patch_device, patch_system, patch_auth:
                mcp, _ = self._register_tools()
                fn = mcp.tools["set_system_identity"]

                dry = await fn("dev1", "new-id", dry_run=True)
                self.assertTrue(dry["_meta"]["dry_run"])

                applied = await fn("dev1", "new-id", dry_run=False)
                self.assertTrue(applied["_meta"]["changed"])

                no_change = await fn("dev1", "new-id", dry_run=False)
                self.assertFalse(no_change["_meta"]["changed"])

        asyncio.run(_run())

    def test_system_overview_mcp_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.mcp.errors import MCPError

            class BoomSystem(FakeSystemService):
                async def get_system_overview(self, *_args, **_kwargs):  # type: ignore[override]
                    raise MCPError("fail", data={"stage": "overview"})

            with (
                patch.object(
                    system_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(system_module, "DeviceService", FakeDeviceService),
                patch.object(system_module, "SystemService", lambda *_a, **_k: BoomSystem()),
                patch.object(system_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                result = await mcp.tools["get_system_overview"]("dev1")
                self.assertTrue(result["isError"])
                self.assertEqual("overview", result["_meta"]["stage"])

        asyncio.run(_run())

    def test_system_overview_with_fallback_metadata(self) -> None:
        async def _run() -> None:
            class FallbackSystem(FakeSystemService):
                async def get_system_overview(self, *_args, **_kwargs):  # type: ignore[override]
                    return {
                        "device_name": "dev",
                        "system_identity": "dev",
                        "routeros_version": "7",
                        "hardware_model": "hEX",
                        "cpu_usage_percent": 1.0,
                        "cpu_count": 1,
                        "memory_usage_percent": 2.0,
                        "memory_used_bytes": 1024,
                        "memory_total_bytes": 2048,
                        "uptime_formatted": "1d",
                        "transport": "ssh",
                        "fallback_used": True,
                        "rest_error": "timeout",
                    }

            patch_session, patch_device, patch_system, patch_auth = self._common_patches(
                FallbackSystem()
            )

            with patch_session, patch_device, patch_system, patch_auth:
                mcp, _ = self._register_tools()
                fn = mcp.tools["get_system_overview"]
                result = await fn("dev1")

                self.assertIn("Transport: ssh (REST fallback: timeout)", result["content"][0]["text"])
                self.assertTrue(result["_meta"].get("fallback_used"))
                self.assertEqual("ssh", result["_meta"].get("transport"))

        asyncio.run(_run())

    def test_system_packages_generic_error(self) -> None:
        async def _run() -> None:
            class BoomSystem(FakeSystemService):
                async def get_system_packages(self, *_args, **_kwargs):  # type: ignore[override]
                    raise RuntimeError("pkg fail")

            with (
                patch.object(
                    system_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(system_module, "DeviceService", FakeDeviceService),
                patch.object(system_module, "SystemService", lambda *_a, **_k: BoomSystem()),
                patch.object(system_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                result = await mcp.tools["get_system_packages"]("dev1")
                self.assertTrue(result["isError"])
                self.assertEqual("RuntimeError", result["_meta"]["original_error"])

        asyncio.run(_run())

    def test_system_clock_mcp_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.mcp.errors import MCPError

            class FakeSystemServiceError(FakeSystemService):
                async def get_system_clock(self, *_args, **_kwargs):  # type: ignore[override]
                    raise MCPError("clock", data={"path": "/rest/system/clock"})

            with (
                patch.object(
                    system_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(system_module, "DeviceService", FakeDeviceService),
                patch.object(system_module, "SystemService", FakeSystemServiceError),
                patch.object(system_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                result = await mcp.tools["get_system_clock"]("dev1")
                self.assertTrue(result["isError"])
                self.assertEqual("/rest/system/clock", result["_meta"]["path"])

        asyncio.run(_run())

    def test_set_system_identity_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.mcp.errors import MCPError

            class BoomSystem(FakeSystemService):
                async def update_system_identity(self, *_args, **_kwargs):  # type: ignore[override]
                    raise MCPError("id fail", data={"attempt": "set"})

            with (
                patch.object(
                    system_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(system_module, "DeviceService", FakeDeviceService),
                patch.object(system_module, "SystemService", lambda *_a, **_k: BoomSystem()),
                patch.object(system_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                result = await mcp.tools["set_system_identity"]("dev1", "id")
                self.assertTrue(result["isError"])
                self.assertEqual("set", result["_meta"]["attempt"])

        asyncio.run(_run())
