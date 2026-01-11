"""Approval service for managing approval requests for professional-tier plans.

This service implements approval workflow for high-risk professional-tier
operations, providing request creation, listing, approval, and rejection.

See Phase 5 #7 requirements for detailed specifications.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.infra.db.models import ApprovalRequest as ApprovalRequestModel
from routeros_mcp.infra.db.models import Plan as PlanModel

logger = logging.getLogger(__name__)


class ApprovalService:
    """Service for managing approval requests.

    Provides:
    - Approval request creation for professional-tier plans
    - Listing requests with status filtering
    - Approval and rejection workflows
    - Validation of approval permissions and plan state
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize approval service.

        Args:
            session: Database session
        """
        self.session = session

    async def create_request(
        self,
        plan_id: str,
        requested_by: str,
        notes: str | None = None,
    ) -> ApprovalRequestModel:
        """Create a new approval request for a plan.

        Args:
            plan_id: Plan requiring approval
            requested_by: User sub requesting approval
            notes: Optional notes explaining the request

        Returns:
            Created approval request

        Raises:
            ValueError: If plan not found or already has pending request
        """
        # Verify plan exists
        result = await self.session.execute(select(PlanModel).where(PlanModel.id == plan_id))
        plan = result.scalar_one_or_none()

        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        # Check for existing pending request
        existing = await self.session.execute(
            select(ApprovalRequestModel)
            .where(ApprovalRequestModel.plan_id == plan_id)
            .where(ApprovalRequestModel.status == "pending")
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Plan {plan_id} already has a pending approval request")

        # Create approval request
        approval_request = ApprovalRequestModel(
            id=f"approval-{uuid.uuid4().hex[:16]}",
            plan_id=plan_id,
            requested_by=requested_by,
            requested_at=datetime.now(UTC),
            status="pending",
            notes=notes,
        )

        self.session.add(approval_request)
        await self.session.commit()
        await self.session.refresh(approval_request)

        logger.info(
            "Approval request created",
            extra={
                "approval_request_id": approval_request.id,
                "plan_id": plan_id,
                "requested_by": requested_by,
            },
        )

        return approval_request

    async def list_requests(
        self,
        status: Literal["pending", "approved", "rejected"] | None = None,
        plan_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApprovalRequestModel]:
        """List approval requests with optional filtering.

        Args:
            status: Filter by status (pending/approved/rejected)
            plan_id: Filter by plan ID
            limit: Maximum number of requests to return
            offset: Number of requests to skip

        Returns:
            List of approval requests matching criteria
        """
        query = select(ApprovalRequestModel)

        if status:
            query = query.where(ApprovalRequestModel.status == status)

        if plan_id:
            query = query.where(ApprovalRequestModel.plan_id == plan_id)

        # Order by requested_at descending (newest first)
        query = query.order_by(ApprovalRequestModel.requested_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def approve_request(
        self,
        approval_request_id: str,
        approved_by: str,
        notes: str | None = None,
    ) -> ApprovalRequestModel:
        """Approve an approval request.

        Args:
            approval_request_id: Approval request ID
            approved_by: User sub approving the request
            notes: Optional notes explaining the approval

        Returns:
            Updated approval request

        Raises:
            ValueError: If request not found, already processed, or approver same as requester
        """
        result = await self.session.execute(
            select(ApprovalRequestModel).where(ApprovalRequestModel.id == approval_request_id)
        )
        approval_request = result.scalar_one_or_none()

        if not approval_request:
            raise ValueError(f"Approval request not found: {approval_request_id}")

        if approval_request.status != "pending":
            raise ValueError(
                f"Approval request {approval_request_id} is already {approval_request.status}"
            )

        # Prevent self-approval
        if approval_request.requested_by == approved_by:
            raise ValueError("Users cannot approve their own requests")

        # Update request
        approval_request.status = "approved"
        approval_request.approved_by = approved_by
        approval_request.approved_at = datetime.now(UTC)
        if notes:
            approval_request.notes = notes

        await self.session.commit()
        await self.session.refresh(approval_request)

        logger.info(
            "Approval request approved",
            extra={
                "approval_request_id": approval_request_id,
                "plan_id": approval_request.plan_id,
                "approved_by": approved_by,
            },
        )

        return approval_request

    async def reject_request(
        self,
        approval_request_id: str,
        rejected_by: str,
        notes: str | None = None,
    ) -> ApprovalRequestModel:
        """Reject an approval request.

        Args:
            approval_request_id: Approval request ID
            rejected_by: User sub rejecting the request
            notes: Optional notes explaining the rejection

        Returns:
            Updated approval request

        Raises:
            ValueError: If request not found or already processed
        """
        result = await self.session.execute(
            select(ApprovalRequestModel).where(ApprovalRequestModel.id == approval_request_id)
        )
        approval_request = result.scalar_one_or_none()

        if not approval_request:
            raise ValueError(f"Approval request not found: {approval_request_id}")

        if approval_request.status != "pending":
            raise ValueError(
                f"Approval request {approval_request_id} is already {approval_request.status}"
            )

        # Update request
        approval_request.status = "rejected"
        approval_request.rejected_by = rejected_by
        approval_request.rejected_at = datetime.now(UTC)
        if notes:
            approval_request.notes = notes

        await self.session.commit()
        await self.session.refresh(approval_request)

        logger.info(
            "Approval request rejected",
            extra={
                "approval_request_id": approval_request_id,
                "plan_id": approval_request.plan_id,
                "rejected_by": rejected_by,
            },
        )

        return approval_request

    async def get_request(self, approval_request_id: str) -> ApprovalRequestModel | None:
        """Get a single approval request by ID.

        Args:
            approval_request_id: Approval request ID

        Returns:
            Approval request or None if not found
        """
        result = await self.session.execute(
            select(ApprovalRequestModel).where(ApprovalRequestModel.id == approval_request_id)
        )
        return result.scalar_one_or_none()
