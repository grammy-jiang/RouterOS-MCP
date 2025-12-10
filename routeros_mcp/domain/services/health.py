"""Health service for device and fleet health computation.

Computes device health based on metrics, RouterOS responses, and failure history.
"""

import logging
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import HealthCheckResult, HealthSummary
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.utils import parse_routeros_uptime
from routeros_mcp.infra.db.models import HealthCheck as HealthCheckORM

logger = logging.getLogger(__name__)


class HealthService:
    """Service for computing device and fleet health.

    Responsibilities:
    - Run health checks on individual devices
    - Compute fleet-wide health summaries
    - Store health check results in database
    - Determine health status based on thresholds

    Example:
        async with get_session() as session:
            service = HealthService(session, settings)

            # Check single device
            health = await service.run_health_check("dev-lab-01")

            # Get fleet health
            fleet_health = await service.get_fleet_health()
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize health service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def run_health_check(
        self,
        device_id: str,
    ) -> HealthCheckResult:
        """Run health check on a device.

        Args:
            device_id: Device identifier

        Returns:
            Health check result

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        # Get device
        device = await self.device_service.get_device(device_id)

        # Try to check connectivity and get metrics
        try:
            client = await self.device_service.get_rest_client(device_id)

            # Get system resource metrics
            resource_data = await client.get("/rest/system/resource")

            await client.close()

            # Parse metrics
            cpu_usage = self._parse_cpu_usage(resource_data)
            memory_total = resource_data.get("total-memory", 0)
            memory_free = resource_data.get("free-memory", 0)
            memory_usage_pct = (
                ((memory_total - memory_free) / memory_total * 100)
                if memory_total > 0
                else 0.0
            )

            uptime = parse_routeros_uptime(resource_data.get("uptime", "0s"))

            # Determine health status based on thresholds
            issues = []
            warnings = []

            # CPU threshold checks
            if cpu_usage > 90.0:
                issues.append(f"Critical CPU usage: {cpu_usage:.1f}%")
            elif cpu_usage > 75.0:
                warnings.append(f"High CPU usage: {cpu_usage:.1f}%")

            # Memory threshold checks
            if memory_usage_pct > 90.0:
                issues.append(f"Critical memory usage: {memory_usage_pct:.1f}%")
            elif memory_usage_pct > 75.0:
                warnings.append(f"High memory usage: {memory_usage_pct:.1f}%")

            # Determine overall status
            if issues:
                status_str = "degraded"
            elif warnings:
                status_str = "degraded"  # Treat warnings as degraded too
            else:
                status_str = "healthy"

            # Type assertion for status
            status = cast(Literal["healthy", "degraded", "unreachable"], status_str)

            result = HealthCheckResult(
                device_id=device_id,
                status=status,
                timestamp=datetime.now(UTC),
                cpu_usage_percent=cpu_usage,
                memory_usage_percent=memory_usage_pct,
                uptime_seconds=uptime,
                issues=issues,
                warnings=warnings,
                metadata={
                    "routeros_version": device.routeros_version,
                    "hardware_model": device.hardware_model,
                },
            )

        except Exception as e:
            logger.warning(
                "Health check failed for device",
                extra={"device_id": device_id, "error": str(e)},
            )

            result = HealthCheckResult(
                device_id=device_id,
                status="unreachable",
                timestamp=datetime.now(UTC),
                issues=[f"Device unreachable: {str(e)}"],
            )

        # Store health check result
        await self._store_health_check(result)

        return result

    async def get_fleet_health(
        self,
        environment: str | None = None,
    ) -> HealthSummary:
        """Get fleet-wide health summary.

        Args:
            environment: Filter by environment (defaults to service environment)

        Returns:
            Fleet health summary
        """
        if environment is None:
            environment = self.settings.environment

        # Get all devices in environment
        devices = await self.device_service.list_devices(environment=environment)

        # Run health checks on all devices
        health_results = []
        healthy_count = 0
        degraded_count = 0
        unreachable_count = 0

        for device in devices:
            try:
                health = await self.run_health_check(device.id)
                health_results.append(health)

                if health.status == "healthy":
                    healthy_count += 1
                elif health.status == "degraded":
                    degraded_count += 1
                else:
                    unreachable_count += 1

            except Exception as e:
                logger.error(
                    "Failed to check device health",
                    extra={"device_id": device.id, "error": str(e)},
                )
                unreachable_count += 1

        # Determine overall fleet status
        overall_status_value: str = "degraded" if unreachable_count > 0 or degraded_count > 0 else "healthy"
        # Type cast for Literal type
        overall_status = cast(Literal["healthy", "degraded", "unreachable"], overall_status_value)

        return HealthSummary(
            overall_status=overall_status,
            timestamp=datetime.now(UTC),
            devices=health_results,
            total_devices=len(devices),
            healthy_count=healthy_count,
            degraded_count=degraded_count,
            unreachable_count=unreachable_count,
        )

    async def _store_health_check(
        self,
        result: HealthCheckResult,
    ) -> None:
        """Store health check result in database.

        Args:
            result: Health check result to store
        """
        health_check_orm = HealthCheckORM(
            id=f"hc-{result.device_id}-{int(result.timestamp.timestamp())}",
            device_id=result.device_id,
            status=result.status,
            timestamp=result.timestamp,
            cpu_usage_percent=result.cpu_usage_percent,
            memory_usage_percent=result.memory_usage_percent,
            uptime_seconds=result.uptime_seconds,
            issues=result.issues,
            warnings=result.warnings,
            metadata=result.metadata,
        )

        self.session.add(health_check_orm)
        await self.session.commit()

    def _parse_cpu_usage(self, resource_data: dict) -> float:
        """Parse CPU usage from RouterOS resource data.

        Args:
            resource_data: Data from /rest/system/resource

        Returns:
            CPU usage percentage (0-100)
        """
        cpu_load = resource_data.get("cpu-load", 0)

        # cpu-load can be integer (0-100) or might need conversion
        if isinstance(cpu_load, str):
            cpu_load = float(cpu_load.rstrip("%"))

        return float(cpu_load)
