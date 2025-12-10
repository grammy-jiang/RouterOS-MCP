"""MCP resources for plan data (plan:// URI scheme)."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.mcp.errors import MCPError
from routeros_mcp.mcp_resources.utils import format_resource_content

logger = logging.getLogger(__name__)


def register_plan_resources(
    mcp: FastMCP,
    session_factory: Any,
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
        # Placeholder implementation
        # TODO: Integrate with actual PlanService when available

        result = {
            "plan_id": plan_id,
            "name": f"Plan {plan_id}",
            "description": "Placeholder plan summary",
            "status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
            "note": "Plan service integration pending - T7",
        }

        content = format_resource_content(result, "application/json")

        logger.info(
            f"Resource accessed: plan://{plan_id}/summary",
            extra={"plan_id": plan_id},
        )

        return content

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
        # Placeholder implementation
        result = {
            "plan_id": plan_id,
            "details": "Detailed plan information",
            "devices": [],
            "changes": [],
            "note": "Plan service integration pending - T7",
        }

        content = format_resource_content(result, "application/json")

        logger.info(
            f"Resource accessed: plan://{plan_id}/details",
            extra={"plan_id": plan_id},
        )

        return content

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
        # Placeholder implementation
        result = {
            "plan_id": plan_id,
            "execution_log": [],
            "status": "not_executed",
            "note": "Plan service integration pending - T7",
        }

        content = format_resource_content(result, "application/json")

        logger.info(
            f"Resource accessed: plan://{plan_id}/execution-log",
            extra={"plan_id": plan_id},
        )

        return content


__all__ = ["register_plan_resources"]
