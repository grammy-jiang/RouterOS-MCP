"""Bridge service for network bridge operations.

Provides operations for querying RouterOS bridge information,
including bridge configurations, member interfaces, and VLAN settings.
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


class BridgeService:
    """Service for RouterOS bridge operations.

    Responsibilities:
    - Query bridge list and configuration
    - Retrieve bridge ports and their assignments
    - Query VLAN configuration on bridges
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = BridgeService(session, settings)

            # Get bridge list
            bridges = await service.list_bridges("dev-lab-01")

            # Get bridge ports
            ports = await service.list_bridge_ports("dev-lab-01")
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize bridge service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def list_bridges(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """List all bridge interfaces on a device with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            List of bridge information dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            bridges = await self._list_bridges_via_rest(device_id)
            # Add transport metadata
            for bridge in bridges:
                bridge["transport"] = "rest"
                bridge["fallback_used"] = False
                bridge["rest_error"] = None
            return bridges
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST bridge listing failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            # Try SSH fallback
            try:
                bridges = await self._list_bridges_via_ssh(device_id)
                # Add transport metadata
                for bridge in bridges:
                    bridge["transport"] = "ssh"
                    bridge["fallback_used"] = True
                    bridge["rest_error"] = str(rest_exc)
                return bridges
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH bridge listing failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Bridge listing failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _list_bridges_via_rest(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch bridges via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            bridges_data = await client.get("/rest/interface/bridge")

            # Normalize bridge data
            result: list[dict[str, Any]] = []
            if isinstance(bridges_data, list):
                for bridge in bridges_data:
                    if isinstance(bridge, dict):
                        result.append({
                            "id": bridge.get(".id", ""),
                            "name": bridge.get("name", ""),
                            "mtu": bridge.get("mtu", 1500),
                            "actual_mtu": bridge.get("actual-mtu", 1500),
                            "l2mtu": bridge.get("l2mtu", 1514),
                            "mac_address": bridge.get("mac-address", ""),
                            "arp": bridge.get("arp", "enabled"),
                            "arp_timeout": bridge.get("arp-timeout", "auto"),
                            "disabled": bridge.get("disabled", False),
                            "running": bridge.get("running", False),
                            "auto_mac": bridge.get("auto-mac", True),
                            "ageing_time": bridge.get("ageing-time", "5m"),
                            "priority": bridge.get("priority", "0x8000"),
                            "protocol_mode": bridge.get("protocol-mode", "rstp"),
                            "fast_forward": bridge.get("fast-forward", True),
                            "vlan_filtering": bridge.get("vlan-filtering", False),
                            "comment": bridge.get("comment", ""),
                        })

            return result

        finally:
            await client.close()

    async def _list_bridges_via_ssh(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch bridges via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/interface/bridge/print")
            return self._parse_bridge_print_output(output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_bridge_print_output(output: str) -> list[dict[str, Any]]:
        """Parse /interface/bridge/print output into bridge list.

        Handles RouterOS multi-line detail format with continuation lines.
        RouterOS output format:
        Flags: D - dynamic; X - disabled, R - running
         0  R name="bridge-lan" mtu=auto actual-mtu=1500 l2mtu=1514 arp=enabled arp-timeout=auto
              mac-address=78:9A:18:A2:F3:D3 protocol-mode=rstp fast-forward=yes igmp-snooping=yes
              [...more key=value pairs on continuation lines...]
         1  R ;;; Comment line (optional)
              name="lo-router-id" mtu=auto ...
        """
        bridges: list[dict[str, Any]] = []

        lines = output.strip().split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            # Skip empty lines and header lines
            if not line.strip() or line.strip().startswith("Flags:") or line.strip().startswith("Columns:"):
                i += 1
                continue

            # Parse data line (starts with ID number, potentially with leading spaces)
            stripped = line.lstrip()
            if stripped and stripped[0].isdigit():
                # This is a data line for a bridge entry
                parts = stripped.split()
                if not parts:
                    i += 1
                    continue

                try:
                    # Format: [id] [flags] [comment*] key=value key=value ...
                    bridge_id = parts[0]
                    flags = ""
                    idx = 1

                    # Check if second part is a flag (single letter like R, D, etc.)
                    if len(parts) > 1 and len(parts[1]) == 1 and parts[1] in "RDSX":
                        flags = parts[1]
                        idx = 2

                    # Skip comment if present (starts with ;;;)
                    if len(parts) > idx and parts[idx].startswith(";;;"):
                        idx += 1
                        # Collect rest of comment line until we find key=value
                        while idx < len(parts) and "=" not in parts[idx]:
                            idx += 1

                    # Parse key=value pairs on this line
                    bridge_data = {
                        "id": bridge_id,
                        "disabled": "D" in flags or "X" in flags,
                        "running": "R" in flags,
                        # Defaults
                        "name": "",
                        "mtu": "auto",
                        "actual_mtu": 1500,
                        "l2mtu": 1514,
                        "mac_address": "",
                        "protocol_mode": "rstp",
                        "fast_forward": True,
                        "vlan_filtering": False,
                        "arp": "enabled",
                        "arp_timeout": "auto",
                        "auto_mac": True,
                        "ageing_time": "5m",
                        "priority": "0x8000",
                        "comment": "",
                    }

                    # Parse key=value pairs on this line
                    for part in parts[idx:]:
                        if "=" in part:
                            key, value = part.split("=", 1)
                            # Remove quotes if present
                            value = value.strip('"')
                            # Store known fields
                            key_lower = key.lower().replace("-", "_")
                            if key_lower in [
                                "name", "mtu", "actual_mtu", "l2mtu", "mac_address",
                                "protocol_mode", "fast_forward", "igmp_snooping",
                                "vlan_filtering", "arp", "comment", "auto_mac",
                                "ageing_time", "priority", "max_message_age",
                                "forward_delay", "transmit_hold_count"
                            ]:
                                # Convert yes/no to boolean
                                if value in ("yes", "true"):
                                    bridge_data[key_lower] = True
                                elif value in ("no", "false"):
                                    bridge_data[key_lower] = False
                                elif key_lower == "actual_mtu" and value.isdigit():
                                    bridge_data[key_lower] = int(value)
                                else:
                                    bridge_data[key_lower] = value

                    bridges.append(bridge_data)
                    i += 1

                    # Process continuation lines (lines that start with spaces and are part of this bridge)
                    while i < len(lines):
                        continuation_line = lines[i]
                        # Continuation lines start with spaces and don't start a new entry (no leading digit after lstrip)
                        if continuation_line.startswith(" ") or continuation_line.startswith("\t"):
                            stripped_cont = continuation_line.lstrip()
                            # If after stripping leading space it doesn't start with a digit, it's a continuation
                            if stripped_cont and not stripped_cont[0].isdigit():
                                # This is a continuation line - parse key=value pairs
                                # Skip if this is a comment line (;;;)
                                if ";;;" not in stripped_cont:
                                    parts_cont = stripped_cont.split()
                                    current_bridge = bridges[-1]
                                    for part in parts_cont:
                                        if "=" in part:
                                            key, value = part.split("=", 1)
                                            # Remove quotes if present
                                            value = value.strip('"')
                                            # Store known fields
                                            key_lower = key.lower().replace("-", "_")
                                            if key_lower in [
                                                "name", "mtu", "actual_mtu", "l2mtu", "mac_address",
                                                "protocol_mode", "fast_forward", "igmp_snooping",
                                                "vlan_filtering", "arp", "comment", "auto_mac",
                                                "ageing_time", "priority", "max_message_age",
                                                "forward_delay", "transmit_hold_count"
                                            ]:
                                                # Convert yes/no to boolean
                                                if value in ("yes", "true"):
                                                    current_bridge[key_lower] = True
                                                elif value in ("no", "false"):
                                                    current_bridge[key_lower] = False
                                                elif key_lower == "actual_mtu" and value.isdigit():
                                                    current_bridge[key_lower] = int(value)
                                                else:
                                                    current_bridge[key_lower] = value
                                i += 1
                            else:
                                # This is a new entry, break the continuation loop
                                break
                        else:
                            # Empty line or next section
                            if not continuation_line.strip():
                                i += 1
                            break

                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse bridge line: {line!r}: {e}")
                    i += 1
            else:
                # Skip non-data lines
                i += 1

        return bridges

    async def list_bridge_ports(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """List all bridge port assignments with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            List of bridge port information dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            ports = await self._list_bridge_ports_via_rest(device_id)
            # Add transport metadata
            for port in ports:
                port["transport"] = "rest"
                port["fallback_used"] = False
                port["rest_error"] = None
            return ports
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST bridge port listing failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            # Try SSH fallback
            try:
                ports = await self._list_bridge_ports_via_ssh(device_id)
                # Add transport metadata
                for port in ports:
                    port["transport"] = "ssh"
                    port["fallback_used"] = True
                    port["rest_error"] = str(rest_exc)
                return ports
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH bridge port listing failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Bridge port listing failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _list_bridge_ports_via_rest(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch bridge ports via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            ports_data = await client.get("/rest/interface/bridge/port")

            # Normalize port data
            result: list[dict[str, Any]] = []
            if isinstance(ports_data, list):
                for port in ports_data:
                    if isinstance(port, dict):
                        result.append({
                            "id": port.get(".id", ""),
                            "interface": port.get("interface", ""),
                            "bridge": port.get("bridge", ""),
                            "disabled": port.get("disabled", False),
                            "hw": port.get("hw", True),
                            "pvid": port.get("pvid", 1),
                            "priority": port.get("priority", "0x80"),
                            "path_cost": port.get("path-cost", 10),
                            "horizon": port.get("horizon", "none"),
                            "edge": port.get("edge", "auto"),
                            "point_to_point": port.get("point-to-point", "auto"),
                            "learn": port.get("learn", "auto"),
                            "trusted": port.get("trusted", False),
                            "frame_types": port.get("frame-types", "admit-all"),
                            "ingress_filtering": port.get("ingress-filtering", False),
                            "tag_stacking": port.get("tag-stacking", False),
                            "comment": port.get("comment", ""),
                        })

            return result

        finally:
            await client.close()

    async def _list_bridge_ports_via_ssh(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch bridge ports via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/interface/bridge/port/print")
            return self._parse_bridge_port_print_output(output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_bridge_port_print_output(output: str) -> list[dict[str, Any]]:
        """Parse /interface/bridge/port/print output into port list.

        Handles RouterOS table format with flags, multiple columns.
        RouterOS output format:
        Flags: I - INACTIVE; D - DYNAMIC; H - HW-OFFLOAD
        Columns: INTERFACE, BRIDGE, HW, HORIZON, TRUSTED, FAST-LEAVE, BPDU-GUARD, EDGE, POINT-TO-POINT, PVID, FRAME-TYPES
         #     INTERFACE  BRIDGE      HW   HORIZON  TRUSTED  FAST-LEAVE  BPDU-GUARD  EDGE  POINT-TO-POINT  PVID  FRAME-TYPES
         0   H ether2     bridge-lan  yes  none     no       no          yes         auto  auto              20  admit-all
         1 I H ether3     bridge-lan  yes  none     no       no          yes         auto  auto              30  admit-all
        """
        ports: list[dict[str, Any]] = []

        # Skip header lines
        lines = output.strip().split("\n")
        for line in lines:
            # Skip header/metadata/comment lines
            if (
                not line.strip()
                or line.startswith("Flags:")
                or line.startswith("Columns:")
                or line.startswith("#")
                or line.startswith(";;;")
            ):
                continue

            # Parse data lines (start with number, potentially with flags)
            parts = line.split()
            if not parts or not parts[0][0].isdigit():
                continue

            try:
                # Format: [id] [flags...] [interface] [bridge] [hw] [horizon] [trusted] [fast-leave] [bpdu-guard] [edge] [point-to-point] [pvid] [frame-types]
                idx = 0

                # First part is always the ID
                port_id = parts[0]
                idx = 1

                # Parse flags (can be single or multiple letters: I, D, H, or combinations like "I H", "ID", "IH", etc.)
                flags = ""
                while idx < len(parts) and all(c in "HIDhid " for c in parts[idx]) and len(parts[idx]) <= 2:
                    flags += parts[idx].replace(" ", "")
                    idx += 1

                # Extract interface name
                if idx >= len(parts):
                    continue
                interface = parts[idx]
                idx += 1

                # Extract bridge name
                if idx >= len(parts):
                    continue
                bridge = parts[idx]
                idx += 1

                # Parse remaining columns: hw, horizon, trusted, fast-leave, bpdu-guard, edge, point-to-point, pvid, frame-types
                # The HW column can be empty (missing), so we need to detect it intelligently
                hw = False
                horizon = "none"
                trusted = False
                fast_leave = False
                bpdu_guard = False
                edge = "auto"
                point_to_point = "auto"
                pvid = 1
                frame_types = "admit-all"

                # Check if next column is HW (yes/no)
                if idx < len(parts) and parts[idx] in ("yes", "no"):
                    hw = parts[idx] == "yes"
                    idx += 1
                # If not, HW column is empty/missing, so we don't consume a part

                # Now parse the remaining columns in order
                if idx < len(parts):
                    horizon = parts[idx]
                    idx += 1

                if idx < len(parts):
                    trusted = parts[idx] == "yes"
                    idx += 1

                if idx < len(parts):
                    fast_leave = parts[idx] == "yes"
                    idx += 1

                if idx < len(parts):
                    bpdu_guard = parts[idx] == "yes"
                    idx += 1

                if idx < len(parts):
                    edge = parts[idx]
                    idx += 1

                if idx < len(parts):
                    point_to_point = parts[idx]
                    idx += 1

                if idx < len(parts):
                    pvid = int(parts[idx]) if parts[idx].isdigit() else 1
                    idx += 1

                if idx < len(parts):
                    frame_types = parts[idx]
                    idx += 1

                # Determine status flags from flags string
                # I = INACTIVE, D = DYNAMIC, H = HW-OFFLOAD
                inactive = "I" in flags
                dynamic = "D" in flags
                hw_offload_flag = "H" in flags

                ports.append({
                    "id": port_id,
                    "interface": interface,
                    "bridge": bridge,
                    "disabled": inactive,  # INACTIVE flag = disabled
                    "dynamic": dynamic,  # DYNAMIC flag
                    "hw": hw,  # The HW column value (yes/no)
                    "hw_offload_flag": hw_offload_flag,  # The H flag in the left margin
                    "pvid": pvid,
                    "priority": "0x80",  # Default
                    "path_cost": 10,  # Default
                    "horizon": horizon,
                    "edge": edge,
                    "point_to_point": point_to_point,
                    "learn": "auto",  # Default
                    "trusted": trusted,
                    "frame_types": frame_types,
                    "bpdu_guard": bpdu_guard,
                    "fast_leave": fast_leave,
                    "ingress_filtering": False,  # Default
                    "tag_stacking": False,  # Default
                    "comment": "",
                })

            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse bridge port line: {line!r}: {e}")
                continue

        return ports
