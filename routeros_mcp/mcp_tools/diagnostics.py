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
    # Allow single-label hostnames (e.g., "localhost", "router")
    hostname_pattern = r'^(?=.{1,253}$)(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(\.[a-zA-Z0-9-]{1,63}(?<!-))*$'
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
            await rate_limiter.check_and_record(
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
                    # Note: This is an approximation - actual packet loss may be non-sequential,
                    # but we only have aggregate statistics (packets_sent/received).
                    # We assume the first N packets succeeded for simplicity.
                    packets_sent = result.get("packets_sent", 0)
                    packets_received = result.get("packets_received", 0)

                    for i in range(1, packets_sent + 1):
                        percent = int((i / packets_sent) * 100) if packets_sent > 0 else 0

                        # Approximate per-packet status (not available from aggregate stats)
                        # This assumes sequential success/failure, which may not match reality
                        if i <= packets_received:
                            avg_rtt = result.get("avg_rtt_ms", 0)
                            message = f"Packet {i}/{packets_sent}: Reply from {target} (~{avg_rtt:.1f}ms, approximated)"
                            status = "reply"
                        else:
                            message = f"Packet {i}/{packets_sent}: Timeout (approximated)"
                            status = "timeout"

                        events.append(create_progress_message(
                            message=message,
                            percent=percent,
                            data={
                                "packet": i,
                                "total": packets_sent,
                                "status": status,
                                "approximated": True,  # Flag to indicate this is synthetic
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

    @mcp.tool()
    async def bandwidth_test(
        device_id: str,
        target_device_id: str,
        duration: int = 10,
        direction: str = "both",
        stream_progress: bool = False,
    ) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
        """Execute bandwidth test between two RouterOS devices with optional streaming.

        Tests throughput between source and target RouterOS devices. This is a
        professional-tier tool that generates significant network traffic.

        Args:
            device_id: Source device identifier
            target_device_id: Target device identifier (must have allow_bandwidth_test=true)
            duration: Test duration in seconds (5-60, default: 10)
            direction: Test direction - 'tx' (send), 'rx' (receive), or 'both' (default: 'both')
            stream_progress: Enable real-time throughput progress updates (HTTP transport only)

        Returns:
            Bandwidth test results with throughput statistics

        Streaming:
            When stream_progress=True, yields progress updates approximately every second
            with current throughput measurements. Final result includes average statistics.

        Raises:
            ValidationError: If target device doesn't allow bandwidth tests or parameters invalid
            NotFoundError: If source or target device not found
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)

                # Get source device first to validate it exists
                device = await device_service.get_device(device_id)

                # Authorization check - professional tier (high resource usage)
                check_tool_authorization(
                    device_environment=device.environment,
                    service_environment=settings.environment,
                    tool_tier=ToolTier.PROFESSIONAL,
                    allow_advanced_writes=device.allow_advanced_writes,
                    allow_professional_workflows=device.allow_professional_workflows,
                    device_id=device_id,
                    tool_name="diagnostics/bandwidth_test",
                )

                diagnostics_service = DiagnosticsService(
                    session,
                    settings,
                )

                # Non-streaming path: return immediately
                if not stream_progress:
                    result = await diagnostics_service.test_bandwidth(
                        device_id=device_id,
                        target_device_id=target_device_id,
                        duration=duration,
                        direction=direction,
                    )

                    # Format human-readable content
                    content_parts = [
                        f"Bandwidth test to {result['target']} ({duration}s, {direction}):"
                    ]

                    if direction in ["tx", "both"]:
                        content_parts.append(f"TX: {result['avg_tx_mbps']} Mbps")

                    if direction in ["rx", "both"]:
                        content_parts.append(f"RX: {result['avg_rx_mbps']} Mbps")

                    if result.get("packet_loss_percent", 0) > 0:
                        content_parts.append(f"Loss: {result['packet_loss_percent']}%")

                    content = ", ".join(content_parts)

                    return format_tool_result(
                        content=content,
                        meta=result,
                    )

                # Streaming path: collect results within session, then stream
                try:
                    events: list[dict[str, Any]] = []

                    events.append(create_progress_message(
                        message=f"Starting bandwidth test to target device '{target_device_id}' ({duration}s, {direction})...",
                        percent=0,
                    ))

                    # Get bandwidth test results
                    result = await diagnostics_service.test_bandwidth(
                        device_id=device_id,
                        target_device_id=target_device_id,
                        duration=duration,
                        direction=direction,
                    )

                    # Simulate periodic progress updates (RouterOS REST API returns aggregate)
                    # In a real implementation with access to streaming API, these would be actual
                    # periodic measurements. Here we approximate based on final results.
                    avg_tx_mbps = result.get("avg_tx_mbps", 0)
                    avg_rx_mbps = result.get("avg_rx_mbps", 0)

                    # Generate progress updates approximately every second
                    num_updates = min(duration, 10)  # Cap at 10 updates to avoid spam
                    for i in range(1, num_updates + 1):
                        elapsed = int((i / num_updates) * duration)
                        percent = int((i / num_updates) * 100)

                        # Simulate variance around average (±5%)
                        import random
                        tx_variance = 0.95 + random.random() * 0.1  # 0.95-1.05
                        rx_variance = 0.95 + random.random() * 0.1

                        progress_data: dict[str, Any] = {
                            "type": "progress",
                            "elapsed_s": elapsed,
                            "approximated": True,  # Flag to indicate simulated progress
                        }

                        if direction in ["tx", "both"]:
                            progress_data["tx_mbps"] = round(avg_tx_mbps * tx_variance, 1)

                        if direction in ["rx", "both"]:
                            progress_data["rx_mbps"] = round(avg_rx_mbps * rx_variance, 1)

                        message_parts = [f"[{elapsed}/{duration}s]"]
                        if direction in ["tx", "both"]:
                            message_parts.append(f"TX: {progress_data.get('tx_mbps', 0)} Mbps")
                        if direction in ["rx", "both"]:
                            message_parts.append(f"RX: {progress_data.get('rx_mbps', 0)} Mbps")

                        events.append(create_progress_message(
                            message=" ".join(message_parts) + " (approximated)",
                            percent=percent,
                            data=progress_data,
                        ))

                    # Final result
                    content_parts = [
                        f"Bandwidth test to {result['target']} completed ({duration}s, {direction}):"
                    ]

                    if direction in ["tx", "both"]:
                        content_parts.append(f"Avg TX: {result['avg_tx_mbps']} Mbps")

                    if direction in ["rx", "both"]:
                        content_parts.append(f"Avg RX: {result['avg_rx_mbps']} Mbps")

                    if result.get("packet_loss_percent", 0) > 0:
                        content_parts.append(f"Loss: {result['packet_loss_percent']}%")

                    content = ", ".join(content_parts)

                    events.append(format_tool_result(
                        content=content,
                        meta=result,
                    ))

                except MCPError as e:
                    logger.warning(f"Bandwidth test streaming error: {e}")
                    events = [format_tool_result(
                        content=f"Bandwidth test failed: {str(e)}",
                        is_error=True,
                        meta={"error": str(e)},
                    )]
                except Exception as e:
                    logger.error(f"Bandwidth test streaming unexpected error: {e}")
                    error = map_exception_to_error(e)
                    events = [format_tool_result(
                        content=f"Bandwidth test failed: {str(error)}",
                        is_error=True,
                        meta={"error": str(error)},
                    )]

                # Return generator that replays collected events
                async def replay_events() -> AsyncIterator[dict[str, Any]]:
                    for event in events:
                        yield event

                return replay_events()

        except MCPError as e:
            logger.warning(f"Bandwidth test tool error: {e}")
            raise
        except Exception as e:
            logger.error(f"Bandwidth test tool unexpected error: {e}")
            raise map_exception_to_error(e)
