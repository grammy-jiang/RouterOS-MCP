from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import firewall_logs as fw_module
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


class FakeDevice:
    def __init__(self, env="lab"):
        self.environment = env
        self.allow_advanced_writes = True
        self.allow_professional_workflows = True


class FakeDeviceService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def get_device(self, device_id):
        return FakeDevice()


class FakeFirewallLogsService:
    def __init__(self, *_args, **_kwargs):
        self.calls = []

    async def list_filter_rules(self, device_id):
        self.calls.append(("filter", device_id))
        return [{"id": "1", "chain": "input"}]

    async def list_nat_rules(self, device_id):
        self.calls.append(("nat", device_id))
        return [{"id": "2", "chain": "dstnat"}]

    async def list_address_lists(self, device_id, list_name=None):
        self.calls.append(("addr", device_id, list_name))
        return [{"id": "a1", "list": list_name or "all"}]

    async def get_recent_logs(
        self,
        device_id,
        limit=100,
        topics=None,
        start_time=None,
        end_time=None,
        message=None,
    ):
        self.calls.append(("logs", limit, topics))
        return [{"message": "ok"}], 1

    async def get_logging_config(self, device_id):
        self.calls.append(("config", device_id))
        return [{"id": "1", "topics": ["system"], "action": "memory"}]


class FakeSession:
    def session(self):
        class Ctx:
            async def __aenter__(self):
                return None

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return Ctx()


class TestMCPToolsFirewallLogsExtra(unittest.TestCase):
    def _register_tools(self) -> tuple[DummyMCP, Settings]:
        mcp = DummyMCP()
        settings = Settings()
        fw_module.register_firewall_logs_tools(mcp, settings)
        return mcp, settings

    def _common_patch(self, service: FakeFirewallLogsService):
        return [
            patch.object(fw_module, "get_session_factory", return_value=FakeSessionFactory()),
            patch.object(fw_module, "DeviceService", FakeDeviceService),
            patch.object(fw_module, "FirewallLogsService", lambda *a, **k: service),
            patch.object(fw_module, "check_tool_authorization", lambda **_kwargs: None),
        ]

    def test_list_filter_rules_tool(self) -> None:
        async def _run() -> None:
            service = FakeFirewallLogsService()
            patches = self._common_patch(service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp, _ = self._register_tools()
                fn = mcp.tools["list_firewall_filter_rules"]
                result = await fn("dev1")
                self.assertEqual(1, result["_meta"]["total_count"])

        asyncio.run(_run())

    def test_list_nat_rules_tool(self) -> None:
        async def _run() -> None:
            service = FakeFirewallLogsService()
            patches = self._common_patch(service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp, _ = self._register_tools()
                fn = mcp.tools["list_firewall_nat_rules"]
                result = await fn("dev1")
                self.assertEqual("dstnat", result["_meta"]["nat_rules"][0]["chain"])

        asyncio.run(_run())

    def test_list_address_lists_tool(self) -> None:
        async def _run() -> None:
            service = FakeFirewallLogsService()
            patches = self._common_patch(service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp, _ = self._register_tools()
                fn = mcp.tools["list_firewall_address_lists"]
                result = await fn("dev1", list_name="mcp-list")
                self.assertEqual("mcp-list", result["_meta"]["address_lists"][0]["list"])

        asyncio.run(_run())

    def test_get_recent_logs_tool(self) -> None:
        async def _run() -> None:
            service = FakeFirewallLogsService()
            patches = self._common_patch(service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp, _ = self._register_tools()
                fn = mcp.tools["get_recent_logs"]
                result = await fn("dev1", limit=5, topics=["firewall"])
                self.assertEqual("ok", result["_meta"]["log_entries"][0]["message"])

        asyncio.run(_run())

    def test_get_logging_config(self) -> None:
        async def _run() -> None:
            service = FakeFirewallLogsService()
            patches = self._common_patch(service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp, _ = self._register_tools()
                fn = mcp.tools["get_logging_config"]
                result = await fn("dev1")
                self.assertEqual(1, result["_meta"]["total_count"])

        asyncio.run(_run())

    def test_list_address_lists_all(self) -> None:
        async def _run() -> None:
            service = FakeFirewallLogsService()
            patches = self._common_patch(service)
            with patches[0], patches[1], patches[2], patches[3]:
                mcp, _ = self._register_tools()
                fn = mcp.tools["list_firewall_address_lists"]
                result = await fn("dev1")
                self.assertEqual("all", result["_meta"]["address_lists"][0]["list"])

        asyncio.run(_run())

    def test_firewall_tool_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.mcp.errors import MCPError

            async def boom(*_args, **_kwargs):
                raise MCPError("fail", data={"detail": "x"})

            with (
                patch.object(fw_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(fw_module, "DeviceService", FakeDeviceService),
                patch.object(fw_module.FirewallLogsService, "list_filter_rules", boom),
                patch.object(fw_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["list_firewall_filter_rules"]
                result = await fn("dev1")
                self.assertTrue(result["isError"])
                self.assertEqual("x", result["_meta"]["detail"])

        asyncio.run(_run())

    def test_firewall_filter_rules_generic_error(self) -> None:
        async def _run() -> None:
            async def boom(*_args, **_kwargs):
                raise RuntimeError("explode")

            with (
                patch.object(fw_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(fw_module, "DeviceService", FakeDeviceService),
                patch.object(fw_module.FirewallLogsService, "list_filter_rules", boom),
                patch.object(fw_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["list_firewall_filter_rules"]
                result = await fn("dev1")
                self.assertTrue(result["isError"])
                self.assertEqual("RuntimeError", result["_meta"]["original_error"])

        asyncio.run(_run())

    def test_nat_rules_generic_error(self) -> None:
        async def _run() -> None:
            async def boom(*_args, **_kwargs):
                raise ValueError("bad nat")

            with (
                patch.object(fw_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(fw_module, "DeviceService", FakeDeviceService),
                patch.object(fw_module.FirewallLogsService, "list_nat_rules", boom),
                patch.object(fw_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["list_firewall_nat_rules"]
                result = await fn("dev1")
                self.assertTrue(result["isError"])
                self.assertEqual("bad nat", result["content"][0]["text"])

        asyncio.run(_run())

    def test_address_lists_generic_error(self) -> None:
        async def _run() -> None:
            async def boom(*_args, **_kwargs):
                raise RuntimeError("addr fail")

            with (
                patch.object(fw_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(fw_module, "DeviceService", FakeDeviceService),
                patch.object(fw_module.FirewallLogsService, "list_address_lists", boom),
                patch.object(fw_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["list_firewall_address_lists"]
                result = await fn("dev1")
                self.assertTrue(result["isError"])
                self.assertEqual("RuntimeError", result["_meta"]["original_error"])

        asyncio.run(_run())

    def test_recent_logs_mcp_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.mcp.errors import MCPError

            async def boom(*_args, **_kwargs):
                raise MCPError("nope", data={"context": "logs"})

            with (
                patch.object(fw_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(fw_module, "DeviceService", FakeDeviceService),
                patch.object(fw_module.FirewallLogsService, "get_recent_logs", boom),
                patch.object(fw_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["get_recent_logs"]
                result = await fn("dev1")
                self.assertTrue(result["isError"])
                self.assertEqual("logs", result["_meta"]["context"])

        asyncio.run(_run())

    def test_logging_config_mcp_error(self) -> None:
        async def _run() -> None:
            from routeros_mcp.mcp.errors import MCPError

            async def boom(*_args, **_kwargs):
                raise MCPError("log cfg", data={"step": "config"})

            with (
                patch.object(fw_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(fw_module, "DeviceService", FakeDeviceService),
                patch.object(fw_module.FirewallLogsService, "get_logging_config", boom),
                patch.object(fw_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["get_logging_config"]
                result = await fn("dev1")
                self.assertTrue(result["isError"])
                self.assertEqual("config", result["_meta"]["step"])

        asyncio.run(_run())

    def test_logging_config_generic_error(self) -> None:
        async def _run() -> None:
            async def boom(*_args, **_kwargs):
                raise RuntimeError("cfg blow up")

            with (
                patch.object(fw_module, "get_session_factory", return_value=FakeSessionFactory()),
                patch.object(fw_module, "DeviceService", FakeDeviceService),
                patch.object(fw_module.FirewallLogsService, "get_logging_config", boom),
                patch.object(fw_module, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp, _ = self._register_tools()
                fn = mcp.tools["get_logging_config"]
                result = await fn("dev1")
                self.assertTrue(result["isError"])
                self.assertEqual("RuntimeError", result["_meta"]["original_error"])

        asyncio.run(_run())
