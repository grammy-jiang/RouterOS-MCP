"""Diagnostics MCP tools.

Provides MCP tools for network diagnostic operations (ping, traceroute).
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.diagnostics import DiagnosticsService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_diagnostics_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register network diagnostics tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings.database_url)

    @mcp.tool()
    async def run_ping(
        device_id: str,
        address: str,
        count: int = 4,
        interval_ms: int = 1000,
    ) -> dict[str, Any]:
        """Run ICMP ping test from the router to a target address.

        Use when:
        - User asks "can you ping X?" or "is host Y reachable?"
        - Testing network connectivity
        - Verifying routing to destination
        - Measuring latency/round-trip time
        - Troubleshooting packet loss
        - Verifying DNS resolution (can use hostname)

        Returns: Packets sent/received, packet loss percentage, min/avg/max RTT.

        Constraints:
        - Max 10 pings per call (count parameter)
        - Results are snapshot, not continuous monitoring

        Tip: Use interval_ms parameter to control ping frequency.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            address: Target IP address or hostname (e.g., '8.8.8.8' or 'google.com')
            count: Number of pings to send (default 4, max 10)
            interval_ms: Interval between pings in milliseconds (default 1000)

        Returns:
            Formatted tool result with ping statistics
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                diagnostics_service = DiagnosticsService(session, settings)

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
                    tool_name="tool/ping",
                )

                # Run ping
                result = await diagnostics_service.ping(device_id, address, count, interval_ms)

                content = (
                    f"Ping to {result['host']}: {result['packets_sent']} sent, "
                    f"{result['packets_received']} received, "
                    f"{result['packet_loss_percent']:.1f}% loss"
                )

                if result["packets_received"] > 0:
                    content += (
                        f", RTT min/avg/max = "
                        f"{result['min_rtt_ms']:.1f}/"
                        f"{result['avg_rtt_ms']:.1f}/"
                        f"{result['max_rtt_ms']:.1f} ms"
                    )

                return format_tool_result(
                    content=content,
                    is_error=result["packet_loss_percent"] >= 100,
                    meta={
                        "device_id": device_id,
                        **result,
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
    async def run_traceroute(
        device_id: str,
        address: str,
        count: int = 1,
    ) -> dict[str, Any]:
        """Run traceroute to show network path to destination.

        Use when:
        - User asks "trace route to X" or "show me path to Y"
        - Troubleshooting routing issues (finding where packets go)
        - Identifying network hops
        - Measuring latency per hop
        - Diagnosing routing loops or suboptimal paths

        Returns: List of hops with hop number, IP address, and RTT.

        Constraints:
        - Max 30 hops
        - Max 3 probes per hop (count parameter)

        Tip: Some hops may not respond (shown as * in results).

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            address: Target IP address or hostname (e.g., '8.8.8.8')
            count: Number of probes per hop (default 1, max 3)

        Returns:
            Formatted tool result with traceroute hops
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                diagnostics_service = DiagnosticsService(session, settings)

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
                    tool_name="tool/traceroute",
                )

                # Run traceroute
                result = await diagnostics_service.traceroute(device_id, address, count)

                hop_count = len(result["hops"])
                content = f"Traceroute to {result['target']} completed in {hop_count} hops"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        **result,
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

    logger.info("Registered diagnostics tools")
