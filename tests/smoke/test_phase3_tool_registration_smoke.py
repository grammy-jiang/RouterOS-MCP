"""Smoke tests to verify Phase 3 tool registrars register expected tool names."""

from __future__ import annotations

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import bridge as bridge_tools
from routeros_mcp.mcp_tools import dhcp as dhcp_tools
from routeros_mcp.mcp_tools import wireless as wireless_tools
from routeros_mcp.mcp_tools import firewall_write as firewall_write_tools
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


pytestmark = pytest.mark.smoke


def test_bridge_tool_registration_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bridge registrar should register known tool names without touching DB."""

    # Patch session factory to avoid DB init during registration
    monkeypatch.setattr(bridge_tools, "get_session_factory", lambda _s=None: FakeSessionFactory())

    mcp = DummyMCP()
    settings = Settings()

    bridge_tools.register_bridge_tools(mcp, settings)

    tool_names = set(mcp.tools.keys())

    # Bridge tools (6 tools for Phase 3)
    assert "list_bridges" in tool_names
    assert "list_bridge_ports" in tool_names
    assert "plan_add_bridge_port" in tool_names
    assert "plan_remove_bridge_port" in tool_names
    assert "plan_modify_bridge_settings" in tool_names
    assert "apply_bridge_plan" in tool_names


def test_dhcp_tool_registration_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """DHCP registrar should register known tool names without DB."""

    # Patch session factory to avoid DB init during registration
    monkeypatch.setattr(dhcp_tools, "get_session_factory", lambda _s=None: FakeSessionFactory())

    mcp = DummyMCP()
    settings = Settings()

    dhcp_tools.register_dhcp_tools(mcp, settings)

    tool_names = set(mcp.tools.keys())

    # DHCP tools (6 tools for Phase 3)
    assert "get_dhcp_server_status" in tool_names
    assert "get_dhcp_leases" in tool_names
    assert "plan_create_dhcp_pool" in tool_names
    assert "plan_modify_dhcp_pool" in tool_names
    assert "plan_remove_dhcp_pool" in tool_names
    assert "apply_dhcp_plan" in tool_names


def test_wireless_tool_registration_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wireless registrar should register known tool names without DB."""

    # Patch session factory to avoid DB init during registration
    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _s=None: FakeSessionFactory())

    mcp = DummyMCP()
    settings = Settings()

    wireless_tools.register_wireless_tools(mcp, settings)

    tool_names = set(mcp.tools.keys())

    # Wireless tools (9 tools for Phase 3)
    assert "get_wireless_interfaces" in tool_names
    assert "get_wireless_clients" in tool_names
    assert "get_capsman_remote_caps" in tool_names
    assert "get_capsman_registrations" in tool_names
    assert "plan_create_wireless_ssid" in tool_names
    assert "plan_modify_wireless_ssid" in tool_names
    assert "plan_remove_wireless_ssid" in tool_names
    assert "plan_wireless_rf_settings" in tool_names
    assert "apply_wireless_plan" in tool_names


def test_firewall_write_tool_registration_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Firewall write registrar should register known tool names without DB."""

    # Patch session factory to avoid DB init during registration
    monkeypatch.setattr(firewall_write_tools, "get_session_factory", lambda _s=None: FakeSessionFactory())

    mcp = DummyMCP()
    settings = Settings()

    firewall_write_tools.register_firewall_write_tools(mcp, settings)

    tool_names = set(mcp.tools.keys())

    # Firewall write tools (5 tools for Phase 3)
    assert "plan_add_firewall_rule" in tool_names
    assert "plan_modify_firewall_rule" in tool_names
    assert "plan_remove_firewall_rule" in tool_names
    assert "update_firewall_address_list" in tool_names
    assert "apply_firewall_plan" in tool_names
