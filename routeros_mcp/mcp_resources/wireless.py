"""MCP resources for wireless data (device://{device_id}/wireless URI scheme)."""

import logging

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.wireless import WirelessService
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.mcp.errors import DeviceNotFoundError
from routeros_mcp.mcp_resources.utils import (
    format_resource_content,
)

logger = logging.getLogger(__name__)


def register_wireless_resources(
    mcp: FastMCP,
    session_factory: DatabaseSessionManager,
    settings: Settings,
) -> None:
    """Register device://{device_id}/wireless resources with MCP server.

    Args:
        mcp: FastMCP instance
        session_factory: Database session factory
        settings: Application settings
    """

    @mcp.resource("device://{device_id}/wireless")
    async def wireless_config(device_id: str) -> str:
        """Wireless configuration snapshot for a device.

        Provides comprehensive wireless interface configuration including:
        - SSID names and broadcast settings
        - Frequency, band, and channel width
        - TX power and power mode
        - Operating mode (ap-bridge, station, etc.)
        - Interface status (running, disabled)
        - Connected client counts

        Args:
            device_id: Internal device identifier

        Returns:
            JSON-formatted wireless configuration
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)
            wireless_service = WirelessService(session, settings)

            try:
                # Get device info
                device = await device_service.get_device(device_id)

                # Get wireless interfaces
                interfaces = await wireless_service.get_wireless_interfaces(device_id)

                # Combine data
                result = {
                    "device_id": device.id,
                    "device_name": device.name,
                    "environment": device.environment,
                    "interfaces": interfaces,
                    "total_interfaces": len(interfaces),
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/wireless",
                    extra={"device_id": device_id},
                )

                return content

            except Exception as e:
                logger.error(
                    f"Failed to fetch wireless config for {device_id}: {e}",
                    exc_info=True,
                    extra={"device_id": device_id},
                )
                raise DeviceNotFoundError(
                    f"Failed to fetch wireless config: {e}", {"device_id": device_id}
                ) from e

    @mcp.resource("device://{device_id}/wireless/clients")
    async def wireless_clients(device_id: str) -> str:
        """Connected wireless clients list for a device.

        Provides information about currently connected wireless clients including:
        - Interface name (which AP they're connected to)
        - MAC address
        - Signal strength (RSSI in dBm, negative values)
        - Signal-to-noise ratio
        - TX/RX rates (in Mbps)
        - Connection uptime
        - Traffic statistics (bytes/packets sent and received)

        Note: Signal strength is RSSI in negative dBm. Typical values:
        - -30 dBm: Excellent signal
        - -50 dBm: Very good signal
        - -65 dBm: Good signal
        - -75 dBm: Fair signal
        - -80 dBm or lower: Poor signal

        Args:
            device_id: Internal device identifier

        Returns:
            JSON-formatted wireless clients list
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)
            wireless_service = WirelessService(session, settings)

            try:
                # Get device info
                device = await device_service.get_device(device_id)

                # Get wireless clients
                clients = await wireless_service.get_wireless_clients(device_id)

                # Combine data
                result = {
                    "device_id": device.id,
                    "device_name": device.name,
                    "environment": device.environment,
                    "clients": clients,
                    "total_clients": len(clients),
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/wireless/clients",
                    extra={"device_id": device_id},
                )

                return content

            except Exception as e:
                logger.error(
                    f"Failed to fetch wireless clients for {device_id}: {e}",
                    exc_info=True,
                    extra={"device_id": device_id},
                )
                raise DeviceNotFoundError(
                    f"Failed to fetch wireless clients: {e}", {"device_id": device_id}
                ) from e

    logger.info("Registered wireless resources")
