"""SSE (Server-Sent Events) subscription manager for MCP resources.

Manages client subscriptions to RouterOS device resources and broadcasts
real-time updates via SSE streams. Supports subscription limits, cleanup
on disconnect, and update debouncing.

See docs/14-mcp-protocol-integration-and-transport-design.md
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from collections.abc import AsyncIterator
from uuid import uuid4

from sqlalchemy import select, desc

from routeros_mcp.infra.db.models import HealthCheck
from routeros_mcp.infra.observability import metrics
from routeros_mcp.infra.observability.metrics import resource_notifications_total

logger = logging.getLogger(__name__)

# Type for database session factory (optional dependency)
DatabaseSessionFactory = Any  # Will be properly typed when passed


@dataclass
class SSESubscription:
    """Tracks a single SSE subscription from a client to a resource.

    Attributes:
        subscription_id: Unique identifier for this subscription
        client_id: Identifier for the subscribing client
        resource_uri: Resource URI being subscribed to (e.g., "device://dev-001/health")
        queue: AsyncIO queue for sending events to this subscription
        created_at: Timestamp when subscription was created
        last_activity: Timestamp of last client activity (event sent or ping)
    """

    subscription_id: str = field(default_factory=lambda: str(uuid4()))
    client_id: str = field(default="")
    resource_uri: str = field(default="")
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=lambda: asyncio.Queue())
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))


class SSEManager:
    """Manages SSE subscriptions for MCP resource updates.

    Features:
    - Track active SSE connections per client
    - Broadcast resource updates to subscribers
    - Handle client disconnect with cleanup
    - Enforce subscription limits (max per device)
    - Debounce rapid updates within configurable interval

    Example:
        manager = SSEManager(max_subscriptions_per_device=100)

        # Subscribe to device health updates
        subscription = await manager.subscribe(
            client_id="client-123",
            resource_uri="device://dev-001/health"
        )

        # Stream events to client
        async for event in manager.stream_events(subscription):
            yield event

        # Broadcast update to all subscribers
        await manager.broadcast(
            resource_uri="device://dev-001/health",
            data={"status": "healthy", "cpu": 25.5}
        )

        # Cleanup on disconnect
        await manager.unsubscribe(subscription.subscription_id)
    """

    def __init__(
        self,
        max_subscriptions_per_device: int = 100,
        client_timeout_seconds: int = 1800,  # 30 minutes
        update_batch_interval_seconds: float = 1.0,
        health_update_interval_seconds: float = 30.0,  # 30 seconds
        session_factory: DatabaseSessionFactory | None = None,
    ) -> None:
        """Initialize SSE subscription manager.

        Args:
            max_subscriptions_per_device: Maximum subscriptions per device (prevent DoS)
            client_timeout_seconds: Timeout for inactive clients (0 = no timeout)
            update_batch_interval_seconds: Debounce interval for batching updates
            health_update_interval_seconds: Interval for periodic health updates
            session_factory: Optional database session factory for health updates
        """
        self.max_subscriptions_per_device = max_subscriptions_per_device
        self.client_timeout_seconds = client_timeout_seconds
        self.update_batch_interval_seconds = update_batch_interval_seconds
        self.health_update_interval_seconds = health_update_interval_seconds
        self.session_factory = session_factory

        # Subscription tracking
        self._subscriptions: dict[str, SSESubscription] = {}
        self._subscriptions_by_resource: dict[str, set[str]] = defaultdict(set)
        self._subscriptions_by_client: dict[str, set[str]] = defaultdict(set)
        self._resource_patterns: dict[str, str] = {}

        # Lock to prevent race conditions during subscription creation
        self._subscription_lock = asyncio.Lock()

        # Debouncing state
        self._pending_updates: dict[str, dict[str, Any]] = {}
        self._debounce_tasks: dict[str, asyncio.Task[None]] = {}

        # Health update tasks (one per device health subscription)
        self._health_update_tasks: dict[str, asyncio.Task[None]] = {}

        # Statistics
        self._total_broadcasts = 0
        self._total_events_sent = 0

        logger.info(
            "SSEManager initialized",
            extra={
                "max_subscriptions_per_device": max_subscriptions_per_device,
                "client_timeout_seconds": client_timeout_seconds,
                "update_batch_interval_seconds": update_batch_interval_seconds,
                "health_update_interval_seconds": health_update_interval_seconds,
            },
        )

    async def subscribe(
        self,
        client_id: str,
        resource_uri: str,
    ) -> SSESubscription:
        """Subscribe a client to resource updates.

        Args:
            client_id: Unique client identifier
            resource_uri: Resource URI to subscribe to (e.g., "device://dev-001/health")

        Returns:
            SSESubscription object for streaming events

        Raises:
            ValueError: If subscription limit exceeded for this device or URI not subscribable
        """
        async with self._subscription_lock:
            # Validate resource URI is subscribable (Phase 4: only device health)
            if not self._is_subscribable(resource_uri):
                # Record subscription error
                metrics.record_sse_subscription_error(error_type="invalid_uri")
                raise ValueError(
                    f"Resource URI '{resource_uri}' is not subscribable. "
                    "In Phase 4, only 'device://<device_id>/health' resources support subscriptions."
                )

            # Check subscription limits per device
            device_id = self._extract_device_id(resource_uri)
            if device_id:
                device_subscriptions = sum(
                    1
                    for sub_id in self._subscriptions.values()
                    if self._extract_device_id(sub_id.resource_uri) == device_id
                )

                if device_subscriptions >= self.max_subscriptions_per_device:
                    # Record subscription error
                    metrics.record_sse_subscription_error(error_type="limit_exceeded")
                    raise ValueError(
                        f"Subscription limit exceeded for device {device_id}: "
                        f"{device_subscriptions} active (max: {self.max_subscriptions_per_device})"
                    )

            # Create subscription
            subscription = SSESubscription(
                client_id=client_id,
                resource_uri=resource_uri,
            )

            # Track subscription
            self._subscriptions[subscription.subscription_id] = subscription
            self._subscriptions_by_resource[resource_uri].add(subscription.subscription_id)
            self._subscriptions_by_client[client_id].add(subscription.subscription_id)

            # Update metrics for subscription count
            resource_pattern = self._get_resource_pattern(resource_uri)
            self._resource_patterns[resource_uri] = resource_pattern
            self._update_subscription_metrics(resource_pattern)

            # Phase 4: Update per-resource subscription count
            self._update_sse_active_subscriptions(resource_uri)

            # Start periodic health updates if this is a health resource and first subscriber
            if self._is_health_resource(resource_uri):
                if resource_uri not in self._health_update_tasks and self.session_factory:
                    self._health_update_tasks[resource_uri] = asyncio.create_task(
                        self._periodic_health_updates(resource_uri)
                    )
                    logger.info(
                        "Started periodic health updates for resource",
                        extra={"resource_uri": resource_uri},
                    )

            logger.info(
                "Client subscribed to resource",
                extra={
                    "subscription_id": subscription.subscription_id,
                    "client_id": client_id,
                    "resource_uri": resource_uri,
                    "resource_uri_pattern": resource_pattern,
                    "total_subscriptions": len(self._subscriptions),
                },
            )

            return subscription

    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe and cleanup a subscription.

        Args:
            subscription_id: Subscription ID to remove
        """
        subscription = self._subscriptions.pop(subscription_id, None)
        if not subscription:
            logger.warning(
                "Attempted to unsubscribe non-existent subscription",
                extra={"subscription_id": subscription_id},
            )
            return

        # Remove from resource tracking
        resource_uri = subscription.resource_uri
        self._subscriptions_by_resource[resource_uri].discard(subscription_id)

        resource_pattern = self._get_resource_pattern(resource_uri)

        if not self._subscriptions_by_resource[resource_uri]:
            del self._subscriptions_by_resource[resource_uri]
            self._resource_patterns.pop(resource_uri, None)

            # Stop health update task if this was the last subscriber
            if self._is_health_resource(resource_uri) and resource_uri in self._health_update_tasks:
                task = self._health_update_tasks.pop(resource_uri)
                task.cancel()
                # Await the cancelled task to ensure proper cleanup
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # Expected when task is cancelled
                logger.info(
                    "Stopped periodic health updates for resource",
                    extra={"resource_uri": resource_uri},
                )

        self._update_subscription_metrics(resource_pattern)

        # Phase 4: Update per-resource subscription count
        self._update_sse_active_subscriptions(resource_uri)

        # Remove from client tracking
        self._subscriptions_by_client[subscription.client_id].discard(subscription_id)
        if not self._subscriptions_by_client[subscription.client_id]:
            del self._subscriptions_by_client[subscription.client_id]

        logger.info(
            "Client unsubscribed from resource",
            extra={
                "subscription_id": subscription_id,
                "client_id": subscription.client_id,
                "resource_uri": resource_uri,
                "resource_uri_pattern": resource_pattern,
                "total_subscriptions": len(self._subscriptions),
            },
        )

    async def broadcast(
        self,
        resource_uri: str,
        data: dict[str, Any],
        event_type: str = "update",
    ) -> int:
        """Broadcast an update to all subscribers of a resource.

        Updates are debounced: multiple calls within update_batch_interval_seconds
        will be batched into a single event.

        Args:
            resource_uri: Resource URI to broadcast to
            data: Event data to send
            event_type: Event type (default: "update")

        Returns:
            Number of subscribers that received the event
        """
        # Store pending update
        self._pending_updates[resource_uri] = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Cancel existing debounce task if any
        if resource_uri in self._debounce_tasks:
            self._debounce_tasks[resource_uri].cancel()

        # Schedule debounced broadcast
        self._debounce_tasks[resource_uri] = asyncio.create_task(
            self._debounced_broadcast(resource_uri)
        )

        # Return current subscriber count (actual count will be determined after debounce)
        return len(self._subscriptions_by_resource.get(resource_uri, set()))

    async def _debounced_broadcast(self, resource_uri: str) -> None:
        """Execute debounced broadcast after delay.

        Args:
            resource_uri: Resource URI to broadcast to
        """
        try:
            # Wait for debounce interval
            await asyncio.sleep(self.update_batch_interval_seconds)

            # Get pending update
            update = self._pending_updates.pop(resource_uri, None)
            if not update:
                return

            # Get subscribers
            subscriber_ids = self._subscriptions_by_resource.get(resource_uri, set())
            if not subscriber_ids:
                logger.debug(
                    "No subscribers for resource",
                    extra={"resource_uri": resource_uri},
                )
                return

            # Send to all subscribers
            sent_count = 0
            dropped_count = 0
            resource_pattern = self._get_resource_pattern(resource_uri)

            for sub_id in list(subscriber_ids):  # Copy to avoid modification during iteration
                subscription = self._subscriptions.get(sub_id)
                if not subscription:
                    continue

                try:
                    subscription.queue.put_nowait(update)
                    subscription.last_activity = datetime.now(UTC)
                    sent_count += 1
                    self._total_events_sent += 1
                except asyncio.QueueFull:
                    dropped_count += 1
                    logger.warning(
                        "Subscription queue full, dropping event",
                        extra={
                            "subscription_id": sub_id,
                            "resource_uri": resource_uri,
                            "resource_uri_pattern": resource_pattern,
                            "reason": "queue_full",
                        },
                    )
                    # Record dropped notification metric
                    metrics.record_resource_notification_dropped(reason="queue_full")

            self._total_broadcasts += 1

            # Record notification metrics for successfully sent notifications
            if sent_count > 0:
                # Use Counter.inc(amount) to increment by sent_count in one operation
                resource_notifications_total.labels(
                    resource_uri_pattern=resource_pattern,
                ).inc(sent_count)

                # Phase 4: Record events sent with resource_type and device_id
                device_id = self._extract_device_id(resource_uri)
                resource_type = self._extract_resource_type(resource_uri)
                if device_id and resource_type:
                    metrics.record_sse_event_sent(
                        resource_type=resource_type,
                        device_id=device_id,
                        count=sent_count,
                    )

            logger.info(
                "Broadcast event to subscribers",
                extra={
                    "resource_uri": resource_uri,
                    "resource_uri_pattern": resource_pattern,
                    "event_type": update.get("event", "update"),
                    "subscriber_count": sent_count,
                    "dropped_count": dropped_count,
                    "total_broadcasts": self._total_broadcasts,
                },
            )

        except asyncio.CancelledError:
            # Debounce was cancelled, this is expected
            pass
        finally:
            # Cleanup debounce task
            self._debounce_tasks.pop(resource_uri, None)

    async def stream_events(
        self,
        subscription: SSESubscription,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream events to a subscription.

        Yields SSE-formatted events from the subscription's queue.
        Includes automatic keepalive pings and timeout handling.

        Args:
            subscription: Subscription to stream events from

        Yields:
            Event dictionaries with 'event' and 'data' keys
        """
        # Record SSE connection start (existing Phase 2.1 metric)
        metrics.record_sse_connection_start()
        # Phase 4: Record active connection
        metrics.record_sse_active_connection_start()
        connection_start_time = datetime.now(UTC)

        try:
            # Send initial connection confirmation
            yield {
                "event": "connected",
                "data": {
                    "subscription_id": subscription.subscription_id,
                    "resource_uri": subscription.resource_uri,
                    "timestamp": connection_start_time.isoformat(),
                },
            }

            while True:
                try:
                    # Wait for event with timeout for periodic pings
                    event = await asyncio.wait_for(
                        subscription.queue.get(),
                        timeout=30.0,  # Send ping every 30 seconds
                    )

                    # Send event
                    yield event
                    subscription.last_activity = datetime.now(UTC)

                except TimeoutError:
                    # Send keepalive ping
                    now = datetime.now(UTC)
                    yield {
                        "event": "ping",
                        "data": {
                            "timestamp": now.isoformat(),
                        },
                    }

                    # Check for client timeout (based on last actual activity, not ping)
                    if self.client_timeout_seconds > 0:
                        inactive_seconds = (now - subscription.last_activity).total_seconds()
                        if inactive_seconds > self.client_timeout_seconds:
                            # Phase 4: Record timeout error
                            metrics.record_sse_subscription_error(error_type="timeout")
                            logger.warning(
                                "Client timeout, closing subscription",
                                extra={
                                    "subscription_id": subscription.subscription_id,
                                    "inactive_seconds": inactive_seconds,
                                },
                            )
                            break

        except asyncio.CancelledError:
            logger.info(
                "SSE stream cancelled",
                extra={"subscription_id": subscription.subscription_id},
            )
            raise
        finally:
            # Record SSE connection end with duration (existing Phase 2.1 metric)
            connection_duration = (datetime.now(UTC) - connection_start_time).total_seconds()
            metrics.record_sse_connection_end(duration=connection_duration)
            # Phase 4: Record active connection end
            metrics.record_sse_active_connection_end()

            # Cleanup subscription on disconnect
            await self.unsubscribe(subscription.subscription_id)

    def get_subscription_count(self, resource_uri: str | None = None) -> int:
        """Get count of active subscriptions.

        Args:
            resource_uri: Optional resource URI to filter by

        Returns:
            Number of active subscriptions
        """
        if resource_uri:
            return len(self._subscriptions_by_resource.get(resource_uri, set()))
        return len(self._subscriptions)

    def get_stats(self) -> dict[str, Any]:
        """Get subscription statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_subscriptions": len(self._subscriptions),
            "total_resources": len(self._subscriptions_by_resource),
            "total_clients": len(self._subscriptions_by_client),
            "total_broadcasts": self._total_broadcasts,
            "total_events_sent": self._total_events_sent,
        }

    @staticmethod
    def _is_subscribable(resource_uri: str) -> bool:
        """Check if a resource URI supports subscriptions.
        
        Phase 4: Only device health resources are subscribable.
        
        Args:
            resource_uri: Resource URI to check
            
        Returns:
            True if the URI supports subscriptions, False otherwise
        """
        # Phase 4: Only device://*/health is subscribable
        if not resource_uri.startswith("device://"):
            return False

        # Parse device://<device_id>/health
        parts = resource_uri.split("/")
        if len(parts) >= 4 and parts[3] == "health":
            return True

        return False

    @staticmethod
    def _is_health_resource(resource_uri: str) -> bool:
        """Check if a resource URI is a device health resource.
        
        Uses the same validation logic as _is_subscribable to ensure consistency.
        
        Args:
            resource_uri: Resource URI to check
            
        Returns:
            True if the URI is a device health resource
        """
        return SSEManager._is_subscribable(resource_uri)

    @staticmethod
    def _extract_device_id(resource_uri: str) -> str | None:
        """Extract device ID from resource URI.

        Args:
            resource_uri: Resource URI (e.g., "device://dev-001/health")

        Returns:
            Device ID or None if not a device resource
        """
        if not resource_uri.startswith("device://"):
            return None

        # Parse device://dev-001/health -> dev-001
        parts = resource_uri.split("/")
        if len(parts) >= 3 and parts[2]:
            return parts[2]

        return None

    @staticmethod
    def _extract_resource_type(resource_uri: str) -> str | None:
        """Extract resource type from resource URI.

        Args:
            resource_uri: Resource URI (e.g., "device://dev-001/health")

        Returns:
            Resource type (e.g., "health", "config") or None if not extractable
        """
        if not resource_uri.startswith("device://"):
            return None

        # Parse device://dev-001/health -> health
        parts = resource_uri.split("/")
        if len(parts) >= 4 and parts[3]:
            return parts[3]

        return None

    @staticmethod
    def _get_resource_pattern(resource_uri: str) -> str:
        """Get resource URI pattern for metrics (generalized form).

        Converts specific URIs to patterns for aggregated metrics:
        - "device://dev-001/health" -> "device://*/health"
        - "device://dev-002/config" -> "device://*/config"
        - "fleet://prod" -> "fleet://*"

        Args:
            resource_uri: Specific resource URI

        Returns:
            Generalized resource URI pattern for metrics
        """
        if not resource_uri:
            return "unknown"

        # Parse URI scheme
        if "://" not in resource_uri:
            return "unknown"

        scheme, rest = resource_uri.split("://", 1)

        # For device:// URIs, replace device ID with wildcard
        if scheme == "device":
            parts = rest.split("/")
            if len(parts) >= 2:
                # device://dev-001/health -> device://*/health
                return f"{scheme}://*/{'/'.join(parts[1:])}"
            else:
                return f"{scheme}://*"

        # For other schemes, just use wildcard
        return f"{scheme}://*"

    def _update_subscription_metrics(self, resource_pattern: str) -> None:
        """Update aggregated subscription metrics for a resource pattern."""
        total_count = self._get_pattern_subscription_count(resource_pattern)
        metrics.update_resource_subscriptions(
            resource_uri_pattern=resource_pattern,
            count=total_count,
        )

    def _update_sse_active_subscriptions(self, resource_uri: str) -> None:
        """Update Phase 4 per-resource subscription count metric.
        
        Args:
            resource_uri: Specific resource URI (e.g., "device://dev-001/health")
        """
        count = len(self._subscriptions_by_resource.get(resource_uri, set()))
        metrics.update_sse_active_subscriptions(
            resource_uri=resource_uri,
            count=count,
        )

    def _get_pattern_subscription_count(self, resource_pattern: str) -> int:
        """Calculate total subscriptions across resources sharing a pattern."""
        total = 0
        for resource_uri, subscription_ids in self._subscriptions_by_resource.items():
            pattern = self._resource_patterns.get(resource_uri)
            if pattern is None:
                pattern = self._get_resource_pattern(resource_uri)
                self._resource_patterns[resource_uri] = pattern

            if pattern == resource_pattern:
                total += len(subscription_ids)
        return total

    async def _periodic_health_updates(self, resource_uri: str) -> None:
        """Periodically query and broadcast health data for a subscribed resource.
        
        Args:
            resource_uri: Device health resource URI (e.g., "device://dev-001/health")
        """
        if not self.session_factory:
            logger.warning(
                "No session factory provided, cannot start periodic health updates",
                extra={"resource_uri": resource_uri},
            )
            return

        device_id = self._extract_device_id(resource_uri)
        if not device_id:
            logger.error(
                "Cannot extract device ID from health resource URI",
                extra={"resource_uri": resource_uri},
            )
            return

        logger.info(
            "Starting periodic health updates",
            extra={
                "resource_uri": resource_uri,
                "device_id": device_id,
                "interval_seconds": self.health_update_interval_seconds,
            },
        )

        try:
            while True:
                try:
                    # Query latest health check from database
                    async with self.session_factory.session() as session:
                        result = await session.execute(
                            select(HealthCheck)
                            .where(HealthCheck.device_id == device_id)
                            .order_by(desc(HealthCheck.timestamp))
                            .limit(1)
                        )
                        health_check = result.scalar_one_or_none()

                        if health_check:
                            # Build health data
                            health_data = {
                                "device_id": device_id,
                                "status": health_check.status,
                                "timestamp": health_check.timestamp.isoformat(),
                                "metrics": {
                                    "cpu_usage_percent": health_check.cpu_usage_percent,
                                    "memory_used_bytes": health_check.memory_used_bytes,
                                    "memory_total_bytes": health_check.memory_total_bytes,
                                    "temperature_celsius": health_check.temperature_celsius,
                                    "uptime_seconds": health_check.uptime_seconds,
                                },
                            }

                            # Calculate memory usage percent if we have the data
                            if (
                                health_check.memory_used_bytes is not None
                                and health_check.memory_total_bytes is not None
                                and health_check.memory_total_bytes > 0
                            ):
                                health_data["metrics"]["memory_usage_percent"] = (
                                    health_check.memory_used_bytes / health_check.memory_total_bytes * 100
                                )

                            # Broadcast to subscribers
                            await self.broadcast(
                                resource_uri=resource_uri,
                                data=health_data,
                                event_type="health",
                            )

                            logger.debug(
                                "Broadcasted health update",
                                extra={
                                    "resource_uri": resource_uri,
                                    "device_id": device_id,
                                    "status": health_check.status,
                                },
                            )
                        else:
                            # No health check found - send error event
                            await self.broadcast(
                                resource_uri=resource_uri,
                                data={
                                    "device_id": device_id,
                                    "error": "No health check data found",
                                },
                                event_type="error",
                            )

                            logger.debug(
                                "No health check data found for device",
                                extra={"resource_uri": resource_uri, "device_id": device_id},
                            )

                except Exception as e:
                    logger.error(
                        "Error querying health data",
                        extra={
                            "resource_uri": resource_uri,
                            "device_id": device_id,
                            "error": str(e),
                        },
                        exc_info=True,
                    )
                    # Send error event but continue running
                    try:
                        await self.broadcast(
                            resource_uri=resource_uri,
                            data={
                                "device_id": device_id,
                                "error": f"Failed to query health data: {str(e)}",
                            },
                            event_type="error",
                        )
                    except Exception:
                        pass  # Ignore broadcast errors

                # Wait for next update
                await asyncio.sleep(self.health_update_interval_seconds)

        except asyncio.CancelledError:
            logger.info(
                "Periodic health updates cancelled",
                extra={"resource_uri": resource_uri, "device_id": device_id},
            )
            raise


__all__ = ["SSEManager", "SSESubscription"]
