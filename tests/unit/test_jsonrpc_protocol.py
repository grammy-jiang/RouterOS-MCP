"""Tests for JSON-RPC protocol helpers."""

import pytest

from routeros_mcp.mcp.errors import InternalError, ValidationError
from routeros_mcp.mcp.protocol.jsonrpc import (
    create_error_response,
    create_success_response,
    extract_tool_arguments,
    format_tool_result,
    validate_jsonrpc_request,
)


class TestCreateSuccessResponse:
    """Tests for successful JSON-RPC responses."""

    def test_success_response_structure(self) -> None:
        """Success response should include jsonrpc, id, and result."""
        response = create_success_response("req-1", {"ok": True})

        assert response == {"jsonrpc": "2.0", "id": "req-1", "result": {"ok": True}}


class TestCreateErrorResponse:
    """Tests for error response formatting."""

    def test_error_response_with_mcp_error(self) -> None:
        """MCPError instances should be used directly."""
        error = ValidationError("Bad input", data={"field": "device_id"})
        response = create_error_response("req-2", error)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == "req-2"
        assert response["error"]["code"] == error.code
        assert response["error"]["message"] == "Bad input"
        assert response["error"]["data"] == {"field": "device_id"}

    def test_error_response_with_generic_exception_maps_to_internal(self) -> None:
        """Generic exceptions should be mapped to InternalError."""
        response = create_error_response(None, RuntimeError("boom"))

        assert response["jsonrpc"] == "2.0"
        # Notifications omit the id field
        assert "id" not in response
        assert response["error"]["code"] == InternalError().code
        assert "boom" in response["error"]["message"]
        assert response["error"]["data"]["original_error"] == "RuntimeError"


class TestValidateJsonRpcRequest:
    """Tests for request validation."""

    @pytest.mark.parametrize(
        "input_data,expected_error",
        [
            ("not-a-dict", "Request must be a JSON object"),
            ({"jsonrpc": "1.0"}, "jsonrpc field must be '2.0'"),
            ({"jsonrpc": "2.0"}, "method field is required"),
            ({"jsonrpc": "2.0", "method": 123}, "method must be a string"),
            (
                {"jsonrpc": "2.0", "method": "ping", "id": {}},
                "id must be a string, number, or null",
            ),
            (
                {"jsonrpc": "2.0", "method": "ping", "params": "oops"},
                "params must be an object or array",
            ),
        ],
    )
    def test_invalid_requests(self, input_data: dict, expected_error: str) -> None:
        """Invalid request shapes should return False with error message."""
        valid, error = validate_jsonrpc_request(input_data)

        assert valid is False
        assert error == expected_error

    def test_valid_request(self) -> None:
        """Valid requests should return True with no error."""
        request = {
            "jsonrpc": "2.0",
            "id": "123",
            "method": "tool/call",
            "params": {"name": "ping", "arguments": {"target": "1.1.1.1"}},
        }

        valid, error = validate_jsonrpc_request(request)

        assert valid is True
        assert error is None


class TestFormatToolResult:
    """Tests for formatting tool results."""

    def test_format_with_string_content(self) -> None:
        result = format_tool_result("hello", meta={"device_id": "dev-1"})

        assert result["content"] == [{"type": "text", "text": "hello"}]
        assert result["isError"] is False
        assert result["_meta"] == {"device_id": "dev-1"}

    def test_format_with_dict_content_and_error_flag(self) -> None:
        content = {"type": "resource", "resource": {"uri": "device://dev-1"}}
        result = format_tool_result(content, is_error=True)

        assert result["content"] == [content]
        assert result["isError"] is True
        assert "_meta" not in result

    def test_format_with_list_content(self) -> None:
        content = [
            {"type": "text", "text": "Line 1"},
            {"type": "text", "text": "Line 2"},
        ]
        result = format_tool_result(content)

        assert result["content"] == content


class TestExtractToolArguments:
    """Tests for extracting tool arguments."""

    def test_extracts_name_and_arguments(self) -> None:
        name, args = extract_tool_arguments({"name": "tool/run", "arguments": {"k": "v"}})

        assert name == "tool/run"
        assert args == {"k": "v"}

    @pytest.mark.parametrize(
        "params,expected_message",
        [
            ("not-a-dict", "params must be an object"),
            ({}, "params.name is required"),
            ({"name": 123}, "params.name must be a string"),
            (
                {"name": "tool/run", "arguments": []},
                "params.arguments must be an object",
            ),
        ],
    )
    def test_invalid_params_raise_value_error(self, params: dict, expected_message: str) -> None:
        with pytest.raises(ValueError, match=expected_message):
            extract_tool_arguments(params)
