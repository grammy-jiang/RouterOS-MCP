"""Audit service for querying audit events.

Provides business logic for audit event queries with filtering and pagination.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import String, and_, cast, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.infra.db.models import AuditEvent as AuditEventORM

logger = logging.getLogger(__name__)


class AuditService:
    """Service for querying audit events.

    Responsibilities:
    - Query audit events with filtering
    - Pagination support
    - Search functionality

    Example:
        async with get_session() as session:
            service = AuditService(session)

            # List events with filters
            result = await service.list_events(
                page=1,
                page_size=20,
                device_id="dev-001",
                success=True
            )
    """

    def __init__(self, session: AsyncSession):
        """Initialize audit service.

        Args:
            session: Database session
        """
        self.session = session

    async def list_events(
        self,
        page: int = 1,
        page_size: int = 20,
        device_id: str | None = None,
        tool_name: str | None = None,
        success: bool | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
        user_id: str | None = None,
        approver_id: str | None = None,
        approval_request_id: str | None = None,
    ) -> dict[str, Any]:
        """List audit events with filters and pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Number of events per page
            device_id: Filter by device ID
            tool_name: Filter by tool name
            success: Filter by success status
            date_from: Filter events from this date
            date_to: Filter events to this date
            search: Search in event details (result_summary, error_message, parameters)
            user_id: Filter by user ID who performed the action (Phase 5)
            approver_id: Filter by approver ID (Phase 5)
            approval_request_id: Filter by approval request ID (Phase 5)

        Returns:
            Dictionary with events, pagination info
        """
        # Build filter conditions
        conditions = []

        if device_id:
            conditions.append(AuditEventORM.device_id == device_id)

        if tool_name:
            conditions.append(AuditEventORM.tool_name == tool_name)

        if success is not None:
            conditions.append(AuditEventORM.result == ("SUCCESS" if success else "FAILURE"))

        if date_from:
            conditions.append(AuditEventORM.timestamp >= date_from)

        if date_to:
            conditions.append(AuditEventORM.timestamp <= date_to)

        # Phase 5: Per-user filters
        if user_id:
            conditions.append(AuditEventORM.user_id == user_id)

        if approver_id:
            conditions.append(AuditEventORM.approver_id == approver_id)

        if approval_request_id:
            conditions.append(AuditEventORM.approval_request_id == approval_request_id)

        if search:
            # Search in error_message and meta (as JSON string)
            # Note: Casting JSON to string for search can be inefficient for large datasets
            # Consider using database-specific JSON search operators (e.g., PostgreSQL's jsonb_path_query)
            # or creating a GIN index on meta for better performance if this becomes a bottleneck
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    AuditEventORM.error_message.ilike(search_pattern),
                    cast(AuditEventORM.meta, String).ilike(search_pattern),
                )
            )

        # Count total matching events
        count_stmt = select(func.count()).select_from(AuditEventORM)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Calculate pagination
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        offset = (page - 1) * page_size

        # Query events
        stmt = select(AuditEventORM).order_by(desc(AuditEventORM.timestamp))
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.limit(page_size).offset(offset)

        result = await self.session.execute(stmt)
        events = result.scalars().all()

        # Convert to dict format
        events_data = [
            {
                "id": event.id,
                "timestamp": event.timestamp.isoformat(),
                "user_sub": event.user_sub,
                "user_email": event.user_email,
                "user_role": event.user_role,
                "user_id": event.user_id,
                "approver_id": event.approver_id,
                "approval_request_id": event.approval_request_id,
                "device_id": event.device_id,
                "environment": event.environment,
                "action": event.action,
                "tool_name": event.tool_name,
                "tool_tier": event.tool_tier,
                "success": event.result == "SUCCESS",
                "error_message": event.error_message,
                "parameters": event.meta.get("parameters") if event.meta else None,
                "result_summary": event.meta.get("result_summary") if event.meta else None,
                "correlation_id": event.meta.get("correlation_id") if event.meta else None,
            }
            for event in events
        ]

        return {
            "events": events_data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def get_unique_devices(self) -> list[str]:
        """Get list of unique device IDs that have audit events.

        Returns:
            List of device IDs
        """
        stmt = (
            select(AuditEventORM.device_id)
            .distinct()
            .where(AuditEventORM.device_id.isnot(None))
            .order_by(AuditEventORM.device_id)
        )

        result = await self.session.execute(stmt)
        devices = result.scalars().all()
        return list(devices)

    async def get_unique_tools(self) -> list[str]:
        """Get list of unique tool names that have audit events.

        Returns:
            List of tool names
        """
        stmt = (
            select(AuditEventORM.tool_name)
            .distinct()
            .order_by(AuditEventORM.tool_name)
        )

        result = await self.session.execute(stmt)
        tools = result.scalars().all()
        return list(tools)

    async def log_approval_request_created(
        self,
        event_id: str,
        user_id: str,
        user_sub: str,
        user_email: str | None,
        user_role: str,
        approval_request_id: str,
        plan_id: str,
        tool_name: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Log an approval request creation event (Phase 5).

        Args:
            event_id: Unique event identifier
            user_id: User ID who created the approval request
            user_sub: User subject from OIDC token
            user_email: User email
            user_role: User role
            approval_request_id: ID of the created approval request
            plan_id: ID of the plan requiring approval
            tool_name: Tool that generated the plan
            meta: Additional metadata
        """
        from datetime import UTC, datetime

        event = AuditEventORM(
            id=event_id,
            timestamp=datetime.now(UTC),
            user_sub=user_sub,
            user_email=user_email,
            user_role=user_role,
            user_id=user_id,
            approver_id=None,
            approval_request_id=approval_request_id,
            device_id=None,
            environment=None,
            action="APPROVAL_REQUEST_CREATED",
            tool_name=tool_name,
            tool_tier="professional",
            plan_id=plan_id,
            job_id=None,
            result="SUCCESS",
            meta=meta or {},
            error_message=None,
        )
        self.session.add(event)
        await self.session.commit()

    async def log_approval_granted(
        self,
        event_id: str,
        user_id: str,
        approver_id: str,
        user_sub: str,
        user_email: str | None,
        user_role: str,
        approval_request_id: str,
        plan_id: str,
        tool_name: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Log an approval granted event (Phase 5).

        Args:
            event_id: Unique event identifier
            user_id: Original user ID who requested approval
            approver_id: User ID who approved the request
            user_sub: Approver's subject from OIDC token
            user_email: Approver's email
            user_role: Approver's role
            approval_request_id: ID of the approval request
            plan_id: ID of the approved plan
            tool_name: Tool associated with the plan
            meta: Additional metadata
        """
        from datetime import UTC, datetime

        event = AuditEventORM(
            id=event_id,
            timestamp=datetime.now(UTC),
            user_sub=user_sub,
            user_email=user_email,
            user_role=user_role,
            user_id=user_id,
            approver_id=approver_id,
            approval_request_id=approval_request_id,
            device_id=None,
            environment=None,
            action="APPROVAL_GRANTED",
            tool_name=tool_name,
            tool_tier="professional",
            plan_id=plan_id,
            job_id=None,
            result="SUCCESS",
            meta=meta or {},
            error_message=None,
        )
        self.session.add(event)
        await self.session.commit()

    async def log_approval_rejected(
        self,
        event_id: str,
        user_id: str,
        approver_id: str,
        user_sub: str,
        user_email: str | None,
        user_role: str,
        approval_request_id: str,
        plan_id: str,
        tool_name: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Log an approval rejected event (Phase 5).

        Args:
            event_id: Unique event identifier
            user_id: Original user ID who requested approval
            approver_id: User ID who rejected the request
            user_sub: Rejecter's subject from OIDC token
            user_email: Rejecter's email
            user_role: Rejecter's role
            approval_request_id: ID of the approval request
            plan_id: ID of the rejected plan
            tool_name: Tool associated with the plan
            meta: Additional metadata (should include rejection reason)
        """
        from datetime import UTC, datetime

        event = AuditEventORM(
            id=event_id,
            timestamp=datetime.now(UTC),
            user_sub=user_sub,
            user_email=user_email,
            user_role=user_role,
            user_id=user_id,
            approver_id=approver_id,
            approval_request_id=approval_request_id,
            device_id=None,
            environment=None,
            action="APPROVAL_REJECTED",
            tool_name=tool_name,
            tool_tier="professional",
            plan_id=plan_id,
            job_id=None,
            result="SUCCESS",
            meta=meta or {},
            error_message=None,
        )
        self.session.add(event)
        await self.session.commit()

    async def log_plan_execution_started(
        self,
        event_id: str,
        user_id: str,
        approver_id: str | None,
        user_sub: str,
        user_email: str | None,
        user_role: str,
        approval_request_id: str | None,
        plan_id: str,
        job_id: str,
        tool_name: str,
        device_id: str | None = None,
        environment: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Log a plan execution started event (Phase 5).

        Args:
            event_id: Unique event identifier
            user_id: User ID who initiated execution
            approver_id: User ID who approved (if applicable)
            user_sub: Executor's subject from OIDC token
            user_email: Executor's email
            user_role: Executor's role
            approval_request_id: Associated approval request (if applicable)
            plan_id: ID of the plan being executed
            job_id: ID of the execution job
            tool_name: Tool associated with the plan
            device_id: Target device (if single-device plan)
            environment: Target environment
            meta: Additional metadata
        """
        from datetime import UTC, datetime

        event = AuditEventORM(
            id=event_id,
            timestamp=datetime.now(UTC),
            user_sub=user_sub,
            user_email=user_email,
            user_role=user_role,
            user_id=user_id,
            approver_id=approver_id,
            approval_request_id=approval_request_id,
            device_id=device_id,
            environment=environment,
            action="PLAN_EXECUTION_STARTED",
            tool_name=tool_name,
            tool_tier="professional",
            plan_id=plan_id,
            job_id=job_id,
            result="SUCCESS",
            meta=meta or {},
            error_message=None,
        )
        self.session.add(event)
        await self.session.commit()

