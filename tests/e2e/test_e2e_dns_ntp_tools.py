from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.mcp_tools import dns_ntp as dns_ntp_tools

from .e2e_test_utils import DummyMCP, FakeSessionFactory, make_test_settings


class _FakeDeviceService:
    def __init__(self, *_args, **_kwargs) -> None:
        self.id = "dev-lab-01"
        self.environment = "lab"
        self.allow_advanced_writes = True
        self.allow_professional_workflows = False

    async def get_device(self, device_id: str):
        return self


class _FakeDNSNTPService:
    async def get_dns_status(self, device_id: str):
        return {
            "dns_servers": ["1.1.1.1", "8.8.8.8"],
            "allow_remote_requests": True,
            "cache_size_kb": 2048,
            "cache_used_kb": 128,
        }

    async def get_dns_cache(self, device_id: str, limit: int):
        entries = [
            {"name": "example.com", "type": "A", "data": "93.184.216.34", "ttl": 100},
            {"name": "example.net", "type": "AAAA", "data": "2001:db8::1", "ttl": 200},
        ]
        return entries[:limit], len(entries)

    async def get_ntp_status(self, device_id: str):
        return {
            "enabled": True,
            "ntp_servers": ["time.nist.gov"],
            "mode": "unicast",
            "status": "synchronized",
            "stratum": 2,
            "offset_ms": 0.5,
        }

    async def update_dns_servers(self, device_id: str, dns_servers: list[str], dry_run: bool):
        if dry_run:
            return {
                "changed": False,
                "dry_run": True,
                "planned_changes": {
                    "old_servers": ["1.1.1.1"],
                    "new_servers": dns_servers,
                },
                "new_servers": dns_servers,
                "old_servers": ["1.1.1.1"],
            }
        return {
            "changed": True,
            "old_servers": ["1.1.1.1"],
            "new_servers": dns_servers,
            "dry_run": False,
        }

    async def flush_dns_cache(self, device_id: str):
        return {"changed": True, "entries_flushed": 5}

    async def update_ntp_servers(
        self,
        device_id: str,
        ntp_servers: list[str],
        enabled: bool,
        dry_run: bool,
    ):
        if dry_run:
            return {
                "changed": False,
                "dry_run": True,
                "planned_changes": {
                    "old_servers": ["time.nist.gov"],
                    "new_servers": ntp_servers,
                    "old_enabled": True,
                    "new_enabled": enabled,
                },
                "new_servers": ntp_servers,
                "old_servers": ["time.nist.gov"],
                "enabled": enabled,
            }
        return {
            "changed": True,
            "old_servers": ["time.nist.gov"],
            "new_servers": ntp_servers,
            "enabled": enabled,
            "dry_run": False,
        }


class TestE2EDNSNTPTools(unittest.TestCase):
    def _register_tools(self) -> DummyMCP:
        mcp = DummyMCP()
        settings = make_test_settings()
        dns_ntp_tools.register_dns_ntp_tools(mcp, settings)
        return mcp

    def test_dns_ntp_tools_end_to_end(self) -> None:
        async def _run() -> None:
            with (
                patch.object(
                    dns_ntp_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    dns_ntp_tools,
                    "DNSNTPService",
                    lambda *args, **kwargs: _FakeDNSNTPService(),
                ),
                patch.object(dns_ntp_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()

                dns_status = await mcp.tools["get_dns_status"]("dev-lab-01")
                self.assertFalse(dns_status["isError"])
                self.assertIn("1.1.1.1", dns_status["_meta"]["dns_servers"])

                dns_cache = await mcp.tools["get_dns_cache"]("dev-lab-01", 1)
                self.assertEqual(1, dns_cache["_meta"]["returned_count"])
                self.assertEqual(2, dns_cache["_meta"]["total_count"])

                ntp_status = await mcp.tools["get_ntp_status"]("dev-lab-01")
                self.assertEqual("synchronized", ntp_status["_meta"]["status"])
                self.assertEqual(
                    ["time.nist.gov"],
                    ntp_status["_meta"]["ntp_servers"],
                )

                dns_dry = await mcp.tools["update_dns_servers"](
                    "dev-lab-01",
                    ["9.9.9.9"],
                    dry_run=True,
                )
                self.assertTrue(dns_dry["_meta"]["dry_run"])
                self.assertEqual(
                    ["9.9.9.9"],
                    dns_dry["_meta"]["new_servers"],
                )

                ntp_dry = await mcp.tools["update_ntp_servers"](
                    "dev-lab-01",
                    ["time.example.com"],
                    enabled=True,
                    dry_run=True,
                )
                self.assertTrue(ntp_dry["_meta"]["dry_run"])
                self.assertEqual(
                    ["time.example.com"],
                    ntp_dry["_meta"]["new_servers"],
                )

                flush = await mcp.tools["flush_dns_cache"]("dev-lab-01")
                self.assertTrue(flush["_meta"]["changed"])
                self.assertEqual(5, flush["_meta"]["entries_flushed"])

        asyncio.run(_run())

    def test_dns_cache_error_from_service(self) -> None:
        async def _run() -> None:
            class _ErrorDNSNTPService:
                async def get_dns_cache(self, device_id: str, limit: int):
                    raise ValueError("dns-cache failed in e2e")

            with (
                patch.object(
                    dns_ntp_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    dns_ntp_tools,
                    "DNSNTPService",
                    lambda *args, **kwargs: _ErrorDNSNTPService(),
                ),
                patch.object(dns_ntp_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                cache_fn = mcp.tools["get_dns_cache"]

                result = await cache_fn("dev-lab-01", 5)
                self.assertTrue(result["isError"])
                self.assertIn("dns-cache failed in e2e", result["content"][0]["text"])

        asyncio.run(_run())

    def test_update_ntp_servers_no_change(self) -> None:
        async def _run() -> None:
            class _NoChangeDNSNTPService:
                async def update_ntp_servers(
                    self,
                    device_id: str,
                    ntp_servers: list[str],
                    enabled: bool,
                    dry_run: bool,
                ):
                    return {
                        "changed": False,
                        "new_servers": ntp_servers,
                        "old_servers": ntp_servers,
                        "enabled": enabled,
                        "dry_run": False,
                    }

            with (
                patch.object(
                    dns_ntp_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    dns_ntp_tools,
                    "DNSNTPService",
                    lambda *args, **kwargs: _NoChangeDNSNTPService(),
                ),
                patch.object(dns_ntp_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                ntp_fn = mcp.tools["update_ntp_servers"]

                result = await ntp_fn(
                    "dev-lab-01",
                    ["time.google.com"],
                    enabled=True,
                    dry_run=False,
                )
                self.assertFalse(result["isError"])
                self.assertIn("no change", result["content"][0]["text"])
                self.assertFalse(result["_meta"]["changed"])

        asyncio.run(_run())

    def test_get_ntp_status_not_synchronized(self) -> None:
        async def _run() -> None:
            class _NotSyncDNSNTPService:
                async def get_ntp_status(self, device_id: str):
                    return {
                        "enabled": True,
                        "ntp_servers": ["time.example.com"],
                        "mode": "unicast",
                        "status": "not synchronized",
                        "stratum": 0,
                        "offset_ms": 0.0,
                    }

            with (
                patch.object(
                    dns_ntp_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    dns_ntp_tools,
                    "DNSNTPService",
                    lambda *args, **kwargs: _NotSyncDNSNTPService(),
                ),
                patch.object(dns_ntp_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()

                ntp_status = await mcp.tools["get_ntp_status"]("dev-lab-01")
                self.assertFalse(ntp_status["isError"])
                self.assertIn("NTP status: not synchronized", ntp_status["content"][0]["text"])
                self.assertEqual("not synchronized", ntp_status["_meta"]["status"])

        asyncio.run(_run())

    def test_update_dns_servers_changed(self) -> None:
        async def _run() -> None:
            class _ChangedDNSNTPService:
                async def update_dns_servers(
                    self,
                    device_id: str,
                    dns_servers: list[str],
                    dry_run: bool,
                ):
                    return {
                        "changed": True,
                        "old_servers": ["1.1.1.1"],
                        "new_servers": dns_servers,
                        "dry_run": False,
                    }

            with (
                patch.object(
                    dns_ntp_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    dns_ntp_tools,
                    "DNSNTPService",
                    lambda *args, **kwargs: _ChangedDNSNTPService(),
                ),
                patch.object(dns_ntp_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                dns_fn = mcp.tools["update_dns_servers"]

                result = await dns_fn("dev-lab-01", ["9.9.9.9"], dry_run=False)
                self.assertFalse(result["isError"])
                self.assertIn("DNS servers updated to 9.9.9.9", result["content"][0]["text"])
                self.assertTrue(result["_meta"]["changed"])
                self.assertEqual(["9.9.9.9"], result["_meta"]["new_servers"])

        asyncio.run(_run())

    def test_update_ntp_servers_changed(self) -> None:
        async def _run() -> None:
            class _ChangedDNSNTPService:
                async def update_ntp_servers(
                    self,
                    device_id: str,
                    ntp_servers: list[str],
                    enabled: bool,
                    dry_run: bool,
                ):
                    return {
                        "changed": True,
                        "old_servers": ["time.nist.gov"],
                        "new_servers": ntp_servers,
                        "enabled": enabled,
                        "dry_run": False,
                    }

            with (
                patch.object(
                    dns_ntp_tools,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(dns_ntp_tools, "DeviceService", _FakeDeviceService),
                patch.object(
                    dns_ntp_tools,
                    "DNSNTPService",
                    lambda *args, **kwargs: _ChangedDNSNTPService(),
                ),
                patch.object(dns_ntp_tools, "check_tool_authorization", lambda **_kwargs: None),
            ):
                mcp = self._register_tools()
                ntp_fn = mcp.tools["update_ntp_servers"]

                result = await ntp_fn(
                    "dev-lab-01",
                    ["time.google.com"],
                    enabled=True,
                    dry_run=False,
                )
                self.assertFalse(result["isError"])
                self.assertIn(
                    "NTP servers updated to time.google.com", result["content"][0]["text"]
                )
                self.assertTrue(result["_meta"]["changed"])
                self.assertEqual(["time.google.com"], result["_meta"]["new_servers"])
                self.assertTrue(result["_meta"]["enabled"])

        asyncio.run(_run())
