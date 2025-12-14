"""Diagnostics MCP tools.

Provides MCP tools for running network diagnostic operations (ping, traceroute).
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.diagnostics import DiagnosticsService
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_diagnostics_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register diagnostics tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    @mcp.tool()
    async def ping(
        device_id: str,
        target: str,
        count: int = 4,
        timeout_seconds: int = 10,
    ) -> dict[str, Any]:
        """Execute ping command on a RouterOS device.

        Args:
            device_id: Device identifier
            target: Target IP or hostname
            count: Number of ping attempts (max 10)
            timeout_seconds: Command timeout in seconds

        Returns:
            Ping results with response times
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)

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
                    tool_name="diagnostics/ping",
                )

                diagnostics_service = DiagnosticsService(
                    session,
                    settings,
                    device_service,
                )

                result = await diagnostics_service.ping(
                    device_id=device_id,
                    address=target,
                    count=count,
                    interval_ms=1000,
                )

                content = (
                    f"Ping to {target}: {result['packets_sent']} packets sent, "
                    f"{result['packets_received']} received, "
                    f"{result['packet_loss_percent']:.1f}% loss"
                )

                return format_tool_result(
                    content=content,
                    meta=result,
                )

        except MCPError as e:
            logger.warning(f"Ping tool error: {e}")
            raise
        except Exception as e:
            logger.error(f"Ping tool unexpected error: {e}")
            raise map_exception_to_error(e)

    @mcp.tool()
    async def traceroute(
        device_id: str,
        target: str,
        max_hops: int = 30,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        """Execute traceroute command on a RouterOS device.

        Args:
            device_id: Device identifier
            target: Target IP or hostname
            max_hops: Maximum hops to trace (max 30)
            timeout_seconds: Command timeout in seconds

        Returns:
            Traceroute hop information
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)

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
                    tool_name="diagnostics/traceroute",
                )

                diagnostics_service = DiagnosticsService(
                    session,
                    settings,
                    device_service,
                )

                result = await diagnostics_service.traceroute(
                    device_id=device_id,
                    address=target,
                    count=1,
                )

                hop_count = len(result.get("hops", []))
                content = f"Traceroute to {target} completed in {hop_count} hops"

                return format_tool_result(
                    content=content,
                    meta=result,
                )

        except MCPError as e:
            logger.warning(f"Traceroute tool error: {e}")
            raise
        except Exception as e:
            logger.error(f"Traceroute tool unexpected error: {e}")
            raise map_exception_to_error(e)
