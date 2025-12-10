"""System information MCP tools.

Provides MCP tools for system overview, packages, and clock information.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.system import SystemService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_system_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register system information tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings.database_url)

    @mcp.tool()
    async def get_system_overview(device_id: str) -> dict[str, Any]:
        """Get comprehensive system information including identity, hardware, resource usage, and health metrics.

        Use when:
        - User asks "show me system status" or "what's the router's health?"
        - Troubleshooting performance issues (CPU, memory usage)
        - Gathering device information for documentation or inventory
        - Checking hardware specs (model, serial number, firmware version)
        - Verifying system uptime or recent reboots
        - Initial device assessment before configuration changes

        Returns: Identity, RouterOS version, uptime, hardware model, serial number, 
        CPU usage, memory usage, temperature, voltage.

        Tip: This is the primary "health dashboard" tool - use it as a starting point 
        for most device interactions.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with system overview
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                system_service = SystemService(session, settings)

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
                    tool_name="system/get-overview",
                )

                # Get system overview
                overview = await system_service.get_system_overview(device_id)

                # Format content
                content_parts = [
                    f"Device: {overview['device_name']}",
                    f"Identity: {overview['system_identity']}",
                    f"RouterOS: {overview['routeros_version']}",
                    f"Hardware: {overview['hardware_model']}",
                    f"CPU: {overview['cpu_usage_percent']:.1f}% "
                    f"({overview['cpu_count']} cores)",
                    f"Memory: {overview['memory_usage_percent']:.1f}% "
                    f"({overview['memory_used_bytes'] // 1024 // 1024}MB / "
                    f"{overview['memory_total_bytes'] // 1024 // 1024}MB)",
                    f"Uptime: {overview['uptime_formatted']}",
                ]

                content = "\n".join(content_parts)

                return format_tool_result(
                    content=content,
                    meta=overview,
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
    async def get_system_packages(device_id: str) -> dict[str, Any]:
        """List all installed RouterOS packages and their versions.

        Use when:
        - User asks "what packages are installed?" or "what version is wireless package?"
        - Verifying software capabilities before attempting feature-specific operations
        - Troubleshooting missing features (checking if required package is installed)
        - Auditing software inventory across fleet
        - Planning package upgrades

        Returns: List of packages with name, version, build time, and disabled status.

        Note: Does not show available upgrades (use RouterOS upgrade tools for that).

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with package list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                system_service = SystemService(session, settings)

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
                    tool_name="system/get-packages",
                )

                # Get packages
                packages = await system_service.get_system_packages(device_id)

                content = f"Found {len(packages)} installed packages"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "packages": packages,
                        "total_count": len(packages),
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
    async def get_system_clock(device_id: str) -> dict[str, Any]:
        """Get current system time, timezone, and time configuration.

        Use when:
        - User asks "what time is it on the router?" or "what timezone is configured?"
        - Troubleshooting time-related issues (logs, certificates, scheduled tasks)
        - Verifying NTP synchronization indirectly (check if time is accurate)
        - Diagnosing time drift problems
        - Before/after NTP configuration changes

        Returns: Current time (ISO 8601), timezone name, autodetect status.

        Tip: Compare with ntp/get-status to verify time synchronization health.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with clock information
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
                    tool_name="system/get-clock",
                )

                # Get clock info
                client = await device_service.get_rest_client(device_id)
                try:
                    clock_data = await client.get("/rest/system/clock")

                    time_str = clock_data.get("time", "")
                    timezone = clock_data.get("time-zone-name", "UTC")

                    content = f"System time: {time_str} {timezone}"

                    return format_tool_result(
                        content=content,
                        meta={
                            "device_id": device_id,
                            "time": time_str,
                            "time_zone_autodetect": clock_data.get("time-zone-autodetect", False),
                            "time_zone_name": timezone,
                        },
                    )
                finally:
                    await client.close()

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

    logger.info("Registered system information tools")
