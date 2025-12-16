"""DHCP management MCP tools.

Provides MCP tools for querying DHCP server configuration and active leases.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.dhcp import DHCPService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_dhcp_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register DHCP tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    @mcp.tool()
    async def get_dhcp_server_status(device_id: str) -> dict[str, Any]:
        """Get DHCP server configuration and status.

        Use when:
        - User asks "what DHCP servers are configured?" or "is DHCP working?"
        - Troubleshooting DHCP-related connectivity issues
        - Verifying DHCP configuration after changes
        - Checking which interfaces have DHCP enabled
        - Planning DHCP server updates
        - Auditing DHCP settings across fleet

        Returns: List of DHCP servers with name, interface, lease time, address pool, and status.

        Note: Multiple DHCP servers can exist on RouterOS. This returns all configured servers.

        Tip: Use with dhcp/get-leases to see active clients for each server.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with DHCP server status
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                dhcp_service = DHCPService(session, settings)

                # Get device first to validate it exists
                device = await device_service.get_device(device_id)

                # Authorization check - fundamental tier, read-only
                check_tool_authorization(
                    device_environment=device.environment,
                    service_environment=settings.environment,
                    tool_tier=ToolTier.FUNDAMENTAL,
                    allow_advanced_writes=device.allow_advanced_writes,
                    allow_professional_workflows=device.allow_professional_workflows,
                    device_id=device_id,
                    tool_name="dhcp/get-server-status",
                )

                # Get DHCP server status
                server_status = await dhcp_service.get_dhcp_server_status(device_id)

                # Format content
                server_count = server_status["total_count"]
                if server_count == 0:
                    content = "No DHCP servers configured"
                elif server_count == 1:
                    server = server_status["servers"][0]
                    content = f"DHCP server '{server['name']}' on {server['interface']}"
                else:
                    server_names = [s["name"] for s in server_status["servers"]]
                    content = f"{server_count} DHCP servers: {', '.join(server_names)}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        **server_status,
                    },
                )

        except MCPError as e:
            return format_tool_result(
                content=e.message,
                is_error=True,
                meta=e.data,
            )
        except Exception as e:
            error = map_exception_to_error(e)
            return format_tool_result(
                content=error.message,
                is_error=True,
                meta=error.data,
            )

    @mcp.tool()
    async def get_dhcp_leases(device_id: str) -> dict[str, Any]:
        """Get active DHCP leases with client information.

        Use when:
        - User asks "what devices have DHCP leases?" or "show me DHCP clients"
        - Troubleshooting client connectivity (verify lease is active)
        - Checking IP address allocation across DHCP pools
        - Identifying clients by hostname or MAC address
        - Monitoring DHCP server usage
        - Before planning IP address changes

        Returns: List of active DHCP leases with IP address, MAC address, client ID, hostname, and server name.

        Note: Only returns ACTIVE leases (status=bound). Expired or released leases are filtered out.
              Lease expiry is relative to last activity on RouterOS.

        Tip: Use with ip/get-arp-table to cross-reference active connections.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with DHCP leases
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                dhcp_service = DHCPService(session, settings)

                # Get device first to validate it exists
                device = await device_service.get_device(device_id)

                # Authorization check - fundamental tier, read-only
                check_tool_authorization(
                    device_environment=device.environment,
                    service_environment=settings.environment,
                    tool_tier=ToolTier.FUNDAMENTAL,
                    allow_advanced_writes=device.allow_advanced_writes,
                    allow_professional_workflows=device.allow_professional_workflows,
                    device_id=device_id,
                    tool_name="dhcp/get-leases",
                )

                # Get DHCP leases
                leases_data = await dhcp_service.get_dhcp_leases(device_id)

                # Format content
                lease_count = leases_data["total_count"]
                if lease_count == 0:
                    content = "No active DHCP leases"
                elif lease_count == 1:
                    lease = leases_data["leases"][0]
                    content = f"1 active lease: {lease['address']} ({lease.get('host_name', 'unknown')})"
                else:
                    content = f"{lease_count} active DHCP leases"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        **leases_data,
                    },
                )

        except MCPError as e:
            return format_tool_result(
                content=e.message,
                is_error=True,
                meta=e.data,
            )
        except Exception as e:
            error = map_exception_to_error(e)
            return format_tool_result(
                content=error.message,
                is_error=True,
                meta=error.data,
            )

    logger.info("Registered DHCP tools")
