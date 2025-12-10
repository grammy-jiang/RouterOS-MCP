"""Plan service for managing multi-device configuration change plans.

This service implements the plan/apply framework for high-risk operations,
providing plan creation, validation, approval, and execution coordination.

See docs/07-device-control-and-high-risk-operations-safeguards.md for
detailed requirements.
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.infra.db.models import Device as DeviceModel
from routeros_mcp.infra.db.models import Plan as PlanModel

logger = logging.getLogger(__name__)


class PlanService:
    """Service for managing configuration change plans.

    Provides:
    - Plan creation with validation
    - Approval token generation and validation
    - Plan status management
    - Risk assessment

    All high-risk operations must use the plan/apply workflow.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize plan service.

        Args:
            session: Database session
        """
        self.session = session

    async def create_plan(
        self,
        tool_name: str,
        created_by: str,
        device_ids: list[str],
        summary: str,
        changes: dict[str, Any],
        risk_level: str = "medium",
    ) -> dict[str, Any]:
        """Create a new plan for multi-device changes.

        Args:
            tool_name: Name of the tool creating the plan
            created_by: User sub who created the plan
            device_ids: List of target device IDs
            summary: Human-readable plan summary
            changes: Detailed change specifications
            risk_level: Risk level (low/medium/high)

        Returns:
            Plan details including plan_id and approval_token

        Raises:
            ValueError: If validation fails
        """
        # Validate devices exist and are appropriate for the operation
        await self._validate_devices(device_ids)

        # Generate plan ID and approval token
        plan_id = f"plan-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        approval_token = f"approve-{secrets.token_urlsafe(16)}"

        # Create plan record
        plan = PlanModel(
            id=plan_id,
            created_by=created_by,
            tool_name=tool_name,
            status="draft",
            device_ids=device_ids,
            summary=summary,
            changes={
                **changes,
                "risk_level": risk_level,
                "approval_token": approval_token,
                "approval_expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            },
        )

        self.session.add(plan)
        await self.session.commit()
        await self.session.refresh(plan)

        logger.info(
            f"Created plan {plan_id}",
            extra={
                "plan_id": plan_id,
                "tool_name": tool_name,
                "device_count": len(device_ids),
                "risk_level": risk_level,
            },
        )

        return {
            "plan_id": plan_id,
            "approval_token": approval_token,
            "approval_expires_at": plan.changes["approval_expires_at"],
            "risk_level": risk_level,
            "device_count": len(device_ids),
            "devices": device_ids,
            "summary": summary,
            "status": "draft",
        }

    async def _validate_devices(self, device_ids: list[str]) -> None:
        """Validate that devices exist and are appropriate for operations.

        Args:
            device_ids: List of device IDs to validate

        Raises:
            ValueError: If any device is invalid
        """
        if not device_ids:
            raise ValueError("At least one device must be specified")

        # Check all devices exist
        stmt = select(DeviceModel).where(DeviceModel.id.in_(device_ids))
        result = await self.session.execute(stmt)
        devices = result.scalars().all()

        found_ids = {d.id for d in devices}
        missing_ids = set(device_ids) - found_ids

        if missing_ids:
            raise ValueError(f"Devices not found: {', '.join(missing_ids)}")

        # Check device statuses
        for device in devices:
            if device.status == "unreachable":
                raise ValueError(
                    f"Device {device.id} is unreachable and cannot be included in plan"
                )
            if device.status == "decommissioned":
                raise ValueError(
                    f"Device {device.id} is decommissioned and cannot be included in plan"
                )

    async def get_plan(self, plan_id: str) -> dict[str, Any]:
        """Get plan details.

        Args:
            plan_id: Plan identifier

        Returns:
            Plan details

        Raises:
            ValueError: If plan not found
        """
        stmt = select(PlanModel).where(PlanModel.id == plan_id)
        result = await self.session.execute(stmt)
        plan = result.scalar_one_or_none()

        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        return {
            "plan_id": plan.id,
            "tool_name": plan.tool_name,
            "created_by": plan.created_by,
            "status": plan.status,
            "device_ids": plan.device_ids,
            "summary": plan.summary,
            "changes": plan.changes,
            "approved_by": plan.approved_by,
            "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
            "created_at": plan.created_at.isoformat(),
            "updated_at": plan.updated_at.isoformat(),
        }

    async def approve_plan(
        self, plan_id: str, approval_token: str, approved_by: str
    ) -> dict[str, Any]:
        """Approve a plan for execution.

        Args:
            plan_id: Plan identifier
            approval_token: Approval token from plan creation
            approved_by: User sub who is approving

        Returns:
            Updated plan details

        Raises:
            ValueError: If plan not found, token invalid, or already approved
        """
        stmt = select(PlanModel).where(PlanModel.id == plan_id)
        result = await self.session.execute(stmt)
        plan = result.scalar_one_or_none()

        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        if plan.status == "approved":
            raise ValueError(f"Plan {plan_id} is already approved")

        if plan.status != "draft":
            raise ValueError(f"Plan {plan_id} cannot be approved (status: {plan.status})")

        # Validate approval token
        stored_token = plan.changes.get("approval_token")
        if not stored_token or stored_token != approval_token:
            raise ValueError("Invalid approval token")

        # Check token expiration
        expires_at_str = plan.changes.get("approval_expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(UTC) > expires_at:
                raise ValueError("Approval token has expired")

        # Update plan
        plan.status = "approved"
        plan.approved_by = approved_by
        plan.approved_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(plan)

        logger.info(
            f"Approved plan {plan_id}",
            extra={
                "plan_id": plan_id,
                "approved_by": approved_by,
            },
        )

        return await self.get_plan(plan_id)

    async def update_plan_status(self, plan_id: str, status: str) -> None:
        """Update plan status.

        Args:
            plan_id: Plan identifier
            status: New status (draft/approved/applied/failed/cancelled)

        Raises:
            ValueError: If plan not found or invalid status transition
        """
        valid_statuses = ["draft", "approved", "applied", "failed", "cancelled"]
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}")

        stmt = select(PlanModel).where(PlanModel.id == plan_id)
        result = await self.session.execute(stmt)
        plan = result.scalar_one_or_none()

        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        plan.status = status
        await self.session.commit()

        logger.info(
            f"Updated plan {plan_id} status to {status}",
            extra={
                "plan_id": plan_id,
                "status": status,
            },
        )

    async def list_plans(
        self,
        created_by: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List plans with optional filtering.

        Args:
            created_by: Filter by creator user sub
            status: Filter by status
            limit: Maximum number of results

        Returns:
            List of plan summaries
        """
        stmt = select(PlanModel)

        if created_by:
            stmt = stmt.where(PlanModel.created_by == created_by)
        if status:
            stmt = stmt.where(PlanModel.status == status)

        stmt = stmt.order_by(PlanModel.created_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        plans = result.scalars().all()

        return [
            {
                "plan_id": p.id,
                "tool_name": p.tool_name,
                "created_by": p.created_by,
                "status": p.status,
                "device_count": len(p.device_ids),
                "summary": p.summary,
                "created_at": p.created_at.isoformat(),
            }
            for p in plans
        ]
