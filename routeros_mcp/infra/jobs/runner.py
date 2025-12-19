"""Job runner for executing periodic snapshot capture.

Implements the snapshot capture workflow:
1. Query eligible devices
2. Capture configuration via SnapshotService
3. Update device last_seen_at timestamp
4. Handle failures gracefully
5. Prune old snapshots based on retention policy

Design principles:
- Concurrent execution with semaphore limit
- Graceful failure handling (log and continue)
- Update metrics for monitoring
- Transaction management per device

See docs/18-database-schema-and-orm-specification.md (Snapshot Model)
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import Device as DeviceDomain
from routeros_mcp.domain.services.snapshot import SnapshotService
from routeros_mcp.infra.db.models import Device as DeviceORM
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.infra.observability import metrics

logger = logging.getLogger(__name__)

# Concurrency limit for snapshot capture
MAX_CONCURRENT_CAPTURES = 5


async def run_snapshot_capture_job(
    session_factory: DatabaseSessionManager,
    settings: Settings,
) -> dict:
    """Execute periodic snapshot capture for all eligible devices.

    Args:
        session_factory: Database session factory
        settings: Application settings

    Returns:
        Job execution summary
    """
    if not settings.snapshot_capture_enabled:
        logger.debug("Snapshot capture disabled, skipping job")
        return {
            "status": "skipped",
            "reason": "disabled",
        }

    logger.info("Starting periodic snapshot capture job")

    start_time = datetime.now(UTC)
    results = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }

    # Get eligible devices
    async with session_factory.session() as session:
        devices = await _get_eligible_devices(session, settings)
        results["total"] = len(devices)

        logger.info(
            f"Found {len(devices)} eligible devices for snapshot capture",
            extra={"device_count": len(devices)},
        )

    # Capture snapshots concurrently with limit
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CAPTURES)

    async def capture_with_semaphore(device: DeviceDomain) -> None:
        async with semaphore:
            await _capture_device_snapshot(
                device=device,
                session_factory=session_factory,
                settings=settings,
                results=results,
            )

    # Execute captures
    tasks = [capture_with_semaphore(device) for device in devices]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Log summary
    duration = (datetime.now(UTC) - start_time).total_seconds()
    logger.info(
        f"Snapshot capture job completed in {duration:.2f}s",
        extra={
            "duration_seconds": duration,
            "total_devices": results["total"],
            "success": results["success"],
            "failed": results["failed"],
            "skipped": results["skipped"],
        },
    )

    return results


async def run_retention_cleanup_job(
    session_factory: DatabaseSessionManager,
    settings: Settings,
) -> dict:
    """Execute periodic snapshot retention cleanup.

    Args:
        session_factory: Database session factory
        settings: Application settings

    Returns:
        Job execution summary
    """
    logger.info("Starting snapshot retention cleanup job")

    start_time = datetime.now(UTC)
    results = {
        "total_devices": 0,
        "total_pruned": 0,
        "errors": [],
    }

    async with session_factory.session() as session:
        # Get all devices
        stmt = select(DeviceORM)
        result = await session.execute(stmt)
        devices = result.scalars().all()
        results["total_devices"] = len(devices)

        snapshot_service = SnapshotService(session, settings)

        # Prune snapshots for each device
        for device_orm in devices:
            try:
                pruned = await snapshot_service.prune_old_snapshots(
                    device_id=device_orm.id,
                    kind="config",
                    keep_count=settings.snapshot_retention_count,
                )
                results["total_pruned"] += pruned

                if pruned > 0:
                    metrics.snapshot_retention_pruned.labels(
                        device_id=device_orm.id,
                        kind="config",
                    ).inc(pruned)

            except Exception as e:
                error_msg = f"Failed to prune snapshots for device {device_orm.id}: {e}"
                logger.error(error_msg, exc_info=True)
                results["errors"].append(error_msg)

        await session.commit()

    duration = (datetime.now(UTC) - start_time).total_seconds()
    logger.info(
        f"Retention cleanup completed in {duration:.2f}s",
        extra={
            "duration_seconds": duration,
            "devices_processed": results["total_devices"],
            "snapshots_pruned": results["total_pruned"],
            "errors": len(results["errors"]),
        },
    )

    return results


async def _get_eligible_devices(
    session: AsyncSession,
    settings: Settings,
) -> list[DeviceDomain]:
    """Get devices eligible for snapshot capture.

    Eligibility criteria:
    - Not decommissioned
    - Matches service environment

    Args:
        session: Database session
        settings: Application settings

    Returns:
        List of eligible devices
    """
    stmt = select(DeviceORM).where(
        DeviceORM.environment == settings.environment,
        DeviceORM.status != "decommissioned",
    )
    result = await session.execute(stmt)
    devices_orm = result.scalars().all()

    # Convert to domain models
    devices = [DeviceDomain.model_validate(d) for d in devices_orm]

    return devices


async def _capture_device_snapshot(
    device: DeviceDomain,
    session_factory: DatabaseSessionManager,
    settings: Settings,
    results: dict,
) -> None:
    """Capture snapshot for a single device.

    Args:
        device: Device domain model
        session_factory: Database session factory
        settings: Application settings
        results: Results dict to update
    """
    try:
        # Use separate session per device for isolation
        async with session_factory.session() as session:
            snapshot_service = SnapshotService(session, settings)

            # Capture snapshot
            snapshot_id = await snapshot_service.capture_device_snapshot(
                device=device,
                kind="config",
                use_ssh_fallback=settings.snapshot_use_ssh_fallback,
            )

            # Update device last_seen_at
            stmt = select(DeviceORM).where(DeviceORM.id == device.id)
            result = await session.execute(stmt)
            device_orm = result.scalar_one_or_none()
            if device_orm:
                device_orm.last_seen_at = datetime.now(UTC)

            await session.commit()

            results["success"] += 1

            logger.info(
                f"Captured snapshot for device {device.id}",
                extra={
                    "device_id": device.id,
                    "snapshot_id": snapshot_id,
                },
            )

    except Exception as e:
        results["failed"] += 1
        error_msg = f"Failed to capture snapshot for device {device.id}: {e}"
        results["errors"].append(error_msg)

        logger.error(
            error_msg,
            extra={"device_id": device.id},
            exc_info=True,
        )

        # Record failure metric
        metrics.snapshot_capture_total.labels(
            device_id=device.id,
            kind="config",
            source="unknown",
            status="failed",
        ).inc()


__all__ = [
    "run_snapshot_capture_job",
    "run_retention_cleanup_job",
]
