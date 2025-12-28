"""Bridge service for network bridge operations.

Provides operations for querying RouterOS bridge information,
including bridge configurations, member interfaces, and VLAN settings,
plus plan/apply workflow for bridge changes.
"""

import gzip
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
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
from routeros_mcp.infra.routeros.rest_client import RouterOSRestClient

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
                    "Both REST and SSH bridge listing failed",
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
                    "Both REST and SSH bridge port listing failed",
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


class BridgePlanService:
    """Service for bridge planning operations.

    Provides:
    - Bridge parameter validation (interface exists, not already bridged)
    - Risk level assessment based on operation type and environment
    - STP safety rules (block STP changes on production bridges)
    - Preview generation for planned changes
    - Snapshot creation for rollback
    - Health check after bridge changes

    All bridge operations follow the plan/apply workflow.
    """

    # High-risk conditions for risk assessment
    HIGH_RISK_ENVIRONMENTS = ["prod"]  # Production environment
    HIGH_RISK_OPERATIONS = ["modify_bridge_stp", "modify_bridge_vlan_filtering"]

    # Production STP protection
    PROTECTED_PRODUCTION_BRIDGES = ["bridge-lan", "bridge-core", "bridge-prod"]

    def validate_bridge_params(
        self,
        bridge_name: str,
        interface: str | None = None,
        settings: dict[str, Any] | None = None,
        operation: str = "add_port",
    ) -> dict[str, Any]:
        """Validate bridge operation parameters.

        Args:
            bridge_name: Name of the bridge
            interface: Interface name (for add/remove port operations)
            settings: Bridge settings dict (for modify operations)
            operation: Operation type (add_port/remove_port/modify_settings)

        Returns:
            Dictionary with validation result

        Raises:
            ValueError: If any parameter is invalid
        """
        errors = []

        # Validate bridge name
        if not bridge_name or not bridge_name.strip():
            errors.append("Bridge name cannot be empty")

        # Validate interface for port operations
        if operation in ["add_bridge_port", "remove_bridge_port"]:
            if not interface or not interface.strip():
                errors.append(f"Interface name is required for {operation} operation")
            elif interface.strip() == bridge_name.strip():
                errors.append("Cannot add bridge interface to itself")

        # Validate settings for modify operations
        if operation == "modify_bridge_settings":
            if not settings:
                errors.append("Settings dict is required for modify_settings operation")
            else:
                # Validate known settings
                valid_settings = {
                    "protocol_mode", "stp", "vlan_filtering", "priority",
                    "ageing_time", "forward_delay", "max_message_age"
                }
                invalid_settings = set(settings.keys()) - valid_settings
                if invalid_settings:
                    errors.append(
                        f"Invalid settings: {', '.join(invalid_settings)}. "
                        f"Valid settings: {', '.join(valid_settings)}"
                    )

                # Validate protocol_mode if present
                if "protocol_mode" in settings:
                    valid_modes = ["none", "stp", "rstp", "mstp"]
                    if settings["protocol_mode"] not in valid_modes:
                        errors.append(
                            f"Invalid protocol_mode '{settings['protocol_mode']}'. "
                            f"Must be one of: {', '.join(valid_modes)}"
                        )

        if errors:
            raise ValueError("Bridge parameter validation failed:\n- " + "\n- ".join(errors))

        logger.debug(
            f"Bridge parameter validation passed for bridge={bridge_name}, "
            f"operation={operation}"
        )

        return {
            "valid": True,
            "bridge_name": bridge_name,
            "interface": interface,
            "settings": settings,
            "operation": operation,
        }

    def check_interface_available(
        self,
        interface: str,
        existing_ports: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Check if interface is available for bridging.

        Args:
            interface: Interface name to check
            existing_ports: List of existing bridge port assignments

        Returns:
            Dictionary with availability status

        Raises:
            ValueError: If interface is already bridged
        """
        for port in existing_ports:
            if port.get("interface") == interface:
                raise ValueError(
                    f"Interface '{interface}' is already a member of bridge '{port.get('bridge')}'"
                )

        logger.debug(f"Interface '{interface}' is available for bridging")
        return {
            "available": True,
            "interface": interface,
        }

    def check_stp_safety(
        self,
        bridge_name: str,
        settings: dict[str, Any],
        device_environment: str,
    ) -> dict[str, Any]:
        """Check if STP/protocol changes are safe.

        Blocks STP changes on production bridges to prevent loops.

        Args:
            bridge_name: Bridge name
            settings: Proposed settings changes
            device_environment: Device environment (lab/staging/prod)

        Returns:
            Dictionary with safety check result

        Raises:
            ValueError: If STP changes are blocked
        """
        # Check if changing STP/protocol settings
        stp_related_keys = {"protocol_mode", "stp", "priority", "forward_delay", "max_message_age"}
        is_stp_change = bool(set(settings.keys()) & stp_related_keys)

        # Block STP changes on protected production bridges
        if (
            device_environment == "prod"
            and is_stp_change
            and bridge_name in self.PROTECTED_PRODUCTION_BRIDGES
        ):
            raise ValueError(
                f"STP/protocol changes are blocked on production bridge '{bridge_name}'. "
                f"Protected production bridges: {', '.join(self.PROTECTED_PRODUCTION_BRIDGES)}"
            )

        logger.debug(
            f"STP safety check passed for bridge={bridge_name}, env={device_environment}"
        )
        return {
            "safe": True,
            "bridge_name": bridge_name,
            "is_stp_change": is_stp_change,
        }

    def assess_risk(
        self,
        operation: str,
        device_environment: str = "lab",
        is_stp_change: bool = False,
        is_vlan_filtering_change: bool = False,
    ) -> str:
        """Assess risk level for a bridge operation.

        Risk classification:
        - High risk:
          - Production environment
          - STP/RSTP/MSTP parameter changes
          - VLAN filtering changes
          - Port removal from production bridge
        - Medium risk:
          - Lab/staging environments
          - Port additions
          - Non-STP/VLAN setting changes

        Args:
            operation: Operation type (add_port/remove_port/modify_settings)
            device_environment: Device environment (lab/staging/prod)
            is_stp_change: Whether operation modifies STP settings
            is_vlan_filtering_change: Whether operation modifies VLAN filtering

        Returns:
            Risk level: "medium" or "high"
        """
        # High risk conditions
        if device_environment in self.HIGH_RISK_ENVIRONMENTS:
            logger.info("High risk: production environment")
            return "high"

        if is_stp_change:
            logger.info("High risk: STP parameter changes can create loops")
            return "high"

        if is_vlan_filtering_change:
            logger.info("High risk: VLAN filtering changes affect network segmentation")
            return "high"

        if operation == "remove_bridge_port":
            logger.info("High risk: port removal may disrupt connectivity")
            return "high"

        # Default to medium risk
        logger.debug(
            f"Medium risk: operation={operation}, env={device_environment}, "
            f"stp={is_stp_change}, vlan={is_vlan_filtering_change}"
        )
        return "medium"

    def generate_preview(
        self,
        operation: str,
        device_id: str,
        device_name: str,
        device_environment: str,
        bridge_name: str,
        interface: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate detailed preview for a bridge operation.

        Args:
            operation: Operation type (add_bridge_port/remove_bridge_port/modify_bridge_settings)
            device_id: Device identifier
            device_name: Device name
            device_environment: Device environment
            bridge_name: Bridge name
            interface: Interface name (for add/remove port)
            settings: Settings dict (for modify)

        Returns:
            Preview dictionary with operation details
        """
        preview: dict[str, Any] = {
            "device_id": device_id,
            "name": device_name,
            "environment": device_environment,
            "operation": operation,
            "pre_check_status": "passed",
        }

        if operation == "add_bridge_port":
            preview["preview"] = {
                "operation": "add_bridge_port",
                "bridge_name": bridge_name,
                "interface": interface,
                "estimated_impact": "Medium - interface will join bridge, forwarding will begin",
            }

        elif operation == "remove_bridge_port":
            preview["preview"] = {
                "operation": "remove_bridge_port",
                "bridge_name": bridge_name,
                "interface": interface,
                "estimated_impact": "High - interface will leave bridge, may disrupt connectivity",
            }

        elif operation == "modify_bridge_settings":
            is_stp_change = bool(
                set(settings.keys() if settings else [])
                & {"protocol_mode", "stp", "priority", "forward_delay", "max_message_age"}
            )
            is_vlan_change = "vlan_filtering" in (settings or {})

            impact = "Medium - bridge settings will be updated"
            if is_stp_change:
                impact = "High - STP changes can create loops or outages"
            elif is_vlan_change:
                impact = "High - VLAN filtering affects network segmentation"

            preview["preview"] = {
                "operation": "modify_bridge_settings",
                "bridge_name": bridge_name,
                "settings": settings or {},
                "is_stp_change": is_stp_change,
                "is_vlan_filtering_change": is_vlan_change,
                "estimated_impact": impact,
            }

        logger.debug(f"Generated preview for {operation} on device {device_id}")

        return preview

    async def create_bridge_snapshot(
        self,
        device_id: str,
        device_name: str,
        rest_client: RouterOSRestClient,
    ) -> dict[str, Any]:
        """Create snapshot of current bridge configuration for rollback.

        Args:
            device_id: Device identifier
            device_name: Device name
            rest_client: REST client instance for device

        Returns:
            Snapshot metadata with snapshot_id and bridge configuration payload

        Raises:
            Exception: If snapshot creation fails
        """
        try:
            # Fetch current bridge configuration
            bridges = await rest_client.get("/rest/interface/bridge")

            # Fetch bridge ports
            bridge_ports = await rest_client.get("/rest/interface/bridge/port")

            # Fetch bridge VLAN configuration
            bridge_vlans = await rest_client.get("/rest/interface/bridge/vlan")

            # Create snapshot payload
            snapshot_payload = {
                "device_id": device_id,
                "device_name": device_name,
                "timestamp": datetime.now(UTC).isoformat(),
                "bridges": bridges if isinstance(bridges, list) else [],
                "bridge_ports": bridge_ports if isinstance(bridge_ports, list) else [],
                "bridge_vlans": bridge_vlans if isinstance(bridge_vlans, list) else [],
            }

            # Serialize and compress
            payload_json = json.dumps(snapshot_payload)
            payload_bytes = payload_json.encode("utf-8")
            compressed_data = gzip.compress(payload_bytes, compresslevel=6)

            # Calculate checksum
            checksum = hashlib.sha256(payload_bytes).hexdigest()

            # Generate snapshot ID
            snapshot_id = f"snap-bridge-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

            logger.info(
                f"Created bridge snapshot {snapshot_id} for device {device_id}",
                extra={
                    "snapshot_id": snapshot_id,
                    "device_id": device_id,
                    "bridge_count": len(snapshot_payload["bridges"]),
                    "port_count": len(snapshot_payload["bridge_ports"]),
                    "size_bytes": len(payload_bytes),
                    "compressed_size": len(compressed_data),
                },
            )

            return {
                "snapshot_id": snapshot_id,
                "device_id": device_id,
                "timestamp": snapshot_payload["timestamp"],
                "bridge_count": len(snapshot_payload["bridges"]),
                "port_count": len(snapshot_payload["bridge_ports"]),
                "size_bytes": len(payload_bytes),
                "compressed_size": len(compressed_data),
                "checksum": checksum,
                "data": compressed_data,
            }

        except Exception as e:
            logger.error(
                f"Failed to create bridge snapshot for device {device_id}: {e}",
                exc_info=True,
            )
            raise

    async def perform_health_check(
        self,
        device_id: str,
        rest_client: RouterOSRestClient,
        bridge_name: str | None = None,
        expected_port: str | None = None,
        timeout_seconds: float = 30.0,  # noqa: ARG002 - reserved for future timeout implementation
    ) -> dict[str, Any]:
        """Perform health check after bridge changes.

        Verifies:
        - Device still responds to REST API
        - Bridge configuration is accessible
        - Expected port exists (if specified)
        - Bridge is running (if specified)

        Args:
            device_id: Device identifier
            rest_client: REST client instance for device
            bridge_name: Bridge name to verify (optional)
            expected_port: Port to verify (optional)
            timeout_seconds: Health check timeout (default: 30s)

        Returns:
            Health check results with status and details

        Raises:
            Exception: If health check fails critically
        """
        try:
            # Test 1: Check device responds to REST API
            system_resource = await rest_client.get("/rest/system/resource")

            if not system_resource:
                return {
                    "status": "failed",
                    "device_id": device_id,
                    "checks": [
                        {
                            "check": "rest_api_response",
                            "status": "failed",
                            "message": "Device did not respond to REST API",
                        }
                    ],
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            # Test 2: Verify bridge configuration is accessible
            bridges = await rest_client.get("/rest/interface/bridge")

            if bridges is None:
                return {
                    "status": "failed",
                    "device_id": device_id,
                    "checks": [
                        {
                            "check": "bridge_config_accessible",
                            "status": "failed",
                            "message": "Bridge configuration not accessible",
                        }
                    ],
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            checks = [
                {
                    "check": "rest_api_response",
                    "status": "passed",
                    "message": "Device responding to REST API",
                },
                {
                    "check": "bridge_config_accessible",
                    "status": "passed",
                    "message": "Bridge configuration accessible",
                },
            ]

            # Test 3: Verify expected bridge exists and is running (if specified)
            if bridge_name:
                bridge_list = bridges if isinstance(bridges, list) else []
                target_bridge = next(
                    (b for b in bridge_list if b.get("name") == bridge_name),
                    None
                )

                if target_bridge:
                    is_running = target_bridge.get("running", False)
                    checks.append({
                        "check": "expected_bridge_exists",
                        "status": "passed",
                        "message": f"Bridge '{bridge_name}' exists (running={is_running})",
                    })

                    if not is_running:
                        checks.append({
                            "check": "bridge_running",
                            "status": "warning",
                            "message": f"Bridge '{bridge_name}' is not running",
                        })
                else:
                    checks.append({
                        "check": "expected_bridge_exists",
                        "status": "failed",
                        "message": f"Bridge '{bridge_name}' not found",
                    })
                    return {
                        "status": "failed",
                        "device_id": device_id,
                        "checks": checks,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }

            # Test 4: Verify expected port exists (if specified)
            if expected_port and bridge_name:
                bridge_ports = await rest_client.get("/rest/interface/bridge/port")
                port_list = bridge_ports if isinstance(bridge_ports, list) else []

                port_exists = any(
                    port.get("interface") == expected_port and port.get("bridge") == bridge_name
                    for port in port_list
                )

                if port_exists:
                    checks.append({
                        "check": "expected_port_exists",
                        "status": "passed",
                        "message": f"Port '{expected_port}' exists in bridge '{bridge_name}'",
                    })
                else:
                    checks.append({
                        "check": "expected_port_exists",
                        "status": "failed",
                        "message": f"Port '{expected_port}' not found in bridge '{bridge_name}'",
                    })
                    return {
                        "status": "failed",
                        "device_id": device_id,
                        "checks": checks,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }

            logger.info(
                f"Bridge health check passed for device {device_id}",
                extra={"device_id": device_id, "checks": len(checks)},
            )

            return {
                "status": "passed",
                "device_id": device_id,
                "checks": checks,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error(
                f"Bridge health check failed for device {device_id}: {e}",
                exc_info=True,
            )
            return {
                "status": "failed",
                "device_id": device_id,
                "checks": [
                    {
                        "check": "health_check_execution",
                        "status": "failed",
                        "message": f"Health check failed with error: {str(e)}",
                    }
                ],
                "timestamp": datetime.now(UTC).isoformat(),
            }
