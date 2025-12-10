"""Diagnostics service for network diagnostic operations.

Provides operations for running RouterOS diagnostic tools like ping and traceroute.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService

logger = logging.getLogger(__name__)

# Safety limits
MAX_PING_COUNT = 10
MAX_TRACEROUTE_HOPS = 30
MAX_TRACEROUTE_COUNT = 3


class DiagnosticsService:
    """Service for RouterOS diagnostic operations.

    Responsibilities:
    - Run ping tests with safety limits
    - Run traceroute with safety limits
    - Normalize RouterOS diagnostic responses
    - Enforce resource usage limits

    Example:
        async with get_session() as session:
            service = DiagnosticsService(session, settings)

            # Run ping
            ping_result = await service.ping("dev-lab-01", "8.8.8.8", count=4)

            # Run traceroute
            trace_result = await service.traceroute("dev-lab-01", "8.8.8.8")
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize diagnostics service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def ping(
        self,
        device_id: str,
        address: str,
        count: int = 4,
        interval_ms: int = 1000,
    ) -> dict[str, Any]:
        """Run ICMP ping test from the router to a target address.

        Args:
            device_id: Device identifier
            address: Target IP address or hostname
            count: Number of pings (max 10)
            interval_ms: Interval between pings in milliseconds

        Returns:
            Ping result dictionary with statistics

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValidationError: If count exceeds maximum
        """
        from routeros_mcp.mcp.errors import ValidationError

        await self.device_service.get_device(device_id)

        # Enforce safety limit
        if count > MAX_PING_COUNT:
            raise ValidationError(
                f"Ping count cannot exceed {MAX_PING_COUNT}",
                data={"requested_count": count, "max_count": MAX_PING_COUNT},
            )

        if count < 1:
            raise ValidationError(
                "Ping count must be at least 1",
                data={"requested_count": count},
            )

        client = await self.device_service.get_rest_client(device_id)

        try:
            # Run ping
            ping_params = {
                "address": address,
                "count": count,
                "interval": f"{interval_ms}ms",
            }
            
            ping_data = await client.post("/rest/tool/ping", ping_params)

            # Parse ping results
            # RouterOS returns array of individual ping results
            packets_sent = 0
            packets_received = 0
            rtts: list[float] = []

            if isinstance(ping_data, list):
                for result in ping_data:
                    if isinstance(result, dict):
                        packets_sent += 1
                        if result.get("status") == "echo reply" or "time" in result:
                            packets_received += 1
                            # Parse RTT
                            time_str = result.get("time", "0ms")
                            if isinstance(time_str, str):
                                rtt_ms = float(time_str.rstrip("ms"))
                            else:
                                rtt_ms = float(time_str)
                            rtts.append(rtt_ms)

            # Calculate statistics
            packet_loss_percent = (
                ((packets_sent - packets_received) / packets_sent * 100)
                if packets_sent > 0
                else 0.0
            )

            min_rtt_ms = min(rtts) if rtts else 0.0
            max_rtt_ms = max(rtts) if rtts else 0.0
            avg_rtt_ms = sum(rtts) / len(rtts) if rtts else 0.0

            return {
                "host": address,
                "packets_sent": packets_sent,
                "packets_received": packets_received,
                "packet_loss_percent": packet_loss_percent,
                "min_rtt_ms": min_rtt_ms,
                "avg_rtt_ms": avg_rtt_ms,
                "max_rtt_ms": max_rtt_ms,
            }

        finally:
            await client.close()

    async def traceroute(
        self,
        device_id: str,
        address: str,
        count: int = 1,
    ) -> dict[str, Any]:
        """Run traceroute to show network path to destination.

        Args:
            device_id: Device identifier
            address: Target IP address or hostname
            count: Number of probes per hop (max 3)

        Returns:
            Traceroute result dictionary with hops

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValidationError: If count exceeds maximum
        """
        from routeros_mcp.mcp.errors import ValidationError

        await self.device_service.get_device(device_id)

        # Enforce safety limit
        if count > MAX_TRACEROUTE_COUNT:
            raise ValidationError(
                f"Traceroute count cannot exceed {MAX_TRACEROUTE_COUNT}",
                data={"requested_count": count, "max_count": MAX_TRACEROUTE_COUNT},
            )

        if count < 1:
            raise ValidationError(
                "Traceroute count must be at least 1",
                data={"requested_count": count},
            )

        client = await self.device_service.get_rest_client(device_id)

        try:
            # Run traceroute
            # Note: MAX_TRACEROUTE_HOPS is enforced by RouterOS itself (default 30)
            # The RouterOS API automatically limits the number of hops
            trace_params = {
                "address": address,
                "count": count,
            }
            
            trace_data = await client.post("/rest/tool/traceroute", trace_params)

            # Parse traceroute results
            hops: list[dict[str, Any]] = []
            
            if isinstance(trace_data, list):
                for result in trace_data:
                    if isinstance(result, dict):
                        hop_num = result.get("hop", 0)
                        hop_address = result.get("address", "*")
                        
                        # Parse RTT
                        time_str = result.get("time", "")
                        if time_str and isinstance(time_str, str):
                            try:
                                rtt_ms = float(time_str.rstrip("ms"))
                            except (ValueError, AttributeError):
                                rtt_ms = 0.0
                        else:
                            rtt_ms = 0.0

                        hops.append({
                            "hop": hop_num,
                            "address": hop_address,
                            "rtt_ms": rtt_ms,
                        })

            return {
                "target": address,
                "hops": hops,
            }

        finally:
            await client.close()
