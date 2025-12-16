"""Wireless service for wireless network operations.

Provides operations for querying RouterOS wireless interface information,
including SSID configuration, client connections, and signal statistics.
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


class WirelessService:
    """Service for RouterOS wireless operations.

    Responsibilities:
    - Query wireless interface list and configuration
    - Retrieve connected client information
    - Monitor signal strength and connection rates
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = WirelessService(session, settings)

            # Get wireless interfaces
            interfaces = await service.get_wireless_interfaces("dev-lab-01")

            # Get connected clients
            clients = await service.get_wireless_clients("dev-lab-01")
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize wireless service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def get_wireless_interfaces(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """List wireless interfaces with configuration with REST→SSH fallback.

        Returns information about wireless interfaces including SSIDs, frequencies,
        channels, TX power, and operational status.

        Args:
            device_id: Device identifier

        Returns:
            List of wireless interface dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            interfaces = await self._get_wireless_interfaces_via_rest(device_id)
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
                f"REST wireless interface listing failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            # Try SSH fallback
            try:
                interfaces = await self._get_wireless_interfaces_via_ssh(device_id)
                # Add transport metadata
                for iface in interfaces:
                    iface["transport"] = "ssh"
                    iface["fallback_used"] = True
                    iface["rest_error"] = str(rest_exc)
                return interfaces
            except Exception as ssh_exc:
                logger.error(
                    "Both REST and SSH wireless interface listing failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Wireless interface listing failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_wireless_interfaces_via_rest(
        self, device_id: str
    ) -> list[dict[str, Any]]:
        """Fetch wireless interfaces via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            interfaces_data = await client.get("/rest/interface/wireless")

            # Normalize interface data
            result: list[dict[str, Any]] = []
            if isinstance(interfaces_data, list):
                for iface in interfaces_data:
                    if isinstance(iface, dict):
                        result.append({
                            "id": iface.get(".id", ""),
                            "name": iface.get("name", ""),
                            "ssid": iface.get("ssid", ""),
                            "frequency": iface.get("frequency", ""),
                            "band": iface.get("band", ""),
                            "channel_width": iface.get("channel-width", ""),
                            "tx_power": iface.get("tx-power", ""),
                            "tx_power_mode": iface.get("tx-power-mode", ""),
                            "mode": iface.get("mode", ""),
                            "running": iface.get("running", False),
                            "disabled": iface.get("disabled", False),
                            "comment": iface.get("comment", ""),
                            "mac_address": iface.get("mac-address", ""),
                            "registered_clients": iface.get("registered-clients", 0),
                            "authenticated_clients": iface.get("authenticated-clients", 0),
                        })

            return result

        finally:
            await client.close()

    async def _get_wireless_interfaces_via_ssh(
        self, device_id: str
    ) -> list[dict[str, Any]]:
        """Fetch wireless interfaces via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/interface/wireless/print")
            return self._parse_wireless_print_output(output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_wireless_print_output(output: str) -> list[dict[str, Any]]:
        """Parse /interface/wireless/print output into interface list.

        Handles RouterOS standard table format with flags in left margin.
        """
        interfaces: list[dict[str, Any]] = []

        # Skip header lines
        lines = output.strip().split("\n")
        for line in lines:
            # Skip header/metadata lines
            if (
                not line.strip()
                or line.startswith("Flags:")
                or line.startswith("Columns:")
                or line.startswith("#")
            ):
                continue

            # Parse data lines (start with number, potentially with flags)
            parts = line.split()
            if not parts or not parts[0][0].isdigit():
                continue

            try:
                # Format: [id] [flags*] [name] [ssid] [frequency] [band] ...
                idx = 0

                # First part is always the ID
                iface_id = parts[0]
                idx = 1

                # Check if second part contains flags
                flags = ""
                if len(parts) > 1 and all(c in "DRSXdrsx " for c in parts[1]):
                    flags = parts[1].replace(" ", "")
                    idx = 2

                # Extract fields
                if len(parts) > idx:
                    name = parts[idx] if idx < len(parts) else ""
                    ssid = parts[idx + 1] if idx + 1 < len(parts) else ""
                    frequency = parts[idx + 2] if idx + 2 < len(parts) else ""
                    band = parts[idx + 3] if idx + 3 < len(parts) else ""

                    # Determine running and disabled status from flags
                    running = "R" in flags
                    disabled = "D" in flags

                    interfaces.append({
                        "id": iface_id,
                        "name": name,
                        "ssid": ssid,
                        "frequency": frequency,
                        "band": band,
                        "channel_width": "",
                        "tx_power": "",
                        "tx_power_mode": "",
                        "mode": "",
                        "running": running,
                        "disabled": disabled,
                        "comment": "",
                        "mac_address": "",
                        "registered_clients": 0,
                        "authenticated_clients": 0,
                    })
            except (IndexError, ValueError) as e:
                # Skip lines that don't parse properly
                logger.debug(f"Failed to parse wireless interface line: {line}", exc_info=e)
                continue

        return interfaces

    async def get_wireless_clients(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """List connected wireless clients with REST→SSH fallback.

        Returns information about connected wireless clients including MAC addresses,
        signal strength (RSSI in dBm), connection rates, and association time.

        Note: Signal strength is reported as RSSI in negative dBm (e.g., -65 dBm).
              Rates are in Mbps.

        Args:
            device_id: Device identifier

        Returns:
            List of wireless client dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            clients = await self._get_wireless_clients_via_rest(device_id)
            # Add transport metadata
            for client in clients:
                client["transport"] = "rest"
                client["fallback_used"] = False
                client["rest_error"] = None
            return clients
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST wireless client listing failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            # Try SSH fallback
            try:
                clients = await self._get_wireless_clients_via_ssh(device_id)
                # Add transport metadata
                for client in clients:
                    client["transport"] = "ssh"
                    client["fallback_used"] = True
                    client["rest_error"] = str(rest_exc)
                return clients
            except Exception as ssh_exc:
                logger.error(
                    "Both REST and SSH wireless client listing failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Wireless client listing failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_wireless_clients_via_rest(
        self, device_id: str
    ) -> list[dict[str, Any]]:
        """Fetch wireless clients via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get registration table which shows connected clients
            clients_data = await client.get("/rest/interface/wireless/registration-table")

            # Normalize client data
            result: list[dict[str, Any]] = []
            if isinstance(clients_data, list):
                for client_entry in clients_data:
                    if isinstance(client_entry, dict):
                        result.append({
                            "id": client_entry.get(".id", ""),
                            "interface": client_entry.get("interface", ""),
                            "mac_address": client_entry.get("mac-address", ""),
                            "signal_strength": self._parse_signal_strength(
                                client_entry.get("signal-strength", "")
                            ),
                            "signal_to_noise": self._parse_signal_strength(
                                client_entry.get("signal-to-noise", "")
                            ),
                            "tx_rate": self._parse_rate(client_entry.get("tx-rate", "")),
                            "rx_rate": self._parse_rate(client_entry.get("rx-rate", "")),
                            "uptime": client_entry.get("uptime", ""),
                            "bytes_sent": client_entry.get("bytes", 0),
                            "bytes_received": client_entry.get("bytes", 0),
                            "packets_sent": client_entry.get("packets", 0),
                            "packets_received": client_entry.get("packets", 0),
                        })

            return result

        finally:
            await client.close()

    async def _get_wireless_clients_via_ssh(
        self, device_id: str
    ) -> list[dict[str, Any]]:
        """Fetch wireless clients via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/interface/wireless/registration-table/print")
            return self._parse_wireless_clients_output(output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_wireless_clients_output(output: str) -> list[dict[str, Any]]:
        """Parse /interface/wireless/registration-table/print output.

        Handles RouterOS standard table format.
        """
        clients: list[dict[str, Any]] = []

        # Skip header lines
        lines = output.strip().split("\n")
        for line in lines:
            # Skip header/metadata lines
            if (
                not line.strip()
                or line.startswith("Flags:")
                or line.startswith("Columns:")
                or line.startswith("#")
            ):
                continue

            # Parse data lines
            parts = line.split()
            if not parts or not parts[0][0].isdigit():
                continue

            try:
                # Extract available fields
                idx = 0
                client_id = parts[0]
                idx = 1

                # Check for flags
                if len(parts) > 1 and all(c in "DRSXdrsx " for c in parts[1]):
                    idx = 2

                # Extract fields (format varies by RouterOS version)
                interface = parts[idx] if idx < len(parts) else ""
                mac_address = parts[idx + 1] if idx + 1 < len(parts) else ""
                signal_strength_str = parts[idx + 2] if idx + 2 < len(parts) else ""

                clients.append({
                    "id": client_id,
                    "interface": interface,
                    "mac_address": mac_address,
                    "signal_strength": WirelessService._parse_signal_strength(signal_strength_str),
                    "signal_to_noise": 0,
                    "tx_rate": "",
                    "rx_rate": "",
                    "uptime": "",
                    "bytes_sent": 0,
                    "bytes_received": 0,
                    "packets_sent": 0,
                    "packets_received": 0,
                })
            except (IndexError, ValueError) as e:
                # Skip lines that don't parse properly
                logger.debug(f"Failed to parse wireless client line: {line}", exc_info=e)
                continue

        return clients

    @staticmethod
    def _parse_signal_strength(value: Any) -> int:
        """Parse signal strength value to integer dBm.

        Signal strength is typically in negative dBm (e.g., -65 means -65 dBm).
        """
        if value is None or value == "":
            return 0

        if isinstance(value, int):
            return value

        # Parse string like "-65dBm" or "-65"
        try:
            value_str = str(value).strip().lower()
            # Remove "dbm" suffix if present
            value_str = value_str.replace("dbm", "").replace("@", "").strip()
            return int(value_str)
        except (ValueError, AttributeError):
            return 0

    @staticmethod
    def _parse_rate(value: Any) -> str:
        """Parse rate value (in Mbps).

        RouterOS returns rates like "54Mbps" or "144.4Mbps".
        We preserve the string format with units.
        """
        if value is None or value == "":
            return ""

        return str(value).strip()
