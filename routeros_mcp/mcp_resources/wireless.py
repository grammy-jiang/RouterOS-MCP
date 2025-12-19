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
                    f"Failed to fetch wireless config: {e}",
                    data={"device_id": device_id},
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
                    f"Failed to fetch wireless clients: {e}",
                    data={"device_id": device_id},
                ) from e

    @mcp.resource("device://{device_id}/capsman/remote-caps")
    async def capsman_remote_caps(device_id: str) -> str:
        """CAPsMAN remote CAP devices list for a device.

        Provides information about remote CAP (Controlled Access Point) devices
        managed by the CAPsMAN controller on this device, including:
        - Device identity and name
        - Network address
        - Connection state (authorized, provisioning, etc.)
        - RouterOS version
        - Board/hardware information
        - Signal metrics
        - Uptime

        Returns empty list if device is not a CAPsMAN controller or no CAPs
        are registered.

        Args:
            device_id: Internal device identifier

        Returns:
            JSON-formatted remote CAP list
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)
            wireless_service = WirelessService(session, settings)

            try:
                # Get device info
                device = await device_service.get_device(device_id)

                # Get CAPsMAN remote CAPs
                caps = await wireless_service.get_capsman_remote_caps(device_id)

                # Combine data
                result = {
                    "device_id": device.id,
                    "device_name": device.name,
                    "environment": device.environment,
                    "remote_caps": caps,
                    "total_caps": len(caps),
                    "note": (
                        "This lists CAP devices managed by CAPsMAN on this controller. "
                        "Empty list indicates no CAPsMAN or no registered CAPs."
                    ),
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/capsman/remote-caps",
                    extra={"device_id": device_id},
                )

                return content

            except Exception as e:
                logger.error(
                    f"Failed to fetch CAPsMAN remote CAPs for {device_id}: {e}",
                    exc_info=True,
                    extra={"device_id": device_id},
                )
                raise DeviceNotFoundError(
                    f"Failed to fetch CAPsMAN remote CAPs: {e}",
                    data={"device_id": device_id},
                ) from e

    @mcp.resource("device://{device_id}/capsman/registrations")
    async def capsman_registrations(device_id: str) -> str:
        """CAPsMAN active registrations list for a device.

        Provides information about active wireless client registrations managed
        by CAPsMAN, including:
        - Interface/radio name
        - Client MAC address
        - SSID
        - AP name (which CAP device)
        - Signal strength (RSSI in dBm)
        - Connection uptime
        - Traffic statistics

        This provides controller-centric visibility of all clients across
        CAPsMAN-managed infrastructure. Returns empty list if device is not
        a CAPsMAN controller or no clients are connected.

        Note: Signal strength is RSSI in negative dBm. Typical values:
        - -30 dBm: Excellent
        - -50 dBm: Very good
        - -65 dBm: Good
        - -75 dBm: Fair
        - -80 dBm or lower: Poor

        Args:
            device_id: Internal device identifier

        Returns:
            JSON-formatted registrations list
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)
            wireless_service = WirelessService(session, settings)

            try:
                # Get device info
                device = await device_service.get_device(device_id)

                # Get CAPsMAN registrations
                registrations = await wireless_service.get_capsman_registrations(device_id)

                # Combine data
                result = {
                    "device_id": device.id,
                    "device_name": device.name,
                    "environment": device.environment,
                    "registrations": registrations,
                    "total_registrations": len(registrations),
                    "note": (
                        "This lists client registrations managed by CAPsMAN. "
                        "Empty list indicates no CAPsMAN or no connected clients."
                    ),
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/capsman/registrations",
                    extra={"device_id": device_id},
                )

                return content

            except Exception as e:
                logger.error(
                    f"Failed to fetch CAPsMAN registrations for {device_id}: {e}",
                    exc_info=True,
                    extra={"device_id": device_id},
                )
                raise DeviceNotFoundError(
                    f"Failed to fetch CAPsMAN registrations: {e}",
                    data={"device_id": device_id},
                ) from e

    logger.info("Registered wireless resources")
