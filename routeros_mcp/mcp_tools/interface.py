"""Interface management MCP tools.

Provides MCP tools for querying network interface information and statistics.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.interface import InterfaceService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_interface_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register interface management tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    @mcp.tool()
    async def list_interfaces(device_id: str) -> dict[str, Any]:
        """List all network interfaces with operational status and metadata.

        Use when:
        - User asks "show me all interfaces" or "what's the interface status?"
        - Finding interfaces by type (ether, vlan, bridge, wireless)
        - Identifying disabled or down interfaces
        - Discovering interface names for other operations
        - Auditing interface inventory and comments
        - Troubleshooting connectivity (checking running status)

        Returns: List of interfaces with ID, name, type, running status, disabled status, 
        comment, MTU, MAC address.

        Tip: Use this first to discover interface names/IDs, then use interface/get-interface 
        for details.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with interface list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                interface_service = InterfaceService(session, settings)

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
                    tool_name="interface/list-interfaces",
                )

                # Get interfaces
                interfaces = await interface_service.list_interfaces(device_id)

                content = f"Found {len(interfaces)} interface(s) on {device.name}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "interfaces": interfaces,
                        "total_count": len(interfaces),
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
    async def get_interface(device_id: str, interface_id: str) -> dict[str, Any]:
        """Get detailed information about a specific interface.

        Use when:
        - User asks about a specific interface ("tell me about ether1")
        - Need complete interface configuration details
        - Checking interface-specific settings before making changes
        - Verifying last link up/down events
        - Detailed troubleshooting of single interface

        Returns: Complete interface configuration including all fields from interface list 
        plus additional details.

        Note: Requires interface ID (from interface/list-interfaces) or name.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            interface_id: Interface ID (e.g., '*1')

        Returns:
            Formatted tool result with interface details
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                interface_service = InterfaceService(session, settings)

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
                    tool_name="interface/get-interface",
                )

                # Get interface
                interface = await interface_service.get_interface(device_id, interface_id)

                content = f"Interface {interface['name']} details"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "interface": interface,
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
    async def get_interface_stats(
        device_id: str,
        interface_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get real-time traffic statistics for network interfaces.

        Use when:
        - User asks "how much traffic on ether1?" or "show bandwidth usage"
        - Monitoring current network load (bits/packets per second)
        - Troubleshooting performance issues (identifying saturated links)
        - Verifying traffic flow after configuration changes
        - Capacity planning (understanding current utilization)

        Returns: Real-time RX/TX rates in bits per second and packets per second.

        Tip: This is a snapshot at the time of the call. For trends, compare multiple 
        calls over time.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            interface_names: Optional list of interface names to filter (e.g., ['ether1', 'ether2'])

        Returns:
            Formatted tool result with traffic statistics
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                interface_service = InterfaceService(session, settings)

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
                    tool_name="interface/get-stats",
                )

                # Get interface stats
                stats = await interface_service.get_interface_stats(device_id, interface_names)

                if interface_names:
                    content = f"Traffic statistics for {len(stats)} interface(s)"
                else:
                    content = f"Traffic statistics for all interfaces"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "stats": stats,
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

    logger.info("Registered interface management tools")
