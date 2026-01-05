# Streaming Tools Implementation Guide

## Overview

Phase 4 adds support for streaming progress updates from long-running MCP tools. This enables real-time feedback for operations like ping, traceroute, and bandwidth tests.

## How Streaming Works

### Transport Behavior

- **HTTP/SSE Transport**: Progress messages are sent as Server-Sent Events (SSE), allowing clients to receive real-time updates
- **STDIO Transport**: Progress messages are collected but not streamed; only the final result is returned (backward compatible)

### Protocol Details

Clients request streaming by including `stream_progress: true` in tool arguments:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "diagnostics/ping",
    "arguments": {
      "device_id": "dev-001",
      "target": "8.8.8.8",
      "count": 4,
      "stream_progress": true
    }
  },
  "id": "req-001"
}
```

## Implementing a Streaming Tool

### Basic Pattern

Convert your tool from returning a single result to yielding progress updates:

```python
from collections.abc import AsyncIterator
from typing import Any
from routeros_mcp.mcp.protocol.jsonrpc import create_progress_message, format_tool_result

@mcp.tool()
async def ping(
    device_id: str,
    target: str,
    count: int = 4,
    stream_progress: bool = False,  # Add streaming parameter
) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
    """Execute ping with optional progress streaming."""
    
    if not stream_progress:
        # Non-streaming: return final result immediately
        result = await diagnostics_service.ping(device_id, target, count)
        return format_tool_result(
            content=f"Ping complete: {result['packets_received']}/{result['packets_sent']} received",
            meta=result,
        )
    
    # Streaming: yield progress updates
    async def stream_ping_progress() -> AsyncIterator[dict[str, Any]]:
        replies_received = 0
        total_latency = 0.0
        
        for i in range(count):
            # Send progress update
            yield create_progress_message(
                message=f"Sending ping {i+1}/{count} to {target}...",
                percent=int((i / count) * 100),
            )
            
            # Perform actual ping
            reply = await diagnostics_service.ping_single(device_id, target)
            
            # Track statistics
            if reply['received']:
                replies_received += 1
                total_latency += reply['time_ms']
                
                # Send result progress
                yield create_progress_message(
                    message=f"Reply from {target}: {reply['time_ms']}ms",
                    percent=int(((i+1) / count) * 100),
                    data={"hop": i+1, "time_ms": reply['time_ms']},
                )
            else:
                yield create_progress_message(
                    message=f"No reply from {target}",
                    percent=int(((i+1) / count) * 100),
                    data={"hop": i+1, "timeout": True},
                )
        
        # Calculate final statistics
        avg_latency = total_latency / replies_received if replies_received > 0 else 0
        
        # Yield final result
        final_result = {
            "packets_sent": count,
            "packets_received": replies_received,
            "avg_latency_ms": avg_latency,
        }
        yield format_tool_result(
            content=f"Ping complete: {replies_received}/{count} received",
            meta=final_result,
        )
    
    return stream_ping_progress()
```

### Progress Message Format

Use `create_progress_message()` from `routeros_mcp.mcp.protocol.jsonrpc`:

```python
from routeros_mcp.mcp.protocol.jsonrpc import create_progress_message

# Simple progress message
progress = create_progress_message("Initializing connection...")

# Progress with percentage
progress = create_progress_message(
    message="Processing packet 5/10",
    percent=50,
)

# Progress with additional data
progress = create_progress_message(
    message="Hop 3: 15ms latency",
    percent=30,
    data={"hop": 3, "latency_ms": 15, "ip": "192.168.1.1"},
)
```

**Progress message structure:**
```python
{
    "type": "progress",
    "message": str,        # Human-readable message
    "percent": int,        # Optional: 0-100
    "data": dict,          # Optional: Additional structured data
}
```

### SSE Event Format (HTTP Transport)

Progress events are sent as:

```
event: progress
data: {"type":"progress","message":"Reply from 8.8.8.8: 25ms","percent":25}

event: progress
data: {"type":"progress","message":"Reply from 8.8.8.8: 30ms","percent":50}

event: result
data: {"jsonrpc":"2.0","id":"req-001","result":{"content":[...],"isError":false}}
```

## Best Practices

### 1. Make Streaming Optional

Always provide a `stream_progress: bool = False` parameter so tools work in both modes:

```python
async def my_tool(
    device_id: str,
    stream_progress: bool = False,
) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
    if not stream_progress:
        # Fast path: return immediately
        return format_tool_result(...)
    
    # Streaming path: yield progress
    return stream_with_progress()
```

### 2. Yield Progress at Meaningful Intervals

Don't flood with updates. Send progress at natural checkpoints:

```python
# ✅ Good: Progress every second or logical step
for i in range(ping_count):
    yield create_progress_message(f"Ping {i+1}/{ping_count}")
    await ping_once()

# ❌ Bad: Progress for every millisecond
for ms in range(10000):
    yield create_progress_message(f"Elapsed: {ms}ms")
```

### 3. Always Yield a Final Result

The last yielded item should be a formatted tool result:

```python
async def stream_operation():
    # Progress updates
    yield create_progress_message("Starting...")
    yield create_progress_message("Processing...")
    
    # Final result (REQUIRED)
    yield format_tool_result(
        content="Operation complete",
        meta={"status": "success"},
    )
```

### 4. Handle Errors Gracefully

Errors in streaming tools should yield error results:

```python
async def stream_with_error_handling():
    try:
        for i in range(10):
            yield create_progress_message(f"Step {i+1}")
            await perform_step(i)
        
        yield format_tool_result("Success", meta={"steps": 10})
    
    except Exception as e:
        logger.error(f"Tool failed: {e}", exc_info=True)
        yield format_tool_result(
            content=f"Error: {str(e)}",
            is_error=True,
            meta={"error_type": type(e).__name__},
        )
```

### 5. Document Streaming Capability

Update your tool's docstring to indicate streaming support:

```python
@mcp.tool()
async def bandwidth_test(
    device_id: str,
    target_server: str,
    duration_seconds: int = 10,
    stream_progress: bool = False,
) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
    """Run bandwidth test with optional progress streaming.
    
    Args:
        device_id: Device to run test on
        target_server: Server to test against
        duration_seconds: Test duration (1-60 seconds)
        stream_progress: Enable real-time progress updates (HTTP transport only)
    
    Returns:
        Bandwidth test results with throughput statistics
        
    Streaming:
        When stream_progress=True, yields progress updates every second
        with current throughput, bytes transferred, and time remaining.
    """
```

## Testing Streaming Tools

### Unit Tests

Test both streaming and non-streaming modes:

```python
import pytest

@pytest.mark.asyncio
async def test_ping_non_streaming():
    """Test ping without streaming."""
    result = await ping(
        device_id="dev-001",
        target="8.8.8.8",
        count=4,
        stream_progress=False,
    )
    
    assert isinstance(result, dict)
    assert "content" in result
    assert "isError" in result

@pytest.mark.asyncio
async def test_ping_streaming():
    """Test ping with streaming."""
    generator = await ping(
        device_id="dev-001",
        target="8.8.8.8",
        count=4,
        stream_progress=True,
    )
    
    events = []
    async for event in generator:
        events.append(event)
    
    # Verify progress events
    progress_events = [e for e in events if e.get("type") == "progress"]
    assert len(progress_events) >= 4
    
    # Verify final result
    final_result = events[-1]
    assert "content" in final_result
```

### Manual Testing with curl

Test HTTP/SSE streaming:

```bash
curl -N http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "diagnostics/ping",
      "arguments": {
        "device_id": "dev-001",
        "target": "8.8.8.8",
        "count": 4,
        "stream_progress": true
      }
    },
    "id": 1
  }'
```

Expected output:
```
event: progress
data: {"type":"progress","message":"Sending ping 1/4...","percent":0}

event: progress
data: {"type":"progress","message":"Reply from 8.8.8.8: 25ms","percent":25}

event: progress
data: {"type":"progress","message":"Sending ping 2/4...","percent":25}

event: progress
data: {"type":"progress","message":"Reply from 8.8.8.8: 30ms","percent":50}

event: result
data: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"Ping complete"}]}}
```

## Migration Guide

### Converting Existing Tools

**Before (non-streaming):**
```python
@mcp.tool()
async def my_tool(device_id: str) -> dict[str, Any]:
    result = await service.do_work(device_id)
    return format_tool_result("Done", meta=result)
```

**After (streaming-capable):**
```python
@mcp.tool()
async def my_tool(
    device_id: str,
    stream_progress: bool = False,
) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
    if not stream_progress:
        # Keep existing fast path
        result = await service.do_work(device_id)
        return format_tool_result("Done", meta=result)
    
    # Add streaming path
    async def stream_work():
        yield create_progress_message("Starting...")
        result = await service.do_work(device_id)
        yield create_progress_message("Processing...")
        # ... more progress ...
        yield format_tool_result("Done", meta=result)
    
    return stream_work()
```

## See Also

- `routeros_mcp/mcp/protocol/jsonrpc.py` - Protocol helper functions
- `routeros_mcp/mcp/transport/http_sse.py` - HTTP/SSE streaming implementation
- `tests/unit/test_jsonrpc_protocol.py` - Protocol function tests
- `tests/unit/mcp/transport/test_http_sse.py` - Streaming transport tests
