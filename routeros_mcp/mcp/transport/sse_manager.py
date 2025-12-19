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

from routeros_mcp.infra.observability import metrics

logger = logging.getLogger(__name__)


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
    ) -> None:
        """Initialize SSE subscription manager.

        Args:
            max_subscriptions_per_device: Maximum subscriptions per device (prevent DoS)
            client_timeout_seconds: Timeout for inactive clients (0 = no timeout)
            update_batch_interval_seconds: Debounce interval for batching updates
        """
        self.max_subscriptions_per_device = max_subscriptions_per_device
        self.client_timeout_seconds = client_timeout_seconds
        self.update_batch_interval_seconds = update_batch_interval_seconds

        # Subscription tracking
        self._subscriptions: dict[str, SSESubscription] = {}
        self._subscriptions_by_resource: dict[str, set[str]] = defaultdict(set)
        self._subscriptions_by_client: dict[str, set[str]] = defaultdict(set)

        # Lock to prevent race conditions during subscription creation
        self._subscription_lock = asyncio.Lock()

        # Debouncing state
        self._pending_updates: dict[str, dict[str, Any]] = {}
        self._debounce_tasks: dict[str, asyncio.Task[None]] = {}

        # Statistics
        self._total_broadcasts = 0
        self._total_events_sent = 0

        logger.info(
            "SSEManager initialized",
            extra={
                "max_subscriptions_per_device": max_subscriptions_per_device,
                "client_timeout_seconds": client_timeout_seconds,
                "update_batch_interval_seconds": update_batch_interval_seconds,
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
            ValueError: If subscription limit exceeded for this device
        """
        async with self._subscription_lock:
            # Check subscription limits per device
            device_id = self._extract_device_id(resource_uri)
            if device_id:
                device_subscriptions = sum(
                    1
                    for sub_id in self._subscriptions.values()
                    if self._extract_device_id(sub_id.resource_uri) == device_id
                )

                if device_subscriptions >= self.max_subscriptions_per_device:
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
            metrics.update_resource_subscriptions(
                resource_uri_pattern=resource_pattern,
                count=len(self._subscriptions_by_resource[resource_uri]),
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
        
        # Update metrics before removing resource tracking
        resource_pattern = self._get_resource_pattern(resource_uri)
        remaining_count = len(self._subscriptions_by_resource[resource_uri])
        
        if not self._subscriptions_by_resource[resource_uri]:
            del self._subscriptions_by_resource[resource_uri]
            # Set to 0 when no more subscriptions
            metrics.update_resource_subscriptions(
                resource_uri_pattern=resource_pattern,
                count=0,
            )
        else:
            # Update to remaining count
            metrics.update_resource_subscriptions(
                resource_uri_pattern=resource_pattern,
                count=remaining_count,
            )

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
                for _ in range(sent_count):
                    metrics.record_resource_notification(
                        resource_uri_pattern=resource_pattern,
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
        # Record SSE connection start
        metrics.record_sse_connection_start()
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
            # Record SSE connection end with duration
            connection_duration = (datetime.now(UTC) - connection_start_time).total_seconds()
            metrics.record_sse_connection_end(duration=connection_duration)
            
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


__all__ = ["SSEManager", "SSESubscription"]
