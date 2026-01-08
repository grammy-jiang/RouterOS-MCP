"""APScheduler-based job scheduler for periodic tasks.

Provides scheduling infrastructure for:
- Periodic configuration snapshot capture
- Health check execution
- Retention policy enforcement

Design principles:
- Use AsyncIOScheduler for async compatibility
- Graceful shutdown with job cleanup
- Error handling and retry logic
- Job status tracking and metrics

See docs/08-observability-logging-metrics-and-diagnostics.md for
observability requirements.
"""

import logging
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from routeros_mcp.config import Settings

logger = logging.getLogger(__name__)


class JobScheduler:
    """APScheduler-based job scheduler for periodic tasks.

    Manages periodic execution of background tasks such as
    snapshot capture, health checks, and retention cleanup.

    Example:
        scheduler = JobScheduler(settings)
        await scheduler.start()

        # Register periodic job
        scheduler.add_snapshot_job(capture_fn, interval_seconds=3600)

        # Shutdown
        await scheduler.shutdown()
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize job scheduler.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,  # Combine missed runs
                "max_instances": 1,  # One instance at a time
                "misfire_grace_time": 300,  # 5 minutes grace period
            },
        )

        # Add event listeners
        self.scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
        )

        self._started = False

    async def start(self) -> None:
        """Start the scheduler.

        Raises:
            RuntimeError: If scheduler already started
        """
        if self._started:
            raise RuntimeError("Scheduler already started")

        self.scheduler.start()
        self._started = True

        logger.info(
            "Job scheduler started",
            extra={
                "job_count": len(self.scheduler.get_jobs()),
            },
        )

    async def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler gracefully.

        Args:
            wait: Whether to wait for running jobs to complete
        """
        if not self._started:
            return

        logger.info("Shutting down job scheduler...")

        self.scheduler.shutdown(wait=wait)
        self._started = False

        logger.info("Job scheduler stopped")

    def add_snapshot_capture_job(
        self,
        job_func: Callable,
        interval_seconds: int | None = None,
    ) -> str:
        """Add periodic snapshot capture job.

        Args:
            job_func: Async function to execute
            interval_seconds: Capture interval (default: from settings)

        Returns:
            Job ID
        """
        interval = interval_seconds or self.settings.snapshot_capture_interval_seconds

        job = self.scheduler.add_job(
            job_func,
            trigger=IntervalTrigger(seconds=interval),
            id="snapshot_capture",
            name="Periodic Configuration Snapshot Capture",
            replace_existing=True,
        )

        logger.info(
            f"Added snapshot capture job (interval: {interval}s)",
            extra={
                "job_id": job.id,
                "interval_seconds": interval,
            },
        )

        return job.id

    def add_retention_cleanup_job(
        self,
        job_func: Callable,
        interval_seconds: int = 3600,  # Default: hourly
    ) -> str:
        """Add periodic retention cleanup job.

        Args:
            job_func: Async function to execute
            interval_seconds: Cleanup interval (default: 3600s = 1 hour)

        Returns:
            Job ID
        """
        job = self.scheduler.add_job(
            job_func,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="retention_cleanup",
            name="Snapshot Retention Cleanup",
            replace_existing=True,
        )

        logger.info(
            f"Added retention cleanup job (interval: {interval_seconds}s)",
            extra={
                "job_id": job.id,
                "interval_seconds": interval_seconds,
            },
        )

        return job.id

    def add_health_check_job(
        self,
        device_id: str,
        job_func: Callable,
        interval_seconds: int,
    ) -> str:
        """Add or update health check job for a device (Phase 4 adaptive polling).
        
        Creates a per-device health check job with specified interval.
        If job already exists, updates the interval.
        
        Args:
            device_id: Device identifier
            job_func: Async function to execute health check
            interval_seconds: Health check interval in seconds
            
        Returns:
            Job ID
        """
        job_id = f"health_check_{device_id}"
        
        # Add new job with updated interval (replace_existing handles existing jobs)
        job = self.scheduler.add_job(
            job_func,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name=f"Health Check: {device_id}",
            replace_existing=True,
            kwargs={"device_id": device_id},
        )
        
        logger.info(
            f"Added/updated health check job for device {device_id} (interval: {interval_seconds}s)",
            extra={
                "job_id": job.id,
                "device_id": device_id,
                "interval_seconds": interval_seconds,
            },
        )
        
        return job.id
    
    def update_health_check_interval(
        self,
        device_id: str,
        new_interval_seconds: int,
    ) -> bool:
        """Update health check interval for a device (Phase 4 adaptive polling).
        
        Modifies the interval trigger for an existing health check job.
        
        Args:
            device_id: Device identifier
            new_interval_seconds: New interval in seconds
            
        Returns:
            True if job was updated, False if job not found
        """
        job_id = f"health_check_{device_id}"
        job = self.scheduler.get_job(job_id)
        
        if not job:
            logger.warning(
                f"Cannot update interval: health check job not found for device {device_id}",
                extra={"device_id": device_id, "job_id": job_id},
            )
            return False
        
        # Update the job's trigger with new interval
        job.reschedule(IntervalTrigger(seconds=new_interval_seconds))
        
        logger.info(
            f"Updated health check interval for device {device_id} to {new_interval_seconds}s",
            extra={
                "device_id": device_id,
                "job_id": job_id,
                "new_interval_seconds": new_interval_seconds,
            },
        )
        
        return True

    def remove_job(self, job_id: str) -> None:
        """Remove a scheduled job.

        Args:
            job_id: Job identifier
        """
        self.scheduler.remove_job(job_id)
        logger.info(f"Removed job {job_id}")

    def get_job_status(self, job_id: str) -> dict | None:
        """Get job status.

        Args:
            job_id: Job identifier

        Returns:
            Job status dict or None if job not found
        """
        job = self.scheduler.get_job(job_id)
        if not job:
            return None

        return {
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "pending": job.pending,
        }

    def _on_job_executed(self, event) -> None:
        """Handle job execution events.

        Args:
            event: APScheduler event
        """
        if event.exception:
            logger.error(
                f"Job {event.job_id} failed",
                extra={
                    "job_id": event.job_id,
                    "exception": str(event.exception),
                },
                exc_info=event.exception,
            )
        else:
            logger.debug(
                f"Job {event.job_id} executed successfully",
                extra={
                    "job_id": event.job_id,
                    "run_time": event.scheduled_run_time.isoformat() if event.scheduled_run_time else None,
                },
            )


__all__ = ["JobScheduler"]
