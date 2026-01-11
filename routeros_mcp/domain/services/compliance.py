"""Compliance reporting service for audit logs, approvals, and policy violations.

This service provides read-only compliance reporting endpoints for:
- Audit log exports (CSV/JSON)
- Approval decision summaries
- Policy violations (authorization failures)
- Role assignment audit trails

All data is sourced from existing audit events and approval requests.
This service does NOT modify any data.

See Phase 5 #11 requirements for detailed specifications.
"""

import csv
import io
import logging
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.infra.db.models import ApprovalRequest as ApprovalRequestModel
from routeros_mcp.infra.db.models import AuditEvent as AuditEventORM

logger = logging.getLogger(__name__)


class ComplianceService:
    """Service for compliance reporting and audit analysis.

    Provides:
    - Audit event export in CSV/JSON formats
    - Approval decision summaries with filtering
    - Policy violation detection (AUTHZ_DENIED events)
    - Role assignment audit trails
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize compliance service.

        Args:
            session: Database session
        """
        self.session = session

    async def export_audit_events(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        device_id: str | None = None,
        tool_name: str | None = None,
        user_id: str | None = None,
        format: Literal["json", "csv"] = "json",
        limit: int = 10000,
    ) -> dict[str, Any] | str:
        """Export audit events for compliance reporting.

        Args:
            date_from: Start date for filtering (inclusive)
            date_to: End date for filtering (inclusive)
            device_id: Filter by device ID
            tool_name: Filter by tool name
            user_id: Filter by user ID
            format: Export format ('json' or 'csv')
            limit: Maximum number of events to export (default: 10000)

        Returns:
            For JSON: Dictionary with events array and metadata
            For CSV: CSV string with headers and event data
        """
        # Build query
        query = select(AuditEventORM).order_by(desc(AuditEventORM.timestamp))

        conditions = []
        if date_from:
            conditions.append(AuditEventORM.timestamp >= date_from)
        if date_to:
            conditions.append(AuditEventORM.timestamp <= date_to)
        if device_id:
            conditions.append(AuditEventORM.device_id == device_id)
        if tool_name:
            conditions.append(AuditEventORM.tool_name == tool_name)
        if user_id:
            conditions.append(AuditEventORM.user_id == user_id)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.limit(limit)

        # Execute query
        result = await self.session.execute(query)
        events = result.scalars().all()

        # Convert to data format
        # Note: meta field is excluded from export to prevent accidental exposure of sensitive data
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
                "plan_id": event.plan_id,
                "job_id": event.job_id,
                "result": event.result,
                "error_message": event.error_message,
            }
            for event in events
        ]

        if format == "csv":
            return self._export_events_csv(events_data)
        else:
            return {
                "events": events_data,
                "count": len(events_data),
                "filters": {
                    "date_from": date_from.isoformat() if date_from else None,
                    "date_to": date_to.isoformat() if date_to else None,
                    "device_id": device_id,
                    "tool_name": tool_name,
                    "user_id": user_id,
                },
            }

    def _export_events_csv(self, events: list[dict[str, Any]]) -> str:
        """Convert events to CSV format.

        Args:
            events: List of event dictionaries

        Returns:
            CSV string with headers and event data
        """
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(
            [
                "ID",
                "Timestamp",
                "User Sub",
                "User Email",
                "User Role",
                "User ID",
                "Approver ID",
                "Approval Request ID",
                "Device ID",
                "Environment",
                "Action",
                "Tool Name",
                "Tool Tier",
                "Plan ID",
                "Job ID",
                "Result",
                "Error Message",
            ]
        )

        # Write rows with consistent null handling
        for event in events:
            writer.writerow(
                [
                    event.get("id", ""),
                    event.get("timestamp", ""),
                    event.get("user_sub", ""),
                    event.get("user_email") or "",
                    event.get("user_role", ""),
                    event.get("user_id") or "",
                    event.get("approver_id") or "",
                    event.get("approval_request_id") or "",
                    event.get("device_id") or "",
                    event.get("environment") or "",
                    event.get("action", ""),
                    event.get("tool_name", ""),
                    event.get("tool_tier", ""),
                    event.get("plan_id") or "",
                    event.get("job_id") or "",
                    event.get("result", ""),
                    event.get("error_message") or "",
                ]
            )

        return output.getvalue()

    async def get_approval_decisions(
        self,
        status: Literal["approved", "rejected"] | None = None,
        date_from: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get summary of approval decisions for compliance reporting.

        Args:
            status: Filter by approval status ('approved' or 'rejected')
            date_from: Start date for filtering decisions
            limit: Maximum number of decisions to return
            offset: Number of decisions to skip (pagination)

        Returns:
            Dictionary with approval decisions and summary statistics
        """
        # Build query for approval requests
        query = select(ApprovalRequestModel).order_by(desc(ApprovalRequestModel.requested_at))

        conditions = []
        if status:
            conditions.append(ApprovalRequestModel.status == status)
        if date_from:
            conditions.append(ApprovalRequestModel.requested_at >= date_from)

        if conditions:
            query = query.where(and_(*conditions))

        # Get total count
        count_query = select(func.count()).select_from(ApprovalRequestModel)
        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        query = query.limit(limit).offset(offset)

        # Execute query
        result = await self.session.execute(query)
        requests = result.scalars().all()

        # Convert to data format
        decisions = [
            {
                "id": req.id,
                "plan_id": req.plan_id,
                "requested_by": req.requested_by,
                "requested_at": req.requested_at.isoformat(),
                "status": req.status,
                "approved_by": req.approved_by,
                "approved_at": req.approved_at.isoformat() if req.approved_at else None,
                "rejected_by": req.rejected_by,
                "rejected_at": req.rejected_at.isoformat() if req.rejected_at else None,
                "notes": req.notes,
            }
            for req in requests
        ]

        # Calculate summary statistics
        stats_query = (
            select(
                ApprovalRequestModel.status,
                func.count(ApprovalRequestModel.id).label("count"),
            )
            .select_from(ApprovalRequestModel)
            .group_by(ApprovalRequestModel.status)
        )

        if date_from:
            stats_query = stats_query.where(ApprovalRequestModel.requested_at >= date_from)

        stats_result = await self.session.execute(stats_query)
        stats = {row[0]: row[1] for row in stats_result.all()}

        return {
            "decisions": decisions,
            "total": total,
            "limit": limit,
            "offset": offset,
            "statistics": {
                "approved": stats.get("approved", 0),
                "rejected": stats.get("rejected", 0),
                "pending": stats.get("pending", 0),
            },
            "filters": {
                "status": status,
                "date_from": date_from.isoformat() if date_from else None,
            },
        }

    async def get_policy_violations(
        self,
        device_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get policy violations (authorization failures) for compliance reporting.

        Policy violations are identified as audit events with action='AUTHZ_DENIED'.

        Args:
            device_id: Filter by device ID
            date_from: Start date for filtering
            date_to: End date for filtering
            limit: Maximum number of violations to return

        Returns:
            Dictionary with policy violations and summary statistics
        """
        # Build query for AUTHZ_DENIED events
        query = (
            select(AuditEventORM)
            .where(AuditEventORM.action == "AUTHZ_DENIED")
            .order_by(desc(AuditEventORM.timestamp))
        )

        conditions = [AuditEventORM.action == "AUTHZ_DENIED"]
        if device_id:
            conditions.append(AuditEventORM.device_id == device_id)
        if date_from:
            conditions.append(AuditEventORM.timestamp >= date_from)
        if date_to:
            conditions.append(AuditEventORM.timestamp <= date_to)

        query = query.where(and_(*conditions))

        # Get total count
        count_query = select(func.count()).select_from(AuditEventORM).where(and_(*conditions))
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply limit
        query = query.limit(limit)

        # Execute query
        result = await self.session.execute(query)
        violations = result.scalars().all()

        # Convert to data format (meta excluded to prevent sensitive data exposure)
        violations_data = [
            {
                "id": v.id,
                "timestamp": v.timestamp.isoformat(),
                "user_sub": v.user_sub,
                "user_email": v.user_email,
                "user_role": v.user_role,
                "user_id": v.user_id,
                "device_id": v.device_id,
                "environment": v.environment,
                "tool_name": v.tool_name,
                "tool_tier": v.tool_tier,
                "error_message": v.error_message,
            }
            for v in violations
        ]

        # Get violations by device
        device_stats_query = (
            select(
                AuditEventORM.device_id,
                func.count(AuditEventORM.id).label("violation_count"),
            )
            .select_from(AuditEventORM)
            .where(AuditEventORM.action == "AUTHZ_DENIED")
            .group_by(AuditEventORM.device_id)
        )

        if date_from:
            device_stats_query = device_stats_query.where(AuditEventORM.timestamp >= date_from)
        if date_to:
            device_stats_query = device_stats_query.where(AuditEventORM.timestamp <= date_to)

        device_stats_result = await self.session.execute(device_stats_query)
        device_stats = {row[0]: row[1] for row in device_stats_result.all() if row[0]}

        return {
            "violations": violations_data,
            "total": total,
            "limit": limit,
            "statistics": {
                "total_violations": total,
                "by_device": device_stats,
            },
            "filters": {
                "device_id": device_id,
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
            },
        }

    async def get_role_audit(
        self,
        user_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get role assignment audit trail for compliance reporting.

        Role changes are tracked in audit events with specific action types.

        Args:
            user_id: Filter by user ID
            date_from: Start date for filtering
            date_to: End date for filtering
            limit: Maximum number of role changes to return

        Returns:
            Dictionary with role assignment history
        """
        # Build query for role-related audit events
        # Note: Role assignment actions might be logged as special audit events
        # For now, we look for any user_role changes in audit events
        query = select(AuditEventORM).order_by(desc(AuditEventORM.timestamp))

        conditions = []
        if user_id:
            conditions.append(AuditEventORM.user_id == user_id)
        if date_from:
            conditions.append(AuditEventORM.timestamp >= date_from)
        if date_to:
            conditions.append(AuditEventORM.timestamp <= date_to)

        if conditions:
            query = query.where(and_(*conditions))

        # Get total count
        count_query = select(func.count()).select_from(AuditEventORM)
        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply limit
        query = query.limit(limit)

        # Execute query
        result = await self.session.execute(query)
        events = result.scalars().all()

        # Group by user_id to track role history
        role_history: dict[str, list[dict[str, Any]]] = {}

        for event in events:
            if not event.user_id:
                continue

            if event.user_id not in role_history:
                role_history[event.user_id] = []

            role_history[event.user_id].append(
                {
                    "timestamp": event.timestamp.isoformat(),
                    "user_sub": event.user_sub,
                    "user_email": event.user_email,
                    "user_role": event.user_role,
                    "action": event.action,
                    "tool_name": event.tool_name,
                }
            )

        return {
            "role_history": role_history,
            "total_events": total,
            "limit": limit,
            "filters": {
                "user_id": user_id,
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
            },
        }
