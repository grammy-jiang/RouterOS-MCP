from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import diagnostics as diag_tools
from unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


class _FakeDeviceService:
    def __init__(self) -> None:
        self.device = type(
            "Device",
            (),
            {
                "id": "dev-1",
                "name": "router-1",
                "environment": "lab",
                "allow_advanced_writes": True,
                "allow_professional_workflows": True,
            },
        )

    async def get_device(self, device_id: str):
        return self.device


class _FakeDiagnosticsService:
    def __init__(self, raise_ping: bool = False) -> None:
        self.raise_ping = raise_ping

    async def ping(self, device_id: str, address: str, count: int, interval_ms: int):
        if self.raise_ping:
            raise ValueError("ping failed")
        return {
            "host": address,
            "packets_sent": count,
            "packets_received": count,
            "packet_loss_percent": 0.0,
            "min_rtt_ms": 1.0,
            "avg_rtt_ms": 2.0,
            "max_rtt_ms": 3.0,
        }

    async def traceroute(self, device_id: str, address: str, count: int):
        return {
            "target": address,
            "hops": [
                {"hop": 1, "address": "10.0.0.1", "rtt_ms": 1.0},
                {"hop": 2, "address": "10.0.0.2", "rtt_ms": 2.0},
            ],
        }


class TestMCPToolsDiagnostics(unittest.TestCase):
    def _register_tools(self, fake_diag_service: _FakeDiagnosticsService) -> DummyMCP:
        mcp = DummyMCP()
        settings = Settings()
        diag_tools.register_diagnostics_tools(mcp, settings)
        return mcp

    def test_run_ping_success(self) -> None:
        async def _run() -> None:
            fake_diag_service = _FakeDiagnosticsService()
            with (
                patch.object(
                    diag_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    diag_tools, "DeviceService", lambda *args, **kwargs: _FakeDeviceService()
                ),
                patch.object(
                    diag_tools,
                    "DiagnosticsService",
                    lambda *args, **kwargs: fake_diag_service,
                ),
                patch.object(diag_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_diag_service)
                result = await mcp.tools["run_ping"]("dev-1", "8.8.8.8", count=2, interval_ms=500)
                self.assertEqual(0.0, result["_meta"]["packet_loss_percent"])
                self.assertIn("Ping to", result["content"][0]["text"])

        asyncio.run(_run())

    def test_run_ping_error(self) -> None:
        async def _run() -> None:
            fake_diag_service = _FakeDiagnosticsService(raise_ping=True)
            with (
                patch.object(
                    diag_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    diag_tools, "DeviceService", lambda *args, **kwargs: _FakeDeviceService()
                ),
                patch.object(
                    diag_tools,
                    "DiagnosticsService",
                    lambda *args, **kwargs: fake_diag_service,
                ),
                patch.object(diag_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_diag_service)
                result = await mcp.tools["run_ping"]("dev-1", "8.8.8.8")
                self.assertTrue(result["isError"])

        asyncio.run(_run())

    def test_run_traceroute_success(self) -> None:
        async def _run() -> None:
            fake_diag_service = _FakeDiagnosticsService()
            with (
                patch.object(
                    diag_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    diag_tools, "DeviceService", lambda *args, **kwargs: _FakeDeviceService()
                ),
                patch.object(
                    diag_tools,
                    "DiagnosticsService",
                    lambda *args, **kwargs: fake_diag_service,
                ),
                patch.object(diag_tools, "check_tool_authorization", lambda *args, **kwargs: None),
            ):
                mcp = self._register_tools(fake_diag_service)
                result = await mcp.tools["run_traceroute"]("dev-1", "1.1.1.1", count=1)
                self.assertEqual(1, result["_meta"]["hops"][0]["hop"])
                self.assertIn("Traceroute", result["content"][0]["text"])

        asyncio.run(_run())
