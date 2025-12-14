"""Diagnostics service for network diagnostic operations.

Provides operations for running RouterOS diagnostic tools like ping and traceroute.
"""

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.routeros.exceptions import (
    RouterOSClientError,
    RouterOSNetworkError,
    RouterOSSSHError,
    RouterOSServerError,
    RouterOSTimeoutError,
)

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
        """Run ICMP ping test from the router to a target address with REST→SSH fallback."""
        from routeros_mcp.mcp.errors import AuthenticationError, ValidationError

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

        rest_error: Exception | None = None

        # Attempt REST first
        try:
            result = await self._ping_via_rest(device_id, address, count, interval_ms)
            result["transport"] = "rest"
            result["fallback_used"] = False
            result["rest_error"] = None
            return result
        except (AuthenticationError, RouterOSTimeoutError, RouterOSNetworkError, RouterOSServerError, RouterOSClientError, Exception) as exc:  # noqa: BLE001
            rest_error = exc
            logger.warning(
                "REST ping failed, attempting SSH fallback",
                exc_info=exc,
                extra={"device_id": device_id, "address": address},
            )

        # SSH fallback
        try:
            result = await self._ping_via_ssh(device_id, address, count, interval_ms)
            result["transport"] = "ssh"
            result["fallback_used"] = True
            result["rest_error"] = str(rest_error) if rest_error else None
            return result
        except (RouterOSSSHError, Exception) as ssh_exc:  # noqa: BLE001
            logger.error(
                "Ping failed via REST and SSH",
                exc_info=ssh_exc,
                extra={"device_id": device_id, "address": address, "rest_error": str(rest_error)},
            )
            raise

    async def _ping_via_rest(
        self,
        device_id: str,
        address: str,
        count: int,
        interval_ms: int,
    ) -> dict[str, Any]:
        client = await self.device_service.get_rest_client(device_id)

        try:
            ping_params = {
                "address": address,
                "count": count,
                "interval": f"{interval_ms}ms",
            }

            ping_data = await client.post("/rest/tool/ping", ping_params)
            return self._parse_rest_ping_result(address, ping_data)
        finally:
            await client.close()

    @staticmethod
    def _parse_rest_ping_result(address: str, ping_data: Any) -> dict[str, Any]:
        packets_sent = 0
        packets_received = 0
        rtts: list[float] = []

        if isinstance(ping_data, list):
            for result in ping_data:
                if isinstance(result, dict):
                    packets_sent += 1
                    if result.get("status") == "echo reply" or "time" in result:
                        packets_received += 1
                        time_str = result.get("time", "0ms")
                        if isinstance(time_str, str):
                            rtt_ms = float(time_str.rstrip("ms"))
                        else:
                            rtt_ms = float(time_str)
                        rtts.append(rtt_ms)

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

    async def _ping_via_ssh(
        self,
        device_id: str,
        address: str,
        count: int,
        interval_ms: int,
    ) -> dict[str, Any]:
        ssh_client = await self.device_service.get_ssh_client(device_id)
        try:
            # Use /tool/ping for consistency with CLI output formatting; interval in ms
            command = f"/tool/ping address={address} count={count} interval={interval_ms}ms"
            output = await ssh_client.execute(command)
            logger.debug(
                "SSH ping output",
                extra={
                    "device_id": device_id,
                    "address": address,
                    "command": command,
                    "output_preview": output[:500],
                    "output_len": len(output),
                },
            )
            return self._parse_ssh_ping_output(address, output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_ssh_ping_output(address: str, output: str) -> dict[str, Any]:
        packets_sent = 0
        packets_received = 0
        rtts: list[float] = []

        summary_match = re.search(
            r"sent=(?P<sent>\d+)\s+received=(?P<recv>\d+)\s+packet-loss=(?P<loss>\d+)%\s+"
            r"min-rtt=(?P<min>[0-9a-zA-Z.]+)\s+avg-rtt=(?P<avg>[0-9a-zA-Z.]+)\s+max-rtt=(?P<max>[0-9a-zA-Z.]+)",
            output,
            re.IGNORECASE,
        )

        if summary_match:
            packets_sent = int(summary_match.group("sent"))
            packets_received = int(summary_match.group("recv"))
            packet_loss_percent = float(summary_match.group("loss"))
            min_rtt_ms = DiagnosticsService._parse_rtt_ms(summary_match.group("min"))
            avg_rtt_ms = DiagnosticsService._parse_rtt_ms(summary_match.group("avg"))
            max_rtt_ms = DiagnosticsService._parse_rtt_ms(summary_match.group("max"))
            return {
                "host": address,
                "packets_sent": packets_sent,
                "packets_received": packets_received,
                "packet_loss_percent": packet_loss_percent,
                "min_rtt_ms": min_rtt_ms,
                "avg_rtt_ms": avg_rtt_ms,
                "max_rtt_ms": max_rtt_ms,
            }

        # Fallback: derive stats from per-ping lines (time=xyz or timeout)
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            time_match = re.search(r"time=([0-9a-zA-Z.]+)", line)
            if time_match:
                packets_sent += 1
                packets_received += 1
                rtts.append(DiagnosticsService._parse_rtt_ms(time_match.group(1)))
                continue

            # Some RouterOS outputs omit 'time=' and show e.g. '5ms945us'
            inline_match = re.search(r"([0-9]+(?:\.[0-9]+)?ms[0-9]*us|[0-9]+(?:\.[0-9]+)?ms|[0-9]+us)", line)
            if inline_match:
                packets_sent += 1
                packets_received += 1
                rtts.append(DiagnosticsService._parse_rtt_ms(inline_match.group(1)))
                continue

            if "timeout" in line.lower():
                packets_sent += 1

        packet_loss_percent = (
            ((packets_sent - packets_received) / packets_sent * 100)
            if packets_sent > 0
            else 100.0
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

    @staticmethod
    def _parse_rtt_ms(value: str) -> float:
        """Parse RouterOS RTT strings such as '5ms', '6.2ms', '5ms945us', or '945us' into milliseconds."""

        if not value:
            return 0.0

        match = re.match(r"(?:(?P<ms>[0-9]*\.?[0-9]+)ms)?(?P<us>[0-9]+)?us?", value)
        if match:
            ms_part = float(match.group("ms")) if match.group("ms") else 0.0
            us_part = float(match.group("us")) / 1000.0 if match.group("us") else 0.0
            return ms_part + us_part

        # Fallback: try plain float (assume milliseconds)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    async def traceroute(
        self,
        device_id: str,
        address: str,
        count: int = 1,
    ) -> dict[str, Any]:
        """Run traceroute to show network path with REST→SSH fallback."""
        from routeros_mcp.mcp.errors import AuthenticationError, ValidationError

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

        rest_error: Exception | None = None

        # REST first
        try:
            result = await self._traceroute_via_rest(device_id, address, count)
            result["transport"] = "rest"
            result["fallback_used"] = False
            result["rest_error"] = None
            return result
        except (AuthenticationError, RouterOSTimeoutError, RouterOSNetworkError, RouterOSServerError, RouterOSClientError, Exception) as exc:  # noqa: BLE001
            rest_error = exc
            logger.warning(
                "REST traceroute failed, attempting SSH fallback",
                exc_info=exc,
                extra={"device_id": device_id, "address": address},
            )

        # SSH fallback
        try:
            result = await self._traceroute_via_ssh(device_id, address, count)
            result["transport"] = "ssh"
            result["fallback_used"] = True
            result["rest_error"] = str(rest_error) if rest_error else None
            return result
        except (RouterOSSSHError, Exception) as ssh_exc:  # noqa: BLE001
            logger.error(
                "Traceroute failed via REST and SSH",
                exc_info=ssh_exc,
                extra={"device_id": device_id, "address": address, "rest_error": str(rest_error)},
            )
            raise

    async def _traceroute_via_rest(
        self,
        device_id: str,
        address: str,
        count: int,
    ) -> dict[str, Any]:
        client = await self.device_service.get_rest_client(device_id)

        try:
            trace_params = {
                "address": address,
                "count": count,
            }

            trace_data = await client.post("/rest/tool/traceroute", trace_params)
            hops = self._parse_rest_traceroute(trace_data)
            return {
                "target": address,
                "hops": hops,
            }
        finally:
            await client.close()

    @staticmethod
    def _parse_rest_traceroute(trace_data: Any) -> list[dict[str, Any]]:
        hops: list[dict[str, Any]] = []

        if isinstance(trace_data, list):
            for result in trace_data:
                if isinstance(result, dict):
                    hop_num = result.get("hop", 0)
                    hop_address = result.get("address", "*")

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

        return hops

    async def _traceroute_via_ssh(
        self,
        device_id: str,
        address: str,
        count: int,
    ) -> dict[str, Any]:
        ssh_client = await self.device_service.get_ssh_client(device_id)
        try:
            command = f"/tool/traceroute address={address} count={count}"
            output = await ssh_client.execute(command)
            hops = self._parse_ssh_traceroute_output(output)
            return {
                "target": address,
                "hops": hops,
            }
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_ssh_traceroute_output(output: str) -> list[dict[str, Any]]:
        hops: list[dict[str, Any]] = []
        hop_pattern = re.compile(r"^\s*(?P<hop>\d+)\s+(?P<addr>\S+)", re.IGNORECASE)

        for line in output.splitlines():
            line = line.strip()
            if not line or line.lower().startswith(('#', 'address', 'host', 'loss', 'sent')):
                continue

            match = hop_pattern.match(line)
            if match:
                hop_num = int(match.group("hop"))
                hop_address = match.group("addr")
                rtt_match = re.search(r"([0-9.]+)ms", line)
                rtt_ms = float(rtt_match.group(1)) if rtt_match else 0.0
                hops.append({
                    "hop": hop_num,
                    "address": hop_address,
                    "rtt_ms": rtt_ms,
                })
                continue

            # Handle lines with timeout markers (no RTT)
            timeout_match = re.match(r"^\s*(?P<hop>\d+)\s+(?P<addr>\S+).*timeout", line, re.IGNORECASE)
            if timeout_match:
                hop_num = int(timeout_match.group("hop"))
                hop_address = timeout_match.group("addr")
                hops.append({
                    "hop": hop_num,
                    "address": hop_address,
                    "rtt_ms": 0.0,
                })

        return hops
