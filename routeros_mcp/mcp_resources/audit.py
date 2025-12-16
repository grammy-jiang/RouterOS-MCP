"""MCP resources for audit data (audit:// URI scheme)."""

import logging
from datetime import UTC, datetime

from fastmcp import FastMCP
from sqlalchemy import desc, select

from routeros_mcp.config import Settings
from routeros_mcp.infra.db.models import AuditEvent
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.infra.observability.resource_cache import with_cache
from routeros_mcp.mcp.errors import MCPError
from routeros_mcp.mcp_resources.utils import format_resource_content

logger = logging.getLogger(__name__)


def register_audit_resources(
    mcp: FastMCP,
    session_factory: DatabaseSessionManager,
    settings: Settings,
) -> None:
    """Register audit:// resources with MCP server.

    Args:
        mcp: FastMCP instance
        session_factory: Database session factory
        settings: Application settings
    """

    @mcp.resource("audit://events/recent/{limit}")
    async def audit_events_recent(limit: int = 100) -> str:
        """Recent audit events across all devices.

        Provides:
        - Recent operation logs
        - User actions
        - System events
        - Tool invocations
        - Configuration changes

        Args:
            limit: Maximum number of events to return (default 100)

        Returns:
            JSON array of audit events
        """
        async with session_factory.session() as session:
            try:
                query = (
                    select(AuditEvent)
                    .order_by(desc(AuditEvent.timestamp))
                    .limit(limit)
                )
                result = await session.execute(query)
                events = result.scalars().all()

                payload = {
                    "events": [
                        _serialize_audit_event(event) for event in events
                    ],
                    "count": len(events),
                    "limit": limit,
                }

                logger.info("Resource accessed: audit://events/recent")
                return format_resource_content(payload, "application/json")

            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Failed to load audit events", exc_info=True)
                raise MCPError(
                    code=-32050,
                    message="Failed to load audit events",
                    data={"error": str(exc)},
                )

    @mcp.resource("audit://events/by-user/{user_sub}")
    async def audit_events_by_user(user_sub: str, limit: int = 100) -> str:
        """Audit events filtered by user.

        Args:
            user_sub: User subject identifier
            limit: Maximum number of events to return

        Returns:
            JSON array of audit events for the specified user
        """
        async with session_factory.session() as session:
            try:
                query = (
                    select(AuditEvent)
                    .where(AuditEvent.user_sub == user_sub)
                    .order_by(desc(AuditEvent.timestamp))
                    .limit(limit)
                )
                result = await session.execute(query)
                events = result.scalars().all()

                payload = {
                    "user_sub": user_sub,
                    "events": [
                        _serialize_audit_event(event) for event in events
                    ],
                    "count": len(events),
                    "limit": limit,
                }

                logger.info(
                    "Resource accessed: audit://events/by-user/%s", user_sub
                )
                return format_resource_content(payload, "application/json")

            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Failed to load audit events by user", exc_info=True)
                raise MCPError(
                    code=-32051,
                    message="Failed to load audit events for user",
                    data={"user_sub": user_sub, "error": str(exc)},
                )

    @mcp.resource("audit://events/by-device/{device_id}")
    async def audit_events_by_device(device_id: str, limit: int = 100) -> str:
        """Audit events filtered by device.

        Args:
            device_id: Device identifier
            limit: Maximum number of events to return

        Returns:
            JSON array of audit events for the specified device
        """
        async with session_factory.session() as session:
            try:
                query = (
                    select(AuditEvent)
                    .where(AuditEvent.device_id == device_id)
                    .order_by(desc(AuditEvent.timestamp))
                    .limit(limit)
                )
                result = await session.execute(query)
                events = result.scalars().all()

                payload = {
                    "device_id": device_id,
                    "events": [
                        _serialize_audit_event(event) for event in events
                    ],
                    "count": len(events),
                    "limit": limit,
                }

                logger.info(
                    "Resource accessed: audit://events/by-device/%s", device_id
                )
                return format_resource_content(payload, "application/json")

            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Failed to load audit events by device", exc_info=True)
                raise MCPError(
                    code=-32052,
                    message="Failed to load audit events for device",
                    data={"device_id": device_id, "error": str(exc)},
                )

    @mcp.resource("audit://events/by-tool/{tool_name}")
    async def audit_events_by_tool(tool_name: str, limit: int = 100) -> str:
        """Audit events filtered by tool.

        Args:
            tool_name: Tool name (e.g., "system/get-overview")
            limit: Maximum number of events to return

        Returns:
            JSON array of audit events for the specified tool
        """
        async with session_factory.session() as session:
            try:
                query = (
                    select(AuditEvent)
                    .where(AuditEvent.tool_name == tool_name)
                    .order_by(desc(AuditEvent.timestamp))
                    .limit(limit)
                )
                result = await session.execute(query)
                events = result.scalars().all()

                payload = {
                    "tool_name": tool_name,
                    "events": [
                        _serialize_audit_event(event) for event in events
                    ],
                    "count": len(events),
                    "limit": limit,
                }

                logger.info(
                    "Resource accessed: audit://events/by-tool/%s", tool_name
                )
                return format_resource_content(payload, "application/json")

            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Failed to load audit events by tool", exc_info=True)
                raise MCPError(
                    code=-32053,
                    message="Failed to load audit events for tool",
                    data={"tool_name": tool_name, "error": str(exc)},
                )


def _serialize_audit_event(event: AuditEvent) -> dict:
    """Convert an AuditEvent ORM instance into a JSON-serializable dict."""

    return {
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
        "plan_id": event.plan_id,
        "job_id": event.job_id,
        "result": event.result,
        "meta": event.meta or {},
        "error_message": event.error_message,
    }


__all__ = ["register_audit_resources"]
