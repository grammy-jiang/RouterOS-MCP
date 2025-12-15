"""End-to-end tests for SSE resource subscriptions.

Tests the full flow of subscribing to resources, triggering updates,
and receiving events via SSE streams.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from routeros_mcp.config import Settings
from routeros_mcp.mcp.transport.http_sse import HTTPSSETransport
from routeros_mcp.mcp.transport.sse_manager import SSEManager


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        mcp_transport="http",
        mcp_http_host="127.0.0.1",
        mcp_http_port=8080,
        mcp_http_base_path="/mcp",
        sse_max_subscriptions_per_device=10,
        sse_client_timeout_seconds=60,
        sse_update_batch_interval_seconds=0.1,
    )


@pytest.fixture
def sse_manager(settings: Settings) -> SSEManager:
    """Create SSE manager for testing."""
    return SSEManager(
        max_subscriptions_per_device=settings.sse_max_subscriptions_per_device,
        client_timeout_seconds=settings.sse_client_timeout_seconds,
        update_batch_interval_seconds=settings.sse_update_batch_interval_seconds,
    )


@pytest.fixture
def mock_mcp_instance() -> MagicMock:
    """Create mock MCP instance."""
    mock = MagicMock()
    mock.run_http_async = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_sse_subscription_end_to_end(
    settings: Settings,
    sse_manager: SSEManager,
) -> None:
    """Test complete SSE subscription flow: subscribe → update → receive event."""
    
    # Subscribe to a resource
    subscription = await sse_manager.subscribe(
        client_id="test-client",
        resource_uri="device://dev-001/health",
    )
    
    # Start streaming events in background
    events = []
    
    async def collect_events() -> None:
        count = 0
        async for event in sse_manager.stream_events(subscription):
            events.append(event)
            count += 1
            if count >= 2:  # connection + update
                break
    
    stream_task = asyncio.create_task(collect_events())
    
    # Wait for stream to start
    await asyncio.sleep(0.05)
    
    # Trigger update
    await sse_manager.broadcast(
        resource_uri="device://dev-001/health",
        data={
            "status": "healthy",
            "cpu_usage": 25.5,
            "memory_usage": 60.2,
        },
        event_type="health_update",
    )
    
    # Wait for events to be processed
    try:
        await asyncio.wait_for(stream_task, timeout=2.0)
    except asyncio.TimeoutError:
        stream_task.cancel()
    
    # Verify events received
    assert len(events) >= 2
    
    # First event: connection
    assert events[0]["event"] == "connected"
    assert events[0]["data"]["subscription_id"] == subscription.subscription_id
    assert events[0]["data"]["resource_uri"] == "device://dev-001/health"
    
    # Second event: health update
    assert events[1]["event"] == "health_update"
    assert events[1]["data"]["status"] == "healthy"
    assert events[1]["data"]["cpu_usage"] == 25.5


@pytest.mark.asyncio
async def test_multiple_concurrent_subscriptions(sse_manager: SSEManager) -> None:
    """Test multiple clients subscribing to different resources concurrently."""
    
    # Create multiple subscriptions
    sub1 = await sse_manager.subscribe("client-1", "device://dev-001/health")
    sub2 = await sse_manager.subscribe("client-2", "device://dev-001/health")
    sub3 = await sse_manager.subscribe("client-3", "device://dev-002/health")
    
    # Collect events from all subscriptions
    events_1 = []
    events_2 = []
    events_3 = []
    
    async def collect_from_sub1() -> None:
        count = 0
        async for event in sse_manager.stream_events(sub1):
            events_1.append(event)
            count += 1
            if count >= 2:
                break
    
    async def collect_from_sub2() -> None:
        count = 0
        async for event in sse_manager.stream_events(sub2):
            events_2.append(event)
            count += 1
            if count >= 2:
                break
    
    async def collect_from_sub3() -> None:
        count = 0
        async for event in sse_manager.stream_events(sub3):
            events_3.append(event)
            count += 1
            if count >= 1:  # Only connection event
                break
    
    # Start all streams
    tasks = [
        asyncio.create_task(collect_from_sub1()),
        asyncio.create_task(collect_from_sub2()),
        asyncio.create_task(collect_from_sub3()),
    ]
    
    await asyncio.sleep(0.05)
    
    # Broadcast to dev-001 only
    await sse_manager.broadcast(
        resource_uri="device://dev-001/health",
        data={"status": "degraded"},
    )
    
    # Wait for all tasks
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2.0)
    except asyncio.TimeoutError:
        for task in tasks:
            task.cancel()
    
    # Verify: sub1 and sub2 got update, sub3 did not
    assert len(events_1) >= 2
    assert len(events_2) >= 2
    assert len(events_3) == 1  # Only connection event
    
    # Verify update events
    assert events_1[1]["data"]["status"] == "degraded"
    assert events_2[1]["data"]["status"] == "degraded"


@pytest.mark.asyncio
async def test_subscription_limit_enforcement(sse_manager: SSEManager) -> None:
    """Test max subscriptions per device limit is enforced."""
    
    # Settings has max 10 subscriptions per device
    # Create 10 subscriptions to dev-001
    for i in range(10):
        await sse_manager.subscribe(
            f"client-{i}",
            f"device://dev-001/resource-{i}",
        )
    
    assert sse_manager.get_subscription_count() == 10
    
    # 11th subscription should fail
    with pytest.raises(ValueError, match="Subscription limit exceeded"):
        await sse_manager.subscribe("client-11", "device://dev-001/another")
    
    # But subscription to different device should succeed
    sub = await sse_manager.subscribe("client-11", "device://dev-002/health")
    assert sub.resource_uri == "device://dev-002/health"


@pytest.mark.asyncio
async def test_client_disconnect_cleanup(sse_manager: SSEManager) -> None:
    """Test subscription cleanup on client disconnect."""
    
    subscription = await sse_manager.subscribe(
        "test-client",
        "device://dev-001/health",
    )
    
    assert sse_manager.get_subscription_count() == 1
    
    # Start streaming and close
    stream_gen = sse_manager.stream_events(subscription)
    
    # Get first event
    try:
        await stream_gen.__anext__()
    except StopAsyncIteration:
        pass
    
    # Close stream (simulates disconnect)
    try:
        await stream_gen.aclose()
    except Exception:
        pass
    
    await asyncio.sleep(0.1)
    
    # Subscription should be cleaned up
    assert sse_manager.get_subscription_count() == 0


@pytest.mark.asyncio
async def test_broadcast_debouncing(sse_manager: SSEManager) -> None:
    """Test that rapid updates are debounced within the interval."""
    
    subscription = await sse_manager.subscribe(
        "test-client",
        "device://dev-001/health",
    )
    
    events = []
    
    async def collect_events() -> None:
        count = 0
        async for event in sse_manager.stream_events(subscription):
            events.append(event)
            count += 1
            if count >= 2:  # connection + 1 update
                break
    
    stream_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.05)
    
    # Send 3 rapid updates
    await sse_manager.broadcast(
        "device://dev-001/health",
        {"value": 1},
    )
    await sse_manager.broadcast(
        "device://dev-001/health",
        {"value": 2},
    )
    await sse_manager.broadcast(
        "device://dev-001/health",
        {"value": 3},
    )
    
    # Wait for debounce
    try:
        await asyncio.wait_for(stream_task, timeout=2.0)
    except asyncio.TimeoutError:
        stream_task.cancel()
    
    # Should only receive 1 update (the last one)
    assert len(events) == 2  # connection + 1 update
    assert events[1]["data"]["value"] == 3


@pytest.mark.asyncio
async def test_http_sse_transport_with_manager(
    settings: Settings,
    mock_mcp_instance: MagicMock,
) -> None:
    """Test HTTPSSETransport integration with SSEManager."""
    
    transport = HTTPSSETransport(settings, mock_mcp_instance)
    
    # Verify SSE manager is initialized
    assert transport.sse_manager is not None
    assert isinstance(transport.sse_manager, SSEManager)
    assert transport.sse_manager.max_subscriptions_per_device == 10
    
    # Test subscription through manager
    sub = await transport.sse_manager.subscribe(
        "test-client",
        "device://dev-001/health",
    )
    
    assert sub.client_id == "test-client"
    assert sub.resource_uri == "device://dev-001/health"


@pytest.mark.asyncio
async def test_subscription_stats(sse_manager: SSEManager) -> None:
    """Test subscription statistics tracking."""
    
    # Initial stats
    stats = sse_manager.get_stats()
    assert stats["total_subscriptions"] == 0
    assert stats["total_resources"] == 0
    assert stats["total_clients"] == 0
    assert stats["total_broadcasts"] == 0
    
    # Add subscriptions
    await sse_manager.subscribe("client-1", "device://dev-001/health")
    await sse_manager.subscribe("client-1", "device://dev-001/config")
    await sse_manager.subscribe("client-2", "device://dev-002/health")
    
    # Broadcast some events
    await sse_manager.broadcast("device://dev-001/health", {"test": 1})
    await asyncio.sleep(0.15)  # Wait for debounce
    
    await sse_manager.broadcast("device://dev-002/health", {"test": 2})
    await asyncio.sleep(0.15)
    
    # Check stats
    stats = sse_manager.get_stats()
    assert stats["total_subscriptions"] == 3
    assert stats["total_resources"] == 3
    assert stats["total_clients"] == 2
    assert stats["total_broadcasts"] == 2
    assert stats["total_events_sent"] >= 2  # At least 2 events sent


@pytest.mark.asyncio
async def test_fleet_resource_subscription(sse_manager: SSEManager) -> None:
    """Test subscribing to fleet-wide resources (not device-specific)."""
    
    # Fleet resources don't have device limits
    sub = await sse_manager.subscribe(
        "test-client",
        "fleet://health-summary",
    )
    
    assert sub.resource_uri == "fleet://health-summary"
    
    # Broadcast to fleet resource
    events = []
    
    async def collect_events() -> None:
        count = 0
        async for event in sse_manager.stream_events(sub):
            events.append(event)
            count += 1
            if count >= 2:
                break
    
    stream_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.05)
    
    await sse_manager.broadcast(
        "fleet://health-summary",
        {"total_devices": 10, "healthy": 9, "degraded": 1},
    )
    
    try:
        await asyncio.wait_for(stream_task, timeout=1.0)
    except asyncio.TimeoutError:
        stream_task.cancel()
    
    assert len(events) >= 2
    assert events[1]["data"]["total_devices"] == 10
