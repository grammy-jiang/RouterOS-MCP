"""Tests for JSON-RPC protocol helpers."""

import pytest

from routeros_mcp.mcp.errors import DeviceNotFoundError, ValidationError
from routeros_mcp.mcp.protocol.jsonrpc import (
    create_error_response,
    create_success_response,
    extract_tool_arguments,
    format_tool_result,
    validate_jsonrpc_request,
)


class TestCreateSuccessResponse:
    """Tests for create_success_response."""

    def test_basic_success_response(self) -> None:
        """Test basic success response creation."""
        response = create_success_response(
            request_id="req-123",
            result={"content": [{"type": "text", "text": "Success"}]},
        )
        
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == "req-123"
        assert "result" in response
        assert "error" not in response

    def test_success_response_with_int_id(self) -> None:
        """Test success response with integer ID."""
        response = create_success_response(
            request_id=42,
            result={"data": "test"},
        )
        
        assert response["id"] == 42


class TestCreateErrorResponse:
    """Tests for create_error_response."""

    def test_error_response_with_mcp_error(self) -> None:
        """Test error response with MCPError."""
        error = DeviceNotFoundError(
            "Device not found",
            data={"device_id": "dev-123"},
        )
        response = create_error_response(
            request_id="req-123",
            error=error,
        )
        
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == "req-123"
        assert "error" in response
        assert response["error"]["code"] == error.code
        assert response["error"]["message"] == error.message
        assert response["error"]["data"] == error.data

    def test_error_response_with_generic_exception(self) -> None:
        """Test error response with generic exception."""
        exc = ValueError("Invalid value")
        response = create_error_response(
            request_id="req-123",
            error=exc,
        )
        
        assert response["jsonrpc"] == "2.0"
        assert "error" in response
        # Should be mapped to ValidationError
        assert response["error"]["message"] == "Invalid value"

    def test_error_response_with_null_id(self) -> None:
        """Test error response with null ID (notification error)."""
        error = ValidationError("Test error")
        response = create_error_response(
            request_id=None,
            error=error,
        )

        # Per JSON-RPC 2.0 spec, notification errors should not have 'id' field
        assert "id" not in response
        assert response["jsonrpc"] == "2.0"
        assert "error" in response


class TestValidateJsonRpcRequest:
    """Tests for validate_jsonrpc_request."""

    def test_valid_request(self) -> None:
        """Test validation of valid request."""
        request = {
            "jsonrpc": "2.0",
            "id": "req-123",
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"message": "test"}},
        }
        
        valid, error = validate_jsonrpc_request(request)
        assert valid is True
        assert error is None

    def test_request_without_jsonrpc_field(self) -> None:
        """Test request without jsonrpc field."""
        request = {
            "id": "req-123",
            "method": "tools/call",
        }
        
        valid, error = validate_jsonrpc_request(request)
        assert valid is False
        assert "jsonrpc" in error.lower()

    def test_request_with_wrong_jsonrpc_version(self) -> None:
        """Test request with wrong JSON-RPC version."""
        request = {
            "jsonrpc": "1.0",
            "id": "req-123",
            "method": "tools/call",
        }
        
        valid, error = validate_jsonrpc_request(request)
        assert valid is False
        assert "2.0" in error

    def test_request_without_method(self) -> None:
        """Test request without method field."""
        request = {
            "jsonrpc": "2.0",
            "id": "req-123",
        }
        
        valid, error = validate_jsonrpc_request(request)
        assert valid is False
        assert "method" in error.lower()

    def test_request_with_invalid_id_type(self) -> None:
        """Test request with invalid ID type."""
        request = {
            "jsonrpc": "2.0",
            "id": ["invalid"],  # Array is not valid
            "method": "tools/call",
        }
        
        valid, error = validate_jsonrpc_request(request)
        assert valid is False
        assert "id" in error.lower()

    def test_request_with_invalid_params_type(self) -> None:
        """Test request with invalid params type."""
        request = {
            "jsonrpc": "2.0",
            "id": "req-123",
            "method": "tools/call",
            "params": "invalid",  # String is not valid
        }
        
        valid, error = validate_jsonrpc_request(request)
        assert valid is False
        assert "params" in error.lower()

    def test_notification_without_id(self) -> None:
        """Test notification (request without ID)."""
        request = {
            "jsonrpc": "2.0",
            "method": "notify",
            "params": {},
        }
        
        valid, error = validate_jsonrpc_request(request)
        assert valid is True


class TestFormatToolResult:
    """Tests for format_tool_result."""

    def test_format_string_content(self) -> None:
        """Test formatting string content."""
        result = format_tool_result(
            content="Test message",
            meta={"device_id": "dev-123"},
        )
        
        assert result["isError"] is False
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Test message"
        assert result["_meta"]["device_id"] == "dev-123"

    def test_format_dict_content(self) -> None:
        """Test formatting dictionary content."""
        content_item = {"type": "text", "text": "Test"}
        result = format_tool_result(content=content_item)
        
        assert len(result["content"]) == 1
        assert result["content"][0] == content_item

    def test_format_list_content(self) -> None:
        """Test formatting list content."""
        content_items = [
            {"type": "text", "text": "Line 1"},
            {"type": "text", "text": "Line 2"},
        ]
        result = format_tool_result(content=content_items)
        
        assert len(result["content"]) == 2
        assert result["content"] == content_items

    def test_format_error_result(self) -> None:
        """Test formatting error result."""
        result = format_tool_result(
            content="Error occurred",
            is_error=True,
            meta={"error_code": 123},
        )
        
        assert result["isError"] is True
        assert result["_meta"]["error_code"] == 123

    def test_format_result_without_meta(self) -> None:
        """Test formatting result without metadata."""
        result = format_tool_result(content="Test")
        
        assert "isError" in result
        assert "content" in result
        assert "_meta" not in result


class TestExtractToolArguments:
    """Tests for extract_tool_arguments."""

    def test_extract_basic_arguments(self) -> None:
        """Test extracting basic tool arguments."""
        params = {
            "name": "system/get-overview",
            "arguments": {"device_id": "dev-123"},
        }
        
        tool_name, args = extract_tool_arguments(params)
        
        assert tool_name == "system/get-overview"
        assert args == {"device_id": "dev-123"}

    def test_extract_without_arguments(self) -> None:
        """Test extracting when arguments field is missing."""
        params = {
            "name": "echo",
        }
        
        tool_name, args = extract_tool_arguments(params)
        
        assert tool_name == "echo"
        assert args == {}

    def test_extract_with_invalid_params_type(self) -> None:
        """Test extracting with invalid params type."""
        with pytest.raises(ValueError, match="params must be an object"):
            extract_tool_arguments("invalid")

    def test_extract_without_name(self) -> None:
        """Test extracting without name field."""
        params = {
            "arguments": {},
        }
        
        with pytest.raises(ValueError, match="name is required"):
            extract_tool_arguments(params)

    def test_extract_with_invalid_name_type(self) -> None:
        """Test extracting with invalid name type."""
        params = {
            "name": 123,  # Should be string
            "arguments": {},
        }
        
        with pytest.raises(ValueError, match="name must be a string"):
            extract_tool_arguments(params)

    def test_extract_with_invalid_arguments_type(self) -> None:
        """Test extracting with invalid arguments type."""
        params = {
            "name": "echo",
            "arguments": "invalid",  # Should be object
        }
        
        with pytest.raises(ValueError, match="arguments must be an object"):
            extract_tool_arguments(params)
