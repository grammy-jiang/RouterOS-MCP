"""MCP resources for RouterOS devices and fleet data.

This package contains resource providers for device://, fleet://,
plan://, and audit:// URI schemes.
"""

from routeros_mcp.mcp_resources.audit import register_audit_resources
from routeros_mcp.mcp_resources.device import register_device_resources
from routeros_mcp.mcp_resources.dhcp import register_dhcp_resources
from routeros_mcp.mcp_resources.fleet import register_fleet_resources
from routeros_mcp.mcp_resources.plan import register_plan_resources
from routeros_mcp.mcp_resources.wireless import register_wireless_resources

__all__ = [
    "register_device_resources",
    "register_dhcp_resources",
    "register_fleet_resources",
    "register_plan_resources",
    "register_audit_resources",
    "register_wireless_resources",
]
