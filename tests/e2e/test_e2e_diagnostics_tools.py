from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import diagnostics as diagnostics_tools

from .e2e_test_utils import DummyMCP, FakeSessionFactory


class _FakeDeviceService:
    def __init__(self, *_args, **_kwargs) -> None:
        self.id = "dev-lab-01"
        self.environment = "lab"
        self.allow_advanced_writes = True
        self.allow_professional_workflows = False

    async def get_device(self, device_id: str):
        return self


class _FakeDiagnosticsService:
    async def ping(
        self,
        device_id: str,
        address: str,
        count: int,
        interval_ms: int,
    ):
        return {
            "host": address,
            "packets_sent": count,
            "packets_received": count,
            "packet_loss_percent": 0.0,
            "min_rtt_ms": 10.0,
            "avg_rtt_ms": 12.5,
            "max_rtt_ms": 15.0,
        }

    async def traceroute(
        self,
        device_id: str,
        address: str,
        count: int,
    ):
        return {
            "target": address,
            "hops": [
                {"hop": 1, "address": "192.0.2.1", "rtt_ms": 5.0},
                {"hop": 2, "address": "8.8.8.8", "rtt_ms": 10.0},
            ],
        }


class TestE2EDiagnosticsTools(unittest.TestCase):
    def _register_tools(self) -> DummyMCP:
        mcp = DummyMCP()
        settings = Settings()
        diagnostics_tools.register_diagnostics_tools(mcp, settings)
        return mcp

    def test_diagnostics_tools_end_to_end(self) -> None:
        async def _run() -> None:
            with (
                patch.object(
                    diagnostics_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    diagnostics_tools,
                    "DeviceService",
                    _FakeDeviceService,
                ),
                patch.object(
                    diagnostics_tools,
                    "DiagnosticsService",
                    lambda *args, **kwargs: _FakeDiagnosticsService(),
                ),
                patch.object(
                    diagnostics_tools,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_tools()

                ping = await mcp.tools["run_ping"]("dev-lab-01", "8.8.8.8", 4, 1000)
                self.assertFalse(ping["isError"])
                self.assertEqual(4, ping["_meta"]["packets_sent"])
                self.assertEqual(0.0, ping["_meta"]["packet_loss_percent"])

                trace = await mcp.tools["run_traceroute"]("dev-lab-01", "8.8.8.8", 1)
                self.assertFalse(trace["isError"])
                self.assertEqual(2, len(trace["_meta"]["hops"]))
                self.assertEqual("8.8.8.8", trace["_meta"]["target"])

        asyncio.run(_run())

    def test_ping_error_from_service(self) -> None:
        async def _run() -> None:
            class _ErrorDiagnosticsService:
                async def ping(
                    self,
                    device_id: str,
                    address: str,
                    count: int,
                    interval_ms: int,
                ):
                    raise ValueError("ping failed in e2e")

            with (
                patch.object(
                    diagnostics_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    diagnostics_tools,
                    "DeviceService",
                    _FakeDeviceService,
                ),
                patch.object(
                    diagnostics_tools,
                    "DiagnosticsService",
                    lambda *args, **kwargs: _ErrorDiagnosticsService(),
                ),
                patch.object(
                    diagnostics_tools,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_tools()
                ping_fn = mcp.tools["run_ping"]

                result = await ping_fn("dev-lab-01", "8.8.8.8", 4, 1000)
                self.assertTrue(result["isError"])
                self.assertIn("ping failed in e2e", result["content"][0]["text"])

        asyncio.run(_run())
