"""Tests for domain services structure and imports.

Basic smoke tests to verify that all new domain services can be imported
and instantiated correctly.
"""

import pytest

from routeros_mcp.config import Settings


class TestDomainServicesStructure:
    """Test that all domain services can be imported and instantiated."""

    def test_interface_service_import(self):
        """Test that InterfaceService can be imported."""
        from routeros_mcp.domain.services.interface import InterfaceService
        assert InterfaceService is not None

    def test_ip_service_import(self):
        """Test that IPService can be imported."""
        from routeros_mcp.domain.services.ip import IPService
        assert IPService is not None

    def test_dns_ntp_service_import(self):
        """Test that DNSNTPService can be imported."""
        from routeros_mcp.domain.services.dns_ntp import DNSNTPService
        assert DNSNTPService is not None

    def test_routing_service_import(self):
        """Test that RoutingService can be imported."""
        from routeros_mcp.domain.services.routing import RoutingService
        assert RoutingService is not None

    def test_firewall_logs_service_import(self):
        """Test that FirewallLogsService can be imported."""
        from routeros_mcp.domain.services.firewall_logs import FirewallLogsService
        assert FirewallLogsService is not None

    def test_diagnostics_service_import(self):
        """Test that DiagnosticsService can be imported."""
        from routeros_mcp.domain.services.diagnostics import DiagnosticsService
        assert DiagnosticsService is not None

    def test_all_services_in_init(self):
        """Test that all services are exported from __init__.py."""
        from routeros_mcp.domain.services import (
            DeviceService,
            DiagnosticsService,
            DNSNTPService,
            FirewallLogsService,
            HealthService,
            InterfaceService,
            IPService,
            RoutingService,
            SystemService,
        )
        
        assert DeviceService is not None
        assert DiagnosticsService is not None
        assert DNSNTPService is not None
        assert FirewallLogsService is not None
        assert HealthService is not None
        assert InterfaceService is not None
        assert IPService is not None
        assert RoutingService is not None
        assert SystemService is not None


class TestMCPToolsStructure:
    """Test that all MCP tools can be imported."""

    def test_device_tools_import(self):
        """Test that device tools can be imported."""
        from routeros_mcp.mcp_tools.device import register_device_tools
        assert register_device_tools is not None

    def test_system_tools_import(self):
        """Test that system tools can be imported."""
        from routeros_mcp.mcp_tools.system import register_system_tools
        assert register_system_tools is not None

    def test_interface_tools_import(self):
        """Test that interface tools can be imported."""
        from routeros_mcp.mcp_tools.interface import register_interface_tools
        assert register_interface_tools is not None

    def test_ip_tools_import(self):
        """Test that IP tools can be imported."""
        from routeros_mcp.mcp_tools.ip import register_ip_tools
        assert register_ip_tools is not None

    def test_dns_ntp_tools_import(self):
        """Test that DNS/NTP tools can be imported."""
        from routeros_mcp.mcp_tools.dns_ntp import register_dns_ntp_tools
        assert register_dns_ntp_tools is not None

    def test_routing_tools_import(self):
        """Test that routing tools can be imported."""
        from routeros_mcp.mcp_tools.routing import register_routing_tools
        assert register_routing_tools is not None

    def test_firewall_logs_tools_import(self):
        """Test that firewall/logs tools can be imported."""
        from routeros_mcp.mcp_tools.firewall_logs import register_firewall_logs_tools
        assert register_firewall_logs_tools is not None

    def test_diagnostics_tools_import(self):
        """Test that diagnostics tools can be imported."""
        from routeros_mcp.mcp_tools.diagnostics import register_diagnostics_tools
        assert register_diagnostics_tools is not None

    def test_all_tools_in_init(self):
        """Test that all tool registration functions are exported from __init__.py."""
        from routeros_mcp.mcp_tools import (
            register_device_tools,
            register_diagnostics_tools,
            register_dns_ntp_tools,
            register_firewall_logs_tools,
            register_interface_tools,
            register_ip_tools,
            register_routing_tools,
            register_system_tools,
        )
        
        assert register_device_tools is not None
        assert register_diagnostics_tools is not None
        assert register_dns_ntp_tools is not None
        assert register_firewall_logs_tools is not None
        assert register_interface_tools is not None
        assert register_ip_tools is not None
        assert register_routing_tools is not None
        assert register_system_tools is not None


class TestSafetyLimits:
    """Test that safety limits are defined correctly."""

    def test_dns_cache_limit(self):
        """Test that DNS cache limit is defined."""
        from routeros_mcp.domain.services.dns_ntp import MAX_DNS_CACHE_ENTRIES
        assert MAX_DNS_CACHE_ENTRIES == 1000

    def test_log_entry_limit(self):
        """Test that log entry limit is defined."""
        from routeros_mcp.domain.services.firewall_logs import MAX_LOG_ENTRIES
        assert MAX_LOG_ENTRIES == 1000

    def test_ping_count_limit(self):
        """Test that ping count limit is defined."""
        from routeros_mcp.domain.services.diagnostics import MAX_PING_COUNT
        assert MAX_PING_COUNT == 10

    def test_traceroute_limits(self):
        """Test that traceroute limits are defined."""
        from routeros_mcp.domain.services.diagnostics import (
            MAX_TRACEROUTE_COUNT,
            MAX_TRACEROUTE_HOPS,
        )
        assert MAX_TRACEROUTE_COUNT == 3
        assert MAX_TRACEROUTE_HOPS == 30
