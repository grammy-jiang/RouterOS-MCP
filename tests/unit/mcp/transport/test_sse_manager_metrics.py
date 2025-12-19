"""Tests for SSE manager metrics instrumentation."""

import asyncio

import pytest

from routeros_mcp.infra.observability import metrics
from routeros_mcp.mcp.transport.sse_manager import SSEManager


def get_metric_value(metric_name, labels=None):
    """Helper to get current metric value from the custom registry.
    
    Args:
        metric_name: Name of the metric
        labels: Optional dictionary of label filters
        
    Returns:
        Metric value or 0 if not found
    """
    registry = metrics.get_registry()
    for metric in registry.collect():
        if metric.name == metric_name:
            for sample in metric.samples:
                # Check if this is the right sample
                if sample.name.startswith(metric_name):
                    # Check labels match if provided
                    if labels:
                        matches = all(
                            sample.labels.get(k) == v
                            for k, v in labels.items()
                        )
                        if matches:
                            return sample.value
                    else:
                        # No label filter, return first match
                        return sample.value
    return 0


@pytest.mark.asyncio
async def test_sse_connection_metrics_on_stream() -> None:
    """Test that SSE connection metrics are recorded when streaming events."""
    manager = SSEManager()
    sub = await manager.subscribe("client-1", "device://dev-001/health")

    initial_active = get_metric_value("routeros_mcp_sse_connections_active")
    
    # Create task that will consume events
    async def consume_stream():
        """Consume one event from stream."""
        async for event in manager.stream_events(sub):
            if event["event"] == "connected":
                # Wait a bit to ensure metrics are recorded
                await asyncio.sleep(0.1)
                break
    
    # Start streaming in background
    stream_task = asyncio.create_task(consume_stream())
    
    # Give it time to start and record metrics
    await asyncio.sleep(0.15)
    
    # Active connections should be incremented
    current_active = get_metric_value("routeros_mcp_sse_connections_active")
    assert current_active == initial_active + 1, f"Expected {initial_active + 1}, got {current_active}"
    
    # Cancel the stream (simulating disconnect)
    stream_task.cancel()
    
    # Wait for cleanup
    try:
        await stream_task
    except asyncio.CancelledError:
        # Expected when cancelling the background stream task during test cleanup
        pass
    
    # Give cleanup time to run
    await asyncio.sleep(0.1)
    
    # Active connections should be decremented back
    final_active = get_metric_value("routeros_mcp_sse_connections_active")
    assert final_active == initial_active, f"Expected {initial_active}, got {final_active}"


@pytest.mark.asyncio
async def test_subscription_metrics_on_subscribe() -> None:
    """Test that subscription metrics are updated when subscribing."""
    manager = SSEManager()
    
    resource_pattern = "device://*/health"
    
    # Initial count
    initial_count = get_metric_value(
        "routeros_mcp_resource_subscriptions_active",
        labels={"resource_uri_pattern": resource_pattern}
    )
    
    # Subscribe to a resource
    sub = await manager.subscribe("client-1", "device://dev-001/health")
    
    # The metric should be set to 1 more than initial
    assert get_metric_value(
        "routeros_mcp_resource_subscriptions_active",
        labels={"resource_uri_pattern": resource_pattern}
    ) == initial_count + 1
    
    # Subscribe another client to same resource
    sub2 = await manager.subscribe("client-2", "device://dev-001/health")
    
    # Metric should be updated to 2 more than initial
    assert get_metric_value(
        "routeros_mcp_resource_subscriptions_active",
        labels={"resource_uri_pattern": resource_pattern}
    ) == initial_count + 2
    
    # Unsubscribe one
    await manager.unsubscribe(sub.subscription_id)
    
    # Metric should be updated to 1 more than initial
    assert get_metric_value(
        "routeros_mcp_resource_subscriptions_active",
        labels={"resource_uri_pattern": resource_pattern}
    ) == initial_count + 1
    
    # Unsubscribe the other
    await manager.unsubscribe(sub2.subscription_id)
    
    # Metric should be back to initial
    assert get_metric_value(
        "routeros_mcp_resource_subscriptions_active",
        labels={"resource_uri_pattern": resource_pattern}
    ) == initial_count


@pytest.mark.asyncio
async def test_subscription_metrics_aggregated_across_resources() -> None:
    """Ensure subscription gauge aggregates counts across same resource pattern."""
    manager = SSEManager()

    resource_pattern = "device://*/health"
    initial_count = get_metric_value(
        "routeros_mcp_resource_subscriptions_active",
        labels={"resource_uri_pattern": resource_pattern},
    )

    sub1 = await manager.subscribe("client-1", "device://dev-001/health")
    sub2 = await manager.subscribe("client-2", "device://dev-002/health")

    assert get_metric_value(
        "routeros_mcp_resource_subscriptions_active",
        labels={"resource_uri_pattern": resource_pattern},
    ) == initial_count + 2

    await manager.unsubscribe(sub1.subscription_id)

    assert get_metric_value(
        "routeros_mcp_resource_subscriptions_active",
        labels={"resource_uri_pattern": resource_pattern},
    ) == initial_count + 1

    await manager.unsubscribe(sub2.subscription_id)

    assert get_metric_value(
        "routeros_mcp_resource_subscriptions_active",
        labels={"resource_uri_pattern": resource_pattern},
    ) == initial_count


@pytest.mark.asyncio
async def test_notification_metrics_on_broadcast() -> None:
    """Test that notification metrics are recorded when broadcasting."""
    manager = SSEManager(update_batch_interval_seconds=0.1)
    
    resource_pattern = "device://*/health"
    
    # Get initial metric values
    initial_count = get_metric_value(
        "routeros_mcp_resource_notifications_total",
        labels={"resource_uri_pattern": resource_pattern}
    )
    
    # Create subscribers
    await manager.subscribe("client-1", "device://dev-001/health")
    await manager.subscribe("client-2", "device://dev-001/health")
    
    # Broadcast to subscribers
    await manager.broadcast(
        resource_uri="device://dev-001/health",
        data={"status": "healthy"},
    )
    
    # Wait for debounce to complete
    await asyncio.sleep(0.15)
    
    # Should have recorded 2 notifications (one per subscriber)
    final_count = get_metric_value(
        "routeros_mcp_resource_notifications_total",
        labels={"resource_uri_pattern": resource_pattern}
    )
    assert final_count == initial_count + 2, f"Expected {initial_count + 2}, got {final_count}"


@pytest.mark.asyncio
async def test_notification_dropped_metrics() -> None:
    """Test that dropped notification metrics are recorded when queue is full."""
    # This is a simplified test since asyncio.Queue has unlimited size by default
    # We test the metric exists and can be incremented
    
    initial_dropped = get_metric_value(
        "routeros_mcp_resource_notifications_dropped_total",
        labels={"reason": "queue_full"}
    )
    
    # Manually record a dropped notification to verify metric works
    metrics.record_resource_notification_dropped(reason="queue_full")
    
    # Dropped count should increase
    final_dropped = get_metric_value(
        "routeros_mcp_resource_notifications_dropped_total",
        labels={"reason": "queue_full"}
    )
    assert final_dropped == initial_dropped + 1


@pytest.mark.asyncio
async def test_resource_pattern_extraction() -> None:
    """Test that resource URI patterns are correctly extracted for metrics."""
    manager = SSEManager()
    
    # Test device URI pattern extraction
    pattern = manager._get_resource_pattern("device://dev-001/health")
    assert pattern == "device://*/health"
    
    pattern = manager._get_resource_pattern("device://dev-002/config")
    assert pattern == "device://*/config"
    
    pattern = manager._get_resource_pattern("device://test-device/metrics")
    assert pattern == "device://*/metrics"
    
    # Test fleet URI pattern
    pattern = manager._get_resource_pattern("fleet://prod")
    assert pattern == "fleet://*"
    
    # Test unknown/malformed URIs
    pattern = manager._get_resource_pattern("invalid-uri")
    assert pattern == "unknown"
    
    pattern = manager._get_resource_pattern("")
    assert pattern == "unknown"
