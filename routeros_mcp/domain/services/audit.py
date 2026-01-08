"""Audit service for querying audit events.

Provides business logic for audit event queries with filtering and pagination.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
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

        if search:
            # Search in error_message and meta (as JSON string)
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    AuditEventORM.error_message.ilike(search_pattern),
                    AuditEventORM.meta.cast(str).ilike(search_pattern),
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
