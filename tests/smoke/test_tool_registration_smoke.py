"""Smoke tests to verify core tool registrars register expected tool names."""

from __future__ import annotations

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import device as device_tools
from routeros_mcp.mcp_tools import system as system_tools
from routeros_mcp.mcp_tools import interface as interface_tools
from routeros_mcp.mcp_tools import ip as ip_tools
from routeros_mcp.mcp_tools import routing as routing_tools
from routeros_mcp.mcp_tools import diagnostics as diagnostics_tools
from routeros_mcp.mcp_tools import firewall_logs as firewall_logs_tools
from routeros_mcp.mcp_tools import dns_ntp as dns_ntp_tools
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


pytestmark = pytest.mark.smoke


def test_core_tool_registration_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Device and system registrars should register known tool names without touching DB."""

    # Patch session factory to avoid DB init during registration
    monkeypatch.setattr(device_tools, "get_session_factory", lambda _s=None: FakeSessionFactory())
    monkeypatch.setattr(system_tools, "get_session_factory", lambda _s=None: FakeSessionFactory())

    mcp = DummyMCP()
    settings = Settings()

    device_tools.register_device_tools(mcp, settings)
    system_tools.register_system_tools(mcp, settings)

    tool_names = set(mcp.tools.keys())

    # Device tools
    assert "list_devices" in tool_names
    assert "check_connectivity" in tool_names

    # System tools
    assert "get_system_overview" in tool_names
    assert "get_system_packages" in tool_names
    assert "get_system_clock" in tool_names


def test_interface_and_ip_tool_registration_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Interface and IP registrars should register known tool names without DB."""

    # Patch session factory to avoid DB init during registration
    monkeypatch.setattr(interface_tools, "get_session_factory", lambda _s=None: FakeSessionFactory())
    monkeypatch.setattr(ip_tools, "get_session_factory", lambda _s=None: FakeSessionFactory())

    mcp = DummyMCP()
    settings = Settings()

    interface_tools.register_interface_tools(mcp, settings)
    ip_tools.register_ip_tools(mcp, settings)

    tool_names = set(mcp.tools.keys())

    # Interface tools
    assert "list_interfaces" in tool_names
    assert "get_interface" in tool_names
    assert "get_interface_stats" in tool_names

    # IP tools
    assert "list_ip_addresses" in tool_names
    assert "get_ip_address" in tool_names
    assert "get_arp_table" in tool_names


def test_routing_and_diagnostics_tool_registration_smoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routing and diagnostics registrars should register known tool names without DB."""

    # Patch session factory to avoid DB init during registration
    monkeypatch.setattr(routing_tools, "get_session_factory", lambda _s=None: FakeSessionFactory())
    monkeypatch.setattr(diagnostics_tools, "get_session_factory", lambda _s=None: FakeSessionFactory())

    mcp = DummyMCP()
    settings = Settings()

    routing_tools.register_routing_tools(mcp, settings)
    diagnostics_tools.register_diagnostics_tools(mcp, settings)

    tool_names = set(mcp.tools.keys())

    # Routing tools
    assert "get_routing_summary" in tool_names
    assert "get_route" in tool_names

    # Diagnostics tools
    assert "ping" in tool_names
    assert "traceroute" in tool_names


def test_firewall_logs_and_dns_ntp_tool_registration_smoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Firewall/logs and DNS/NTP registrars should register known tool names without DB."""

    # Patch session factory to avoid DB init during registration
    monkeypatch.setattr(
        firewall_logs_tools, "get_session_factory", lambda _s=None: FakeSessionFactory()
    )
    monkeypatch.setattr(dns_ntp_tools, "get_session_factory", lambda _s=None: FakeSessionFactory())

    mcp = DummyMCP()
    settings = Settings()

    firewall_logs_tools.register_firewall_logs_tools(mcp, settings)
    dns_ntp_tools.register_dns_ntp_tools(mcp, settings)

    tool_names = set(mcp.tools.keys())

    # Firewall/logs tools
    assert "list_firewall_filter_rules" in tool_names
    assert "list_firewall_nat_rules" in tool_names
    assert "list_firewall_address_lists" in tool_names
    assert "get_recent_logs" in tool_names
    assert "get_logging_config" in tool_names

    # DNS/NTP tools (read + write registered, but we only assert presence)
    assert "get_dns_status" in tool_names
    assert "get_dns_cache" in tool_names
    assert "get_ntp_status" in tool_names
    assert "update_dns_servers" in tool_names
    assert "flush_dns_cache" in tool_names
    assert "update_ntp_servers" in tool_names
