"""Tests for HTTP/SSE transport implementation."""

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sse_starlette import EventSourceResponse
from starlette.requests import Request

from routeros_mcp.config import Settings
from routeros_mcp.mcp.errors import InvalidRequestError
from routeros_mcp.mcp.transport.http_sse import CorrelationIDMiddleware, HTTPSSETransport


@pytest.mark.asyncio
async def test_http_sse_transport_initialization() -> None:
    """Test HTTPSSETransport initializes correctly."""
    settings = Settings(
        mcp_transport="http",
        mcp_http_host="0.0.0.0",
        mcp_http_port=8080,
        mcp_http_base_path="/mcp",
    )
    mock_mcp = MagicMock()

    transport = HTTPSSETransport(settings, mock_mcp)

    assert transport.settings == settings
    assert transport.mcp_instance == mock_mcp


@pytest.mark.asyncio
async def test_http_sse_transport_run_success() -> None:
    """Test HTTPSSETransport.run() calls FastMCP's run_http_async."""
    settings = Settings(
        mcp_transport="http",
        mcp_http_host="127.0.0.1",
        mcp_http_port=9090,
        mcp_http_base_path="/api/mcp",
        log_level="DEBUG",
        environment="lab",
    )

    # Create mock with async run_http_async method
    mock_mcp = MagicMock()
    mock_mcp.run_http_async = AsyncMock()

    transport = HTTPSSETransport(settings, mock_mcp)
    await transport.run()

    # Verify run_http_async was called with correct parameters
    # Now includes middleware parameter
    call_kwargs = mock_mcp.run_http_async.call_args.kwargs
    assert call_kwargs["transport"] == "sse"
    assert call_kwargs["host"] == "127.0.0.1"
    assert call_kwargs["port"] == 9090
    assert call_kwargs["path"] == "/api/mcp"
    assert call_kwargs["log_level"] == "debug"
    assert call_kwargs["show_banner"] is True
    assert "middleware" in call_kwargs


@pytest.mark.asyncio
async def test_http_sse_transport_run_missing_method() -> None:
    """Test HTTPSSETransport.run() raises error if run_http_async is missing."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock(spec=[])  # Empty spec, no run_http_async

    transport = HTTPSSETransport(settings, mock_mcp)

    with pytest.raises(RuntimeError, match="does not support HTTP transport"):
        await transport.run()


@pytest.mark.asyncio
async def test_http_sse_transport_stop() -> None:
    """Test HTTPSSETransport.stop() completes successfully."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    transport = HTTPSSETransport(settings, mock_mcp)
    await transport.stop()

    # Stop should complete without error (cleanup handled by FastMCP)


@pytest.mark.asyncio
async def test_http_sse_transport_uses_config_values() -> None:
    """Test HTTPSSETransport respects all configuration values."""
    settings = Settings(
        mcp_transport="http",
        mcp_http_host="192.168.1.100",
        mcp_http_port=3000,
        mcp_http_base_path="/custom/path",
        log_level="WARNING",
    )

    mock_mcp = MagicMock()
    mock_mcp.run_http_async = AsyncMock()

    transport = HTTPSSETransport(settings, mock_mcp)
    await transport.run()

    # Verify all config values are passed correctly
    call_kwargs = mock_mcp.run_http_async.call_args.kwargs
    assert call_kwargs["host"] == "192.168.1.100"
    assert call_kwargs["port"] == 3000
    assert call_kwargs["path"] == "/custom/path"
    assert call_kwargs["log_level"] == "warning"
    assert call_kwargs["transport"] == "sse"


@pytest.mark.asyncio
async def test_http_sse_transport_run_with_middleware() -> None:
    """Test HTTPSSETransport.run() includes correlation ID middleware."""
    settings = Settings(
        mcp_transport="http",
        mcp_http_host="127.0.0.1",
        mcp_http_port=9090,
        mcp_http_base_path="/api/mcp",
        log_level="DEBUG",
        environment="lab",
    )

    # Create mock with async run_http_async method
    mock_mcp = MagicMock()
    mock_mcp.run_http_async = AsyncMock()

    transport = HTTPSSETransport(settings, mock_mcp)
    await transport.run()

    # Verify run_http_async was called with middleware
    call_kwargs = mock_mcp.run_http_async.call_args.kwargs
    assert "middleware" in call_kwargs
    assert len(call_kwargs["middleware"]) > 0
    # Verify correlation ID middleware is included
    middleware_list = call_kwargs["middleware"]
    assert any(
        getattr(m, "cls", None) and getattr(m.cls, "__name__", "") == "CorrelationIDMiddleware"
        for m in middleware_list
    )


@pytest.mark.asyncio
async def test_handle_request_success() -> None:
    """Test handle_request processes valid JSON-RPC request successfully."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP tool result
    from types import SimpleNamespace

    mock_content = SimpleNamespace(
        type="text", text="Tool result", model_dump=lambda **kwargs: {"text": "Tool result"}
    )
    mock_tool_result = SimpleNamespace(content=[mock_content], isError=False)
    mock_mcp._call_tool_mcp = AsyncMock(return_value=mock_tool_result)

    transport = HTTPSSETransport(settings, mock_mcp)

    # Mock request
    mock_request = MagicMock(spec=Request)
    mock_request.method = "POST"
    mock_request.url.path = "/mcp/rpc"
    mock_request.json = AsyncMock(
        return_value={
            "jsonrpc": "2.0",
            "id": "req-123",
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"message": "test"}},
        }
    )
    mock_request.state.user = None

    # Call handle_request
    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-123"):
        response = await transport.handle_request(mock_request)

    # Verify response structure
    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers
    assert response.headers["X-Correlation-ID"] == "corr-123"

    # Parse response body
    assert isinstance(response.body, bytes)
    body = json.loads(response.body.decode())
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "req-123"
    assert "result" in body
    assert "content" in body["result"]


@pytest.mark.asyncio
async def test_handle_request_invalid_json() -> None:
    """Test handle_request returns parse error for invalid JSON."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
    transport = HTTPSSETransport(settings, mock_mcp)

    # Mock request with invalid JSON
    mock_request = MagicMock(spec=Request)
    mock_request.method = "POST"
    mock_request.url.path = "/mcp/rpc"
    mock_request.json = AsyncMock(side_effect=json.JSONDecodeError("msg", "doc", 0))

    # Call handle_request
    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-456"):
        response = await transport.handle_request(mock_request)

    # Verify error response
    assert response.status_code == 400
    assert isinstance(response.body, bytes)
    body = json.loads(response.body.decode())
    assert body["jsonrpc"] == "2.0"
    assert "error" in body
    assert body["error"]["code"] == -32700  # Parse error


@pytest.mark.asyncio
async def test_handle_request_invalid_jsonrpc() -> None:
    """Test handle_request validates JSON-RPC structure."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
    transport = HTTPSSETransport(settings, mock_mcp)

    # Mock request with invalid JSON-RPC (missing method)
    mock_request = MagicMock(spec=Request)
    mock_request.method = "POST"
    mock_request.url.path = "/mcp/rpc"
    mock_request.json = AsyncMock(
        return_value={
            "jsonrpc": "2.0",
            "id": "req-789",
            # Missing "method" field
        }
    )
    mock_request.state.user = None

    # Call handle_request
    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-789"):
        response = await transport.handle_request(mock_request)

    # Verify error response
    assert response.status_code == 400
    assert isinstance(response.body, bytes)
    body = json.loads(response.body.decode())
    assert body["jsonrpc"] == "2.0"
    assert "error" in body
    assert body["error"]["code"] == -32600  # Invalid request


@pytest.mark.asyncio
async def test_handle_request_with_user_context() -> None:
    """Test handle_request propagates user context from auth middleware."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP tool result
    from types import SimpleNamespace

    mock_content = SimpleNamespace(
        type="text", text="Result", model_dump=lambda **kwargs: {"text": "Result"}
    )
    mock_tool_result = SimpleNamespace(content=[mock_content], isError=False)
    mock_mcp._call_tool_mcp = AsyncMock(return_value=mock_tool_result)

    transport = HTTPSSETransport(settings, mock_mcp)

    # Mock request with user context
    mock_request = MagicMock(spec=Request)
    mock_request.method = "POST"
    mock_request.url.path = "/mcp/rpc"
    mock_request.json = AsyncMock(
        return_value={
            "jsonrpc": "2.0",
            "id": "req-user-123",
            "method": "tools/call",
            "params": {"name": "test", "arguments": {}},
        }
    )
    mock_request.state.user = {"user_id": "user-123", "roles": ["admin"]}

    # Call handle_request
    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-user"):
        response = await transport.handle_request(mock_request)

    # Verify response
    assert response.status_code == 200
    assert isinstance(response.body, bytes)
    body = json.loads(response.body.decode())
    assert "result" in body
    assert "content" in body["result"]

    # Verify user context was passed to FastMCP
    call_args = mock_mcp._call_tool_mcp.call_args
    assert call_args is not None
    arguments = call_args[0][1]  # Second positional argument
    assert "_user" in arguments
    assert arguments["_user"]["user_id"] == "user-123"


@pytest.mark.asyncio
async def test_handle_request_correlation_id_propagation() -> None:
    """Test handle_request propagates correlation ID through request/response."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
    transport = HTTPSSETransport(settings, mock_mcp)

    mock_request = MagicMock(spec=Request)
    mock_request.method = "POST"
    mock_request.url.path = "/mcp/rpc"
    mock_request.json = AsyncMock(
        return_value={
            "jsonrpc": "2.0",
            "id": "req-corr",
            "method": "test",
            "params": {},
        }
    )
    mock_request.state.user = None

    test_correlation_id = "test-correlation-id-12345"

    # Call handle_request with specific correlation ID
    with patch(
        "routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value=test_correlation_id
    ):
        response = await transport.handle_request(mock_request)

    # Verify correlation ID in response headers
    assert response.headers["X-Correlation-ID"] == test_correlation_id


@pytest.mark.asyncio
async def test_process_mcp_request_with_user_context() -> None:
    """Test _process_mcp_request adds user context to params."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP tool result
    from types import SimpleNamespace

    mock_content = SimpleNamespace(
        type="text", text="Result", model_dump=lambda **kwargs: {"text": "Result"}
    )
    mock_tool_result = SimpleNamespace(content=[mock_content], isError=False)
    mock_mcp._call_tool_mcp = AsyncMock(return_value=mock_tool_result)

    transport = HTTPSSETransport(settings, mock_mcp)

    request = {
        "jsonrpc": "2.0",
        "id": "test-123",
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {}},
    }
    user_context = {"user_id": "user-456", "email": "test@example.com"}

    # Call _process_mcp_request
    response = await transport._process_mcp_request(request, user_context=user_context)

    # Verify response structure
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-123"
    assert "result" in response
    assert "content" in response["result"]

    # Verify user context was passed to FastMCP
    call_args = mock_mcp._call_tool_mcp.call_args
    assert call_args is not None
    arguments = call_args[0][1]  # Second positional argument
    assert "_user" in arguments
    assert arguments["_user"] == user_context


@pytest.mark.asyncio
async def test_process_mcp_request_without_user_context() -> None:
    """Test _process_mcp_request works without user context."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP tools list result
    from types import SimpleNamespace

    mock_tool = SimpleNamespace(
        name="echo", description="Echo tool", inputSchema={"type": "object"}
    )
    mock_mcp._list_tools_mcp = AsyncMock(return_value=[mock_tool])

    transport = HTTPSSETransport(settings, mock_mcp)

    request = {
        "jsonrpc": "2.0",
        "id": "test-no-user",
        "method": "tools/list",
        "params": {},
    }

    # Call _process_mcp_request without user context
    response = await transport._process_mcp_request(request, user_context=None)

    # Verify response structure
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-no-user"
    assert "result" in response
    assert "tools" in response["result"]
    assert len(response["result"]["tools"]) == 1


@pytest.mark.asyncio
async def test_default_settings() -> None:
    """Test HTTPSSETransport works with default settings."""
    settings = Settings()  # All defaults
    assert settings.mcp_transport == "stdio"  # Default is stdio

    # Override for HTTP
    settings = Settings(mcp_transport="http")

    mock_mcp = MagicMock()
    mock_mcp.run_http_async = AsyncMock()

    transport = HTTPSSETransport(settings, mock_mcp)
    await transport.run()

    # Verify defaults are used
    call_kwargs = mock_mcp.run_http_async.call_args.kwargs
    assert call_kwargs["host"] == "127.0.0.1"  # Default from config
    assert call_kwargs["port"] == 8080  # Default from config
    assert call_kwargs["path"] == "/mcp"  # Default from config


@pytest.mark.asyncio
async def test_correlation_id_middleware_adds_header_from_request() -> None:
    """CorrelationIDMiddleware should use incoming header and attach it to response."""

    messages: list[dict] = []

    async def app(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = CorrelationIDMiddleware(app)

    scope = {
        "type": "http",
        "headers": [(b"x-correlation-id", b"corr-abc")],
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": b""}

    async def send(message: dict) -> None:
        messages.append(message)

    with patch("routeros_mcp.mcp.transport.http_sse.set_correlation_id") as set_id:
        await middleware(scope, receive, send)

    assert messages and messages[0]["type"] == "http.response.start"
    headers = dict(messages[0].get("headers", []))
    assert headers[b"x-correlation-id"] == b"corr-abc"
    set_id.assert_called_once_with("corr-abc")


@pytest.mark.asyncio
async def test_correlation_id_middleware_generates_when_missing() -> None:
    """CorrelationIDMiddleware should generate correlation id when not provided."""

    messages: list[dict] = []

    async def app(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = CorrelationIDMiddleware(app)
    scope = {"type": "http", "headers": []}

    async def receive() -> dict:
        return {"type": "http.request", "body": b""}

    async def send(message: dict) -> None:
        messages.append(message)

    with (
        patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-gen"),
        patch("routeros_mcp.mcp.transport.http_sse.set_correlation_id") as set_id,
    ):
        await middleware(scope, receive, send)

    headers = dict(messages[0].get("headers", []))
    assert headers[b"x-correlation-id"] == b"corr-gen"
    set_id.assert_called_once_with("corr-gen")


@pytest.mark.asyncio
async def test_http_sse_transport_run_with_oidc_adds_auth_middleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When OIDC is enabled, the transport should add AuthMiddleware with exempt paths."""

    settings = Settings(
        mcp_transport="http",
        mcp_http_host="127.0.0.1",
        mcp_http_port=9090,
        mcp_http_base_path="/api/mcp",
        log_level="INFO",
        oidc_enabled=True,
        oidc_provider_url="https://example.invalid",
        oidc_client_id="client",
        oidc_audience="aud",
        oidc_skip_verification=True,
    )

    class _StubAuthMiddleware:
        pass

    class _StubOIDCValidator:
        def __init__(self, **_kwargs) -> None:
            return None

    import routeros_mcp.mcp.transport.auth_middleware as auth_mod
    import routeros_mcp.security.oidc as oidc_mod

    monkeypatch.setattr(auth_mod, "AuthMiddleware", _StubAuthMiddleware)
    monkeypatch.setattr(oidc_mod, "OIDCValidator", _StubOIDCValidator)

    mock_mcp = MagicMock()
    mock_mcp.run_http_async = AsyncMock()

    transport = HTTPSSETransport(settings, mock_mcp)
    await transport.run()

    middleware_list = mock_mcp.run_http_async.call_args.kwargs["middleware"]
    assert any(getattr(m, "cls", None) is _StubAuthMiddleware for m in middleware_list)

    auth_entry = next(m for m in middleware_list if getattr(m, "cls", None) is _StubAuthMiddleware)
    exempt_paths = auth_entry.kwargs.get("exempt_paths", [])
    assert "/health" in exempt_paths
    assert "/health/" in exempt_paths
    assert "/api/mcp/health" in exempt_paths
    assert "/api/mcp/health/" in exempt_paths


@pytest.mark.asyncio
async def test_handle_request_when_process_raises_mcp_error_returns_jsonrpc_error() -> None:
    settings = Settings(mcp_transport="http")
    transport = HTTPSSETransport(settings, MagicMock())

    mock_request = MagicMock(spec=Request)
    mock_request.method = "POST"
    mock_request.url.path = "/mcp/rpc"
    mock_request.json = AsyncMock(
        return_value={"jsonrpc": "2.0", "id": "req-err", "method": "tools/call", "params": {}}
    )
    mock_request.state.user = None

    transport._process_mcp_request = AsyncMock(side_effect=InvalidRequestError("bad"))

    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-err"):
        response = await transport.handle_request(mock_request)

    assert response.status_code == 500
    body = json.loads(response.body.decode())
    assert body["id"] == "req-err"
    assert body["error"]["code"] == InvalidRequestError.code


@pytest.mark.asyncio
async def test_handle_request_when_process_raises_unexpected_error_maps_to_internal_error() -> None:
    settings = Settings(mcp_transport="http")
    transport = HTTPSSETransport(settings, MagicMock())

    mock_request = MagicMock(spec=Request)
    mock_request.method = "POST"
    mock_request.url.path = "/mcp/rpc"
    mock_request.json = AsyncMock(
        return_value={"jsonrpc": "2.0", "id": "req-boom", "method": "tools/call", "params": {}}
    )
    mock_request.state.user = None

    transport._process_mcp_request = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-boom"):
        response = await transport.handle_request(mock_request)

    assert response.status_code == 500
    body = json.loads(response.body.decode())
    assert body["id"] == "req-boom"
    assert body["error"]["code"] == -32603


@pytest.mark.asyncio
async def test_process_mcp_request_requires_id() -> None:
    settings = Settings(mcp_transport="http")
    transport = HTTPSSETransport(settings, MagicMock())

    request = {"jsonrpc": "2.0", "method": "tools/list", "params": {}}

    with pytest.raises(ValueError, match="Request ID is required"):
        await transport._process_mcp_request(request)


@pytest.mark.asyncio
async def test_handle_subscribe_missing_resource_uri_returns_400() -> None:
    settings = Settings(mcp_transport="http")
    transport = HTTPSSETransport(settings, MagicMock())

    mock_request = MagicMock(spec=Request)
    mock_request.json = AsyncMock(return_value={})
    mock_request.state.user = None

    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-sub"):
        response = await transport.handle_subscribe(mock_request)

    assert response.status_code == 400
    body = json.loads(response.body.decode())
    assert body["code"] == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_handle_subscribe_subscription_limit_returns_429() -> None:
    settings = Settings(mcp_transport="http")
    transport = HTTPSSETransport(settings, MagicMock())

    mock_request = MagicMock(spec=Request)
    mock_request.json = AsyncMock(return_value={"resource_uri": "device://dev-1/health"})
    mock_request.state.user = {"sub": "user-1"}

    transport.sse_manager.subscribe = AsyncMock(side_effect=ValueError("Subscription limit exceeded"))

    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-429"):
        response = await transport.handle_subscribe(mock_request)

    assert response.status_code == 429
    body = json.loads(response.body.decode())
    assert body["code"] == "SUBSCRIPTION_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_handle_subscribe_success_returns_event_source_response() -> None:
    settings = Settings(mcp_transport="http")
    transport = HTTPSSETransport(settings, MagicMock())

    mock_request = MagicMock(spec=Request)
    mock_request.json = AsyncMock(return_value={"resource_uri": "device://dev-1/health"})
    mock_request.state.user = None

    subscription = MagicMock()
    subscription.subscription_id = "sub-1"
    subscription.resource_uri = "device://dev-1/health"

    transport.sse_manager.subscribe = AsyncMock(return_value=subscription)

    async def _stream_events(_sub) -> AsyncIterator[dict]:
        yield {"event": "connected", "data": {"subscription_id": "sub-1"}}

    transport.sse_manager.stream_events = _stream_events

    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-sse"):
        response = await transport.handle_subscribe(mock_request)

    assert isinstance(response, EventSourceResponse)
    assert response.headers.get("X-Correlation-ID") == "corr-sse"
    assert response.headers.get("Cache-Control") == "no-cache"


@pytest.mark.asyncio
async def test_subscription_route_registered_and_invokes_handler() -> None:
    """SSE subscription handler should be exposed via FastMCP custom_route."""

    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
    mock_mcp.run_http_async = AsyncMock()

    registration: dict[str, object] = {}

    def _custom_route(path, methods=None, name=None, include_in_schema=True):  # type: ignore[override] # noqa: ANN001
        def decorator(fn):
            registration["path"] = path
            registration["methods"] = methods
            registration["handler"] = fn
            return fn

        return decorator

    mock_mcp.custom_route = _custom_route

    transport = HTTPSSETransport(settings, mock_mcp)

    assert registration["path"] == "/mcp/subscribe"
    assert registration["methods"] == ["POST"]

    handler = registration["handler"]

    request = MagicMock(spec=Request)
    request.json = AsyncMock(return_value={"resource_uri": "device://dev-001/health"})
    request.state = SimpleNamespace(user=None)

    # Mock sse_manager methods that handle_subscribe uses
    subscription = MagicMock()
    subscription.subscription_id = "sub-test"
    subscription.resource_uri = "device://dev-001/health"

    transport.sse_manager.subscribe = AsyncMock(return_value=subscription)

    async def _stream_events(_sub) -> AsyncIterator[dict]:
        yield {"event": "connected", "data": {"subscription_id": "sub-test"}}

    transport.sse_manager.stream_events = _stream_events

    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-sub"):
        response = await handler(request)

    assert isinstance(response, EventSourceResponse)


@pytest.mark.asyncio
async def test_subscription_route_fallback_when_custom_route_unavailable() -> None:
    """SSE subscription should log warning when FastMCP lacks custom_route support."""

    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
    mock_mcp.run_http_async = AsyncMock()

    # Mock MCP instance where custom_route is not callable / effectively unavailable
    mock_mcp.custom_route = None

    with patch("routeros_mcp.mcp.transport.http_sse.logger") as mock_logger:
        HTTPSSETransport(settings, mock_mcp)

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        call = mock_logger.warning.call_args
        message = call.args[0]
        assert "does not support custom routes" in message
        assert "SSE subscriptions unavailable" in message


# ====================================================================================
# NEW TESTS FOR _process_mcp_request() INTEGRATION WITH FASTMCP
# ====================================================================================


@pytest.mark.asyncio
async def test_process_mcp_request_tools_call_success() -> None:
    """Test _process_mcp_request routes tools/call to FastMCP successfully."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP tool execution result
    from types import SimpleNamespace

    mock_content = SimpleNamespace(
        type="text", text="Tool result", model_dump=lambda **kwargs: {"text": "Tool result"}
    )
    mock_tool_result = SimpleNamespace(content=[mock_content], isError=False)

    mock_mcp._call_tool_mcp = AsyncMock(return_value=mock_tool_result)

    transport = HTTPSSETransport(settings, mock_mcp)

    request = {
        "jsonrpc": "2.0",
        "id": "test-123",
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"message": "test"}},
    }

    response = await transport._process_mcp_request(request)

    # Verify response structure
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-123"
    assert "result" in response
    assert "content" in response["result"]
    assert len(response["result"]["content"]) == 1
    assert response["result"]["content"][0]["type"] == "text"
    assert response["result"]["content"][0]["text"] == "Tool result"

    # Verify FastMCP was called correctly
    mock_mcp._call_tool_mcp.assert_called_once_with("echo", {"message": "test"})


@pytest.mark.asyncio
async def test_process_mcp_request_tools_call_missing_name() -> None:
    """Test _process_mcp_request returns error for tools/call without name."""
    from routeros_mcp.mcp.errors import InvalidParamsError

    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
    transport = HTTPSSETransport(settings, mock_mcp)

    request = {
        "jsonrpc": "2.0",
        "id": "test-456",
        "method": "tools/call",
        "params": {"arguments": {"message": "test"}},  # Missing 'name'
    }

    with pytest.raises(InvalidParamsError) as exc_info:
        await transport._process_mcp_request(request)

    assert "name" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_process_mcp_request_tools_list_success() -> None:
    """Test _process_mcp_request routes tools/list to FastMCP successfully."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP tools list result
    from types import SimpleNamespace

    mock_tool = SimpleNamespace(
        name="echo", description="Echo back a message", inputSchema={"type": "object"}
    )
    mock_mcp._list_tools_mcp = AsyncMock(return_value=[mock_tool])

    transport = HTTPSSETransport(settings, mock_mcp)

    request = {"jsonrpc": "2.0", "id": "test-789", "method": "tools/list", "params": {}}

    response = await transport._process_mcp_request(request)

    # Verify response structure
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-789"
    assert "result" in response
    assert "tools" in response["result"]
    assert len(response["result"]["tools"]) == 1
    assert response["result"]["tools"][0]["name"] == "echo"
    assert response["result"]["tools"][0]["description"] == "Echo back a message"

    # Verify FastMCP was called
    mock_mcp._list_tools_mcp.assert_called_once()


@pytest.mark.asyncio
async def test_process_mcp_request_resources_read_success() -> None:
    """Test _process_mcp_request routes resources/read to FastMCP successfully."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP resource read result
    from types import SimpleNamespace

    mock_content = SimpleNamespace(
        uri="device://dev-001/health", mimeType="application/json", text='{"status": "ok"}', blob=None
    )
    mock_mcp._read_resource_mcp = AsyncMock(return_value=[mock_content])

    transport = HTTPSSETransport(settings, mock_mcp)

    request = {
        "jsonrpc": "2.0",
        "id": "test-res-123",
        "method": "resources/read",
        "params": {"uri": "device://dev-001/health"},
    }

    response = await transport._process_mcp_request(request)

    # Verify response structure
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-res-123"
    assert "result" in response
    assert "contents" in response["result"]
    assert len(response["result"]["contents"]) == 1
    assert response["result"]["contents"][0]["uri"] == "device://dev-001/health"
    assert response["result"]["contents"][0]["text"] == '{"status": "ok"}'

    # Verify FastMCP was called correctly
    mock_mcp._read_resource_mcp.assert_called_once_with("device://dev-001/health")


@pytest.mark.asyncio
async def test_process_mcp_request_resources_read_missing_uri() -> None:
    """Test _process_mcp_request returns error for resources/read without uri."""
    from routeros_mcp.mcp.errors import InvalidParamsError

    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
    transport = HTTPSSETransport(settings, mock_mcp)

    request = {
        "jsonrpc": "2.0",
        "id": "test-res-456",
        "method": "resources/read",
        "params": {},  # Missing 'uri'
    }

    with pytest.raises(InvalidParamsError) as exc_info:
        await transport._process_mcp_request(request)

    assert "uri" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_process_mcp_request_resources_list_success() -> None:
    """Test _process_mcp_request routes resources/list to FastMCP successfully."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP resources list result
    from types import SimpleNamespace

    mock_resource = SimpleNamespace(
        uri="device://dev-001/health",
        name="Device Health",
        description="Device health status",
        mimeType="application/json",
    )
    mock_mcp._list_resources_mcp = AsyncMock(return_value=[mock_resource])

    transport = HTTPSSETransport(settings, mock_mcp)

    request = {"jsonrpc": "2.0", "id": "test-res-list", "method": "resources/list", "params": {}}

    response = await transport._process_mcp_request(request)

    # Verify response structure
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-res-list"
    assert "result" in response
    assert "resources" in response["result"]
    assert len(response["result"]["resources"]) == 1
    assert response["result"]["resources"][0]["uri"] == "device://dev-001/health"
    assert response["result"]["resources"][0]["name"] == "Device Health"

    # Verify FastMCP was called
    mock_mcp._list_resources_mcp.assert_called_once()


@pytest.mark.asyncio
async def test_process_mcp_request_prompts_get_success() -> None:
    """Test _process_mcp_request routes prompts/get to FastMCP successfully."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP prompt result
    from types import SimpleNamespace

    mock_message_content = SimpleNamespace(type="text", text="Prompt text")
    mock_message = SimpleNamespace(role="user", content=mock_message_content)
    mock_prompt_result = SimpleNamespace(description="Test prompt", messages=[mock_message])
    mock_mcp._get_prompt_mcp = AsyncMock(return_value=mock_prompt_result)

    transport = HTTPSSETransport(settings, mock_mcp)

    request = {
        "jsonrpc": "2.0",
        "id": "test-prompt-123",
        "method": "prompts/get",
        "params": {"name": "test-prompt", "arguments": {"key": "value"}},
    }

    response = await transport._process_mcp_request(request)

    # Verify response structure
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-prompt-123"
    assert "result" in response
    assert response["result"]["description"] == "Test prompt"
    assert len(response["result"]["messages"]) == 1
    assert response["result"]["messages"][0]["role"] == "user"

    # Verify FastMCP was called correctly
    mock_mcp._get_prompt_mcp.assert_called_once_with("test-prompt", {"key": "value"})


@pytest.mark.asyncio
async def test_process_mcp_request_prompts_get_missing_name() -> None:
    """Test _process_mcp_request returns error for prompts/get without name."""
    from routeros_mcp.mcp.errors import InvalidParamsError

    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
    transport = HTTPSSETransport(settings, mock_mcp)

    request = {
        "jsonrpc": "2.0",
        "id": "test-prompt-456",
        "method": "prompts/get",
        "params": {"arguments": {}},  # Missing 'name'
    }

    with pytest.raises(InvalidParamsError) as exc_info:
        await transport._process_mcp_request(request)

    assert "name" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_process_mcp_request_prompts_list_success() -> None:
    """Test _process_mcp_request routes prompts/list to FastMCP successfully."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP prompts list result
    from types import SimpleNamespace

    mock_prompt = SimpleNamespace(
        name="test-prompt", description="Test prompt description", arguments=[]
    )
    mock_mcp._list_prompts_mcp = AsyncMock(return_value=[mock_prompt])

    transport = HTTPSSETransport(settings, mock_mcp)

    request = {"jsonrpc": "2.0", "id": "test-prompt-list", "method": "prompts/list", "params": {}}

    response = await transport._process_mcp_request(request)

    # Verify response structure
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-prompt-list"
    assert "result" in response
    assert "prompts" in response["result"]
    assert len(response["result"]["prompts"]) == 1
    assert response["result"]["prompts"][0]["name"] == "test-prompt"

    # Verify FastMCP was called
    mock_mcp._list_prompts_mcp.assert_called_once()


@pytest.mark.asyncio
async def test_process_mcp_request_initialize_method() -> None:
    """Test _process_mcp_request handles initialize method."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
    mock_mcp.name = "routeros-mcp"
    mock_mcp.version = "1.0.0"

    transport = HTTPSSETransport(settings, mock_mcp)

    request = {
        "jsonrpc": "2.0",
        "id": "test-init",
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
    }

    response = await transport._process_mcp_request(request)

    # Verify response structure
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-init"
    assert "result" in response
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert "capabilities" in response["result"]
    assert "serverInfo" in response["result"]
    assert response["result"]["serverInfo"]["name"] == "routeros-mcp"


@pytest.mark.asyncio
async def test_process_mcp_request_unknown_method() -> None:
    """Test _process_mcp_request returns MethodNotFoundError for unknown methods."""
    from routeros_mcp.mcp.errors import MethodNotFoundError

    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
    transport = HTTPSSETransport(settings, mock_mcp)

    request = {
        "jsonrpc": "2.0",
        "id": "test-unknown",
        "method": "unknown/method",
        "params": {},
    }

    with pytest.raises(MethodNotFoundError) as exc_info:
        await transport._process_mcp_request(request)

    assert "unknown/method" in str(exc_info.value)
    assert exc_info.value.code == -32601  # Method not found


@pytest.mark.asyncio
async def test_process_mcp_request_with_user_context() -> None:
    """Test _process_mcp_request propagates user context to tool calls."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP tool execution
    from types import SimpleNamespace

    mock_content = SimpleNamespace(
        type="text", text="Result", model_dump=lambda **kwargs: {"text": "Result"}
    )
    mock_tool_result = SimpleNamespace(content=[mock_content], isError=False)
    mock_mcp._call_tool_mcp = AsyncMock(return_value=mock_tool_result)

    transport = HTTPSSETransport(settings, mock_mcp)

    user_context = {"user_id": "user-123", "roles": ["admin"]}

    request = {
        "jsonrpc": "2.0",
        "id": "test-user-ctx",
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"message": "test"}},
    }

    await transport._process_mcp_request(request, user_context=user_context)

    # Verify user context was added to arguments
    call_args = mock_mcp._call_tool_mcp.call_args
    assert call_args is not None
    arguments = call_args[0][1]  # Second positional argument
    assert "_user" in arguments
    assert arguments["_user"] == user_context


@pytest.mark.asyncio
async def test_process_mcp_request_tool_exception_mapping() -> None:
    """Test _process_mcp_request maps tool exceptions to MCP errors."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    # Mock FastMCP tool execution to raise exception
    mock_mcp._call_tool_mcp = AsyncMock(side_effect=RuntimeError("Tool execution failed"))

    transport = HTTPSSETransport(settings, mock_mcp)

    request = {
        "jsonrpc": "2.0",
        "id": "test-exception",
        "method": "tools/call",
        "params": {"name": "failing_tool", "arguments": {}},
    }

    # Should raise an MCPError after mapping
    from routeros_mcp.mcp.errors import MCPError

    with pytest.raises(MCPError):
        await transport._process_mcp_request(request)
