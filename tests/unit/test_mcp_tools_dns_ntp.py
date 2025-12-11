from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import dns_ntp as dns_ntp_module
from unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


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


class FakeDNSNTPService:
    async def get_dns_status(self, device_id: str):
        return {
            "dns_servers": ["1.1.1.1"],
            "allow_remote_requests": True,
            "cache_size_kb": 10,
            "cache_used_kb": 1,
        }

    async def get_dns_cache(self, device_id: str, limit: int):
        return ([{"name": "example.com", "type": "A", "data": "1.1.1.1", "ttl": 60}], 1)

    async def get_ntp_status(self, device_id: str):
        return {
            "status": "synchronized",
            "stratum": 1,
            "offset_ms": 0.1,
            "ntp_servers": ["pool"],
        }

    async def update_dns_servers(self, device_id: str, servers, dry_run: bool = False):
        if dry_run:
            return {
                "changed": False,
                "planned_changes": {
                    "old_servers": ["1.1.1.1"],
                    "new_servers": servers,
                },
                "dry_run": True,
                "new_servers": servers,
            }
        return {
            "changed": True,
            "servers": servers,
            "new_servers": servers,
            "old_servers": [],
            "dry_run": False,
        }

    async def update_ntp_servers(
        self, device_id: str, servers, enabled: bool = True, dry_run: bool = False
    ):
        if dry_run:
            return {
                "changed": False,
                "planned_changes": {
                    "old_servers": ["pool"],
                    "new_servers": servers,
                    "old_enabled": True,
                    "new_enabled": enabled,
                },
                "dry_run": True,
                "new_servers": servers,
                "enabled": enabled,
            }
        return {
            "changed": True,
            "servers": servers,
            "new_servers": servers,
            "old_servers": ["pool"],
            "enabled": enabled,
            "dry_run": False,
        }

    async def flush_dns_cache(self, device_id: str):
        return {"changed": True, "entries_flushed": 1}


class TestMCPToolsDNSNTP(unittest.TestCase):
    def _register_tools(self) -> DummyMCP:
        mcp = DummyMCP()
        settings = Settings()
        dns_ntp_module.register_dns_ntp_tools(mcp, settings)
        return mcp

    def _patch_common(self, fake_service: object | None = None):
        if fake_service is None:
            fake_service = FakeDNSNTPService()

    def test_get_dns_status_tool(self) -> None:
        async def _run() -> None:
            fake_service = FakeDNSNTPService()
            with (
                patch.object(
                    dns_ntp_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(
                    dns_ntp_module,
                    "DNSNTPService",
                    lambda *args, **kwargs: fake_service,
                ),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["get_dns_status"]
                result = await fn("dev1")
                self.assertTrue(result["content"])
                self.assertEqual(["1.1.1.1"], result["_meta"]["dns_servers"])

        asyncio.run(_run())

    def test_get_dns_cache_tool(self) -> None:
        async def _run() -> None:
            fake_service = FakeDNSNTPService()
            with (
                patch.object(
                    dns_ntp_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(
                    dns_ntp_module,
                    "DNSNTPService",
                    lambda *args, **kwargs: fake_service,
                ),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["get_dns_cache"]
                result = await fn("dev1", 5)
                self.assertEqual(1, result["_meta"]["total_count"])

        asyncio.run(_run())

    def test_update_dns_servers_tool(self) -> None:
        async def _run() -> None:
            fake_service = FakeDNSNTPService()
            with (
                patch.object(
                    dns_ntp_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(
                    dns_ntp_module,
                    "DNSNTPService",
                    lambda *args, **kwargs: fake_service,
                ),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["update_dns_servers"]
                result = await fn("dev1", ["8.8.8.8"], dry_run=True)
                self.assertTrue(result["_meta"]["dry_run"])
                self.assertEqual(["8.8.8.8"], result["_meta"]["planned_changes"]["new_servers"])

        asyncio.run(_run())

    def test_update_ntp_servers_tool(self) -> None:
        async def _run() -> None:
            fake_service = FakeDNSNTPService()
            with (
                patch.object(
                    dns_ntp_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(
                    dns_ntp_module,
                    "DNSNTPService",
                    lambda *args, **kwargs: fake_service,
                ),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["update_ntp_servers"]
                result = await fn("dev1", ["time.google.com"], enabled=True, dry_run=False)
                self.assertTrue(result["_meta"]["changed"])

        asyncio.run(_run())

    def test_flush_dns_cache_tool(self) -> None:
        async def _run() -> None:
            fake_service = FakeDNSNTPService()
            with (
                patch.object(
                    dns_ntp_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(
                    dns_ntp_module,
                    "DNSNTPService",
                    lambda *args, **kwargs: fake_service,
                ),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["flush_dns_cache"]
                result = await fn("dev1")
                self.assertTrue(result["_meta"]["changed"])

        asyncio.run(_run())

    def test_get_ntp_status_tool(self) -> None:
        async def _run() -> None:
            fake_service = FakeDNSNTPService()
            with (
                patch.object(
                    dns_ntp_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(
                    dns_ntp_module,
                    "DNSNTPService",
                    lambda *args, **kwargs: fake_service,
                ),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["get_ntp_status"]
                result = await fn("dev1")
                self.assertIn("synchronized", result["content"][0]["text"])

        asyncio.run(_run())

    def test_get_dns_status_tool_mcp_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.mcp.errors import MCPError

            async def raise_mcp(*_args, **_kwargs):
                raise MCPError("boom", data={"detail": "test"})

            with (
                patch.object(
                    dns_ntp_module, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(dns_ntp_module.DNSNTPService, "get_dns_status", raise_mcp),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["get_dns_status"]
                result = await fn("dev1")
                self.assertTrue(result["isError"])
                self.assertEqual("test", result["_meta"]["detail"])

        asyncio.run(_run())

    def test_get_ntp_status_tool_exception(self) -> None:
        async def _run() -> None:
            async def raise_exc(*_args, **_kwargs):
                raise ValueError("bad")

            with (
                patch.object(
                    dns_ntp_module, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(dns_ntp_module.DNSNTPService, "get_ntp_status", raise_exc),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["get_ntp_status"]
                result = await fn("dev1")
                self.assertTrue(result["isError"])
                self.assertIn("bad", result["content"][0]["text"])

        asyncio.run(_run())

    def test_update_ntp_servers_tool_dry_run(self) -> None:
        async def _run() -> None:
            async def fake_dry_run(*_args, **_kwargs):
                return {
                    "changed": False,
                    "planned_changes": {
                        "old_servers": ["pool"],
                        "new_servers": ["time.example"],
                        "old_enabled": True,
                        "new_enabled": False,
                    },
                    "dry_run": True,
                    "new_servers": ["time.example"],
                    "enabled": False,
                }

            with (
                patch.object(
                    dns_ntp_module, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(dns_ntp_module.DNSNTPService, "update_ntp_servers", fake_dry_run),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["update_ntp_servers"]
                result = await fn("dev1", ["time.example"], enabled=False, dry_run=True)
                self.assertTrue(result["_meta"]["dry_run"])
                self.assertEqual(
                    ["time.example"], result["_meta"]["planned_changes"]["new_servers"]
                )

        asyncio.run(_run())

    def test_get_ntp_status_tool_not_synchronized(self) -> None:
        async def _run() -> None:
            async def not_sync(*_args, **_kwargs):
                return {"status": "not synchronized", "ntp_servers": ["a"], "mode": "unicast"}

            with (
                patch.object(
                    dns_ntp_module, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(dns_ntp_module.DNSNTPService, "get_ntp_status", not_sync),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["get_ntp_status"]
                result = await fn("dev1")
                self.assertIn("not synchronized", result["content"][0]["text"])

        asyncio.run(_run())

    def test_update_dns_servers_tool_no_change(self) -> None:
        async def _run() -> None:
            async def no_change(*_args, **_kwargs):
                return {
                    "changed": False,
                    "new_servers": ["1.1.1.1"],
                    "old_servers": ["1.1.1.1"],
                }

            with (
                patch.object(
                    dns_ntp_module, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(dns_ntp_module.DNSNTPService, "update_dns_servers", no_change),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["update_dns_servers"]
                result = await fn("dev1", ["1.1.1.1"], dry_run=False)
                self.assertIn("already set", result["content"][0]["text"])

        asyncio.run(_run())

    def test_update_ntp_servers_tool_no_change(self) -> None:
        async def _run() -> None:
            async def no_change(*_args, **_kwargs):
                return {
                    "changed": False,
                    "new_servers": ["time.google.com"],
                    "old_servers": ["time.google.com"],
                    "enabled": True,
                }

            with (
                patch.object(
                    dns_ntp_module, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(dns_ntp_module.DNSNTPService, "update_ntp_servers", no_change),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["update_ntp_servers"]
                result = await fn("dev1", ["time.google.com"], enabled=True, dry_run=False)
                self.assertIn("no change", result["content"][0]["text"])

        asyncio.run(_run())

    def test_get_dns_cache_error(self) -> None:
        async def _run() -> None:
            async def boom(*_args, **_kwargs):
                raise ValueError("cache failed")

            with (
                patch.object(
                    dns_ntp_module, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(dns_ntp_module, "DeviceService", FakeDeviceService),
                patch.object(dns_ntp_module.DNSNTPService, "get_dns_cache", boom),
                patch.object(dns_ntp_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["get_dns_cache"]
                result = await fn("dev1", 1)
                self.assertTrue(result["isError"])

        asyncio.run(_run())
