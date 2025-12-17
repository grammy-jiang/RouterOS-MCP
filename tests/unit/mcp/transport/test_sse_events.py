"""Tests for SSE event emission helper."""

import asyncio

import pytest

from routeros_mcp.mcp.transport.sse_events import DeviceStateEmitter
from routeros_mcp.mcp.transport.sse_manager import SSEManager


@pytest.mark.asyncio
async def test_device_state_emitter_without_manager() -> None:
    """Test emitter works without SSE manager (no-op)."""
    emitter = DeviceStateEmitter(sse_manager=None)

    # Should not raise errors
    await emitter.emit_device_online("dev-001", {"ip": "192.168.1.1"})
    await emitter.emit_device_offline("dev-001", "timeout")
    await emitter.emit_health_check_complete("dev-001", {"status": "healthy"})
    await emitter.emit_config_change("dev-001", "dns", {"servers": ["8.8.8.8"]})
    await emitter.emit_plan_execution_complete("plan-001", {"success": True})


@pytest.mark.asyncio
async def test_emit_device_online() -> None:
    """Test emitting device online event."""
    manager = SSEManager(update_batch_interval_seconds=0.05)
    emitter = DeviceStateEmitter(sse_manager=manager)

    # Subscribe to device health
    sub = await manager.subscribe("client-1", "device://dev-001/health")

    # Collect events
    events = []

    async def collect_events() -> None:
        count = 0
        async for event in manager.stream_events(sub):
            events.append(event)
            count += 1
            if count >= 2:  # connection + device_online
                break

    stream_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)

    # Emit online event
    await emitter.emit_device_online(
        "dev-001",
        {"ip": "192.168.1.1", "version": "7.15"},
    )

    try:
        await asyncio.wait_for(stream_task, timeout=1.0)
    except TimeoutError:
        stream_task.cancel()

    assert len(events) >= 2
    assert events[0]["event"] == "connected"
    assert events[1]["event"] == "device_online"
    assert events[1]["data"]["device_id"] == "dev-001"
    assert events[1]["data"]["status"] == "online"
    assert events[1]["data"]["metadata"]["ip"] == "192.168.1.1"


@pytest.mark.asyncio
async def test_emit_device_offline() -> None:
    """Test emitting device offline event."""
    manager = SSEManager(update_batch_interval_seconds=0.05)
    emitter = DeviceStateEmitter(sse_manager=manager)

    sub = await manager.subscribe("client-1", "device://dev-001/health")

    events = []

    async def collect_events() -> None:
        count = 0
        async for event in manager.stream_events(sub):
            events.append(event)
            count += 1
            if count >= 2:
                break

    stream_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)

    await emitter.emit_device_offline("dev-001", "connection_timeout")

    try:
        await asyncio.wait_for(stream_task, timeout=1.0)
    except TimeoutError:
        stream_task.cancel()

    assert len(events) >= 2
    assert events[1]["event"] == "device_offline"
    assert events[1]["data"]["device_id"] == "dev-001"
    assert events[1]["data"]["status"] == "offline"
    assert events[1]["data"]["reason"] == "connection_timeout"


@pytest.mark.asyncio
async def test_emit_health_check_complete() -> None:
    """Test emitting health check complete event."""
    manager = SSEManager(update_batch_interval_seconds=0.05)
    emitter = DeviceStateEmitter(sse_manager=manager)

    sub = await manager.subscribe("client-1", "device://dev-001/health")

    events = []

    async def collect_events() -> None:
        count = 0
        async for event in manager.stream_events(sub):
            events.append(event)
            count += 1
            if count >= 2:
                break

    stream_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)

    await emitter.emit_health_check_complete(
        "dev-001",
        {
            "status": "healthy",
            "cpu_usage": 25.5,
            "memory_usage": 60.2,
            "uptime_seconds": 86400,
        },
    )

    try:
        await asyncio.wait_for(stream_task, timeout=1.0)
    except TimeoutError:
        stream_task.cancel()

    assert len(events) >= 2
    assert events[1]["event"] == "health_check"
    assert events[1]["data"]["status"] == "healthy"
    assert events[1]["data"]["cpu_usage"] == 25.5


@pytest.mark.asyncio
async def test_emit_config_change() -> None:
    """Test emitting config change event."""
    manager = SSEManager(update_batch_interval_seconds=0.05)
    emitter = DeviceStateEmitter(sse_manager=manager)

    # Subscribe to config resource
    sub = await manager.subscribe("client-1", "device://dev-001/config")

    events = []

    async def collect_events() -> None:
        count = 0
        async for event in manager.stream_events(sub):
            events.append(event)
            count += 1
            if count >= 2:
                break

    stream_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)

    await emitter.emit_config_change(
        "dev-001",
        "dns",
        {"servers": ["8.8.8.8", "8.8.4.4"]},
    )

    try:
        await asyncio.wait_for(stream_task, timeout=1.0)
    except TimeoutError:
        stream_task.cancel()

    assert len(events) >= 2
    assert events[1]["event"] == "config_change"
    assert events[1]["data"]["device_id"] == "dev-001"
    assert events[1]["data"]["change_type"] == "dns"
    assert events[1]["data"]["details"]["servers"] == ["8.8.8.8", "8.8.4.4"]


@pytest.mark.asyncio
async def test_emit_plan_execution_complete() -> None:
    """Test emitting plan execution complete event."""
    manager = SSEManager(update_batch_interval_seconds=0.05)
    emitter = DeviceStateEmitter(sse_manager=manager)

    # Subscribe to plan resource
    sub = await manager.subscribe("client-1", "plan://plan-001")

    events = []

    async def collect_events() -> None:
        count = 0
        async for event in manager.stream_events(sub):
            events.append(event)
            count += 1
            if count >= 2:
                break

    stream_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)

    await emitter.emit_plan_execution_complete(
        "plan-001",
        {
            "success": True,
            "devices_updated": 5,
            "duration_seconds": 12.5,
        },
    )

    try:
        await asyncio.wait_for(stream_task, timeout=1.0)
    except TimeoutError:
        stream_task.cancel()

    assert len(events) >= 2
    assert events[1]["event"] == "plan_execution_complete"
    assert events[1]["data"]["plan_id"] == "plan-001"
    assert events[1]["data"]["result"]["success"] is True
    assert events[1]["data"]["result"]["devices_updated"] == 5


@pytest.mark.asyncio
async def test_multiple_events_to_same_resource() -> None:
    """Test emitting multiple events to the same resource."""
    manager = SSEManager(update_batch_interval_seconds=0.05)
    emitter = DeviceStateEmitter(sse_manager=manager)

    sub = await manager.subscribe("client-1", "device://dev-001/health")

    events = []

    async def collect_events() -> None:
        count = 0
        async for event in manager.stream_events(sub):
            events.append(event)
            count += 1
            if count >= 4:  # connection + 3 events
                break

    stream_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)

    # Emit multiple events
    await emitter.emit_device_online("dev-001", {"ip": "192.168.1.1"})
    await asyncio.sleep(0.1)  # Wait for debounce

    await emitter.emit_health_check_complete("dev-001", {"status": "healthy", "cpu_usage": 30.0})
    await asyncio.sleep(0.1)

    await emitter.emit_device_offline("dev-001", "manual_shutdown")

    try:
        await asyncio.wait_for(stream_task, timeout=2.0)
    except TimeoutError:
        stream_task.cancel()

    assert len(events) >= 4
    assert events[0]["event"] == "connected"
    assert events[1]["event"] == "device_online"
    assert events[2]["event"] == "health_check"
    assert events[3]["event"] == "device_offline"
