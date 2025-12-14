"""Interface service for network interface operations.

Provides operations for querying RouterOS interface information,
including status, statistics, and configuration.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.routeros.exceptions import (
    RouterOSClientError,
    RouterOSNetworkError,
    RouterOSServerError,
    RouterOSTimeoutError,
)

logger = logging.getLogger(__name__)


class InterfaceService:
    """Service for RouterOS interface operations.

    Responsibilities:
    - Query interface list and status
    - Retrieve interface details and statistics
    - Monitor real-time traffic statistics
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = InterfaceService(session, settings)

            # Get interface list
            interfaces = await service.list_interfaces("dev-lab-01")

            # Get specific interface
            interface = await service.get_interface("dev-lab-01", "*1")

            # Get traffic stats
            stats = await service.get_interface_stats("dev-lab-01", ["ether1"])
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize interface service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def list_interfaces(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """List all network interfaces on a device with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            List of interface information dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            interfaces = await self._list_interfaces_via_rest(device_id)
            # Add transport metadata
            for iface in interfaces:
                iface["transport"] = "rest"
                iface["fallback_used"] = False
                iface["rest_error"] = None
            return interfaces
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST interface listing failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            # Try SSH fallback
            try:
                interfaces = await self._list_interfaces_via_ssh(device_id)
                # Add transport metadata
                for iface in interfaces:
                    iface["transport"] = "ssh"
                    iface["fallback_used"] = True
                    iface["rest_error"] = str(rest_exc)
                return interfaces
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH interface listing failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Interface listing failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _list_interfaces_via_rest(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch interfaces via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            interfaces_data = await client.get("/rest/interface")

            # Normalize interface data
            result: list[dict[str, Any]] = []
            if isinstance(interfaces_data, list):
                for iface in interfaces_data:
                    if isinstance(iface, dict):
                        result.append({
                            "id": iface.get(".id", ""),
                            "name": iface.get("name", ""),
                            "type": iface.get("type", ""),
                            "running": iface.get("running", False),
                            "disabled": iface.get("disabled", False),
                            "comment": iface.get("comment", ""),
                            "mtu": iface.get("mtu", 1500),
                            "actual_mtu": iface.get("mtu", 1500),
                            "l2mtu": iface.get("l2mtu", 1514),
                            "max_l2mtu": iface.get("max-l2mtu", 9796),
                            "mac_address": iface.get("mac-address", ""),
                        })

            return result

        finally:
            await client.close()

    async def _list_interfaces_via_ssh(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch interfaces via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/interface/print")
            return self._parse_interface_print_output(output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_interface_print_output(output: str) -> list[dict[str, Any]]:
        """Parse /interface/print output into interface list.

        Handles RouterOS standard table format with flags in left margin.
        RouterOS output format:
        Flags: D - DYNAMIC; R - RUNNING; S - SLAVE
        Columns: NAME, TYPE, ACTUAL-MTU, L2MTU, MAX-L2MTU, MAC-ADDRESS
         #     NAME              TYPE      ACTUAL-MTU  L2MTU  MAX-L2MTU  MAC-ADDRESS
         0  R  ether1            ether           1500   1514       9796  78:9A:18:A2:F3:D2
         1  RS ether2            ether           1500   1514       9796  78:9A:18:A2:F3:D3
        """
        interfaces: list[dict[str, Any]] = []

        # Skip header lines (Flags:, Columns:, blank line, column headers with #)
        lines = output.strip().split("\n")
        for line in lines:
            # Skip header/metadata lines
            if not line.strip() or line.startswith("Flags:") or line.startswith("Columns:") or line.startswith("#"):
                continue

            # Parse data lines (start with number, potentially with flags)
            parts = line.split()
            if not parts or not parts[0][0].isdigit():
                continue

            try:
                # Format: [id] [flags*] [name] [type] [actual-mtu] [l2mtu] [max-l2mtu] [mac-address]
                # Flags are single uppercase letters: D, R, S, X
                idx = 0

                # First part is always the ID
                iface_id = parts[0]
                idx = 1

                # Check if second part contains flags (one or more flag characters)
                flags = ""
                if len(parts) > 1 and all(c in "DRSXdrsx " for c in parts[1]):
                    # Parts[1] may contain flags like "R", "RS", "D S", etc.
                    flags = parts[1].replace(" ", "")
                    idx = 2

                # Extract fields: name, type, and optional numeric fields
                if len(parts) > idx + 1:
                    name = parts[idx]
                    iface_type = parts[idx + 1]

                    # Remaining parts are numeric fields and MAC address
                    # Format: [actual-mtu] [l2mtu] [max-l2mtu] [mac-address]
                    remaining = parts[idx + 2:]
                    
                    # Try to extract MTU fields and MAC address from remaining fields
                    actual_mtu = 1500  # Default
                    l2mtu = 1514  # Default
                    max_l2mtu = 9796  # Default
                    mac_address = ""
                    
                    # Extract numeric fields in order
                    numeric_idx = 0
                    for field in remaining:
                        try:
                            # Try to parse as integer
                            value = int(field)
                            if numeric_idx == 0:
                                actual_mtu = value
                            elif numeric_idx == 1:
                                l2mtu = value
                            elif numeric_idx == 2:
                                max_l2mtu = value
                            numeric_idx += 1
                        except ValueError:
                            # Not a number, might be MAC address
                            if ":" in field and len(field) > 5:
                                mac_address = field

                    # Determine running and disabled status from flags
                    # R = running, D = disabled
                    running = "R" in flags
                    disabled = "D" in flags

                    interfaces.append({
                        "id": iface_id,
                        "name": name,
                        "type": iface_type,
                        "running": running,
                        "disabled": disabled,
                        "comment": "",
                        "mtu": actual_mtu,
                        "actual_mtu": actual_mtu,
                        "l2mtu": l2mtu,
                        "max_l2mtu": max_l2mtu,
                        "mac_address": mac_address,
                    })
            except (IndexError, ValueError) as e:
                # Skip lines that don't parse properly
                logger.debug(f"Failed to parse interface line: {line}", exc_info=e)
                continue

        return interfaces

    async def get_interface(
        self,
        device_id: str,
        interface_id: str,
    ) -> dict[str, Any]:
        """Get detailed information about a specific interface with REST→SSH fallback.

        Args:
            device_id: Device identifier
            interface_id: Interface ID

        Returns:
            Interface information dictionary

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            interface = await self._get_interface_via_rest(device_id, interface_id)
            interface["transport"] = "rest"
            interface["fallback_used"] = False
            interface["rest_error"] = None
            return interface
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST get_interface failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id, "interface_id": interface_id},
            )
            # Try SSH fallback
            try:
                interface = await self._get_interface_via_ssh(device_id, interface_id)
                interface["transport"] = "ssh"
                interface["fallback_used"] = True
                interface["rest_error"] = str(rest_exc)
                return interface
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH get_interface failed",
                    exc_info=ssh_exc,
                    extra={
                        "device_id": device_id,
                        "interface_id": interface_id,
                        "rest_error": str(rest_exc),
                    },
                )
                raise RuntimeError(
                    f"Get interface failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_interface_via_rest(
        self,
        device_id: str,
        interface_id: str,
    ) -> dict[str, Any]:
        """Fetch interface details via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            interface_data = await client.get(f"/rest/interface/{interface_id}")

            # Normalize interface data
            return {
                "id": interface_data.get(".id", interface_id),
                "name": interface_data.get("name", ""),
                "type": interface_data.get("type", ""),
                "running": interface_data.get("running", False),
                "disabled": interface_data.get("disabled", False),
                "comment": interface_data.get("comment", ""),
                "mtu": interface_data.get("mtu", 1500),
                "actual_mtu": interface_data.get("mtu", 1500),
                "l2mtu": interface_data.get("l2mtu", 1514),
                "max_l2mtu": interface_data.get("max-l2mtu", 9796),
                "mac_address": interface_data.get("mac-address", ""),
                "last_link_up_time": interface_data.get("last-link-up-time", ""),
            }

        finally:
            await client.close()

    async def _get_interface_via_ssh(
        self,
        device_id: str,
        interface_id: str,
    ) -> dict[str, Any]:
        """Fetch interface details via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            # Get all interfaces and find by ID
            output = await ssh_client.execute("/interface/print")
            interfaces = self._parse_interface_print_output(output)

            for iface in interfaces:
                if iface.get("id") == interface_id:
                    return iface

            # Not found
            return {}

        finally:
            await ssh_client.close()

    async def get_interface_stats(
        self,
        device_id: str,
        interface_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get real-time traffic statistics for interfaces with REST→SSH fallback.

        Args:
            device_id: Device identifier
            interface_names: Optional list of interface names to filter

        Returns:
            List of traffic statistics dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            stats = await self._get_interface_stats_via_rest(device_id, interface_names)
            # Add transport metadata
            for stat in stats:
                stat["transport"] = "rest"
                stat["fallback_used"] = False
                stat["rest_error"] = None
            return stats
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST interface stats failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            # Try SSH fallback
            try:
                stats = await self._get_interface_stats_via_ssh(device_id, interface_names)
                # Add transport metadata
                for stat in stats:
                    stat["transport"] = "ssh"
                    stat["fallback_used"] = True
                    stat["rest_error"] = str(rest_exc)
                return stats
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH interface stats failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Interface stats failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_interface_stats_via_rest(
        self,
        device_id: str,
        interface_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch interface stats via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            # RouterOS monitor-traffic streams unless "once" is supplied. If no
            # interface list is provided, fetch names first to issue per-interface
            # one-shot requests.
            target_interfaces = interface_names
            if not target_interfaces:
                interfaces = await self.list_interfaces(device_id)
                target_interfaces = [iface["name"] for iface in interfaces if iface.get("name")]

            result: list[dict[str, Any]] = []

            # Issue one-shot monitor requests per interface to avoid streaming timeouts.
            for name in target_interfaces or []:
                stats_data = await client.get(
                    "/rest/interface/monitor-traffic",
                    params={
                        "interface": name,
                        "once": "true",
                        "without-paging": "true",
                    },
                )

                # API may return a dict for single interface or list; normalize to list
                candidates: list[dict[str, Any]] = []
                if isinstance(stats_data, list):
                    candidates = [s for s in stats_data if isinstance(s, dict)]
                elif isinstance(stats_data, dict):
                    candidates = [stats_data]

                for stat in candidates:
                    # Respect filter if provided explicitly (defensive for weird responses)
                    if interface_names and stat.get("name") not in interface_names:
                        continue

                    result.append({
                        "name": stat.get("name", name),
                        "rx_bits_per_second": stat.get("rx-bits-per-second", 0),
                        "tx_bits_per_second": stat.get("tx-bits-per-second", 0),
                        "rx_packets_per_second": stat.get("rx-packets-per-second", 0),
                        "tx_packets_per_second": stat.get("tx-packets-per-second", 0),
                    })

            return result

        finally:
            await client.close()

    async def _get_interface_stats_via_ssh(
        self,
        device_id: str,
        interface_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch interface stats via SSH CLI using /interface/monitor-traffic."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            # Get interface list first
            output = await ssh_client.execute("/interface/print")
            interfaces = self._parse_interface_print_output(output)

            result: list[dict[str, Any]] = []
            
            # If no specific interface names requested, get stats for all running interfaces
            target_interfaces = interface_names if interface_names else None
            
            for iface in interfaces:
                name = iface.get("name")
                if not name:
                    continue

                # Filter by interface_names if provided
                if target_interfaces and name not in target_interfaces:
                    continue

                # Get traffic stats for this interface using monitor-traffic once
                try:
                    stats_output = await ssh_client.execute(
                        f"/interface/monitor-traffic {name} once"
                    )
                    stats = self._parse_monitor_traffic_output(stats_output)
                    stats["name"] = name
                except Exception as e:
                    logger.debug(
                        f"Failed to get monitor-traffic for {name}: {e}",
                        extra={"device_id": device_id, "interface_name": name},
                    )
                    # Fallback to zeros if monitor-traffic fails
                    stats = {
                        "name": name,
                        "rx_bits_per_second": 0,
                        "tx_bits_per_second": 0,
                        "rx_packets_per_second": 0,
                        "tx_packets_per_second": 0,
                    }

                result.append(stats)

            return result

        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_monitor_traffic_output(output: str) -> dict[str, Any]:
        """Parse /interface/monitor-traffic output.
        
        Expected format:
                           name:    ether1
          rx-packets-per-second:     3 707
             rx-bits-per-second:  38.2Mbps
       fp-rx-packets-per-second:     3 717
          fp-rx-bits-per-second:  38.2Mbps
          tx-packets-per-second:       462
             tx-bits-per-second: 393.3kbps
       fp-tx-packets-per-second:         0
          fp-tx-bits-per-second:      0bps
      tx-queue-drops-per-second:         0
        """
        stats: dict[str, Any] = {
            "rx_bits_per_second": 0,
            "tx_bits_per_second": 0,
            "rx_packets_per_second": 0,
            "tx_packets_per_second": 0,
        }

        for line in output.strip().split("\n"):
            line = line.strip()
            if not line or ":" not in line:
                continue

            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()

            # Convert value to number, handling unit suffixes (kbps, Mbps, etc.) and spaces
            def parse_value(val: str) -> float:
                val = val.lower().strip()
                # Remove spaces from numbers (e.g., "3 707" -> "3707")
                val = val.replace(" ", "")
                
                if "kbps" in val:
                    return float(val.replace("kbps", "")) * 1000
                elif "mbps" in val:
                    return float(val.replace("mbps", "")) * 1_000_000
                elif "gbps" in val:
                    return float(val.replace("gbps", "")) * 1_000_000_000
                elif "bps" in val:
                    return float(val.replace("bps", ""))
                else:
                    try:
                        return float(val)
                    except ValueError:
                        return 0

            # Use exact key matching to avoid matching fast-path (fp-*) variants
            if key == "rx-packets-per-second":
                stats["rx_packets_per_second"] = int(float(parse_value(value)))
            elif key == "rx-bits-per-second":
                stats["rx_bits_per_second"] = int(float(parse_value(value)))
            elif key == "tx-packets-per-second":
                stats["tx_packets_per_second"] = int(float(parse_value(value)))
            elif key == "tx-bits-per-second":
                stats["tx_bits_per_second"] = int(float(parse_value(value)))

        return stats
