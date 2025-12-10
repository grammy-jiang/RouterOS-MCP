"""Routing management MCP tools.

Provides MCP tools for querying routing table information.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.routing import RoutingService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_routing_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register routing management tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings.database_url)

    @mcp.tool()
    async def get_routing_summary(device_id: str) -> dict[str, Any]:
        """Get routing table summary with route counts and key routes.

        Use when:
        - User asks "show me routes" or "what's the default gateway?"
        - Overview of routing configuration
        - Counting routes by type (static, connected, dynamic)
        - Finding default route quickly
        - Before planning routing changes
        - Troubleshooting routing issues (verifying routes exist)

        Returns: Total route count, counts by type (static/connected/dynamic), list of routes 
        with destination, gateway, distance, comment.

        Tip: For detailed single route info, use routing/get-route.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with routing summary
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                routing_service = RoutingService(session, settings)

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
                    tool_name="routing/get-summary",
                )

                # Get routing summary
                summary = await routing_service.get_routing_summary(device_id)

                content = (
                    f"Routing table: {summary['total_routes']} routes "
                    f"({summary['static_routes']} static, "
                    f"{summary['connected_routes'] + summary['dynamic_routes']} connected/dynamic)"
                )

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        **summary,
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
    async def get_route(device_id: str, route_id: str) -> dict[str, Any]:
        """Get detailed information about a specific route.

        Use when:
        - User asks about a specific route destination
        - Investigating route properties (scope, distance, active/inactive status)
        - Verifying route configuration
        - Detailed troubleshooting of routing behavior

        Returns: Complete route details including destination, gateway, distance, scope, 
        active status, dynamic flag.

        Note: Requires route ID (from routing/get-summary).

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            route_id: Route ID (e.g., '*3')

        Returns:
            Formatted tool result with route details
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                routing_service = RoutingService(session, settings)

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
                    tool_name="routing/get-route",
                )

                # Get route
                route = await routing_service.get_route(device_id, route_id)

                content = f"Route: {route['dst_address']} via {route['gateway']}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "route": route,
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

    logger.info("Registered routing management tools")
