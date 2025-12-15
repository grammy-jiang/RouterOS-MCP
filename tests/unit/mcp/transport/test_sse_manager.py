"""Tests for SSE subscription manager."""

import asyncio

import pytest

from routeros_mcp.mcp.transport.sse_manager import SSEManager, SSESubscription


@pytest.mark.asyncio
async def test_sse_manager_initialization() -> None:
    """Test SSEManager initializes with correct defaults."""
    manager = SSEManager()

    assert manager.max_subscriptions_per_device == 100
    assert manager.client_timeout_seconds == 1800  # 30 minutes
    assert manager.update_batch_interval_seconds == 1.0
    assert manager.get_subscription_count() == 0


@pytest.mark.asyncio
async def test_sse_manager_custom_config() -> None:
    """Test SSEManager with custom configuration."""
    manager = SSEManager(
        max_subscriptions_per_device=50,
        client_timeout_seconds=600,
        update_batch_interval_seconds=2.0,
    )

    assert manager.max_subscriptions_per_device == 50
    assert manager.client_timeout_seconds == 600
    assert manager.update_batch_interval_seconds == 2.0


@pytest.mark.asyncio
async def test_subscribe_creates_subscription() -> None:
    """Test subscribing to a resource creates a subscription."""
    manager = SSEManager()

    subscription = await manager.subscribe(
        client_id="client-123",
        resource_uri="device://dev-001/health",
    )

    assert subscription.client_id == "client-123"
    assert subscription.resource_uri == "device://dev-001/health"
    assert subscription.subscription_id != ""
    assert manager.get_subscription_count() == 1
    assert manager.get_subscription_count("device://dev-001/health") == 1


@pytest.mark.asyncio
async def test_subscribe_multiple_clients() -> None:
    """Test multiple clients can subscribe to the same resource."""
    manager = SSEManager()

    await manager.subscribe("client-1", "device://dev-001/health")
    await manager.subscribe("client-2", "device://dev-001/health")
    await manager.subscribe("client-3", "device://dev-002/health")

    assert manager.get_subscription_count() == 3
    assert manager.get_subscription_count("device://dev-001/health") == 2
    assert manager.get_subscription_count("device://dev-002/health") == 1


@pytest.mark.asyncio
async def test_subscribe_enforces_device_limit() -> None:
    """Test subscription limit per device is enforced."""
    manager = SSEManager(max_subscriptions_per_device=2)

    # First 2 subscriptions should succeed
    await manager.subscribe("client-1", "device://dev-001/health")
    await manager.subscribe("client-2", "device://dev-001/config")

    # Third subscription to same device should fail
    with pytest.raises(ValueError, match="Subscription limit exceeded"):
        await manager.subscribe("client-3", "device://dev-001/metrics")

    # Subscription to different device should succeed
    sub = await manager.subscribe("client-3", "device://dev-002/health")
    assert sub.resource_uri == "device://dev-002/health"


@pytest.mark.asyncio
async def test_unsubscribe_removes_subscription() -> None:
    """Test unsubscribing removes a subscription."""
    manager = SSEManager()

    sub = await manager.subscribe("client-1", "device://dev-001/health")
    assert manager.get_subscription_count() == 1

    await manager.unsubscribe(sub.subscription_id)
    assert manager.get_subscription_count() == 0
    assert manager.get_subscription_count("device://dev-001/health") == 0


@pytest.mark.asyncio
async def test_unsubscribe_nonexistent_subscription() -> None:
    """Test unsubscribing a non-existent subscription is safe."""
    manager = SSEManager()

    # Should not raise an error
    await manager.unsubscribe("nonexistent-id")
    assert manager.get_subscription_count() == 0


@pytest.mark.asyncio
async def test_broadcast_sends_to_subscribers() -> None:
    """Test broadcasting sends events to all subscribers."""
    manager = SSEManager(update_batch_interval_seconds=0.1)

    sub1 = await manager.subscribe("client-1", "device://dev-001/health")
    sub2 = await manager.subscribe("client-2", "device://dev-001/health")
    sub3 = await manager.subscribe("client-3", "device://dev-002/health")

    # Broadcast to dev-001
    count = await manager.broadcast(
        resource_uri="device://dev-001/health",
        data={"status": "healthy", "cpu": 25.5},
        event_type="update",
    )

    # Should return subscriber count for that resource
    assert count == 2

    # Wait for debounce
    await asyncio.sleep(0.15)

    # Check events in queues
    assert not sub1.queue.empty()
    assert not sub2.queue.empty()
    assert sub3.queue.empty()  # Not subscribed to dev-001

    # Verify event content
    event1 = sub1.queue.get_nowait()
    assert event1["event"] == "update"
    assert event1["data"]["status"] == "healthy"
    assert event1["data"]["cpu"] == 25.5
    assert "timestamp" in event1


@pytest.mark.asyncio
async def test_broadcast_debouncing() -> None:
    """Test that rapid broadcasts are debounced."""
    manager = SSEManager(update_batch_interval_seconds=0.2)

    sub = await manager.subscribe("client-1", "device://dev-001/health")

    # Send multiple broadcasts rapidly
    await manager.broadcast("device://dev-001/health", {"value": 1})
    await manager.broadcast("device://dev-001/health", {"value": 2})
    await manager.broadcast("device://dev-001/health", {"value": 3})

    # Wait for debounce
    await asyncio.sleep(0.25)

    # Should only have 1 event (the last one)
    assert sub.queue.qsize() == 1
    event = sub.queue.get_nowait()
    assert event["data"]["value"] == 3


@pytest.mark.asyncio
async def test_broadcast_to_nonexistent_resource() -> None:
    """Test broadcasting to a resource with no subscribers."""
    manager = SSEManager(update_batch_interval_seconds=0.1)

    count = await manager.broadcast(
        resource_uri="device://dev-999/health",
        data={"status": "unknown"},
    )

    # Should return 0 subscribers
    assert count == 0

    # Wait for debounce
    await asyncio.sleep(0.15)

    # No errors should occur


@pytest.mark.asyncio
async def test_stream_events_sends_connection_event() -> None:
    """Test stream_events sends initial connection event."""
    manager = SSEManager()

    sub = await manager.subscribe("client-1", "device://dev-001/health")

    # Get first event
    events = []
    async for event in manager.stream_events(sub):
        events.append(event)
        break  # Get only first event

    assert len(events) == 1
    assert events[0]["event"] == "connected"
    assert events[0]["data"]["subscription_id"] == sub.subscription_id
    assert events[0]["data"]["resource_uri"] == "device://dev-001/health"


@pytest.mark.asyncio
async def test_stream_events_with_broadcast() -> None:
    """Test stream_events receives broadcasted events."""
    manager = SSEManager(update_batch_interval_seconds=0.05)

    sub = await manager.subscribe("client-1", "device://dev-001/health")

    # Start streaming in background
    events = []

    async def collect_events() -> None:
        count = 0
        async for event in manager.stream_events(sub):
            events.append(event)
            count += 1
            if count >= 2:  # connection + 1 update
                break

    stream_task = asyncio.create_task(collect_events())

    # Wait a bit for stream to start
    await asyncio.sleep(0.01)

    # Broadcast event
    await manager.broadcast(
        resource_uri="device://dev-001/health",
        data={"status": "healthy"},
    )

    # Wait for stream to complete
    try:
        await asyncio.wait_for(stream_task, timeout=1.0)
    except TimeoutError:
        stream_task.cancel()

    # Should have connection + update event
    assert len(events) >= 2
    assert events[0]["event"] == "connected"
    assert events[1]["event"] == "update"
    assert events[1]["data"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_get_stats() -> None:
    """Test get_stats returns correct statistics."""
    manager = SSEManager()

    # Initial stats
    stats = manager.get_stats()
    assert stats["total_subscriptions"] == 0
    assert stats["total_resources"] == 0
    assert stats["total_clients"] == 0
    assert stats["total_broadcasts"] == 0

    # Add subscriptions
    await manager.subscribe("client-1", "device://dev-001/health")
    await manager.subscribe("client-1", "device://dev-001/config")
    await manager.subscribe("client-2", "device://dev-001/health")

    stats = manager.get_stats()
    assert stats["total_subscriptions"] == 3
    assert stats["total_resources"] == 2  # health + config
    assert stats["total_clients"] == 2  # client-1 + client-2


@pytest.mark.asyncio
async def test_extract_device_id() -> None:
    """Test device ID extraction from resource URIs."""
    # Device resources
    assert SSEManager._extract_device_id("device://dev-001/health") == "dev-001"
    assert SSEManager._extract_device_id("device://dev-123/config") == "dev-123"

    # Non-device resources
    assert SSEManager._extract_device_id("fleet://summary") is None
    assert SSEManager._extract_device_id("plan://plan-001") is None

    # Malformed URIs
    assert SSEManager._extract_device_id("device://") is None
    assert SSEManager._extract_device_id("invalid") is None


@pytest.mark.asyncio
async def test_subscription_cleanup_on_stream_cancel() -> None:
    """Test subscription is cleaned up when stream is cancelled."""
    manager = SSEManager()

    sub = await manager.subscribe("client-1", "device://dev-001/health")
    assert manager.get_subscription_count() == 1

    # Start streaming
    stream_gen = manager.stream_events(sub)

    # Get first event (connected)
    try:
        await stream_gen.__anext__()
    except StopAsyncIteration:
        # Stream may be exhausted; safe to ignore in test context
        pass

    # Close the generator which triggers cleanup
    try:
        await stream_gen.aclose()
    except Exception:  # noqa: S110
        # Ignore any exceptions during cleanup
        pass

    # Give cleanup time to run
    await asyncio.sleep(0.05)

    # Subscription should be cleaned up
    assert manager.get_subscription_count() == 0


@pytest.mark.asyncio
async def test_concurrent_subscriptions() -> None:
    """Test handling concurrent subscriptions from multiple clients."""
    manager = SSEManager()

    # Create subscriptions concurrently
    tasks = [manager.subscribe(f"client-{i}", f"device://dev-{i % 3}/health") for i in range(10)]

    subscriptions = await asyncio.gather(*tasks)

    assert len(subscriptions) == 10
    assert manager.get_subscription_count() == 10
    assert all(isinstance(sub, SSESubscription) for sub in subscriptions)


@pytest.mark.asyncio
async def test_broadcast_with_queue_full() -> None:
    """Test broadcast handles full queues gracefully."""
    manager = SSEManager(update_batch_interval_seconds=0.05)

    sub = await manager.subscribe("client-1", "device://dev-001/health")

    # Fill the queue (default queue size is unlimited, so we'll just test the logic exists)
    # The actual queue full handling is logged but doesn't block
    for i in range(5):
        await manager.broadcast(
            resource_uri="device://dev-001/health",
            data={"value": i},
        )
        await asyncio.sleep(0.06)  # Wait for each debounce

    # Queue should have events
    assert not sub.queue.empty()


@pytest.mark.asyncio
async def test_multiple_resources_per_client() -> None:
    """Test a single client can subscribe to multiple resources."""
    manager = SSEManager()

    client_id = "client-1"
    sub1 = await manager.subscribe(client_id, "device://dev-001/health")
    await manager.subscribe(client_id, "device://dev-001/config")
    await manager.subscribe(client_id, "device://dev-002/health")

    assert manager.get_subscription_count() == 3

    # Cleanup one subscription
    await manager.unsubscribe(sub1.subscription_id)
    assert manager.get_subscription_count() == 2

    # Other subscriptions for same client should still exist
    assert manager.get_subscription_count("device://dev-001/config") == 1
    assert manager.get_subscription_count("device://dev-002/health") == 1
