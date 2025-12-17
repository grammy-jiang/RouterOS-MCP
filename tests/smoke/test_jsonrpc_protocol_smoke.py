"""Smoke tests for JSON-RPC protocol helpers."""

from __future__ import annotations

import pytest

from routeros_mcp.mcp.protocol.jsonrpc import (
    create_success_response,
    extract_tool_arguments,
    validate_jsonrpc_request,
)


pytestmark = pytest.mark.smoke


def test_validate_jsonrpc_request_valid_smoke() -> None:
    req = {"jsonrpc": "2.0", "id": "1", "method": "tools/call", "params": {}}
    valid, error = validate_jsonrpc_request(req)
    assert valid is True
    assert error is None


def test_validate_jsonrpc_request_invalid_smoke() -> None:
    req = {"jsonrpc": "1.0", "id": 1}
    valid, error = validate_jsonrpc_request(req)
    assert valid is False
    assert isinstance(error, str)


def test_create_success_response_smoke() -> None:
    resp = create_success_response("abc", result={"ok": True})
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "abc"
    assert resp["result"]["ok"] is True


def test_extract_tool_arguments_smoke() -> None:
    params = {"name": "echo", "arguments": {"message": "hi"}}
    name, args = extract_tool_arguments(params)
    assert name == "echo"
    assert args == {"message": "hi"}
