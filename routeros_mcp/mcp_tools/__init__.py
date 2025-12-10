"""MCP tools for RouterOS management.

This package contains all MCP tool implementations organized by topic:
- device: Device management and connectivity
- system: System information and configuration
- interface: Network interface operations
- ip: IP address configuration
- dns_ntp: DNS and NTP configuration
- routing: Routing table operations
- firewall_logs: Firewall rules and system logs
- diagnostics: Network diagnostic tools (ping, traceroute)
- config: Multi-device configuration workflows (plan/apply)
"""

from routeros_mcp.mcp_tools.config import register_config_tools
from routeros_mcp.mcp_tools.device import register_device_tools
from routeros_mcp.mcp_tools.diagnostics import register_diagnostics_tools
from routeros_mcp.mcp_tools.dns_ntp import register_dns_ntp_tools
from routeros_mcp.mcp_tools.firewall_logs import register_firewall_logs_tools
from routeros_mcp.mcp_tools.firewall_write import register_firewall_write_tools
from routeros_mcp.mcp_tools.interface import register_interface_tools
from routeros_mcp.mcp_tools.ip import register_ip_tools
from routeros_mcp.mcp_tools.routing import register_routing_tools
from routeros_mcp.mcp_tools.system import register_system_tools

__all__ = [
    "register_config_tools",
    "register_device_tools",
    "register_diagnostics_tools",
    "register_dns_ntp_tools",
    "register_firewall_logs_tools",
    "register_firewall_write_tools",
    "register_interface_tools",
    "register_ip_tools",
    "register_routing_tools",
    "register_system_tools",
]
