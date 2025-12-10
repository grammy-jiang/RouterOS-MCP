"""MCP resources for device data (device:// URI scheme)."""

import json
import logging
from typing import Any

from fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.health import HealthService
from routeros_mcp.domain.services.system import SystemService
from routeros_mcp.mcp.errors import DeviceNotFoundError, MCPError
from routeros_mcp.mcp_resources.utils import create_resource_metadata, format_resource_content

logger = logging.getLogger(__name__)


def register_device_resources(
    mcp: FastMCP,
    session_factory: Any,
    settings: Settings,
) -> None:
    """Register device:// resources with MCP server.

    Args:
        mcp: FastMCP instance
        session_factory: Database session factory
        settings: Application settings
    """

    @mcp.resource("device://{device_id}/overview")
    async def device_overview(device_id: str) -> str:
        """Device overview with system information and health status.

        Provides comprehensive system information including:
        - RouterOS version and platform
        - System identity and board info
        - Uptime and performance metrics
        - CPU, memory, and temperature
        - Current health status

        Args:
            device_id: Internal device identifier

        Returns:
            JSON-formatted device overview
        """
        async with session_factory() as session:
            device_service = DeviceService(session, settings)
            system_service = SystemService(session, settings)
            health_service = HealthService(session, settings)

            try:
                # Get device info
                device = await device_service.get_device(device_id)

                # Get system overview
                overview = await system_service.get_overview(device_id)

                # Get current health
                try:
                    health = await health_service.get_current_health(device_id)
                    health_data = {
                        "status": health.status,
                        "last_check": health.last_check_timestamp.isoformat()
                        if health.last_check_timestamp
                        else None,
                        "metrics": health.metrics,
                    }
                except Exception as e:
                    logger.warning(
                        f"Could not fetch health data for device {device_id}: {e}"
                    )
                    health_data = {"status": "unknown", "error": str(e)}

                # Combine data
                result = {
                    "device_id": device.id,
                    "name": device.name,
                    "environment": device.environment,
                    "management_address": device.management_address,
                    "tags": device.tags or [],
                    "system": overview,
                    "health": health_data,
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/overview",
                    extra={"device_id": device_id},
                )

                return content

            except DeviceNotFoundError:
                raise MCPError(
                    code=-32000,
                    message="Device not found",
                    data={"device_id": device_id, "resource_uri": f"device://{device_id}/overview"},
                )
            except Exception as e:
                logger.error(f"Error fetching device overview: {e}", exc_info=True)
                raise MCPError(
                    code=-32001,
                    message="Failed to fetch device overview",
                    data={"device_id": device_id, "error": str(e)},
                )

    @mcp.resource("device://{device_id}/health")
    async def device_health(device_id: str) -> str:
        """Device health metrics and status.

        Provides current health status including:
        - Overall health state (healthy/warning/critical)
        - CPU usage percentage
        - Memory usage and available
        - Temperature and voltage (if available)
        - Last health check timestamp
        - Historical health metrics summary

        Args:
            device_id: Device identifier

        Returns:
            JSON-formatted health metrics
        """
        async with session_factory() as session:
            device_service = DeviceService(session, settings)
            health_service = HealthService(session, settings)

            try:
                # Verify device exists
                device = await device_service.get_device(device_id)

                # Get current health
                health = await health_service.get_current_health(device_id)

                result = {
                    "device_id": device.id,
                    "device_name": device.name,
                    "environment": device.environment,
                    "status": health.status,
                    "last_check_timestamp": health.last_check_timestamp.isoformat()
                    if health.last_check_timestamp
                    else None,
                    "metrics": health.metrics,
                    "checks": {
                        "cpu_ok": health.metrics.get("cpu_usage", 0) < 80,
                        "memory_ok": health.metrics.get("memory_usage_percent", 0) < 90,
                        "temperature_ok": health.metrics.get("temperature", 0) < 70,
                    },
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/health",
                    extra={"device_id": device_id},
                )

                return content

            except DeviceNotFoundError:
                raise MCPError(
                    code=-32000,
                    message="Device not found",
                    data={"device_id": device_id},
                )
            except Exception as e:
                logger.error(f"Error fetching device health: {e}", exc_info=True)
                raise MCPError(
                    code=-32001,
                    message="Failed to fetch device health",
                    data={"device_id": device_id, "error": str(e)},
                )

    @mcp.resource("device://{device_id}/config")
    async def device_config(device_id: str) -> str:
        """RouterOS configuration export.

        Returns the current device configuration as a RouterOS script.
        This is a placeholder - actual config export would require
        additional RouterOS API integration.

        Args:
            device_id: Device identifier

        Returns:
            RouterOS configuration script (placeholder)
        """
        async with session_factory() as session:
            device_service = DeviceService(session, settings)

            try:
                device = await device_service.get_device(device_id)

                # Placeholder - actual config export would use RouterOS API
                config_content = f"""# Configuration export for {device.name}
# Device ID: {device.id}
# Environment: {device.environment}
# Management Address: {device.management_address}
# Generated: {datetime.now(UTC).isoformat()}
#
# NOTE: Full configuration export requires RouterOS REST API integration
# This is a placeholder for the configuration export feature.

/system identity set name="{device.name}"
# Additional configuration would be exported here...
"""

                logger.info(
                    f"Resource accessed: device://{device_id}/config",
                    extra={"device_id": device_id},
                )

                return config_content

            except DeviceNotFoundError:
                raise MCPError(
                    code=-32000,
                    message="Device not found",
                    data={"device_id": device_id},
                )

    @mcp.resource("device://{device_id}/logs")
    async def device_logs(device_id: str) -> str:
        """Device system logs.

        Returns recent system logs from the device.
        This is a placeholder - actual log retrieval would require
        additional RouterOS API integration.

        Args:
            device_id: Device identifier

        Returns:
            JSON array of log entries (placeholder)
        """
        async with session_factory() as session:
            device_service = DeviceService(session, settings)

            try:
                device = await device_service.get_device(device_id)

                # Placeholder - actual logs would be fetched from RouterOS
                logs = {
                    "device_id": device.id,
                    "device_name": device.name,
                    "logs": [
                        {
                            "timestamp": datetime.now(UTC).isoformat(),
                            "level": "info",
                            "message": "Placeholder log entry",
                            "topics": ["system"],
                        }
                    ],
                    "note": "Full log retrieval requires RouterOS REST API integration",
                }

                content = format_resource_content(logs, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/logs",
                    extra={"device_id": device_id},
                )

                return content

            except DeviceNotFoundError:
                raise MCPError(
                    code=-32000,
                    message="Device not found",
                    data={"device_id": device_id},
                )


__all__ = ["register_device_resources"]
