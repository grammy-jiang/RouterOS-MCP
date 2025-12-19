"""MCP resources for device data (device:// URI scheme)."""

import gzip
import logging
from datetime import UTC, datetime
from typing import Optional

from fastmcp import FastMCP
from sqlalchemy import desc, select

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.health import HealthService
from routeros_mcp.domain.services.system import SystemService
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.infra.db.models import AuditEvent, Snapshot
from routeros_mcp.infra.observability.resource_cache import with_cache
from routeros_mcp.mcp.errors import DeviceNotFoundError, MCPError
from routeros_mcp.mcp_resources.utils import (
    create_resource_metadata,
    format_resource_content,
)

logger = logging.getLogger(__name__)


def register_device_resources(
    mcp: FastMCP,
    session_factory: DatabaseSessionManager,
    settings: Settings,
) -> None:
    """Register device:// resources with MCP server.

    Args:
        mcp: FastMCP instance
        session_factory: Database session factory
        settings: Application settings
    """

    @mcp.resource("device://{device_id}/overview")
    @with_cache("device://{device_id}/overview")
    async def device_overview(device_id: str) -> str:
        """Device overview with system information and health status.

        Provides comprehensive system information including:
        - RouterOS version and platform
        - System identity and board info
        - Uptime and performance metrics
        - CPU, memory, and temperature
        - Current health status

        Args:
            device_id: Internal device identifier

        Returns:
            JSON-formatted device overview
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)
            system_service = SystemService(session, settings)
            health_service = HealthService(session, settings)

            try:
                # Get device info
                device = await device_service.get_device(device_id)

                # Get system overview
                overview = await system_service.get_system_overview(device_id)

                # Get current health
                try:
                    health = await health_service.run_health_check(device_id)
                    health_data = {
                        "status": health.status,
                        "last_check": health.last_check_timestamp.isoformat()
                        if health.last_check_timestamp
                        else None,
                        "metrics": health.metrics,
                    }
                except Exception as e:
                    logger.warning(
                        f"Could not fetch health data for device {device_id}: {e}"
                    )
                    health_data = {"status": "unknown", "error": str(e)}

                # Combine data
                result = {
                    "device_id": device.id,
                    "name": device.name,
                    "environment": device.environment,
                    "management_ip": device.management_ip,
                    "management_port": device.management_port,
                    "tags": device.tags or [],
                    "system": overview,
                    "health": health_data,
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/overview",
                    extra={"device_id": device_id},
                )

                return content

            except DeviceNotFoundError:
                raise MCPError(
                    code=-32000,
                    message="Device not found",
                    data={"device_id": device_id, "resource_uri": f"device://{device_id}/overview"},
                )
            except Exception as e:
                logger.error(f"Error fetching device overview: {e}", exc_info=True)
                raise MCPError(
                    code=-32001,
                    message="Failed to fetch device overview",
                    data={"device_id": device_id, "error": str(e)},
                )

    @mcp.resource("device://{device_id}/health")
    @with_cache("device://{device_id}/health")
    async def device_health(device_id: str) -> str:
        """Device health metrics and status.

        Provides current health status including:
        - Overall health state (healthy/warning/critical)
        - CPU usage percentage
        - Memory usage and available
        - Temperature and voltage (if available)
        - Last health check timestamp
        - Historical health metrics summary

        Args:
            device_id: Device identifier

        Returns:
            JSON-formatted health metrics
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)
            health_service = HealthService(session, settings)

            try:
                # Verify device exists
                device = await device_service.get_device(device_id)

                # Get current health
                health = await health_service.run_health_check(device_id)

                result = {
                    "device_id": device.id,
                    "device_name": device.name,
                    "environment": device.environment,
                    "status": health.status,
                    "last_check_timestamp": health.last_check_timestamp.isoformat()
                    if health.last_check_timestamp
                    else None,
                    "metrics": health.metrics,
                    "checks": {
                        "cpu_ok": health.metrics.get("cpu_usage", 0) < 80,
                        "memory_ok": health.metrics.get("memory_usage_percent", 0) < 90,
                        "temperature_ok": health.metrics.get("temperature", 0) < 70,
                    },
                }

                content = format_resource_content(result, "application/json")

                logger.info(
                    f"Resource accessed: device://{device_id}/health",
                    extra={"device_id": device_id},
                )

                return content

            except DeviceNotFoundError:
                raise MCPError(
                    code=-32000,
                    message="Device not found",
                    data={"device_id": device_id},
                )
            except Exception as e:
                logger.error(f"Error fetching device health: {e}", exc_info=True)
                raise MCPError(
                    code=-32001,
                    message="Failed to fetch device health",
                    data={"device_id": device_id, "error": str(e)},
                )

    @mcp.resource("device://{device_id}/config")
    @with_cache("device://{device_id}/config")
    async def device_config(device_id: str) -> str:
        """RouterOS configuration export.

        Returns the current device configuration as a RouterOS script.
        This is a placeholder - actual config export would require additional RouterOS API integration.

        Args:
            device_id: Device identifier

        Returns:
            RouterOS configuration script from the latest snapshot
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)

            try:
                device = await device_service.get_device(device_id)

                snapshot = await _get_latest_snapshot(
                    session, device_id, kind="config"
                )
                if snapshot is None:
                    raise MCPError(
                        code=-32004,
                        message="Configuration snapshot not found",
                        data={"device_id": device_id},
                    )

                config_content = _decode_snapshot_data(snapshot)

                metadata = create_resource_metadata(
                    config_content,
                    device_id=device.id,
                    device_name=device.name,
                    environment=device.environment,
                    additional_metadata={
                        "snapshot_id": snapshot.id,
                        "snapshot_kind": snapshot.kind,
                        "snapshot_timestamp": snapshot.timestamp.isoformat(),
                        "snapshot_compression": (snapshot.meta or {}).get("compression"),
                        "snapshot_compression_level": (snapshot.meta or {}).get(
                            "compression_level"
                        ),
                        "snapshot_redacted": (snapshot.meta or {}).get("redacted"),
                        "snapshot_checksum": (snapshot.meta or {}).get("checksum"),
                        "snapshot_checksum_algorithm": (snapshot.meta or {}).get(
                            "checksum_algorithm"
                        ),
                    },
                )

                logger.info(
                    "Resource accessed: device://%s/config", device_id
                )

                return format_resource_content(
                    {
                        "config": config_content,
                        "_meta": metadata,
                    },
                    mime_type="application/json",
                )

            except DeviceNotFoundError:
                raise MCPError(
                    code=-32000,
                    message="Device not found",
                    data={"device_id": device_id},
                )

    @mcp.resource("device://{device_id}/logs")
    async def device_logs(device_id: str, limit: int = 50) -> str:
        """Device system logs.

        Returns recent audit-backed system events for the device.

        Args:
            device_id: Device identifier
            limit: Maximum number of log entries to return

        Returns:
            JSON array of log entries
        """
        async with session_factory.session() as session:
            device_service = DeviceService(session, settings)

            try:
                device = await device_service.get_device(device_id)

                logs = await _get_audit_logs_for_device(session, device_id, limit)

                payload = {
                    "device_id": device.id,
                    "device_name": device.name,
                    "environment": device.environment,
                    "logs": logs,
                    "count": len(logs),
                    "limit": limit,
                }

                content = format_resource_content(payload, "application/json")

                logger.info(
                    "Resource accessed: device://%s/logs", device_id
                )

                return content

            except DeviceNotFoundError:
                raise MCPError(
                    code=-32000,
                    message="Device not found",
                    data={"device_id": device_id},
                )


__all__ = ["register_device_resources"]


async def _get_latest_snapshot(session, device_id: str, kind: str) -> Optional[Snapshot]:
    """Fetch the latest snapshot for a device and kind."""

    result = await session.execute(
        select(Snapshot)
        .where(Snapshot.device_id == device_id, Snapshot.kind == kind)
        .order_by(desc(Snapshot.timestamp))
        .limit(1)
    )
    return result.scalar_one_or_none()


def _decode_snapshot_data(snapshot: Snapshot) -> str:
    """Decode snapshot bytes into text content."""

    try:
        data = snapshot.data or b""
        meta = snapshot.meta or {}

        if meta.get("compression") == "gzip":
            data = gzip.decompress(data)

        return data.decode("utf-8")
    except Exception as exc:
        logger.error(
            "Failed to decode snapshot %s: %s",
            getattr(snapshot, "id", "unknown"),
            exc,
            exc_info=True,
        )
        # Fallback to repr to ensure no placeholder content is returned
        return repr(snapshot.data)


async def _get_audit_logs_for_device(session, device_id: str, limit: int) -> list[dict]:
    """Return audit-backed events for the device as log entries."""

    result = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.device_id == device_id)
        .order_by(desc(AuditEvent.timestamp))
        .limit(limit)
    )
    events = result.scalars().all()

    logs: list[dict] = []
    for event in events:
        level = "error" if (event.result or "").lower() == "failure" else "info"
        meta = event.meta or {}
        message = meta.get("summary") or meta.get("message") or event.error_message or event.action
        logs.append(
            {
                "timestamp": event.timestamp.isoformat(),
                "level": level,
                "message": message,
                "tool": event.tool_name,
                "user": event.user_sub,
                "action": event.action,
                "metadata": meta,
            }
        )

    return logs
