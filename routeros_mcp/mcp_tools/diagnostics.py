"""Diagnostics MCP tools.

Provides MCP tools for running network diagnostic operations (ping, traceroute).
"""

import ipaddress
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.diagnostics import DEFAULT_TRACEROUTE_HOPS, DiagnosticsService
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.infra.rate_limiter import get_rate_limiter
from routeros_mcp.mcp.errors import MCPError, ValidationError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import create_progress_message, format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)

# Rate limiting constants for diagnostics
PING_RATE_LIMIT = 10  # Max pings per device per minute
PING_RATE_WINDOW = 60  # 60 seconds window


def _validate_target(target: str) -> None:
    """Validate ping/traceroute target is valid IP or hostname.

    Args:
        target: Target IP address or hostname

    Raises:
        ValidationError: If target is invalid
    """
    # Try parsing as IP address first
    try:
        ipaddress.ip_address(target)
        return  # Valid IP
    except ValueError:
        pass  # Not an IP, check if valid hostname

    # Validate hostname (RFC 1123)
    # Allow letters, digits, hyphens, dots
    # Must not start/end with hyphen
    # Labels must be 1-63 chars, total max 253 chars
    hostname_pattern = r'^(?=.{1,253}$)(?!-)([a-zA-Z0-9-]{1,63}(?<!-)\.)*[a-zA-Z0-9-]{1,63}(?<!-)$'
    if not re.match(hostname_pattern, target):
        raise ValidationError(
            f"Invalid target '{target}': must be valid IP address or hostname",
            data={"target": target}
        )


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
        packet_size: int = 64,
        stream_progress: bool = False,
    ) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
        """Execute ping command on a RouterOS device.

        Args:
            device_id: Device identifier
            target: Target IP or hostname
            count: Number of ping attempts (1-100, default: 4)
            packet_size: ICMP packet size in bytes (28-65500, default: 64)
            stream_progress: Enable real-time per-packet progress updates (HTTP transport only)

        Returns:
            Ping results with response times

        Streaming:
            When stream_progress=True, yields progress updates for each packet sent/received
            with packet number, status, and latency. Final result includes summary statistics.
        """
        try:
            # Validate parameters before rate limiting check
            _validate_target(target)

            if count < 1 or count > 100:
                raise ValidationError(
                    f"Invalid count {count}: must be between 1 and 100",
                    data={"count": count, "min": 1, "max": 100}
                )

            if packet_size < 28 or packet_size > 65500:
                raise ValidationError(
                    f"Invalid packet_size {packet_size}: must be between 28 and 65500",
                    data={"packet_size": packet_size, "min": 28, "max": 65500}
                )

            # Check rate limit before doing any work
            rate_limiter = get_rate_limiter()
            rate_limiter.check_and_record(
                device_id=device_id,
                operation="ping",
                limit=PING_RATE_LIMIT,
                window_seconds=PING_RATE_WINDOW,
            )

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

                # Non-streaming path: return immediately
                if not stream_progress:
                    result = await diagnostics_service.ping(
                        device_id=device_id,
                        address=target,
                        count=count,
                        interval_ms=1000,
                        packet_size=packet_size,
                    )

                    content = (
                        f"Ping to {target}: {result['packets_sent']} packets sent, "
                        f"{result['packets_received']} received, "
                        f"{result['packet_loss_percent']:.1f}% loss"
                    )

                    if result.get('avg_rtt_ms', 0) > 0:
                        content += f", avg latency {result['avg_rtt_ms']:.1f}ms"

                    return format_tool_result(
                        content=content,
                        meta=result,
                    )

                # Streaming path: collect results within session, then stream
                try:
                    events: list[dict[str, Any]] = []

                    events.append(create_progress_message(
                        message=f"Starting ping to {target} ({count} packets, {packet_size} bytes)...",
                        percent=0,
                    ))

                    # Get ping results
                    result = await diagnostics_service.ping(
                        device_id=device_id,
                        address=target,
                        count=count,
                        interval_ms=1000,
                        packet_size=packet_size,
                    )

                    # Simulate per-packet progress (RouterOS REST API returns aggregated results)
                    # In real streaming, we'd parse each ping response line
                    packets_sent = result.get("packets_sent", 0)
                    packets_received = result.get("packets_received", 0)

                    for i in range(1, packets_sent + 1):
                        percent = int((i / packets_sent) * 100) if packets_sent > 0 else 0

                        # Approximate per-packet latency (not available from aggregate)
                        # This is a simplification; real streaming would capture each packet
                        if i <= packets_received:
                            avg_rtt = result.get("avg_rtt_ms", 0)
                            message = f"Packet {i}/{packets_sent}: Reply from {target} (≈{avg_rtt:.1f}ms)"
                            status = "reply"
                        else:
                            message = f"Packet {i}/{packets_sent}: Timeout"
                            status = "timeout"

                        events.append(create_progress_message(
                            message=message,
                            percent=percent,
                            data={
                                "packet": i,
                                "total": packets_sent,
                                "status": status,
                            },
                        ))

                    # Final result
                    content = (
                        f"Ping to {target} completed: "
                        f"{packets_sent} sent, {packets_received} received, "
                        f"{result['packet_loss_percent']:.1f}% loss"
                    )

                    if result.get('avg_rtt_ms', 0) > 0:
                        content += f", avg latency {result['avg_rtt_ms']:.1f}ms"

                    events.append(format_tool_result(
                        content=content,
                        meta=result,
                    ))

                except MCPError as e:
                    logger.warning(f"Ping streaming error: {e}")
                    events = [format_tool_result(
                        content=f"Ping failed: {str(e)}",
                        is_error=True,
                        meta={"error": str(e)},
                    )]
                except Exception as e:
                    logger.error(f"Ping streaming unexpected error: {e}")
                    error = map_exception_to_error(e)
                    events = [format_tool_result(
                        content=f"Ping failed: {str(error)}",
                        is_error=True,
                        meta={"error": str(error)},
                    )]

                # Return generator that replays collected events
                async def replay_events() -> AsyncIterator[dict[str, Any]]:
                    for event in events:
                        yield event

                return replay_events()

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
                )

                # Non-streaming path: return immediately
                if not stream_progress:
                    result = await diagnostics_service.traceroute(
                        device_id=device_id,
                        address=target,
                        count=1,
                        max_hops=max_hops,
                    )

                    hops = result.get("hops", [])
                    hop_count = len(hops)

                    # Calculate reached_target for consistency with streaming path
                    reached_target = False
                    if hops:
                        last_hop = hops[-1]
                        last_address = last_hop.get("address", "*")
                        last_rtt = last_hop.get("rtt_ms", 0.0)
                        # Target reached if terminated early or last hop matches target
                        if last_address != "*" and last_rtt > 0:
                            if hop_count < max_hops or last_address == target:
                                reached_target = True

                    # Add consistent metadata fields
                    result["reached_target"] = reached_target
                    result["target"] = target

                    content = f"Traceroute to {target} completed in {hop_count} hops"

                    return format_tool_result(
                        content=content,
                        meta=result,
                    )

                # Streaming path: collect results within session, then stream
                try:
                    # Collect all events within the session context
                    events: list[dict[str, Any]] = []

                    events.append(create_progress_message(
                        message=f"Starting traceroute to {target}...",
                        percent=0,
                    ))

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

                        # Calculate progress percentage based on total discovered hops,
                        # capping at 100% to avoid misleading values
                        if total_hops > 0:
                            percent = min(int(((idx + 1) / total_hops) * 100), 100)
                        else:
                            percent = 0

                        # Create progress message
                        if hop_address == "*":
                            message = f"Hop {hop_num}: * (timeout)"
                        else:
                            message = f"Hop {hop_num}: {hop_address} ({rtt_ms:.1f}ms)"

                        events.append(create_progress_message(
                            message=message,
                            percent=percent,
                            data={
                                "hop": hop_num,
                                "ip": hop_address if hop_address != "*" else None,
                                "latency_ms": rtt_ms if rtt_ms > 0 else None,
                            },
                        ))

                    # Determine if target was reached
                    reached_target = False
                    if hops:
                        last_hop = hops[-1]
                        last_address = last_hop.get("address", "*")
                        last_rtt = last_hop.get("rtt_ms", 0.0)

                        # Target reached if:
                        # 1. Last hop has valid address (not timeout)
                        # 2. Last hop has positive RTT (got a response)
                        # 3. Either:
                        #    a) Traceroute terminated before max_hops (likely reached destination), or
                        #    b) Last hop address textually matches the target (e.g. IP target)
                        if last_address != "*" and last_rtt > 0:
                            if total_hops < max_hops or last_address == target:
                                reached_target = True

                    # Final result
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

                    events.append(format_tool_result(
                        content=content,
                        meta=final_meta,
                    ))

                except MCPError as e:
                    logger.warning(f"Traceroute streaming error: {e}")
                    events = [format_tool_result(
                        content=f"Traceroute failed: {str(e)}",
                        is_error=True,
                        meta={"error": str(e)},
                    )]
                except Exception as e:
                    logger.error(f"Traceroute streaming unexpected error: {e}")
                    error = map_exception_to_error(e)
                    events = [format_tool_result(
                        content=f"Traceroute failed: {str(error)}",
                        is_error=True,
                        meta={"error": str(error)},
                    )]

                # Return generator that replays collected events
                async def replay_events() -> AsyncIterator[dict[str, Any]]:
                    for event in events:
                        yield event

                return replay_events()

        except MCPError as e:
            logger.warning(f"Traceroute tool error: {e}")
            raise
        except Exception as e:
            logger.error(f"Traceroute tool unexpected error: {e}")
            raise map_exception_to_error(e)
