"""MCP resources for fleet data (fleet:// URI scheme)."""

import logging
from datetime import UTC, datetime

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.health import HealthService
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.mcp.errors import MCPError
from routeros_mcp.mcp_resources.utils import format_resource_content

logger = logging.getLogger(__name__)


def register_fleet_resources(
    mcp: FastMCP,
    session_factory: DatabaseSessionManager,
    settings: Settings,
) -> None:
    """Register fleet:// resources with MCP server.

    Args:
        mcp: FastMCP instance
        session_factory: Database session factory
        settings: Application settings
    """

    @mcp.resource("fleet://health-summary")
    async def fleet_health_summary() -> str:
        """Fleet-wide health summary with aggregated metrics.

        Provides:
        - Total device count
        - Health status distribution
        - Average CPU/memory usage
        - Devices requiring attention
        - Recent health trends

        Returns:
            JSON-formatted fleet health summary
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)
            health_service = HealthService(session, settings)

            try:
                # Get all devices
                devices = await device_service.list_devices()

                # Collect health status for each device
                healthy_count = 0
                warning_count = 0
                critical_count = 0
                unreachable_count = 0

                total_cpu = 0.0
                total_memory = 0.0
                devices_with_metrics = 0

                devices_needing_attention = []

                for device in devices:
                    try:
                        health = await health_service.run_health_check(device.id)

                        if health.status == "healthy":
                            healthy_count += 1
                        elif health.status == "warning":
                            warning_count += 1
                            devices_needing_attention.append(
                                {
                                    "device_id": device.id,
                                    "name": device.name,
                                    "status": "warning",
                                    "environment": device.environment,
                                }
                            )
                        elif health.status == "critical":
                            critical_count += 1
                            devices_needing_attention.append(
                                {
                                    "device_id": device.id,
                                    "name": device.name,
                                    "status": "critical",
                                    "environment": device.environment,
                                }
                            )

                        # Aggregate metrics
                        if health.metrics:
                            cpu = health.metrics.get("cpu_usage", 0)
                            memory = health.metrics.get("memory_usage_percent", 0)
                            if cpu > 0 or memory > 0:
                                total_cpu += cpu
                                total_memory += memory
                                devices_with_metrics += 1

                    except Exception as e:
                        logger.warning(
                            f"Could not fetch health for device {device.id}: {e}"
                        )
                        unreachable_count += 1
                        devices_needing_attention.append(
                            {
                                "device_id": device.id,
                                "name": device.name,
                                "status": "unreachable",
                                "environment": device.environment,
                                "error": str(e),
                            }
                        )

                total_devices = len(devices)
                avg_cpu = total_cpu / devices_with_metrics if devices_with_metrics > 0 else 0
                avg_memory = (
                    total_memory / devices_with_metrics if devices_with_metrics > 0 else 0
                )

                result = {
                    "summary": {
                        "total_devices": total_devices,
                        "healthy_devices": healthy_count,
                        "warning_devices": warning_count,
                        "critical_devices": critical_count,
                        "unreachable_devices": unreachable_count,
                        "average_cpu_usage": round(avg_cpu, 2),
                        "average_memory_usage": round(avg_memory, 2),
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    "devices_needing_attention": devices_needing_attention,
                    "health_distribution": {
                        "healthy": healthy_count,
                        "warning": warning_count,
                        "critical": critical_count,
                        "unreachable": unreachable_count,
                    },
                }

                content = format_resource_content(result, "application/json")

                logger.info("Resource accessed: fleet://health-summary")

                return content

            except Exception as e:
                logger.error(f"Error fetching fleet health summary: {e}", exc_info=True)
                raise MCPError(
                    code=-32001,
                    message="Failed to fetch fleet health summary",
                    data={"error": str(e)},
                )

    @mcp.resource("fleet://devices/{environment}")
    async def fleet_devices(
        environment: str = "all",
    ) -> str:
        """List of all managed devices with optional filtering.

        Args:
            environment: Filter by environment (lab/staging/prod). Use "all" for no filter.

        Returns:
            JSON array of device summaries
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)

            try:
                # List devices (with environment filter if provided)
                devices = await device_service.list_devices()

                # Apply environment filter
                env_filter = None if environment in (None, "", "all") else environment

                if env_filter:
                    devices = [d for d in devices if d.environment == env_filter]

                # Build device summaries
                device_summaries = [
                    {
                        "device_id": d.id,
                        "name": d.name,
                        "environment": d.environment,
                        "management_ip": d.management_ip,
                        "management_port": d.management_port,
                        "tags": d.tags or {},
                        "capability_flags": {
                            "allow_advanced_writes": getattr(d, "allow_advanced_writes", False),
                            "allow_professional_workflows": getattr(
                                d, "allow_professional_workflows", False
                            ),
                        },
                    }
                    for d in devices
                ]

                result = {
                    "devices": device_summaries,
                    "count": len(device_summaries),
                    "filters": {
                        "environment": env_filter,
                    },
                    "timestamp": datetime.now(UTC).isoformat(),
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: fleet://devices (env={environment})",
                    extra={"environment": environment},
                )

                return content

            except Exception as e:
                logger.error(f"Error fetching fleet devices: {e}", exc_info=True)
                raise MCPError(
                    code=-32001,
                    message="Failed to fetch fleet devices",
                    data={"error": str(e)},
                )


__all__ = ["register_fleet_resources"]
