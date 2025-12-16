"""MCP resources for DHCP data (device://{device_id}/dhcp-* URI scheme)."""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.dhcp import DHCPService
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.mcp_resources.utils import (
    create_resource_metadata,
    format_resource_content,
)

logger = logging.getLogger(__name__)


def register_dhcp_resources(
    mcp: FastMCP,
    session_factory: DatabaseSessionManager,
    settings: Settings,
) -> None:
    """Register DHCP resources with MCP server.

    Args:
        mcp: FastMCP instance
        session_factory: Database session factory
        settings: Application settings
    """

    @mcp.resource("device://{device_id}/dhcp-server")
    async def dhcp_server_status(device_id: str) -> str:
        """DHCP server configuration and status.

        Provides comprehensive DHCP server information including:
        - Server name and interface
        - Lease time configuration
        - Address pool assignment
        - Server enabled/disabled status

        Args:
            device_id: Internal device identifier

        Returns:
            JSON-formatted DHCP server status
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)
            dhcp_service = DHCPService(session, settings)

            try:
                # Validate device exists
                await device_service.get_device(device_id)

                # Get DHCP server status
                server_status = await dhcp_service.get_dhcp_server_status(device_id)

                # Add metadata
                result = {
                    "device_id": device_id,
                    "servers": server_status["servers"],
                    "total_count": server_status["total_count"],
                    "transport": server_status.get("transport", "rest"),
                    "fallback_used": server_status.get("fallback_used", False),
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/dhcp-server",
                    extra={"device_id": device_id, "server_count": result["total_count"]},
                )

                return content

            except Exception as e:
                logger.error(
                    f"Failed to fetch DHCP server status for device {device_id}: {e}",
                    exc_info=True,
                )
                raise

    @mcp.resource("device://{device_id}/dhcp-leases")
    async def dhcp_leases(device_id: str) -> str:
        """Active DHCP leases with client information.

        Provides active DHCP lease information including:
        - IP address and MAC address
        - Client ID and hostname
        - Server name
        - Lease status and expiry (if available)

        Note: Only returns active (bound) leases. Expired or released leases are filtered out.

        Args:
            device_id: Internal device identifier

        Returns:
            JSON-formatted DHCP leases
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)
            dhcp_service = DHCPService(session, settings)

            try:
                # Validate device exists
                await device_service.get_device(device_id)

                # Get DHCP leases
                leases_data = await dhcp_service.get_dhcp_leases(device_id)

                # Add metadata
                result = {
                    "device_id": device_id,
                    "leases": leases_data["leases"],
                    "total_count": leases_data["total_count"],
                    "transport": leases_data.get("transport", "rest"),
                    "fallback_used": leases_data.get("fallback_used", False),
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/dhcp-leases",
                    extra={"device_id": device_id, "lease_count": result["total_count"]},
                )

                return content

            except Exception as e:
                logger.error(
                    f"Failed to fetch DHCP leases for device {device_id}: {e}",
                    exc_info=True,
                )
                raise

    logger.info("Registered DHCP resources")
