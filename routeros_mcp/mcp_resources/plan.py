"""MCP resources for plan data (plan:// URI scheme)."""

import logging
from datetime import UTC, datetime

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.job import JobService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.mcp_resources.utils import format_resource_content

logger = logging.getLogger(__name__)


def register_plan_resources(
    mcp: FastMCP,
    session_factory: DatabaseSessionManager,
    settings: Settings,
) -> None:
    """Register plan:// resources with MCP server.

    Args:
        mcp: FastMCP instance
        session_factory: Database session factory
        settings: Application settings
    """

    @mcp.resource("plan://{plan_id}/summary")
    async def plan_summary(plan_id: str) -> str:
        """Plan summary with basic information.

        Provides:
        - Plan ID and name
        - Target environment
        - Affected devices
        - Creation time
        - Status (pending/approved/executing/completed/failed)

        Args:
            plan_id: Plan identifier

        Returns:
            JSON-formatted plan summary
        """
        try:
            async with session_factory.session() as session:
                plan_service = PlanService(session)
                plan = await plan_service.get_plan(plan_id)

                result = {
                    "plan_id": plan["plan_id"],
                    "tool_name": plan["tool_name"],
                    "status": plan["status"],
                    "created_by": plan["created_by"],
                    "approved_by": plan["approved_by"],
                    "device_count": len(plan["device_ids"]),
                    "summary": plan["summary"],
                    "created_at": plan["created_at"],
                    "approved_at": plan["approved_at"],
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: plan://{plan_id}/summary",
                    extra={"plan_id": plan_id},
                )

                return content

        except Exception as e:
            logger.error(f"Error retrieving plan summary: {e}", exc_info=True)
            error_result = {
                "error": str(e),
                "plan_id": plan_id,
            }
            return format_resource_content(error_result, "application/json")

    @mcp.resource("plan://{plan_id}/details")
    async def plan_details(plan_id: str) -> str:
        """Detailed plan information with per-device changes.

        Provides:
        - Complete plan details
        - Per-device change descriptions
        - Validation results
        - Risk assessment
        - Execution plan

        Args:
            plan_id: Plan identifier

        Returns:
            JSON-formatted plan details
        """
        try:
            async with session_factory.session() as session:
                plan_service = PlanService(session)
                plan = await plan_service.get_plan(plan_id)

                result = {
                    "plan_id": plan["plan_id"],
                    "tool_name": plan["tool_name"],
                    "status": plan["status"],
                    "created_by": plan["created_by"],
                    "approved_by": plan["approved_by"],
                    "device_ids": plan["device_ids"],
                    "summary": plan["summary"],
                    "changes": plan["changes"],
                    "created_at": plan["created_at"],
                    "approved_at": plan["approved_at"],
                    "updated_at": plan["updated_at"],
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: plan://{plan_id}/details",
                    extra={"plan_id": plan_id},
                )

                return content

        except Exception as e:
            logger.error(f"Error retrieving plan details: {e}", exc_info=True)
            error_result = {
                "error": str(e),
                "plan_id": plan_id,
            }
            return format_resource_content(error_result, "application/json")

    @mcp.resource("plan://{plan_id}/execution-log")
    async def plan_execution_log(plan_id: str) -> str:
        """Plan execution log with per-device results.

        Provides:
        - Execution timeline
        - Per-device execution status
        - Success/failure details
        - Error messages
        - Rollback information (if applicable)

        Args:
            plan_id: Plan identifier

        Returns:
            JSON-formatted execution log
        """
        try:
            async with session_factory.session() as session:
                plan_service = PlanService(session)
                job_service = JobService(session)

                # Get plan details
                plan = await plan_service.get_plan(plan_id)

                # Get associated jobs
                jobs = await job_service.list_jobs(plan_id=plan_id, limit=100)

                result = {
                    "plan_id": plan_id,
                    "status": plan["status"],
                    "jobs": jobs,
                    "execution_summary": {
                        "total_jobs": len(jobs),
                        "completed_jobs": sum(1 for j in jobs if j["status"] == "success"),
                        "failed_jobs": sum(1 for j in jobs if j["status"] == "failed"),
                    },
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: plan://{plan_id}/execution-log",
                    extra={"plan_id": plan_id},
                )

                return content

        except Exception as e:
            logger.error(f"Error retrieving execution log: {e}", exc_info=True)
            error_result = {
                "error": str(e),
                "plan_id": plan_id,
            }
            return format_resource_content(error_result, "application/json")


__all__ = ["register_plan_resources"]
