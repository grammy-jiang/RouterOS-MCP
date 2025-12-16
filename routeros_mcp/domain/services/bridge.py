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

        Handles RouterOS standard table format with flags in left margin.
        RouterOS output format:
        Flags: R - RUNNING; D - DISABLED
         #     NAME              MTU   ACTUAL-MTU  MAC-ADDRESS        PROTOCOL-MODE
         0  R  bridge1           auto  1500        78:9A:18:A2:F3:D4  rstp
        """
        bridges: list[dict[str, Any]] = []

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
                # Format: [id] [flags*] [name] [mtu] [actual-mtu] [mac-address] [protocol-mode]
                idx = 0

                # First part is always the ID
                bridge_id = parts[0]
                idx = 1

                # Check if second part contains flags (one or more flag characters)
                flags = ""
                if len(parts) > 1 and all(c in "RDSXrdsx " for c in parts[1]):
                    flags = parts[1].replace(" ", "")
                    idx = 2

                # Extract fields: name, mtu, actual-mtu, etc.
                if len(parts) > idx + 1:
                    name = parts[idx]
                    mtu_str = parts[idx + 1] if len(parts) > idx + 1 else "auto"

                    # Remaining parts
                    remaining = parts[idx + 2:]

                    # Parse MTU (might be "auto" or numeric)
                    mtu = 1500
                    if mtu_str.isdigit():
                        mtu = int(mtu_str)

                    # Try to extract actual-mtu, mac-address, and protocol-mode
                    actual_mtu = 1500
                    mac_address = ""
                    protocol_mode = "rstp"

                    # Process remaining fields
                    for field in remaining:
                        if field.isdigit() and actual_mtu == 1500:
                            actual_mtu = int(field)
                        elif ":" in field and len(field) > 5:
                            mac_address = field
                        elif field in ("rstp", "stp", "none", "mstp"):
                            protocol_mode = field

                    # Determine running and disabled status from flags
                    running = "R" in flags
                    disabled = "D" in flags

                    bridges.append({
                        "id": bridge_id,
                        "name": name,
                        "mtu": mtu,
                        "actual_mtu": actual_mtu,
                        "l2mtu": 1514,  # Default
                        "mac_address": mac_address,
                        "arp": "enabled",  # Default
                        "arp_timeout": "auto",  # Default
                        "disabled": disabled,
                        "running": running,
                        "auto_mac": True,  # Default
                        "ageing_time": "5m",  # Default
                        "priority": "0x8000",  # Default
                        "protocol_mode": protocol_mode,
                        "fast_forward": True,  # Default
                        "vlan_filtering": False,  # Default
                        "comment": "",
                    })

            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse bridge line: {line!r}: {e}")
                continue

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

        Handles RouterOS standard table format with flags in left margin.
        RouterOS output format:
        Flags: H - HW-OFFLOAD; I - INACTIVE; D - DISABLED
         #     INTERFACE  BRIDGE    HW  PVID  PRIORITY  PATH-COST
         0  H  ether2     bridge1   yes 1     0x80      10
        """
        ports: list[dict[str, Any]] = []

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
                # Format: [id] [flags*] [interface] [bridge] [hw] [pvid] [priority] [path-cost]
                idx = 0

                # First part is always the ID
                port_id = parts[0]
                idx = 1

                # Check if second part contains flags
                flags = ""
                if len(parts) > 1 and all(c in "HIDhid " for c in parts[1]):
                    flags = parts[1].replace(" ", "")
                    idx = 2

                # Extract fields: interface, bridge, hw, pvid, etc.
                if len(parts) > idx + 1:
                    interface = parts[idx]
                    bridge = parts[idx + 1] if len(parts) > idx + 1 else ""

                    # Remaining parts
                    remaining = parts[idx + 2:]

                    # Parse remaining fields in order: hw, pvid, priority, path-cost
                    hw = True
                    pvid = 1
                    priority = "0x80"
                    path_cost = 10

                    field_idx = 0
                    for field in remaining:
                        if field in ("yes", "no"):
                            hw = field == "yes"
                            field_idx += 1
                        elif field.isdigit():
                            # First number is PVID, second is path-cost
                            if field_idx == 1:
                                pvid = int(field)
                            elif field_idx == 3:
                                path_cost = int(field)
                            field_idx += 1
                        elif field.startswith("0x"):
                            priority = field
                            field_idx += 1

                    # Determine disabled status from flags
                    disabled = "D" in flags

                    ports.append({
                        "id": port_id,
                        "interface": interface,
                        "bridge": bridge,
                        "disabled": disabled,
                        "hw": hw,
                        "pvid": pvid,
                        "priority": priority,
                        "path_cost": path_cost,
                        "horizon": "none",  # Default
                        "edge": "auto",  # Default
                        "point_to_point": "auto",  # Default
                        "learn": "auto",  # Default
                        "trusted": False,  # Default
                        "frame_types": "admit-all",  # Default
                        "ingress_filtering": False,  # Default
                        "tag_stacking": False,  # Default
                        "comment": "",
                    })

            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse bridge port line: {line!r}: {e}")
                continue

        return ports
