"""End-to-end tests for HTTP/SSE transport with real MCP clients.

This module tests the complete HTTP/SSE transport integration with MCP clients,
simulating how Claude Desktop, VS Code, and other MCP-compatible clients would
interact with the RouterOS-MCP HTTP server.

Tests cover:
- Tool invocation (simple and parameterized)
- Resource fetching
- Error handling
- Authentication with OIDC
- Connection lifecycle

Design reference: docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md
"""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from routeros_mcp.config import Settings


@pytest.fixture
async def settings() -> Settings:
    """Create test settings for HTTP transport E2E tests."""
    return Settings(
        mcp_transport="http",
        mcp_http_host="127.0.0.1",
        mcp_http_port=18765,  # Use unique port to avoid conflicts
        mcp_http_base_path="/mcp",
        environment="lab",
        database_url="sqlite+aiosqlite:///:memory:",
        oidc_enabled=False,  # Start with auth disabled, enable in specific tests
        log_level="WARNING",
    )


@pytest.fixture
async def http_server(settings: Settings) -> AsyncMock:
    """Create and start RouterOS-MCP HTTP server for testing.

    Returns a mock server that simulates the HTTP/SSE endpoint behavior.
    For full integration tests, this would be a real server instance.
    """
    # For Phase 2, we mock the server startup
    # In Phase 3, this would actually start the server
    server = AsyncMock()
    server.settings = settings
    server.base_url = (
        f"http://{settings.mcp_http_host}:{settings.mcp_http_port}{settings.mcp_http_base_path}"
    )
    return server


@pytest.mark.asyncio
@pytest.mark.skip(reason="Full HTTP server not yet exposed - will be completed in Phase 3")
async def test_mcp_client_basic_tool_call(http_server: AsyncMock) -> None:
    """Test basic tool invocation via MCP client (device_list).

    This test simulates how Claude Desktop or VS Code would call a simple
    tool without parameters through the HTTP/SSE transport.
    """
    # In a real test, we would connect to the running server
    # For now, we test the structure that will be used

    base_url = http_server.base_url

    # MCP client connection using SSE transport
    async with (
        sse_client(url=base_url) as (read_stream, write_stream),
        ClientSession(read_stream=read_stream, write_stream=write_stream) as session,
    ):
        # Initialize session
        await session.initialize()

        # List available tools
        tools_result = await session.list_tools()
        assert tools_result.tools is not None
        assert len(tools_result.tools) > 0

        # Find device_list tool
        device_list_tool = next((t for t in tools_result.tools if t.name == "device_list"), None)
        assert device_list_tool is not None

        # Call device_list tool
        result = await session.call_tool(name="device_list", arguments={})

        # Verify response structure
        assert result is not None
        assert hasattr(result, "content")
        assert len(result.content) > 0

        # Verify metadata
        is_error = getattr(result, "isError", None)
        if is_error is None and isinstance(result, dict):
            is_error = result.get("isError", False)
        if is_error:
            pytest.fail(f"Tool call failed: {result.content}")


@pytest.mark.asyncio
@pytest.mark.skip(reason="Full HTTP server not yet exposed - will be completed in Phase 3")
async def test_mcp_client_tool_with_parameters(http_server: AsyncMock) -> None:
    """Test tool invocation with parameters (device_get).

    This test verifies that tools requiring parameters work correctly,
    similar to how a client would fetch specific device information.
    """
    base_url = http_server.base_url

    async with (
        sse_client(url=base_url) as (read_stream, write_stream),
        ClientSession(read_stream=read_stream, write_stream=write_stream) as session,
    ):
        await session.initialize()

        # Call device_get with device_id parameter
        result = await session.call_tool(name="device_get", arguments={"device_id": "dev-test-001"})

        assert result is not None
        assert hasattr(result, "content")

        # Verify response contains device information
        is_error = getattr(result, "isError", None)
        if is_error is None and isinstance(result, dict):
            is_error = result.get("isError", False)
        if not is_error:
            # Check for expected fields in content
            content_text = str(result.content)
            assert "dev-test-001" in content_text or "device" in content_text.lower()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Full HTTP server not yet exposed - will be completed in Phase 3")
async def test_mcp_client_resource_fetch(http_server: AsyncMock) -> None:
    """Test resource fetching via MCP client (device:// URI).

    This verifies that MCP resources work correctly through HTTP transport,
    testing the resource URI resolution and content delivery.
    """
    base_url = http_server.base_url

    async with (
        sse_client(url=base_url) as (read_stream, write_stream),
        ClientSession(read_stream=read_stream, write_stream=write_stream) as session,
    ):
        await session.initialize()

        # List available resources
        resources_result = await session.list_resources()
        assert resources_result.resources is not None

        # Read a device resource
        resource_uri = "device://dev-test-001/overview"
        result = await session.read_resource(uri=resource_uri)

        assert result is not None
        assert hasattr(result, "contents")
        assert len(result.contents) > 0

        # Verify resource content
        content = result.contents[0]
        assert content.uri == resource_uri


@pytest.mark.asyncio
@pytest.mark.skip(reason="Full HTTP server not yet exposed - will be completed in Phase 3")
async def test_mcp_client_error_handling_invalid_device(
    http_server: AsyncMock,
) -> None:
    """Test error handling for invalid device_id.

    Verifies that the server properly handles errors and returns structured
    error responses that clients can interpret.
    """
    base_url = http_server.base_url

    async with (
        sse_client(url=base_url) as (read_stream, write_stream),
        ClientSession(read_stream=read_stream, write_stream=write_stream) as session,
    ):
        await session.initialize()

        # Call tool with non-existent device
        result = await session.call_tool(
            name="device_get", arguments={"device_id": "non-existent-device"}
        )

        # Should get an error response
        assert result is not None
        # Error might be in isError flag or in content
        if hasattr(result, "isError") and result.isError:
            pass  # Expected error response

        # Verify error message is helpful
        content_text = str(result.content)
        assert "not found" in content_text.lower() or "error" in content_text.lower()


@pytest.mark.asyncio
@pytest.mark.skip(reason="OIDC integration not yet complete - will be completed in Phase 3")
async def test_mcp_client_authentication_valid_token() -> None:
    """Test authentication with valid OIDC token.

    This test verifies that authenticated requests work correctly when
    a valid OAuth/OIDC token is provided.
    """
    # Create settings with OIDC enabled
    settings = Settings(
        mcp_transport="http",
        mcp_http_host="127.0.0.1",
        mcp_http_port=18766,
        mcp_http_base_path="/mcp",
        environment="lab",
        database_url="sqlite+aiosqlite:///:memory:",
        oidc_enabled=True,
        oidc_provider_url="http://localhost:8080/realms/test",
        oidc_client_id="routeros-mcp",
        oidc_audience="routeros-mcp",
        oidc_skip_verification=True,  # For testing only
    )

    # Mock OIDC token (Phase 3: generate from mock-oauth2-server)
    # For now, use a placeholder token structure
    valid_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0LXVzZXIifQ.test"

    # Create HTTP client with auth header
    async with httpx.AsyncClient() as client:
        # Make authenticated request
        response = await client.post(
            f"http://{settings.mcp_http_host}:{settings.mcp_http_port}{settings.mcp_http_base_path}/messages",
            json={
                "jsonrpc": "2.0",
                "id": "auth-test-1",
                "method": "tools/list",
                "params": {},
            },
            headers={
                "Authorization": f"Bearer {valid_token}",
                "Content-Type": "application/json",
            },
        )

        # Should succeed with valid token
        assert response.status_code == 200
        body = response.json()
        assert body["jsonrpc"] == "2.0"
        assert "result" in body


@pytest.mark.asyncio
@pytest.mark.skip(reason="OIDC integration not yet complete - will be completed in Phase 3")
async def test_mcp_client_authentication_invalid_token() -> None:
    """Test authentication with invalid OIDC token.

    Verifies that requests with invalid or missing tokens are rejected
    with appropriate error codes.
    """
    settings = Settings(
        mcp_transport="http",
        mcp_http_host="127.0.0.1",
        mcp_http_port=18767,
        mcp_http_base_path="/mcp",
        environment="lab",
        database_url="sqlite+aiosqlite:///:memory:",
        oidc_enabled=True,
        oidc_provider_url="http://localhost:8080/realms/test",
        oidc_client_id="routeros-mcp",
        oidc_audience="routeros-mcp",
    )

    async with httpx.AsyncClient() as client:
        # Test 1: Missing token
        response = await client.post(
            f"http://{settings.mcp_http_host}:{settings.mcp_http_port}{settings.mcp_http_base_path}/messages",
            json={
                "jsonrpc": "2.0",
                "id": "auth-test-2",
                "method": "tools/list",
                "params": {},
            },
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 401

        # Test 2: Invalid token
        response = await client.post(
            f"http://{settings.mcp_http_host}:{settings.mcp_http_port}{settings.mcp_http_base_path}/messages",
            json={
                "jsonrpc": "2.0",
                "id": "auth-test-3",
                "method": "tools/list",
                "params": {},
            },
            headers={
                "Authorization": "Bearer invalid-token-here",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_http_client_direct_jsonrpc_request() -> None:
    """Test direct HTTP JSON-RPC request to verify transport layer.

    This test validates the HTTP transport without full MCP client,
    testing the raw JSON-RPC request/response cycle.
    """
    from routeros_mcp.mcp.transport.http_sse import HTTPSSETransport
    from fastmcp import FastMCP
    from starlette.requests import Request
    from unittest.mock import AsyncMock, MagicMock

    settings = Settings(mcp_transport="http")
    mcp = FastMCP("test-server")

    # Register a test tool
    @mcp.tool()
    def test_tool(message: str) -> dict[str, Any]:
        """Test tool for HTTP transport testing."""
        return {"content": [{"type": "text", "text": f"Echo: {message}"}]}

    transport = HTTPSSETransport(settings, mcp)

    # Create mock request
    mock_request = MagicMock(spec=Request)
    mock_request.method = "POST"
    mock_request.url.path = "/mcp/messages"
    mock_request.json = AsyncMock(
        return_value={
            "jsonrpc": "2.0",
            "id": "direct-test-1",
            "method": "tools/call",
            "params": {"name": "test_tool", "arguments": {"message": "Hello HTTP"}},
        }
    )
    mock_request.state.user = None

    # Process request
    with patch(
        "routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="test-corr-id"
    ):
        response = await transport.handle_request(mock_request)

    # Verify response
    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers

    body = json.loads(response.body.decode())
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "direct-test-1"
    assert "result" in body


@pytest.mark.asyncio
async def test_http_client_connection_timeout() -> None:
    """Test client timeout handling for unresponsive server.

    Verifies that clients properly handle connection timeouts and errors
    when the server is unavailable or slow to respond.
    """
    # Try to connect to a server that doesn't exist
    non_existent_url = "http://127.0.0.1:19999/mcp"

    async with httpx.AsyncClient(timeout=2.0) as client:
        with pytest.raises((httpx.ConnectError, httpx.TimeoutException)):
            await client.post(
                f"{non_existent_url}/messages",
                json={
                    "jsonrpc": "2.0",
                    "id": "timeout-test",
                    "method": "tools/list",
                    "params": {},
                },
            )


@pytest.mark.asyncio
async def test_correlation_id_propagation() -> None:
    """Test that correlation IDs are properly propagated through requests.

    Verifies the correlation ID middleware correctly extracts, propagates,
    and returns correlation IDs in response headers.
    """
    from routeros_mcp.mcp.transport.http_sse import HTTPSSETransport
    from fastmcp import FastMCP
    from starlette.requests import Request
    from unittest.mock import AsyncMock, MagicMock

    settings = Settings(mcp_transport="http")
    mcp = FastMCP("test-server")
    transport = HTTPSSETransport(settings, mcp)

    # Create mock request
    mock_request = MagicMock(spec=Request)
    mock_request.method = "POST"
    mock_request.url.path = "/mcp/messages"
    mock_request.json = AsyncMock(
        return_value={
            "jsonrpc": "2.0",
            "id": "corr-test",
            "method": "tools/list",
            "params": {},
        }
    )
    mock_request.state.user = None

    # Provide custom correlation ID
    custom_corr_id = "custom-correlation-12345"
    with patch(
        "routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value=custom_corr_id
    ):
        response = await transport.handle_request(mock_request)

    # Verify correlation ID in response
    assert "X-Correlation-ID" in response.headers
    assert response.headers["X-Correlation-ID"] == custom_corr_id


@pytest.mark.asyncio
async def test_concurrent_client_requests() -> None:
    """Test multiple concurrent client requests.

    Verifies that the HTTP server can handle multiple simultaneous requests
    without conflicts or data corruption.
    """
    from routeros_mcp.mcp.transport.http_sse import HTTPSSETransport
    from fastmcp import FastMCP
    from starlette.requests import Request
    from unittest.mock import AsyncMock, MagicMock, patch

    settings = Settings(mcp_transport="http")
    mcp = FastMCP("test-server")
    transport = HTTPSSETransport(settings, mcp)

    async def make_request(request_id: str) -> dict[str, Any]:
        """Make a single request and return the response body."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/mcp/messages"
        mock_request.json = AsyncMock(
            return_value={
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/list",
                "params": {},
            }
        )
        mock_request.state.user = None

        with patch(
            "routeros_mcp.mcp.transport.http_sse.get_correlation_id",
            return_value=f"corr-{request_id}",
        ):
            response = await transport.handle_request(mock_request)

        return json.loads(response.body.decode())

    # Make 10 concurrent requests
    tasks = [make_request(f"req-{i}") for i in range(10)]
    results = await asyncio.gather(*tasks)

    # Verify all requests succeeded and have correct IDs
    assert len(results) == 10
    for i, result in enumerate(results):
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == f"req-{i}"
        assert "result" in result or "error" in result


@pytest.mark.asyncio
async def test_malformed_json_handling() -> None:
    """Test handling of malformed JSON requests.

    Verifies that the server properly handles invalid JSON and returns
    appropriate JSON-RPC parse error responses.
    """
    from routeros_mcp.mcp.transport.http_sse import HTTPSSETransport
    from fastmcp import FastMCP
    from starlette.requests import Request
    from unittest.mock import AsyncMock, MagicMock, patch

    settings = Settings(mcp_transport="http")
    mcp = FastMCP("test-server")
    transport = HTTPSSETransport(settings, mcp)

    # Create mock request with JSON decode error
    mock_request = MagicMock(spec=Request)
    mock_request.method = "POST"
    mock_request.url.path = "/mcp/messages"
    mock_request.json = AsyncMock(side_effect=json.JSONDecodeError("Invalid JSON", "doc", 0))

    with patch(
        "routeros_mcp.mcp.transport.http_sse.get_correlation_id", return_value="malformed-test"
    ):
        response = await transport.handle_request(mock_request)

    # Verify error response
    assert response.status_code == 400
    body = json.loads(response.body.decode())
    assert body["jsonrpc"] == "2.0"
    assert body["error"]["code"] == -32700  # Parse error
    assert "X-Correlation-ID" in response.headers
