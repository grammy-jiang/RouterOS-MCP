"""Diagnostics MCP tools.

Provides MCP tools for running network diagnostic operations (ping, traceroute).
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.diagnostics import DEFAULT_TRACEROUTE_HOPS, DiagnosticsService
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import create_progress_message, format_tool_result
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
        max_hops: int = DEFAULT_TRACEROUTE_HOPS,
        timeout_seconds: int = 60,
        stream_progress: bool = False,
    ) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
        """Execute traceroute command on a RouterOS device with optional streaming.

        Args:
            device_id: Device identifier
            target: Target IP or hostname
            max_hops: Maximum hops to trace (1-64, default: 30)
            timeout_seconds: Command timeout in seconds (default: 60)
            stream_progress: Enable real-time per-hop progress updates (HTTP transport only)

        Returns:
            Traceroute hop information with final result

        Streaming:
            When stream_progress=True, yields progress updates for each hop discovered
            with hop number, IP address, and latency. Final result includes all hops
            and whether the target was reached.
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

                # Non-streaming path: return immediately
                if not stream_progress:
                    result = await diagnostics_service.traceroute(
                        device_id=device_id,
                        address=target,
                        count=1,
                        max_hops=max_hops,
                    )

                    hop_count = len(result.get("hops", []))
                    content = f"Traceroute to {target} completed in {hop_count} hops"

                    return format_tool_result(
                        content=content,
                        meta=result,
                    )

                # Streaming path: yield progress updates
                async def stream_traceroute_progress() -> AsyncIterator[dict[str, Any]]:
                    """Stream traceroute progress with per-hop updates."""
                    try:
                        yield create_progress_message(
                            message=f"Starting traceroute to {target}...",
                            percent=0,
                        )

                        # Get traceroute results
                        result = await diagnostics_service.traceroute(
                            device_id=device_id,
                            address=target,
                            count=1,
                            max_hops=max_hops,
                        )

                        hops = result.get("hops", [])
                        total_hops = len(hops)
                        
                        # Yield progress for each hop
                        for idx, hop in enumerate(hops):
                            hop_num = hop.get("hop", idx + 1)
                            hop_address = hop.get("address", "*")
                            rtt_ms = hop.get("rtt_ms", 0.0)
                            
                            # Calculate progress percentage
                            percent = int(((idx + 1) / max(total_hops, 1)) * 100)
                            
                            # Create progress message
                            if hop_address == "*":
                                message = f"Hop {hop_num}: * (timeout)"
                            else:
                                message = f"Hop {hop_num}: {hop_address} ({rtt_ms:.1f}ms)"
                            
                            yield create_progress_message(
                                message=message,
                                percent=percent,
                                data={
                                    "hop": hop_num,
                                    "ip": hop_address if hop_address != "*" else None,
                                    "latency_ms": rtt_ms if rtt_ms > 0 else None,
                                },
                            )

                        # Determine if target was reached
                        reached_target = False
                        if hops:
                            last_hop = hops[-1]
                            # Target reached if last hop has valid address that matches target or got response
                            reached_target = (
                                last_hop.get("address") != "*" 
                                and last_hop.get("rtt_ms", 0.0) > 0
                            )

                        # Yield final result
                        final_meta = {
                            "hops": hops,
                            "total_hops": total_hops,
                            "reached_target": reached_target,
                            "target": target,
                        }
                        
                        content = (
                            f"Traceroute to {target} completed: "
                            f"{total_hops} hops, "
                            f"{'reached' if reached_target else 'not reached'}"
                        )

                        yield format_tool_result(
                            content=content,
                            meta=final_meta,
                        )

                    except MCPError as e:
                        logger.warning(f"Traceroute streaming error: {e}")
                        yield format_tool_result(
                            content=f"Traceroute failed: {str(e)}",
                            is_error=True,
                            meta={"error": str(e)},
                        )
                    except Exception as e:
                        logger.error(f"Traceroute streaming unexpected error: {e}")
                        error = map_exception_to_error(e)
                        yield format_tool_result(
                            content=f"Traceroute failed: {str(error)}",
                            is_error=True,
                            meta={"error": str(error)},
                        )

                return stream_traceroute_progress()

        except MCPError as e:
            logger.warning(f"Traceroute tool error: {e}")
            raise
        except Exception as e:
            logger.error(f"Traceroute tool unexpected error: {e}")
            raise map_exception_to_error(e)
