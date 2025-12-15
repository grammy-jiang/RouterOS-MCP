"""Tests for HTTP/SSE transport implementation."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

from routeros_mcp.config import Settings
from routeros_mcp.mcp.errors import InvalidRequestError, ParseError
from routeros_mcp.mcp.transport.http_sse import HTTPSSETransport


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
    assert any("CorrelationIDMiddleware" in str(m) for m in middleware_list)


@pytest.mark.asyncio
async def test_handle_request_success() -> None:
    """Test handle_request processes valid JSON-RPC request successfully."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
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
            "params": {"name": "test"},
        }
    )
    mock_request.state.user = {"user_id": "user-123", "roles": ["admin"]}

    # Call handle_request
    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="corr-user"):
        response = await transport.handle_request(mock_request)

    # Verify response includes user context in metadata
    assert isinstance(response.body, bytes)
    body = json.loads(response.body.decode())
    assert body["result"]["_meta"]["has_user_context"] is True


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
    with patch("routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value=test_correlation_id):
        response = await transport.handle_request(mock_request)

    # Verify correlation ID in response headers
    assert response.headers["X-Correlation-ID"] == test_correlation_id


@pytest.mark.asyncio
async def test_process_mcp_request_with_user_context() -> None:
    """Test _process_mcp_request adds user context to params."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
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
    assert response["result"]["_meta"]["has_user_context"] is True


@pytest.mark.asyncio
async def test_process_mcp_request_without_user_context() -> None:
    """Test _process_mcp_request works without user context."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()
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
    assert response["result"]["_meta"]["has_user_context"] is False


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
