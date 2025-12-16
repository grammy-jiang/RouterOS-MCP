"""MCP resources for bridge data (device://{device_id}/bridges URI)."""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.bridge import BridgeService
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.mcp.errors import DeviceNotFoundError, MCPError
from routeros_mcp.mcp_resources.utils import (
    create_resource_metadata,
    format_resource_content,
)

logger = logging.getLogger(__name__)


def register_bridge_resources(
    mcp: FastMCP,
    session_factory: DatabaseSessionManager,
    settings: Settings,
) -> None:
    """Register bridge:// resources with MCP server.

    Args:
        mcp: FastMCP instance
        session_factory: Database session factory
        settings: Application settings
    """

    @mcp.resource("device://{device_id}/bridges")
    async def device_bridges(device_id: str) -> str:
        """Bridge topology overview with all bridges and their member ports.

        Provides comprehensive bridge information including:
        - Bridge interfaces with configuration
        - Bridge port assignments
        - VLAN filtering status
        - STP/RSTP protocol mode and status
        - Hardware offload status
        - Port PVID and tagging configuration

        Args:
            device_id: Internal device identifier

        Returns:
            JSON-formatted bridge topology
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)
            bridge_service = BridgeService(session, settings)

            try:
                # Get device info
                device = await device_service.get_device(device_id)

                # Get bridges
                bridges = await bridge_service.list_bridges(device_id)

                # Get bridge ports
                ports = await bridge_service.list_bridge_ports(device_id)

                # Organize ports by bridge
                ports_by_bridge: dict[str, list[dict[str, Any]]] = {}
                for port in ports:
                    bridge_name = port.get("bridge", "")
                    if bridge_name not in ports_by_bridge:
                        ports_by_bridge[bridge_name] = []
                    ports_by_bridge[bridge_name].append(port)

                # Add member ports to each bridge
                for bridge in bridges:
                    bridge_name = bridge.get("name", "")
                    bridge["member_ports"] = ports_by_bridge.get(bridge_name, [])

                # Combine data
                result = {
                    "device_id": device.id,
                    "device_name": device.name,
                    "environment": device.environment,
                    "bridges": bridges,
                    "total_bridges": len(bridges),
                    "total_ports": len(ports),
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/bridges",
                    extra={"device_id": device_id},
                )

                return content

            except DeviceNotFoundError as e:
                logger.warning(
                    f"Device not found: {device_id}",
                    extra={"device_id": device_id},
                )
                raise MCPError(
                    code=-32002,
                    message=f"Device not found: {device_id}",
                    data={"device_id": device_id},
                ) from e

            except Exception as e:
                logger.error(
                    f"Error accessing device://{device_id}/bridges: {e}",
                    exc_info=True,
                    extra={"device_id": device_id},
                )
                raise MCPError(
                    code=-32000,
                    message=f"Failed to retrieve bridge data: {str(e)}",
                    data={"device_id": device_id, "error": str(e)},
                ) from e

    logger.info("Registered bridge resources")
