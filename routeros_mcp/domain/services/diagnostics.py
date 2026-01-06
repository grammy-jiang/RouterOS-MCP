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
MAX_PING_COUNT = 100  # Updated to match Phase 4 requirement (1-100)
MAX_TRACEROUTE_HOPS = 64  # Updated to match requirement (1-64)
MAX_TRACEROUTE_COUNT = 3
DEFAULT_TRACEROUTE_HOPS = 30  # Default max hops for traceroute
MIN_BANDWIDTH_TEST_DURATION = 5  # Minimum bandwidth test duration (seconds)
MAX_BANDWIDTH_TEST_DURATION = 60  # Maximum bandwidth test duration (seconds)


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
        packet_size: int = 64,
    ) -> dict[str, Any]:
        """Run ICMP ping test from the router to a target address with REST→SSH fallback.

        Args:
            device_id: Device identifier
            address: Target IP or hostname
            count: Number of pings (1-100)
            interval_ms: Interval between pings in milliseconds
            packet_size: ICMP packet size in bytes (28-65500)
        """
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
            result = await self._ping_via_rest(device_id, address, count, interval_ms, packet_size)
            result["transport"] = "rest"
            result["fallback_used"] = False
            result["rest_error"] = None
            return result
        except (
            AuthenticationError,
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as exc:  # noqa: BLE001
            rest_error = exc
            logger.warning(
                "REST ping failed, attempting SSH fallback",
                exc_info=exc,
                extra={"device_id": device_id, "address": address},
            )

        # SSH fallback
        try:
            result = await self._ping_via_ssh(device_id, address, count, interval_ms, packet_size)
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
        packet_size: int,
    ) -> dict[str, Any]:
        client = await self.device_service.get_rest_client(device_id)

        try:
            ping_params = {
                "address": address,
                "count": count,
                "interval": f"{interval_ms}ms",
                "size": packet_size,
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
            ((packets_sent - packets_received) / packets_sent * 100) if packets_sent > 0 else 0.0
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
        packet_size: int,
    ) -> dict[str, Any]:
        ssh_client = await self.device_service.get_ssh_client(device_id)
        try:
            # Use /tool/ping for consistency with CLI output formatting; interval in ms
            command = f"/tool/ping address={address} count={count} interval={interval_ms}ms size={packet_size}"
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
            inline_match = re.search(
                r"([0-9]+(?:\.[0-9]+)?ms[0-9]*us|[0-9]+(?:\.[0-9]+)?ms|[0-9]+us)", line
            )
            if inline_match:
                packets_sent += 1
                packets_received += 1
                rtts.append(DiagnosticsService._parse_rtt_ms(inline_match.group(1)))
                continue

            if "timeout" in line.lower():
                packets_sent += 1

        packet_loss_percent = (
            ((packets_sent - packets_received) / packets_sent * 100) if packets_sent > 0 else 100.0
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

        match = re.match(r"^(?:(?P<ms>[0-9]*\.?[0-9]+)ms)?(?:(?P<us>[0-9]+)us)?$", value)
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
        max_hops: int = DEFAULT_TRACEROUTE_HOPS,
    ) -> dict[str, Any]:
        """Run traceroute to show network path with REST→SSH fallback.

        Args:
            device_id: Device identifier
            address: Target IP or hostname
            count: Number of probes per hop (default: 1)
            max_hops: Maximum number of hops (1-64, default: 30)

        Returns:
            Dictionary with target and hops list
        """
        from routeros_mcp.mcp.errors import AuthenticationError, ValidationError

        await self.device_service.get_device(device_id)

        # Enforce safety limits for count
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

        # Enforce safety limits for max_hops
        if max_hops > MAX_TRACEROUTE_HOPS:
            raise ValidationError(
                f"Traceroute max_hops cannot exceed {MAX_TRACEROUTE_HOPS}",
                data={"requested_max_hops": max_hops, "max_hops": MAX_TRACEROUTE_HOPS},
            )

        if max_hops < 1:
            raise ValidationError(
                "Traceroute max_hops must be at least 1",
                data={"requested_max_hops": max_hops},
            )

        rest_error: Exception | None = None

        # REST first
        try:
            result = await self._traceroute_via_rest(device_id, address, count, max_hops)
            result["transport"] = "rest"
            result["fallback_used"] = False
            result["rest_error"] = None
            return result
        except (
            AuthenticationError,
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as exc:  # noqa: BLE001
            rest_error = exc
            logger.warning(
                "REST traceroute failed, attempting SSH fallback",
                exc_info=exc,
                extra={"device_id": device_id, "address": address},
            )

        # SSH fallback
        try:
            result = await self._traceroute_via_ssh(device_id, address, count, max_hops)
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
        max_hops: int,
    ) -> dict[str, Any]:
        client = await self.device_service.get_rest_client(device_id)

        try:
            trace_params = {
                "address": address,
                "count": count,
            }

            # Add max-hops parameter if not default
            if max_hops != DEFAULT_TRACEROUTE_HOPS:
                trace_params["max-hops"] = max_hops

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

                    hops.append(
                        {
                            "hop": hop_num,
                            "address": hop_address,
                            "rtt_ms": rtt_ms,
                        }
                    )

        return hops

    async def _traceroute_via_ssh(
        self,
        device_id: str,
        address: str,
        count: int,
        max_hops: int,
    ) -> dict[str, Any]:
        ssh_client = await self.device_service.get_ssh_client(device_id)
        try:
            # Add max-hops parameter if not default
            max_hops_param = f" max-hops={max_hops}" if max_hops != DEFAULT_TRACEROUTE_HOPS else ""
            command = f"/tool/traceroute address={address} count={count}{max_hops_param}"
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
            if not line or line.lower().startswith(("#", "address", "host", "loss", "sent")):
                continue

            match = hop_pattern.match(line)
            if match:
                hop_num = int(match.group("hop"))
                hop_address = match.group("addr")
                rtt_match = re.search(r"([0-9.]+)ms", line)
                rtt_ms = float(rtt_match.group(1)) if rtt_match else 0.0
                hops.append(
                    {
                        "hop": hop_num,
                        "address": hop_address,
                        "rtt_ms": rtt_ms,
                    }
                )
                continue

            # Handle lines with timeout markers (no RTT)
            timeout_match = re.match(
                r"^\s*(?P<hop>\d+)\s+(?P<addr>\S+).*timeout", line, re.IGNORECASE
            )
            if timeout_match:
                hop_num = int(timeout_match.group("hop"))
                hop_address = timeout_match.group("addr")
                hops.append(
                    {
                        "hop": hop_num,
                        "address": hop_address,
                        "rtt_ms": 0.0,
                    }
                )

        return hops

    async def test_bandwidth(
        self,
        device_id: str,
        target_device_id: str,
        duration: int = 10,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Run bandwidth test between two RouterOS devices with REST→SSH fallback.

        Args:
            device_id: Source device identifier
            target_device_id: Target device identifier (must have allow_bandwidth_test=true)
            duration: Test duration in seconds (5-60, default: 10)
            direction: Test direction - 'tx', 'rx', or 'both' (default: 'both')

        Returns:
            Dictionary with throughput statistics

        Raises:
            ValidationError: If parameters are invalid or target device doesn't allow bandwidth tests
            NotFoundError: If target device not found
        """
        from routeros_mcp.mcp.errors import AuthenticationError, NotFoundError, ValidationError

        # Get source device (validates it exists)
        await self.device_service.get_device(device_id)

        # Get target device and validate capability
        target_device = await self.device_service.get_device(target_device_id)
        
        # Check if target device has allow_bandwidth_test capability
        if not target_device.allow_bandwidth_test:
            raise ValidationError(
                f"Target device '{target_device_id}' does not allow bandwidth tests. "
                f"Enable 'allow_bandwidth_test' capability on the target device.",
                data={
                    "target_device_id": target_device_id,
                    "allow_bandwidth_test": False,
                    "required_capability": "allow_bandwidth_test",
                },
            )

        # Validate duration
        if duration < MIN_BANDWIDTH_TEST_DURATION:
            raise ValidationError(
                f"Bandwidth test duration must be at least {MIN_BANDWIDTH_TEST_DURATION} seconds",
                data={
                    "requested_duration": duration,
                    "min_duration": MIN_BANDWIDTH_TEST_DURATION,
                },
            )

        if duration > MAX_BANDWIDTH_TEST_DURATION:
            raise ValidationError(
                f"Bandwidth test duration cannot exceed {MAX_BANDWIDTH_TEST_DURATION} seconds",
                data={
                    "requested_duration": duration,
                    "max_duration": MAX_BANDWIDTH_TEST_DURATION,
                },
            )

        # Validate direction
        valid_directions = ["tx", "rx", "both"]
        if direction not in valid_directions:
            raise ValidationError(
                f"Invalid direction '{direction}'. Must be one of: {', '.join(valid_directions)}",
                data={"direction": direction, "valid_directions": valid_directions},
            )

        rest_error: Exception | None = None

        # Attempt REST first
        try:
            result = await self._test_bandwidth_via_rest(
                device_id, target_device.management_ip, duration, direction
            )
            result["transport"] = "rest"
            result["fallback_used"] = False
            result["rest_error"] = None
            result["target_device_id"] = target_device_id
            return result
        except (
            AuthenticationError,
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as exc:  # noqa: BLE001
            rest_error = exc
            logger.warning(
                "REST bandwidth test failed, attempting SSH fallback",
                exc_info=exc,
                extra={
                    "device_id": device_id,
                    "target_device_id": target_device_id,
                    "target_ip": target_device.management_ip,
                },
            )

        # SSH fallback
        try:
            result = await self._test_bandwidth_via_ssh(
                device_id, target_device.management_ip, duration, direction
            )
            result["transport"] = "ssh"
            result["fallback_used"] = True
            result["rest_error"] = str(rest_error) if rest_error else None
            result["target_device_id"] = target_device_id
            return result
        except (RouterOSSSHError, Exception) as ssh_exc:  # noqa: BLE001
            logger.error(
                "Bandwidth test failed via REST and SSH",
                exc_info=ssh_exc,
                extra={
                    "device_id": device_id,
                    "target_device_id": target_device_id,
                    "target_ip": target_device.management_ip,
                    "rest_error": str(rest_error),
                },
            )
            raise

    async def _test_bandwidth_via_rest(
        self,
        device_id: str,
        target_address: str,
        duration: int,
        direction: str,
    ) -> dict[str, Any]:
        """Run bandwidth test via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Build test parameters
            test_params = {
                "address": target_address,
                "duration": f"{duration}s",
                "direction": direction,
            }

            # Run bandwidth test
            test_data = await client.post("/rest/tool/bandwidth-test", test_params)
            return self._parse_rest_bandwidth_result(target_address, test_data)
        finally:
            await client.close()

    @staticmethod
    def _parse_rest_bandwidth_result(target_address: str, test_data: Any) -> dict[str, Any]:
        """Parse REST API bandwidth test response."""
        # RouterOS bandwidth-test returns aggregate results
        # Expected format: list of result dictionaries or single dictionary
        
        if isinstance(test_data, dict):
            # Single result dictionary
            tx_bps = test_data.get("tx-bits-per-second", 0)
            rx_bps = test_data.get("rx-bits-per-second", 0)
            lost = test_data.get("lost", 0)
            
            # Convert to numeric if string
            if isinstance(tx_bps, str):
                tx_bps = int(tx_bps.replace("bps", "").strip())
            if isinstance(rx_bps, str):
                rx_bps = int(rx_bps.replace("bps", "").strip())
                
            return {
                "target": target_address,
                "avg_tx_bps": int(tx_bps),
                "avg_rx_bps": int(rx_bps),
                "avg_tx_mbps": round(int(tx_bps) / 1_000_000, 2),
                "avg_rx_mbps": round(int(rx_bps) / 1_000_000, 2),
                "packet_loss_percent": float(lost) if lost else 0.0,
            }
        
        # List of results (aggregate the last/best result)
        if isinstance(test_data, list) and test_data:
            last_result = test_data[-1]
            tx_bps = last_result.get("tx-bits-per-second", 0)
            rx_bps = last_result.get("rx-bits-per-second", 0)
            lost = last_result.get("lost", 0)
            
            # Convert to numeric if string
            if isinstance(tx_bps, str):
                tx_bps = int(tx_bps.replace("bps", "").strip())
            if isinstance(rx_bps, str):
                rx_bps = int(rx_bps.replace("bps", "").strip())
                
            return {
                "target": target_address,
                "avg_tx_bps": int(tx_bps),
                "avg_rx_bps": int(rx_bps),
                "avg_tx_mbps": round(int(tx_bps) / 1_000_000, 2),
                "avg_rx_mbps": round(int(rx_bps) / 1_000_000, 2),
                "packet_loss_percent": float(lost) if lost else 0.0,
            }
        
        # No data or unexpected format
        return {
            "target": target_address,
            "avg_tx_bps": 0,
            "avg_rx_bps": 0,
            "avg_tx_mbps": 0.0,
            "avg_rx_mbps": 0.0,
            "packet_loss_percent": 0.0,
        }

    async def _test_bandwidth_via_ssh(
        self,
        device_id: str,
        target_address: str,
        duration: int,
        direction: str,
    ) -> dict[str, Any]:
        """Run bandwidth test via SSH."""
        ssh_client = await self.device_service.get_ssh_client(device_id)
        try:
            command = (
                f"/tool/bandwidth-test address={target_address} "
                f"duration={duration}s direction={direction}"
            )
            output = await ssh_client.execute(command)
            logger.debug(
                "SSH bandwidth test output",
                extra={
                    "device_id": device_id,
                    "target_address": target_address,
                    "command": command,
                    "output_preview": output[:500],
                    "output_len": len(output),
                },
            )
            return self._parse_ssh_bandwidth_output(target_address, output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_ssh_bandwidth_output(target_address: str, output: str) -> dict[str, Any]:
        """Parse SSH bandwidth test output.
        
        Example output:
            tx-current: 950Mbps  rx-current: 940Mbps
            tx-10-second-average: 950Mbps  rx-10-second-average: 940Mbps
            lost: 0
        """
        tx_bps = 0
        rx_bps = 0
        packet_loss = 0.0

        # Try to find aggregate/average values first
        avg_match = re.search(
            r"tx-\d+-second-average:\s*([0-9.]+)([KMG]?)bps.*?rx-\d+-second-average:\s*([0-9.]+)([KMG]?)bps",
            output,
            re.IGNORECASE,
        )
        
        if avg_match:
            tx_val = float(avg_match.group(1))
            tx_unit = avg_match.group(2).upper()
            rx_val = float(avg_match.group(3))
            rx_unit = avg_match.group(4).upper()
            
            # Convert to bps
            multipliers = {"K": 1_000, "M": 1_000_000, "G": 1_000_000_000, "": 1}
            tx_bps = int(tx_val * multipliers.get(tx_unit, 1))
            rx_bps = int(rx_val * multipliers.get(rx_unit, 1))
        else:
            # Fallback to current values
            current_match = re.search(
                r"tx-current:\s*([0-9.]+)([KMG]?)bps.*?rx-current:\s*([0-9.]+)([KMG]?)bps",
                output,
                re.IGNORECASE,
            )
            if current_match:
                tx_val = float(current_match.group(1))
                tx_unit = current_match.group(2).upper()
                rx_val = float(current_match.group(3))
                rx_unit = current_match.group(4).upper()
                
                multipliers = {"K": 1_000, "M": 1_000_000, "G": 1_000_000_000, "": 1}
                tx_bps = int(tx_val * multipliers.get(tx_unit, 1))
                rx_bps = int(rx_val * multipliers.get(rx_unit, 1))

        # Parse packet loss
        loss_match = re.search(r"lost:\s*([0-9.]+)", output, re.IGNORECASE)
        if loss_match:
            packet_loss = float(loss_match.group(1))

        return {
            "target": target_address,
            "avg_tx_bps": tx_bps,
            "avg_rx_bps": rx_bps,
            "avg_tx_mbps": round(tx_bps / 1_000_000, 2),
            "avg_rx_mbps": round(rx_bps / 1_000_000, 2),
            "packet_loss_percent": packet_loss,
        }
