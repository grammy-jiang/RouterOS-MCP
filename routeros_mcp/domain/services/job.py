"""Job service for executing configuration changes and workflows.

This service implements job execution, retry logic, batch processing,
and health check integration for plan application.

See docs/05-domain-model-persistence-and-task-job-model.md for
detailed requirements.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.infra.db.models import Job as JobModel
from routeros_mcp.infra.db.models import Plan as PlanModel

logger = logging.getLogger(__name__)


class JobService:
    """Service for job execution and management.

    Provides:
    - Job creation and scheduling
    - Batch execution with health checks
    - Retry logic and failure handling
    - Progress tracking and status updates

    Jobs can be standalone or linked to a Plan for coordinated multi-device
    operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize job service.

        Args:
            session: Database session
        """
        self.session = session

    async def create_job(
        self,
        job_type: str,
        device_ids: list[str],
        plan_id: str | None = None,
        max_attempts: int = 3,
        next_run_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Create a new job for execution.

        Args:
            job_type: Type of job (e.g., APPLY_PLAN, HEALTH_CHECK)
            device_ids: Target device IDs
            plan_id: Optional plan ID to link job to
            max_attempts: Maximum retry attempts
            next_run_at: Scheduled execution time (default: now)

        Returns:
            Job details including job_id

        Raises:
            ValueError: If validation fails
        """
        if plan_id:
            # Verify plan exists
            stmt = select(PlanModel).where(PlanModel.id == plan_id)
            result = await self.session.execute(stmt)
            plan = result.scalar_one_or_none()
            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")

        # Generate job ID
        job_id = f"job-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # Create job record
        job = JobModel(
            id=job_id,
            plan_id=plan_id,
            job_type=job_type,
            status="pending",
            device_ids=device_ids,
            attempts=0,
            max_attempts=max_attempts,
            next_run_at=next_run_at or datetime.now(UTC),
        )

        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)

        logger.info(
            f"Created job {job_id}",
            extra={
                "job_id": job_id,
                "job_type": job_type,
                "plan_id": plan_id,
                "device_count": len(device_ids),
            },
        )

        return {
            "job_id": job_id,
            "job_type": job_type,
            "plan_id": plan_id,
            "status": "pending",
            "device_ids": device_ids,
            "created_at": job.created_at.isoformat(),
        }

    async def execute_job(
        self,
        job_id: str,
        executor: Callable[[str, list[str], dict[str, Any]], Any],
        executor_context: dict[str, Any] | None = None,
        batch_size: int = 5,
        batch_pause_seconds: int = 30,
    ) -> dict[str, Any]:
        """Execute a job with batch processing and health checks.

        Args:
            job_id: Job identifier
            executor: Async callable that executes the job logic
                     Signature: async def executor(job_id, device_ids, context) -> dict
            executor_context: Context data to pass to executor
            batch_size: Number of devices to process per batch
            batch_pause_seconds: Pause between batches for health checks

        Returns:
            Execution results with per-device status

        Raises:
            ValueError: If job not found or invalid state
        """
        stmt = select(JobModel).where(JobModel.id == job_id)
        result = await self.session.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.status not in ["pending", "failed"]:
            raise ValueError(f"Job {job_id} cannot be executed (status: {job.status})")

        # Update job status
        job.status = "running"
        job.attempts += 1
        await self.session.commit()

        logger.info(
            f"Starting job execution {job_id}",
            extra={
                "job_id": job_id,
                "attempt": job.attempts,
                "device_count": len(job.device_ids),
            },
        )

        # Execute in batches
        device_ids = job.device_ids
        batches = [
            device_ids[i : i + batch_size] for i in range(0, len(device_ids), batch_size)
        ]

        results: dict[str, Any] = {
            "job_id": job_id,
            "total_devices": len(device_ids),
            "batches_completed": 0,
            "batches_total": len(batches),
            "device_results": {},
            "errors": [],
        }

        try:
            for batch_idx, batch_device_ids in enumerate(batches):
                logger.info(
                    f"Processing batch {batch_idx + 1}/{len(batches)}",
                    extra={
                        "job_id": job_id,
                        "batch_index": batch_idx,
                        "batch_size": len(batch_device_ids),
                    },
                )

                # Execute batch
                try:
                    batch_results = await executor(
                        job_id, batch_device_ids, executor_context or {}
                    )
                    results["device_results"].update(batch_results.get("devices", {}))
                except Exception as e:
                    error_msg = f"Batch {batch_idx + 1} failed: {str(e)}"
                    logger.error(error_msg, extra={"job_id": job_id}, exc_info=True)
                    results["errors"].append(error_msg)

                    # Stop processing on batch failure
                    job.status = "failed"
                    job.error_message = error_msg
                    await self.session.commit()
                    raise

                results["batches_completed"] += 1

                # Pause between batches for health checks (except after last batch)
                if batch_idx < len(batches) - 1:
                    logger.info(
                        f"Pausing {batch_pause_seconds}s for health checks",
                        extra={"job_id": job_id},
                    )
                    await asyncio.sleep(batch_pause_seconds)

            # Job completed successfully
            job.status = "success"
            job.result_summary = f"Completed {len(device_ids)} devices in {len(batches)} batches"
            await self.session.commit()

            logger.info(
                f"Job {job_id} completed successfully",
                extra={
                    "job_id": job_id,
                    "device_count": len(device_ids),
                    "batches": len(batches),
                },
            )

        except Exception as e:
            # Job failed
            job.status = "failed"
            job.error_message = str(e)
            await self.session.commit()

            logger.error(
                f"Job {job_id} failed: {str(e)}",
                extra={"job_id": job_id},
                exc_info=True,
            )

            results["status"] = "failed"
            results["error"] = str(e)

        return results

    async def get_job(self, job_id: str) -> dict[str, Any]:
        """Get job details.

        Args:
            job_id: Job identifier

        Returns:
            Job details

        Raises:
            ValueError: If job not found
        """
        stmt = select(JobModel).where(JobModel.id == job_id)
        result = await self.session.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError(f"Job not found: {job_id}")

        return {
            "job_id": job.id,
            "plan_id": job.plan_id,
            "job_type": job.job_type,
            "status": job.status,
            "device_ids": job.device_ids,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
            "result_summary": job.result_summary,
            "error_message": job.error_message,
            "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }

    async def schedule_retry(
        self, job_id: str, delay_seconds: int = 60
    ) -> dict[str, Any]:
        """Schedule a job for retry.

        Args:
            job_id: Job identifier
            delay_seconds: Delay before retry

        Returns:
            Updated job details

        Raises:
            ValueError: If job not found or cannot be retried
        """
        stmt = select(JobModel).where(JobModel.id == job_id)
        result = await self.session.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.attempts >= job.max_attempts:
            raise ValueError(f"Job {job_id} has exhausted retry attempts")

        if job.status != "failed":
            raise ValueError(f"Job {job_id} is not in failed state")

        # Schedule retry
        job.status = "pending"
        job.next_run_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        await self.session.commit()

        logger.info(
            f"Scheduled retry for job {job_id}",
            extra={
                "job_id": job_id,
                "attempt": job.attempts,
                "next_run_at": job.next_run_at.isoformat(),
            },
        )

        return await self.get_job(job_id)

    async def list_jobs(
        self,
        plan_id: str | None = None,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List jobs with optional filtering.

        Args:
            plan_id: Filter by plan ID
            status: Filter by status
            job_type: Filter by job type
            limit: Maximum number of results

        Returns:
            List of job summaries
        """
        stmt = select(JobModel)

        if plan_id:
            stmt = stmt.where(JobModel.plan_id == plan_id)
        if status:
            stmt = stmt.where(JobModel.status == status)
        if job_type:
            stmt = stmt.where(JobModel.job_type == job_type)

        stmt = stmt.order_by(JobModel.created_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        jobs = result.scalars().all()

        return [
            {
                "job_id": j.id,
                "plan_id": j.plan_id,
                "job_type": j.job_type,
                "status": j.status,
                "device_count": len(j.device_ids),
                "attempts": j.attempts,
                "created_at": j.created_at.isoformat(),
            }
            for j in jobs
        ]
