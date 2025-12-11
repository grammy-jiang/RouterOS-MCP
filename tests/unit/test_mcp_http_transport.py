"""Tests for the MCP HTTP transport (Starlette-based)."""

from unittest.mock import AsyncMock

import httpx
import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp.transport.http import MCPHTTPTransport


@pytest.mark.asyncio
async def test_http_transport_health_endpoint() -> None:
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)

    asgi_transport = httpx.ASGITransport(app=transport.app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        resp = await client.get("/mcp/health")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "healthy"
    assert payload["transport"] == "http"


@pytest.mark.asyncio
async def test_http_transport_jsonrpc_success(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)

    expected_response = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    mock_process = AsyncMock(return_value=expected_response)
    monkeypatch.setattr(transport, "_process_mcp_request", mock_process)

    asgi_transport = httpx.ASGITransport(app=transport.app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/mcp/rpc",
            json={"jsonrpc": "2.0", "id": 1, "method": "echo"},
            headers={"X-Correlation-ID": "corr-123"},
        )

    assert resp.status_code == 200
    assert resp.headers["X-Correlation-ID"] == "corr-123"
    assert resp.json() == expected_response
    mock_process.assert_awaited_once()


@pytest.mark.asyncio
async def test_http_transport_jsonrpc_parse_error() -> None:
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)

    asgi_transport = httpx.ASGITransport(app=transport.app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/mcp/rpc",
            content=b"{not-json}",
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["error"]["code"] == -32700
    assert payload["error"]["message"] == "Parse error"


@pytest.mark.asyncio
async def test_http_transport_jsonrpc_invalid_request_type() -> None:
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)

    asgi_transport = httpx.ASGITransport(app=transport.app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/mcp/rpc",
            json=[{"jsonrpc": "2.0"}],
        )

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_http_transport_jsonrpc_internal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)

    async def boom(_body):
        raise RuntimeError("fail")

    monkeypatch.setattr(transport, "_process_mcp_request", boom)

    asgi_transport = httpx.ASGITransport(app=transport.app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/mcp/rpc",
            json={"jsonrpc": "2.0", "id": 9, "method": "test"},
        )

    assert resp.status_code == 500
    payload = resp.json()
    assert payload["error"]["code"] == -32603
    assert payload["error"]["data"]["detail"] == "fail"
