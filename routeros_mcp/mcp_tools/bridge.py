"""Bridge management MCP tools.

Provides MCP tools for querying bridge configuration and topology.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.bridge import BridgeService
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_bridge_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register bridge management tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    @mcp.tool()
    async def list_bridges(device_id: str) -> dict[str, Any]:
        """List all bridge interfaces with configuration and status.

        Use when:
        - User asks "show me all bridges" or "what bridges are configured?"
        - Finding bridges by name
        - Discovering bridge topology
        - Checking bridge VLAN filtering status
        - Auditing bridge STP/RSTP configuration
        - Troubleshooting switching issues

        Returns: List of bridges with ID, name, MAC address, MTU, protocol mode (STP/RSTP/MSTP),
        VLAN filtering status, running status, and other bridge-specific settings.

        Tip: Use this first to discover bridge names, then use bridge/list-ports to see
        which interfaces are members of each bridge.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with bridge list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                bridge_service = BridgeService(session, settings)

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
                    tool_name="bridge/list-bridges",
                )

                # Get bridges
                bridges = await bridge_service.list_bridges(device_id)

                content = f"Found {len(bridges)} bridge(s) on {device.name}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "bridges": bridges,
                        "total_count": len(bridges),
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
    async def list_bridge_ports(device_id: str) -> dict[str, Any]:
        """List all bridge port assignments with VLAN and STP configuration.

        Use when:
        - User asks "what interfaces are in bridge X?" or "show bridge members"
        - Finding which bridge an interface belongs to
        - Checking VLAN tagging and PVID configuration
        - Auditing STP priority and path cost
        - Troubleshooting bridge port states
        - Verifying hardware offload status

        Returns: List of bridge ports with interface name, bridge name, PVID, VLAN settings,
        STP status (edge port, point-to-point), hardware offload status, and state.

        Tip: Combine with bridge/list-bridges to understand the complete bridge topology.
        Note: Bridge ports may be enabled/disabled; disabled ports won't forward traffic.
        STP status shows the spanning tree algorithm in use (RSTP, PVST, or disabled).

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with bridge port list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                bridge_service = BridgeService(session, settings)

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
                    tool_name="bridge/list-ports",
                )

                # Get bridge ports
                ports = await bridge_service.list_bridge_ports(device_id)

                content = f"Found {len(ports)} bridge port(s) on {device.name}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "bridge_ports": ports,
                        "total_count": len(ports),
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

    logger.info("Registered bridge tools")
