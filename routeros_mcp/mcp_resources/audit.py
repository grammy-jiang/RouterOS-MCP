"""MCP resources for audit data (audit:// URI scheme)."""

import logging
from datetime import UTC, datetime

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.infra.db.session import DatabaseSessionManager
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

    @mcp.resource("audit://events/recent")
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
        # Placeholder implementation
        # TODO: Integrate with actual AuditService when available

        result = {
            "events": [
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "event_type": "tool_invocation",
                    "user_sub": "user123",
                    "device_id": "dev-001",
                    "tool_name": "system/get-overview",
                    "status": "success",
                }
            ],
            "count": 1,
            "limit": limit,
            "note": "Audit service integration pending",
        }

        content = format_resource_content(result, "application/json")

        logger.info("Resource accessed: audit://events/recent")

        return content

    @mcp.resource("audit://events/by-user/{user_sub}")
    async def audit_events_by_user(user_sub: str, limit: int = 100) -> str:
        """Audit events filtered by user.

        Args:
            user_sub: User subject identifier
            limit: Maximum number of events to return

        Returns:
            JSON array of audit events for the specified user
        """
        # Placeholder implementation
        result = {
            "user_sub": user_sub,
            "events": [],
            "count": 0,
            "limit": limit,
            "note": "Audit service integration pending",
        }

        content = format_resource_content(result, "application/json")

        logger.info(
            f"Resource accessed: audit://events/by-user/{user_sub}",
            extra={"user_sub": user_sub},
        )

        return content

    @mcp.resource("audit://events/by-device/{device_id}")
    async def audit_events_by_device(device_id: str, limit: int = 100) -> str:
        """Audit events filtered by device.

        Args:
            device_id: Device identifier
            limit: Maximum number of events to return

        Returns:
            JSON array of audit events for the specified device
        """
        # Placeholder implementation
        result = {
            "device_id": device_id,
            "events": [],
            "count": 0,
            "limit": limit,
            "note": "Audit service integration pending",
        }

        content = format_resource_content(result, "application/json")

        logger.info(
            f"Resource accessed: audit://events/by-device/{device_id}",
            extra={"device_id": device_id},
        )

        return content

    @mcp.resource("audit://events/by-tool/{tool_name}")
    async def audit_events_by_tool(tool_name: str, limit: int = 100) -> str:
        """Audit events filtered by tool.

        Args:
            tool_name: Tool name (e.g., "system/get-overview")
            limit: Maximum number of events to return

        Returns:
            JSON array of audit events for the specified tool
        """
        # Placeholder implementation
        result = {
            "tool_name": tool_name,
            "events": [],
            "count": 0,
            "limit": limit,
            "note": "Audit service integration pending",
        }

        content = format_resource_content(result, "application/json")

        logger.info(
            f"Resource accessed: audit://events/by-tool/{tool_name}",
            extra={"tool_name": tool_name},
        )

        return content


__all__ = ["register_audit_resources"]
