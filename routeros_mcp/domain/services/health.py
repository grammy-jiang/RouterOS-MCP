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

# Adaptive polling constants (Phase 4)
ADAPTIVE_POLLING_MIN_INTERVAL_SECONDS = 60  # Base backoff interval for unreachable devices
ADAPTIVE_POLLING_MAX_INTERVAL_SECONDS = 960  # Max backoff interval (16 minutes)
ADAPTIVE_POLLING_INTERVAL_CAP_SECONDS = 300  # Max interval for healthy devices (5 minutes)


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

        result = None
        try:
            # Try to check connectivity and get metrics
            resource_data = None
            try:
                # Try REST API first
                client = await self.device_service.get_rest_client(device_id)
                resource_data = await client.get("/rest/system/resource")
                await client.close()
            except Exception as rest_error:
                # Fall back to SSH if REST fails
                logger.info(
                    "REST API unavailable, falling back to SSH",
                    extra={"device_id": device_id, "rest_error": str(rest_error)},
                )
                try:
                    ssh_client = await self.device_service.get_ssh_client(device_id)
                    # Execute RouterOS command to get system resources
                    result_str = await ssh_client.execute("/system/resource/print")
                    await ssh_client.close()
                    
                    # Parse SSH output into resource_data dict
                    resource_data = self._parse_ssh_resource_output(result_str)
                except Exception as ssh_error:
                    logger.warning(
                        "Both REST and SSH failed",
                        extra={"device_id": device_id, "ssh_error": str(ssh_error)},
                    )
                    raise Exception(f"No available connection method: REST={rest_error}, SSH={ssh_error}")

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
                    "total_memory_bytes": memory_total,
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
        
        # Update adaptive polling state based on health check result (Phase 4)
        # Skip if session is None (happens in some test scenarios)
        if self.session is not None:
            await self._update_adaptive_polling(device_id, result)

        # Broadcast health update notification to SSE subscribers (if HTTP/SSE transport active)
        await self._broadcast_health_update(device_id, result)

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

    async def run_batch_health_checks(
        self,
        device_ids: list[str],
        cpu_threshold: float = 80.0,
        memory_threshold: float = 85.0,
    ) -> dict[str, HealthCheckResult]:
        """Run health checks on a batch of devices in parallel.

        This method is used by staged rollout to check device health after
        applying changes to a batch. Devices are checked in parallel for
        efficiency.

        Health criteria (Phase 4 staged rollout):
        - CPU usage < cpu_threshold (default: 80%)
        - Memory usage < memory_threshold (default: 85%)
        - All critical interfaces up (TODO: Phase 4+)

        Args:
            device_ids: List of device IDs to check
            cpu_threshold: CPU usage threshold percentage (default: 80.0)
            memory_threshold: Memory usage threshold percentage (default: 85.0)

        Returns:
            Dict mapping device_id to HealthCheckResult

        Note:
            The health checks are run using run_health_check() which persists
            results with default thresholds to the database. The custom thresholds
            are then applied in-memory for rollout decision making. This approach
            ensures the database contains the raw health data while allowing
            flexible threshold evaluation for staged rollout purposes.
            
            Timeouts and connection failures are treated as "unreachable" status,
            which is considered degraded for rollout purposes (fail-safe).
        """
        import asyncio

        # Run health checks in parallel
        tasks = [self.run_health_check(device_id) for device_id in device_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build results dict, handling exceptions
        health_results = {}
        for device_id, result in zip(device_ids, results):
            if isinstance(result, Exception):
                # Treat exceptions as unreachable
                logger.warning(
                    "Health check failed for device",
                    extra={"device_id": device_id, "error": str(result)},
                )
                health_results[device_id] = HealthCheckResult(
                    device_id=device_id,
                    status="unreachable",
                    timestamp=datetime.now(UTC),
                    issues=[f"Health check failed: {str(result)}"],
                )
            else:
                # Apply custom thresholds for staged rollout
                # Re-evaluate status based on provided thresholds
                status = result.status
                # Start with empty lists to avoid duplicating existing threshold messages
                issues = []
                warnings = []

                # Check CPU threshold
                if result.cpu_usage_percent is not None:
                    if result.cpu_usage_percent >= cpu_threshold:
                        status = "degraded"
                        issues.append(
                            f"CPU usage above threshold: {result.cpu_usage_percent:.1f}% >= {cpu_threshold}%"
                        )

                # Check memory threshold
                if result.memory_usage_percent is not None:
                    if result.memory_usage_percent >= memory_threshold:
                        status = "degraded"
                        issues.append(
                            f"Memory usage above threshold: {result.memory_usage_percent:.1f}% >= {memory_threshold}%"
                        )

                # If no custom threshold violations, use original issues/warnings
                if not issues:
                    issues = list(result.issues) if result.issues else []
                    warnings = list(result.warnings) if result.warnings else []

                # Create updated result with custom thresholds applied
                health_results[device_id] = HealthCheckResult(
                    device_id=device_id,
                    status=cast(Literal["healthy", "degraded", "unreachable"], status),
                    timestamp=result.timestamp,
                    cpu_usage_percent=result.cpu_usage_percent,
                    memory_usage_percent=result.memory_usage_percent,
                    uptime_seconds=result.uptime_seconds,
                    issues=issues,
                    warnings=warnings,
                    metadata=result.metadata,
                )

        return health_results

    async def _store_health_check(
        self,
        result: HealthCheckResult,
    ) -> None:
        """Store health check result in database.

        Args:
            result: Health check result to store
        """
        # Calculate memory bytes from percentage if available
        memory_used_bytes = None
        memory_total_bytes = None
        if result.memory_usage_percent is not None and result.metadata:
            # Try to extract total memory from metadata if stored
            total_mem = result.metadata.get("total_memory_bytes")
            if total_mem:
                memory_total_bytes = int(total_mem)
                memory_used_bytes = int(total_mem * result.memory_usage_percent / 100)
        
        health_check_orm = HealthCheckORM(
            id=f"hc-{result.device_id}-{int(result.timestamp.timestamp())}",
            device_id=result.device_id,
            status=result.status,
            timestamp=result.timestamp,
            cpu_usage_percent=result.cpu_usage_percent,
            memory_used_bytes=memory_used_bytes,
            memory_total_bytes=memory_total_bytes,
            uptime_seconds=result.uptime_seconds,
            error_message="; ".join(result.issues) if result.issues else None,
        )

        self.session.add(health_check_orm)
        await self.session.commit()

    async def _broadcast_health_update(
        self, device_id: str, result: HealthCheckResult
    ) -> None:
        """Broadcast health update notification to SSE subscribers.

        This sends a lightweight notification to subscribers of the
        device://{device_id}/health resource. The notification includes
        the resource URI and optional version hints, but NOT the full payload.

        Clients subscribed to health updates should re-read the resource
        to get the latest data after receiving the notification.

        Args:
            device_id: Device identifier
            result: Health check result (used for version hint)
        """
        try:
            from routeros_mcp.mcp.server import get_sse_manager

            sse_manager = get_sse_manager()
            if sse_manager is None:
                # SSE not active (stdio mode or not initialized yet)
                return

            resource_uri = f"device://{device_id}/health"

            # Create lightweight notification (no full payload!)
            # Include only URI and version hint (last_check timestamp as etag)
            notification_data = {
                "uri": resource_uri,
                "etag": result.timestamp.isoformat(),
                "status_hint": result.status,  # Optional hint to avoid unnecessary re-reads
            }

            # Broadcast to subscribers
            subscriber_count = await sse_manager.broadcast(
                resource_uri=resource_uri,
                data=notification_data,
                event_type="resource_updated",
            )

            if subscriber_count > 0:
                logger.info(
                    "Health update notification sent",
                    extra={
                        "device_id": device_id,
                        "resource_uri": resource_uri,
                        "subscriber_count": subscriber_count,
                        "status": result.status,
                    },
                )

        except Exception as e:
            # Don't fail health check if notification fails
            logger.warning(
                "Failed to broadcast health update notification",
                extra={"device_id": device_id, "error": str(e)},
            )

    def _parse_ssh_resource_output(self, output: str) -> dict:
        """Parse SSH output from /system resource print into dict format.

        Args:
            output: Raw SSH command output

        Returns:
            Dictionary with resource data compatible with REST API format
        """
        resource_data = {}
        
        # Parse key-value pairs from RouterOS output
        # Example format:
        #   uptime: 6d8h41m24s
        #   version: 7.20.6 (stable)
        #   cpu-load: 0%
        #   free-memory: 858.6MiB
        #   total-memory: 1024.0MiB
        
        for line in output.split('\n'):
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                # Convert to REST API format (using hyphens)
                if key == "cpu-load":
                    # Remove % sign and convert to int
                    resource_data["cpu-load"] = int(value.rstrip('%')) if value.rstrip('%').isdigit() else 0
                elif key == "free-memory":
                    # Convert MiB/GiB to bytes
                    resource_data["free-memory"] = self._parse_memory_value(value)
                elif key == "total-memory":
                    # Convert MiB/GiB to bytes
                    resource_data["total-memory"] = self._parse_memory_value(value)
                elif key == "uptime":
                    resource_data["uptime"] = value
                elif key == "version":
                    resource_data["version"] = value
        
        return resource_data
    
    def _parse_memory_value(self, value: str) -> int:
        """Parse memory value from RouterOS format to bytes.
        
        Args:
            value: Memory value like "858.6MiB" or "1024.0MiB" or "1.5GiB"
            
        Returns:
            Memory value in bytes
        """
        value = value.strip()
        
        # Extract numeric part and unit
        if 'GiB' in value:
            num = float(value.replace('GiB', '').strip())
            return int(num * 1024 * 1024 * 1024)
        elif 'MiB' in value:
            num = float(value.replace('MiB', '').strip())
            return int(num * 1024 * 1024)
        elif 'KiB' in value:
            num = float(value.replace('KiB', '').strip())
            return int(num * 1024)
        else:
            # Assume it's already in bytes
            try:
                return int(float(value))
            except ValueError:
                return 0
        
        return resource_data

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
    
    async def _update_adaptive_polling(
        self,
        device_id: str,
        health_result: HealthCheckResult,
    ) -> None:
        """Update device adaptive polling state based on health check result (Phase 4).
        
        Implements adaptive polling strategy:
        1. Track consecutive healthy checks
        2. Increase interval by 50% after 10 consecutive healthy checks (max 300s)
        3. Reset interval on unhealthy/degraded checks
        4. Apply exponential backoff for unreachable devices: 60→120→240→480→960s
        
        Args:
            device_id: Device identifier
            health_result: Health check result
        """
        from sqlalchemy import select, update
        from routeros_mcp.infra.db.models import Device as DeviceORM
        
        # Get current device state
        stmt = select(DeviceORM).where(DeviceORM.id == device_id)
        result = await self.session.execute(stmt)
        device_orm = result.scalar_one_or_none()
        
        if not device_orm:
            logger.warning(f"Device {device_id} not found for adaptive polling update")
            return
        
        # Determine base interval (critical: 30s, non-critical: 60s)
        base_interval = 30 if device_orm.critical else 60
        new_interval = device_orm.polling_interval_seconds
        new_consecutive_healthy = device_orm.consecutive_healthy_checks
        new_health_status = health_result.status
        new_last_backoff_at = device_orm.last_backoff_at
        
        if health_result.status == "healthy":
            # Increment consecutive healthy checks
            new_consecutive_healthy += 1
            
            # After 10 consecutive healthy checks, increase interval by 50%
            if new_consecutive_healthy >= 10:
                new_interval = int(new_interval * 1.5)
                # Cap at 300 seconds (5 minutes)
                new_interval = min(new_interval, ADAPTIVE_POLLING_INTERVAL_CAP_SECONDS)
                # Reset counter after adjustment
                new_consecutive_healthy = 0
                
                logger.info(
                    "Adaptive polling: increased interval",
                    extra={
                        "device_id": device_id,
                        "new_interval_seconds": new_interval,
                        "base_interval": base_interval,
                    },
                )
            
            # Reset backoff tracking on successful health check
            new_last_backoff_at = None
            
        elif health_result.status == "degraded":
            # Reset to base interval on degraded status
            new_interval = base_interval
            new_consecutive_healthy = 0
            new_last_backoff_at = None
            
            logger.info(
                "Adaptive polling: reset to base interval (degraded)",
                extra={
                    "device_id": device_id,
                    "base_interval": base_interval,
                },
            )
            
        elif health_result.status == "unreachable":
            # Apply exponential backoff using configured constants
            if device_orm.last_backoff_at is None:
                # First unreachable, start with base backoff interval
                new_interval = ADAPTIVE_POLLING_MIN_INTERVAL_SECONDS
                new_last_backoff_at = datetime.now(UTC)
            else:
                # Double the interval (exponential backoff) up to max
                new_interval = min(new_interval * 2, ADAPTIVE_POLLING_MAX_INTERVAL_SECONDS)
                new_last_backoff_at = datetime.now(UTC)
            
            new_consecutive_healthy = 0
            
            logger.warning(
                "Adaptive polling: exponential backoff (unreachable)",
                extra={
                    "device_id": device_id,
                    "new_interval_seconds": new_interval,
                    "backoff_started_at": new_last_backoff_at.isoformat() if new_last_backoff_at else None,
                },
            )
        
        # Update device in database
        stmt = (
            update(DeviceORM)
            .where(DeviceORM.id == device_id)
            .values(
                health_status=new_health_status,
                consecutive_healthy_checks=new_consecutive_healthy,
                polling_interval_seconds=new_interval,
                last_backoff_at=new_last_backoff_at,
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()
        
        logger.debug(
            "Adaptive polling state updated",
            extra={
                "device_id": device_id,
                "health_status": new_health_status,
                "consecutive_healthy_checks": new_consecutive_healthy,
                "polling_interval_seconds": new_interval,
            },
        )
    
    def get_device_polling_interval(self, device_id: str, critical: bool = False) -> int:
        """Get polling interval for a device based on its classification (Phase 4).
        
        Args:
            device_id: Device identifier
            critical: Whether device is critical (30s base) vs non-critical (60s base)
            
        Returns:
            Polling interval in seconds
            
        Note:
            This is a synchronous helper for initial interval calculation.
            Actual interval is dynamically adjusted and stored in database.
        """
        return 30 if critical else 60
    
    async def get_adaptive_polling_interval(self, device_id: str) -> int:
        """Get current adaptive polling interval for a device (Phase 4).
        
        Reads the current interval from database, which is dynamically adjusted
        based on device health status and consecutive healthy checks.
        
        Args:
            device_id: Device identifier
            
        Returns:
            Current polling interval in seconds
            
        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        from sqlalchemy import select
        from routeros_mcp.infra.db.models import Device as DeviceORM
        
        stmt = select(DeviceORM.polling_interval_seconds).where(DeviceORM.id == device_id)
        result = await self.session.execute(stmt)
        interval = result.scalar_one_or_none()
        
        if interval is None:
            logger.warning(f"Device {device_id} not found for polling interval query")
            return 60  # Default fallback
        
        return interval
