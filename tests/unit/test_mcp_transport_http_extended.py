from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from starlette.requests import Request

from routeros_mcp.config import Settings
from routeros_mcp.mcp.transport.http import MCPHTTPTransport

if TYPE_CHECKING:
    from starlette.types import Scope


def _make_request(body: bytes, headers: dict[str, str] | None = None) -> Request:
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/rpc",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_handle_jsonrpc_default_path_sets_correlation():
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)
    request = _make_request(json.dumps({"jsonrpc": "2.0", "id": 10, "method": "noop"}).encode())

    response = await transport.handle_jsonrpc(request)
    data = json.loads(response.body)
    assert data["result"]["_meta"]["method"] == "noop"
    assert response.headers["x-correlation-id"]


@pytest.mark.asyncio
async def test_handle_jsonrpc_with_user_context():
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)
    request = _make_request(json.dumps({"jsonrpc": "2.0", "id": 11, "method": "noop"}).encode())
    request.state.user = {"id": "user-1", "role": "admin"}

    response = await transport.handle_jsonrpc(request)
    data = json.loads(response.body)
    assert data["result"]["_meta"]["method"] == "noop"


@pytest.mark.asyncio
async def test_handle_jsonrpc_invalid_body_type():
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)
    request = _make_request(b"123", headers={"Content-Type": "application/json"})

    response = await transport.handle_jsonrpc(request)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_handle_jsonrpc_parse_error():
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)
    request = _make_request(b"{not-json", headers={"Content-Type": "application/json"})

    response = await transport.handle_jsonrpc(request)
    data = json.loads(response.body)
    assert response.status_code == 400
    assert data["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_handle_jsonrpc_internal_error(monkeypatch):
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)

    async def boom(_body):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(transport, "_process_mcp_request", boom)
    request = _make_request(json.dumps({"jsonrpc": "2.0", "id": 42, "method": "noop"}).encode())

    response = await transport.handle_jsonrpc(request)
    assert response.status_code == 500
    data = json.loads(response.body)
    assert data["error"]["data"]["detail"] == "kaboom"


def _make_get_request(path: str) -> Request:
    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_handle_sse_connected_event():
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)
    request = _make_get_request("/mcp/sse")

    response = await transport.handle_sse(request)
    first_chunk = await anext(response.body_iterator)
    assert first_chunk.get("event") == "connected"
    assert response.headers["X-Correlation-ID"]


@pytest.mark.asyncio
async def test_handle_health():
    transport = MCPHTTPTransport(Settings(mcp_transport="http"), mcp_handler=None)
    request = _make_get_request("/mcp/health")

    response = await transport.handle_health(request)
    data = json.loads(response.body)
    assert data["status"] == "healthy"
