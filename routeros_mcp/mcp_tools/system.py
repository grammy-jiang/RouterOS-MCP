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
    session_factory = get_session_factory(settings)

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

                # Indicate transport/fallback to surface REST failures
                transport = overview.get("transport", "rest")
                if overview.get("fallback_used"):
                    rest_err = overview.get("rest_error") or "rest failed"
                    content_parts.append(f"Transport: {transport} (REST fallback: {rest_err})")
                else:
                    content_parts.append(f"Transport: {transport}")

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
        """List RouterOS packages (installed + available) without losing information.

        Use when:
        - User asks "what packages are installed?" or "what packages are available?"
        - Verifying software capabilities before attempting feature-specific operations
        - Troubleshooting missing features (checking if required package is installed)
        - Auditing software inventory across fleet

        Returns: List of packages including both installed packages (with version/build time)
        and available-but-not-installed packages (typically flagged XA), including size when
        present.

        Notes:
        - This is read-only and does not install/upgrade packages.
        - RouterOS REST output may omit available packages; SSH parsing is used as fallback.

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

                installed_count = sum(1 for p in packages if p.get("installed"))
                available_count = sum(1 for p in packages if p.get("available") and not p.get("installed"))

                content = (
                    f"Found {len(packages)} total packages "
                    f"({installed_count} installed, {available_count} available)"
                )

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "packages": packages,
                        "total_count": len(packages),
                        "installed_count": installed_count,
                        "available_count": available_count,
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

                system_service = SystemService(session, settings)

                # Get clock info with REST→SSH fallback
                clock_data = await system_service.get_system_clock(device_id)

                # Extract clock fields (handle both hyphen and underscore variants)
                date_str = clock_data.get("date", "")
                time_str = clock_data.get("time", "")
                timezone = clock_data.get("time-zone-name") or clock_data.get("time_zone_name", "Unknown")
                gmt_offset = clock_data.get("gmt-offset") or clock_data.get("gmt_offset", "")
                dst_active = clock_data.get("dst-active") or clock_data.get("dst_active", "")
                
                content_parts = []
                if date_str and time_str:
                    content_parts.append(f"Date/Time: {date_str} {time_str}")
                elif time_str:
                    content_parts.append(f"Time: {time_str}")
                
                if timezone and timezone != "Unknown":
                    content_parts.append(f"Timezone: {timezone}")
                
                if gmt_offset:
                    content_parts.append(f"GMT Offset: {gmt_offset}")
                
                if dst_active:
                    content_parts.append(f"DST Active: {dst_active}")

                transport = clock_data.get("transport", "rest")
                if clock_data.get("fallback_used"):
                    rest_err = clock_data.get("rest_error") or "rest failed"
                    content_parts.append(f"Transport: {transport} (REST fallback: {rest_err})")
                else:
                    content_parts.append(f"Transport: {transport}")

                content = "\n".join(content_parts)

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "time_zone_name": timezone,
                        **clock_data,
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

    logger.info("Registered system information tools")

    @mcp.tool()
    async def set_system_identity(
        device_id: str, identity: str, dry_run: bool = False
    ) -> dict[str, Any]:
        """Update system identity (hostname).

        Use when:
        - User asks "set hostname to X" or "change device name to Y"
        - Standardizing device naming across fleet
        - Updating device identity for documentation
        - Renaming device after role change

        Side effects:
        - Changes system identity immediately (unless dry_run=True)
        - Device will appear with new name in logs and MikroTik tools
        - No connectivity impact
        - Audit logged

        Safety:
        - Advanced tier (requires allow_advanced_writes=true)
        - Low risk operation
        - Supports dry_run for preview
        - Lab/staging/prod allowed (based on device flags)

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            identity: New identity name
            dry_run: If True, only return planned changes without applying

        Returns:
            Formatted tool result with update status
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                system_service = SystemService(session, settings)

                # Get device first to validate it exists
                device = await device_service.get_device(device_id)

                # Authorization check - advanced tier
                check_tool_authorization(
                    device_environment=device.environment,
                    service_environment=settings.environment,
                    tool_tier=ToolTier.ADVANCED,
                    allow_advanced_writes=device.allow_advanced_writes,
                    allow_professional_workflows=device.allow_professional_workflows,
                    device_id=device_id,
                    tool_name="system/set-identity",
                )

                # Update identity
                result = await system_service.update_system_identity(
                    device_id, identity, dry_run
                )

                # Format content
                if dry_run:
                    content = (
                        f"DRY RUN: Would change system identity from "
                        f"'{result['planned_changes']['old_identity']}' to "
                        f"'{result['planned_changes']['new_identity']}'"
                    )
                elif result["changed"]:
                    content = (
                        f"System identity updated from '{result['old_identity']}' to "
                        f"'{result['new_identity']}'"
                    )
                else:
                    content = f"System identity already set to '{identity}' (no change)"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        **result,
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

    logger.info("Registered system write tools")
