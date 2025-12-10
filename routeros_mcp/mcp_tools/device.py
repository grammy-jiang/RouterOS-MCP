"""Device management MCP tools.

Provides MCP tools for device registry operations and connectivity checks.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_device_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register device management tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings.database_url)

    @mcp.tool()
    async def list_devices(
        environment: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """List all registered RouterOS devices in the MCP service.

        Use when:
        - User asks "what devices are available?" or "show me all routers"
        - Beginning device selection workflows (user needs to choose a target)
        - Filtering devices by environment (lab/staging/prod) or tags (site, role, region)
        - Checking device health status across the fleet
        - Auditing device inventory

        Returns: List of devices with ID, name, management address, environment, 
        status, RouterOS version, tags, and capability flags.

        Tip: Use tags parameter to narrow results (e.g., {"site": "datacenter-1"}).

        Args:
            environment: Optional filter by environment (lab/staging/prod)
            tags: Optional filter by tags (key-value pairs)

        Returns:
            Formatted tool result with device list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)

                # List devices with optional filters
                devices = await device_service.list_devices(
                    environment=environment,
                )

                # Filter by tags if provided
                if tags:
                    filtered_devices = []
                    for device in devices:
                        device_tags = device.tags or {}
                        if all(device_tags.get(k) == v for k, v in tags.items()):
                            filtered_devices.append(device)
                    devices = filtered_devices

                # Format devices for output
                devices_data = []
                for device in devices:
                    devices_data.append({
                        "id": device.id,
                        "name": device.name,
                        "management_address": device.management_address,
                        "environment": device.environment,
                        "status": device.status,
                        "routeros_version": device.routeros_version,
                        "hardware_model": device.hardware_model,
                        "tags": device.tags,
                        "allow_advanced_writes": device.allow_advanced_writes,
                        "allow_professional_workflows": device.allow_professional_workflows,
                    })

                content = f"Found {len(devices)} device(s)"
                if environment:
                    content += f" in {environment} environment"
                if tags:
                    content += f" with tags {tags}"

                return format_tool_result(
                    content=content,
                    meta={
                        "devices": devices_data,
                        "total_count": len(devices),
                    },
                )

        except MCPError as e:
            return format_tool_result(
                content=e.message,
                is_error=True,
                meta=e.data,
            )
        except Exception as e:
            error = map_exception_to_error(e)
            return format_tool_result(
                content=error.message,
                is_error=True,
                meta=error.data,
            )

    @mcp.tool()
    async def check_connectivity(device_id: str) -> dict[str, Any]:
        """Verify if a device is reachable and responsive.

        Use when:
        - User asks "is device X reachable?" or "can you ping this router?"
        - Troubleshooting connectivity issues before attempting configuration changes
        - Validating device registration (checking if new device responds)
        - Quick health check without full system overview
        - Pre-flight check before plan execution

        Returns: Reachability status, response time, RouterOS version.

        Note: Lightweight check (only tests API connectivity, not full health).

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with connectivity status
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)

                # Get device first to validate it exists
                device = await device_service.get_device(device_id)

                # Authorization check - fundamental tier, read-only
                check_tool_authorization(
                    device_environment=device.environment,
                    service_environment=settings.environment,
                    tool_tier=ToolTier.FUNDAMENTAL,
                    allow_advanced_writes=device.allow_advanced_writes,
                    allow_professional_workflows=device.allow_professional_workflows,
                    device_id=device_id,
                    tool_name="device/check-connectivity",
                )

                # Check connectivity
                import time
                start_time = time.time()
                is_reachable = await device_service.check_connectivity(device_id)
                response_time_ms = (time.time() - start_time) * 1000

                if is_reachable:
                    # Refresh device to get updated version
                    device = await device_service.get_device(device_id)
                    
                    return format_tool_result(
                        content=f"Device {device_id} is reachable",
                        meta={
                            "device_id": device_id,
                            "reachable": True,
                            "response_time_ms": round(response_time_ms, 2),
                            "routeros_version": device.routeros_version,
                        },
                    )
                else:
                    return format_tool_result(
                        content=f"Device {device_id} is not reachable",
                        is_error=True,
                        meta={
                            "device_id": device_id,
                            "reachable": False,
                        },
                    )

        except MCPError as e:
            return format_tool_result(
                content=e.message,
                is_error=True,
                meta=e.data,
            )
        except Exception as e:
            error = map_exception_to_error(e)
            return format_tool_result(
                content=error.message,
                is_error=True,
                meta=error.data,
            )

    logger.info("Registered device management tools")
