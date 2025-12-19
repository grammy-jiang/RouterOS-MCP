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
    RouterOSSSHError,
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

    async def has_capsman_managed_aps(self, device_id: str) -> bool:
        """Return True if this device appears to manage any CAP devices via CAPsMAN.

        We detect this by checking whether CAPsMAN has any entries in
        /caps-man/remote-cap. This is a safe, read-only capability probe.

        Notes:
        - If CAPsMAN is not installed/enabled, RouterOS typically returns a "no such command"
          or "bad command" error; in that case this returns False.
        - Uses REST first when available, then SSH fallback.
        """
        await self.device_service.get_device(device_id)

        # Try REST first
        try:
            client = await self.device_service.get_rest_client(device_id)
        except Exception as e:
            logger.debug(
                "No REST client available for CAPsMAN probe; falling back to SSH",
                extra={"device_id": device_id, "error": str(e)},
            )
            client = None

        if client is not None:
            try:
                data: Any = await client.get("/rest/caps-man/remote-cap")
                if isinstance(data, list):
                    return len(data) > 0
            except Exception as rest_exc:
                logger.debug(
                    "REST CAPsMAN remote-cap probe failed; falling back to SSH",
                    extra={"device_id": device_id, "error": str(rest_exc)},
                )
            finally:
                await client.close()

        # SSH fallback
        ssh_client = await self.device_service.get_ssh_client(device_id)
        try:
            try:
                output = await ssh_client.execute("/caps-man/remote-cap/print without-paging")
            except Exception as e:
                msg = str(e).lower()
                # CAPsMAN not available on this RouterOS build/config
                if "no such command" in msg or "bad command" in msg:
                    return False
                raise

            return self._routeros_table_has_data_rows(output)
        finally:
            await ssh_client.close()

    async def get_capsman_remote_caps(self, device_id: str) -> list[dict[str, Any]]:
        """List remote CAP devices managed by CAPsMAN with REST→SSH fallback.

        Returns information about remote CAP (Controlled Access Point) devices
        known to the CAPsMAN controller on this device. Returns empty list
        when CAPsMAN is not present or no CAPs are registered.

        Args:
            device_id: Device identifier

        Returns:
            List of remote CAP dictionaries with device info, status, and capabilities

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            caps = await self._get_capsman_remote_caps_via_rest(device_id)
            for cap in caps:
                cap["transport"] = "rest"
                cap["fallback_used"] = False
                cap["rest_error"] = None
            return caps
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST CAPsMAN remote-cap listing failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            # Try SSH fallback
            try:
                caps = await self._get_capsman_remote_caps_via_ssh(device_id)
                for cap in caps:
                    cap["transport"] = "ssh"
                    cap["fallback_used"] = True
                    cap["rest_error"] = str(rest_exc)
                return caps
            except Exception as ssh_exc:
                logger.error(
                    "Both REST and SSH CAPsMAN remote-cap listing failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"CAPsMAN remote-cap listing failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def get_capsman_registrations(self, device_id: str) -> list[dict[str, Any]]:
        """List active CAPsMAN registrations with REST→SSH fallback.

        Returns information about active client registrations managed by CAPsMAN.
        Returns empty list when CAPsMAN is not present or no registrations exist.

        Note: The exact endpoint for registrations varies by RouterOS package.
        We use a best-effort approach to query available registration tables.

        Args:
            device_id: Device identifier

        Returns:
            List of registration dictionaries with client info and status

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            registrations = await self._get_capsman_registrations_via_rest(device_id)
            for reg in registrations:
                reg["transport"] = "rest"
                reg["fallback_used"] = False
                reg["rest_error"] = None
            return registrations
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST CAPsMAN registration listing failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            # Try SSH fallback
            try:
                registrations = await self._get_capsman_registrations_via_ssh(device_id)
                for reg in registrations:
                    reg["transport"] = "ssh"
                    reg["fallback_used"] = True
                    reg["rest_error"] = str(rest_exc)
                return registrations
            except Exception as ssh_exc:
                logger.error(
                    "Both REST and SSH CAPsMAN registration listing failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"CAPsMAN registration listing failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    @staticmethod
    def _routeros_table_has_data_rows(output: str) -> bool:
        """Best-effort check for at least one data row in RouterOS 'print' table output."""
        for line in output.splitlines():
            s = line.strip()
            if not s or s.startswith("Flags:") or s.startswith("Columns:") or s.startswith("#"):
                continue
            # Most RouterOS tables start rows with an index: '0', '1', ... (possibly padded)
            if s[0].isdigit():
                return True
        return False

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
            # RouterOS can expose WiFi either via legacy 'wireless' package or the newer 'wifi' package.
            # Try legacy first for backwards compatibility, then fall back to 'wifi'.
            try:
                output = await ssh_client.execute("/interface/wireless/print")
                return self._parse_wireless_print_output(output)
            except Exception as e1:
                try:
                    output = await ssh_client.execute("/interface/wifi/print")
                    return self._parse_wireless_print_output(output)
                except Exception as e2:
                    # If wireless is not present on the device, treat as no interfaces.
                    msg = f"{e1} | {e2}"
                    if "no such command" in msg.lower() or "bad command" in msg.lower():
                        return []
                    raise
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
                    # R = running, X = disabled, D = dynamic
                    running = "R" in flags
                    disabled = "X" in flags

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
                            "signal_to_noise": self._parse_snr(
                                client_entry.get("signal-to-noise", "")
                            ),
                            "tx_rate": self._parse_rate(client_entry.get("tx-rate", "")),
                            "rx_rate": self._parse_rate(client_entry.get("rx-rate", "")),
                            "uptime": client_entry.get("uptime", ""),
                            "bytes_sent": client_entry.get("tx-bytes", 0),
                            "bytes_received": client_entry.get("rx-bytes", 0),
                            "packets_sent": client_entry.get("tx-packets", 0),
                            "packets_received": client_entry.get("rx-packets", 0),
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
            # Try legacy wireless registration-table first, then RouterOS v7 wifi package.
            try:
                output = await ssh_client.execute("/interface/wireless/registration-table/print")
                return self._parse_wireless_clients_output(output)
            except Exception as e1:
                try:
                    output = await ssh_client.execute("/interface/wifi/registration-table/print")
                    return self._parse_wireless_clients_output(output)
                except Exception as e2:
                    # If wireless is not present on the device, treat as no connected clients.
                    msg = f"{e1} | {e2}"
                    if "no such command" in msg.lower() or "bad command" in msg.lower():
                        return []
                    # Preserve original error signal for unexpected failures.
                    raise RouterOSSSHError(f"Wireless registration-table failed: {msg}")
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
    def _parse_snr(value: Any) -> int:
        """Parse signal-to-noise ratio value to integer.

        SNR is typically a positive value representing the ratio between signal and noise.
        """
        if value is None or value == "":
            return 0

        if isinstance(value, int):
            return value

        # Parse string like "35" or "35dB"
        try:
            value_str = str(value).strip().lower()
            # Remove "db" suffix if present
            value_str = value_str.replace("db", "").strip()
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

    async def _get_capsman_remote_caps_via_rest(
        self, device_id: str
    ) -> list[dict[str, Any]]:
        """Fetch CAPsMAN remote CAPs via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            caps_data = await client.get("/rest/caps-man/remote-cap")

            # Normalize CAP data
            result: list[dict[str, Any]] = []
            if isinstance(caps_data, list):
                for cap in caps_data:
                    if isinstance(cap, dict):
                        result.append({
                            "id": cap.get(".id", ""),
                            "name": cap.get("name", ""),
                            "address": cap.get("address", ""),
                            "identity": cap.get("identity", ""),
                            "version": cap.get("version", ""),
                            "state": cap.get("state", ""),
                            "base_mac": cap.get("base-mac", ""),
                            "radio_mac": cap.get("radio-mac", ""),
                            "board": cap.get("board", ""),
                            "rx_signal": cap.get("rx-signal", ""),
                            "uptime": cap.get("uptime", ""),
                        })

            return result

        except Exception as e:
            # If CAPsMAN not present, return empty list instead of error
            msg = str(e).lower()
            if "no such command" in msg or "bad command" in msg or "not found" in msg:
                logger.debug(
                    "CAPsMAN not available on device, returning empty list",
                    extra={"device_id": device_id},
                )
                return []
            raise

        finally:
            await client.close()

    async def _get_capsman_remote_caps_via_ssh(
        self, device_id: str
    ) -> list[dict[str, Any]]:
        """Fetch CAPsMAN remote CAPs via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            try:
                output = await ssh_client.execute("/caps-man/remote-cap/print without-paging")
                return self._parse_capsman_remote_caps_output(output)
            except Exception as e:
                msg = str(e).lower()
                # CAPsMAN not available on this RouterOS build/config
                if "no such command" in msg or "bad command" in msg:
                    logger.debug(
                        "CAPsMAN not available on device, returning empty list",
                        extra={"device_id": device_id},
                    )
                    return []
                raise
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_capsman_remote_caps_output(output: str) -> list[dict[str, Any]]:
        """Parse /caps-man/remote-cap/print output into CAP list."""
        caps: list[dict[str, Any]] = []

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

            # Parse data lines (start with number)
            parts = line.split()
            if not parts or not parts[0][0].isdigit():
                continue

            try:
                # Format: [id] [flags*] [name] [address] [identity] [state] ...
                idx = 0
                cap_id = parts[0]
                idx = 1

                # Check for flags
                if len(parts) > 1 and all(c in "DRSXdrsx " for c in parts[1]):
                    idx = 2

                # Extract fields
                name = parts[idx] if idx < len(parts) else ""
                address = parts[idx + 1] if idx + 1 < len(parts) else ""
                identity = parts[idx + 2] if idx + 2 < len(parts) else ""
                state = parts[idx + 3] if idx + 3 < len(parts) else ""

                caps.append({
                    "id": cap_id,
                    "name": name,
                    "address": address,
                    "identity": identity,
                    "version": "",
                    "state": state,
                    "base_mac": "",
                    "radio_mac": "",
                    "board": "",
                    "rx_signal": "",
                    "uptime": "",
                })
            except (IndexError, ValueError) as e:
                logger.debug(f"Failed to parse CAPsMAN remote-cap line: {line}", exc_info=e)
                continue

        return caps

    async def _get_capsman_registrations_via_rest(
        self, device_id: str
    ) -> list[dict[str, Any]]:
        """Fetch CAPsMAN registrations via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Try registration-table first (most common endpoint)
            try:
                regs_data = await client.get("/rest/caps-man/registration-table")
            except Exception:
                # Try alternative endpoints that may exist in different RouterOS versions
                try:
                    regs_data = await client.get("/rest/caps-man/interface")
                except Exception:
                    # No registrations endpoint available
                    return []

            # Normalize registration data
            result: list[dict[str, Any]] = []
            if isinstance(regs_data, list):
                for reg in regs_data:
                    if isinstance(reg, dict):
                        result.append({
                            "id": reg.get(".id", ""),
                            "interface": reg.get("interface", ""),
                            "mac_address": reg.get("mac-address", ""),
                            "ssid": reg.get("ssid", ""),
                            "ap": reg.get("ap", ""),
                            "radio_name": reg.get("radio-name", ""),
                            "rx_signal": reg.get("rx-signal", ""),
                            "tx_signal": reg.get("tx-signal", ""),
                            "uptime": reg.get("uptime", ""),
                            "packets": reg.get("packets", ""),
                            "bytes": reg.get("bytes", ""),
                        })

            return result

        except Exception as e:
            # If CAPsMAN not present, return empty list instead of error
            msg = str(e).lower()
            if "no such command" in msg or "bad command" in msg or "not found" in msg:
                logger.debug(
                    "CAPsMAN registrations not available on device, returning empty list",
                    extra={"device_id": device_id},
                )
                return []
            raise

        finally:
            await client.close()

    async def _get_capsman_registrations_via_ssh(
        self, device_id: str
    ) -> list[dict[str, Any]]:
        """Fetch CAPsMAN registrations via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            # Try registration-table first
            try:
                output = await ssh_client.execute("/caps-man/registration-table/print without-paging")
                return self._parse_capsman_registrations_output(output)
            except Exception as e1:
                # Try interface as alternative
                try:
                    output = await ssh_client.execute("/caps-man/interface/print without-paging")
                    return self._parse_capsman_registrations_output(output)
                except Exception as e2:
                    msg = f"{e1} | {e2}"
                    if "no such command" in msg.lower() or "bad command" in msg.lower():
                        logger.debug(
                            "CAPsMAN registrations not available on device, returning empty list",
                            extra={"device_id": device_id},
                        )
                        return []
                    raise
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_capsman_registrations_output(output: str) -> list[dict[str, Any]]:
        """Parse /caps-man/registration-table/print output into registration list."""
        registrations: list[dict[str, Any]] = []

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
                idx = 0
                reg_id = parts[0]
                idx = 1

                # Check for flags
                if len(parts) > 1 and all(c in "DRSXdrsx " for c in parts[1]):
                    idx = 2

                # Extract fields (format varies by RouterOS version)
                interface = parts[idx] if idx < len(parts) else ""
                mac_address = parts[idx + 1] if idx + 1 < len(parts) else ""
                ssid = parts[idx + 2] if idx + 2 < len(parts) else ""

                registrations.append({
                    "id": reg_id,
                    "interface": interface,
                    "mac_address": mac_address,
                    "ssid": ssid,
                    "ap": "",
                    "radio_name": "",
                    "rx_signal": "",
                    "tx_signal": "",
                    "uptime": "",
                    "packets": "",
                    "bytes": "",
                })
            except (IndexError, ValueError) as e:
                logger.debug(f"Failed to parse CAPsMAN registration line: {line}", exc_info=e)
                continue

        return registrations
