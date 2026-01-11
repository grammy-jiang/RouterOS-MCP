"""Example: Device service integration with SSE subscriptions.

This demonstrates how domain services can emit SSE events when device
state changes occur, allowing clients to receive real-time updates.

The actual integration would be done in domain services like:
- routeros_mcp/domain/services/device.py
- routeros_mcp/domain/services/health.py
- routeros_mcp/domain/services/dns_ntp.py

This file shows the pattern without modifying existing services.
"""

import logging
from typing import Any

from routeros_mcp.mcp.transport.sse_manager import SSEManager

logger = logging.getLogger(__name__)


class DeviceStateEmitter:
    """Helper to emit device state change events via SSE.

    This would typically be integrated into DeviceService or HealthService
    to broadcast state changes to subscribed clients.

    Example integration in DeviceService:

        class DeviceService:
            def __init__(self, session, settings, sse_manager=None):
                self.session = session
                self.settings = settings
                self.sse_manager = sse_manager  # Optional SSE manager

            async def update_device_state(self, device_id: str, state: str) -> None:
                # Update device in database
                await self._update_db(device_id, state)

                # Emit SSE event if manager is available
                if self.sse_manager:
                    await self.sse_manager.broadcast(
                        resource_uri=f"device://{device_id}/health",
                        data={
                            "device_id": device_id,
                            "state": state,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                        event_type="device_state_change",
                    )

    Usage:
        # Initialize SSE manager in main application
        sse_manager = SSEManager()

        # Pass to services that emit events
        device_service = DeviceService(session, settings, sse_manager)
        health_service = HealthService(session, settings, sse_manager)

        # Services will automatically broadcast events
        await device_service.update_device_state("dev-001", "online")
        # -> Broadcasts to subscribers of "device://dev-001/health"
    """

    def __init__(self, sse_manager: SSEManager | None = None) -> None:
        """Initialize device state emitter.

        Args:
            sse_manager: Optional SSE manager for broadcasting events
        """
        self.sse_manager = sse_manager
        if self.sse_manager:
            self.sse_manager.allow_extended_resources = True

    async def emit_device_online(self, device_id: str, metadata: dict[str, Any]) -> None:
        """Emit event when device comes online.

        Args:
            device_id: Device identifier
            metadata: Additional device metadata (IP, version, etc.)
        """
        if not self.sse_manager:
            return

        await self.sse_manager.broadcast(
            resource_uri=f"device://{device_id}/health",
            data={
                "device_id": device_id,
                "status": "online",
                "metadata": metadata,
            },
            event_type="device_online",
        )

        logger.info(
            "Emitted device_online event",
            extra={"device_id": device_id},
        )

    async def emit_device_offline(self, device_id: str, reason: str) -> None:
        """Emit event when device goes offline.

        Args:
            device_id: Device identifier
            reason: Reason for offline status
        """
        if not self.sse_manager:
            return

        await self.sse_manager.broadcast(
            resource_uri=f"device://{device_id}/health",
            data={
                "device_id": device_id,
                "status": "offline",
                "reason": reason,
            },
            event_type="device_offline",
        )

        logger.warning(
            "Emitted device_offline event",
            extra={"device_id": device_id, "reason": reason},
        )

    async def emit_health_check_complete(
        self, device_id: str, health_data: dict[str, Any]
    ) -> None:
        """Emit event when health check completes.

        Args:
            device_id: Device identifier
            health_data: Health check results
        """
        if not self.sse_manager:
            return

        await self.sse_manager.broadcast(
            resource_uri=f"device://{device_id}/health",
            data=health_data,
            event_type="health_check",
        )

        logger.debug(
            "Emitted health_check event",
            extra={"device_id": device_id},
        )

    async def emit_config_change(
        self, device_id: str, change_type: str, details: dict[str, Any]
    ) -> None:
        """Emit event when device configuration changes.

        Args:
            device_id: Device identifier
            change_type: Type of configuration change (dns, ntp, firewall, etc.)
            details: Change details
        """
        if not self.sse_manager:
            return

        await self.sse_manager.broadcast(
            resource_uri=f"device://{device_id}/config",
            data={
                "device_id": device_id,
                "change_type": change_type,
                "details": details,
            },
            event_type="config_change",
        )

        logger.info(
            "Emitted config_change event",
            extra={"device_id": device_id, "change_type": change_type},
        )

    async def emit_plan_execution_complete(
        self, plan_id: str, result: dict[str, Any]
    ) -> None:
        """Emit event when plan execution completes.

        Args:
            plan_id: Plan identifier
            result: Execution result with success/failure details
        """
        if not self.sse_manager:
            return

        await self.sse_manager.broadcast(
            resource_uri=f"plan://{plan_id}",
            data={
                "plan_id": plan_id,
                "result": result,
            },
            event_type="plan_execution_complete",
        )

        logger.info(
            "Emitted plan_execution_complete event",
            extra={"plan_id": plan_id, "success": result.get("success", False)},
        )


__all__ = ["DeviceStateEmitter"]
