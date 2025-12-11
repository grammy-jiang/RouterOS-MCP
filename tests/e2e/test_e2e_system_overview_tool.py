from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.domain.services import system as system_module
from routeros_mcp.mcp_tools import system as system_tools

from .e2e_test_utils import DummyMCP, FakeSessionFactory


class _FakeRestClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.closed = False

    async def get(self, path: str):
        self.calls.append(path)
        if path == "/rest/system/resource":
            return {
                "cpu-load": 12.5,
                "cpu-count": 4,
                "total-memory": 1024 * 1024 * 1024,
                "free-memory": 512 * 1024 * 1024,
                "uptime": "1d1h",
                "version": "7.10",
                "board-name": "RB5009",
                "architecture-name": "arm64",
            }
        if path == "/rest/system/identity":
            return {"name": "router-lab-01"}
        return {}

    async def close(self):
        self.closed = True


class _FakeDevice:
    def __init__(self) -> None:
        self.id = "dev-lab-01"
        self.name = "router-lab-01"
        self.environment = "lab"
        self.system_identity = "router-lab-01"
        self.allow_advanced_writes = True
        self.allow_professional_workflows = False


class _FakeDeviceService:
    """Fake DeviceService that bypasses the real DB and RouterOS client."""

    last_client: _FakeRestClient | None = None

    def __init__(self, *_args, **_kwargs) -> None:
        self.device = _FakeDevice()
        self.client = _FakeRestClient()
        _FakeDeviceService.last_client = self.client

    async def get_device(self, device_id: str):
        # Ignore device_id for this fake; always return the same device
        return self.device

    async def get_rest_client(self, device_id: str):
        return self.client


class TestE2ESystemOverviewTool(unittest.TestCase):
    def test_system_get_overview_from_mcp_tool(self) -> None:
        """End-to-end style test for system/get-overview via MCP tool.

        This patches the DB session factory and DeviceService/RouterOS client,
        then calls the MCP tool as a client would and asserts on the output.
        """

        async def _run() -> None:
            with (
                patch.object(
                    system_tools, "get_session_factory", return_value=FakeSessionFactory()
                ),
                patch.object(system_tools, "DeviceService", _FakeDeviceService),
                patch.object(system_tools, "check_tool_authorization", lambda **_kwargs: None),
                patch.object(system_module, "DeviceService", _FakeDeviceService),
            ):
                mcp = DummyMCP()
                settings = Settings()
                system_tools.register_system_tools(mcp, settings)

                fn = mcp.tools["get_system_overview"]
                result = await fn("dev-lab-01")  # type: ignore[func-returns-value]

                self.assertFalse(result["isError"])
                self.assertIn("Device: router-lab-01", result["content"][0]["text"])
                self.assertEqual("7.10", result["_meta"]["routeros_version"])
                self.assertEqual("RB5009", result["_meta"]["hardware_model"])
                self.assertEqual(12.5, result["_meta"]["cpu_usage_percent"])

                client = _FakeDeviceService.last_client
                self.assertIsNotNone(client)
                # At this point client is guaranteed non-None by the assertion above
                if client is not None:
                    self.assertIn("/rest/system/resource", client.calls)
                    self.assertIn("/rest/system/identity", client.calls)
                    self.assertTrue(client.closed)

        asyncio.run(_run())
