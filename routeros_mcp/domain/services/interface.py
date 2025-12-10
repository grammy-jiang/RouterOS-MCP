"""Interface service for network interface operations.

Provides operations for querying RouterOS interface information,
including status, statistics, and configuration.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService

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
        """List all network interfaces on a device.

        Args:
            device_id: Device identifier

        Returns:
            List of interface information dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
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
                            "mac_address": iface.get("mac-address", ""),
                        })

            return result

        finally:
            await client.close()

    async def get_interface(
        self,
        device_id: str,
        interface_id: str,
    ) -> dict[str, Any]:
        """Get detailed information about a specific interface.

        Args:
            device_id: Device identifier
            interface_id: Interface ID

        Returns:
            Interface information dictionary

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
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
                "mac_address": interface_data.get("mac-address", ""),
                "last_link_up_time": interface_data.get("last-link-up-time", ""),
            }

        finally:
            await client.close()

    async def get_interface_stats(
        self,
        device_id: str,
        interface_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get real-time traffic statistics for interfaces.

        Args:
            device_id: Device identifier
            interface_names: Optional list of interface names to filter

        Returns:
            List of traffic statistics dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Note: RouterOS monitor-traffic endpoint may require specific interface
            # For now, get all interfaces and filter
            stats_data = await client.get("/rest/interface/monitor-traffic")

            # Normalize stats data
            result: list[dict[str, Any]] = []
            if isinstance(stats_data, list):
                for stat in stats_data:
                    if isinstance(stat, dict):
                        name = stat.get("name", "")
                        
                        # Filter by interface names if provided
                        if interface_names and name not in interface_names:
                            continue

                        result.append({
                            "name": name,
                            "rx_bits_per_second": stat.get("rx-bits-per-second", 0),
                            "tx_bits_per_second": stat.get("tx-bits-per-second", 0),
                            "rx_packets_per_second": stat.get("rx-packets-per-second", 0),
                            "tx_packets_per_second": stat.get("tx-packets-per-second", 0),
                        })

            return result

        finally:
            await client.close()
