"""Tests for MCP errors module."""

import pytest

from routeros_mcp.mcp.errors import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    MCP_AUTHENTICATION_FAILED,
    MCP_DEVICE_NOT_FOUND,
    MCP_DEVICE_UNREACHABLE,
    MCP_VALIDATION_ERROR,
    AuthenticationError,
    DeviceNotFoundError,
    DeviceUnreachableError,
    InternalError,
    InvalidParamsError,
    InvalidRequestError,
    MCPError,
    MethodNotFoundError,
    ParseError,
    ValidationError,
    map_exception_to_error,
)


class TestMCPErrorClass:
    """Tests for MCPError base class."""

    def test_default_error(self) -> None:
        """Test MCPError with defaults."""
        error = MCPError()
        assert error.code == JSONRPC_INTERNAL_ERROR
        assert error.message == "Internal server error"
        assert error.data == {}

    def test_error_with_custom_message(self) -> None:
        """Test MCPError with custom message."""
        error = MCPError("Custom error message")
        assert error.message == "Custom error message"

    def test_error_with_data(self) -> None:
        """Test MCPError with additional data."""
        error = MCPError("Error with data", data={"device_id": "dev-123"})
        assert error.data == {"device_id": "dev-123"}

    def test_error_with_custom_code(self) -> None:
        """Test MCPError with custom code."""
        error = MCPError(code=-32000)
        assert error.code == -32000

    def test_to_jsonrpc_error(self) -> None:
        """Test conversion to JSON-RPC error object."""
        error = MCPError(
            "Test error",
            data={"key": "value"},
            code=-32001,
        )
        jsonrpc_error = error.to_jsonrpc_error()
        
        assert jsonrpc_error == {
            "code": -32001,
            "message": "Test error",
            "data": {"key": "value"},
        }

    def test_to_jsonrpc_error_without_data(self) -> None:
        """Test JSON-RPC error without data field."""
        error = MCPError("Simple error")
        jsonrpc_error = error.to_jsonrpc_error()
        
        assert jsonrpc_error == {
            "code": JSONRPC_INTERNAL_ERROR,
            "message": "Simple error",
        }


class TestStandardErrors:
    """Tests for standard JSON-RPC errors."""

    def test_parse_error(self) -> None:
        """Test ParseError."""
        error = ParseError()
        assert error.code == JSONRPC_PARSE_ERROR
        assert error.message == "Parse error"

    def test_invalid_request_error(self) -> None:
        """Test InvalidRequestError."""
        error = InvalidRequestError()
        assert error.code == JSONRPC_INVALID_REQUEST
        assert error.message == "Invalid request"

    def test_method_not_found_error(self) -> None:
        """Test MethodNotFoundError."""
        error = MethodNotFoundError()
        assert error.code == JSONRPC_METHOD_NOT_FOUND
        assert error.message == "Method not found"

    def test_invalid_params_error(self) -> None:
        """Test InvalidParamsError."""
        error = InvalidParamsError()
        assert error.code == JSONRPC_INVALID_PARAMS
        assert error.message == "Invalid params"

    def test_internal_error(self) -> None:
        """Test InternalError."""
        error = InternalError()
        assert error.code == JSONRPC_INTERNAL_ERROR
        assert error.message == "Internal error"


class TestMCPSpecificErrors:
    """Tests for MCP-specific errors."""

    def test_device_not_found_error(self) -> None:
        """Test DeviceNotFoundError."""
        error = DeviceNotFoundError(
            "Device dev-123 not found",
            data={"device_id": "dev-123"},
        )
        assert error.code == MCP_DEVICE_NOT_FOUND
        assert "dev-123" in error.message

    def test_device_unreachable_error(self) -> None:
        """Test DeviceUnreachableError."""
        error = DeviceUnreachableError()
        assert error.code == MCP_DEVICE_UNREACHABLE

    def test_authentication_error(self) -> None:
        """Test AuthenticationError."""
        error = AuthenticationError()
        assert error.code == MCP_AUTHENTICATION_FAILED

    def test_validation_error(self) -> None:
        """Test ValidationError."""
        error = ValidationError(
            "Invalid device ID format",
            data={"field": "device_id", "value": "invalid!"},
        )
        assert error.code == MCP_VALIDATION_ERROR
        assert error.data["field"] == "device_id"


class TestExceptionMapping:
    """Tests for exception mapping."""

    def test_map_mcp_error_returns_unchanged(self) -> None:
        """Test that MCPError is returned unchanged."""
        original = DeviceNotFoundError("Device not found")
        mapped = map_exception_to_error(original)
        
        assert mapped is original

    def test_map_value_error(self) -> None:
        """Test mapping ValueError to ValidationError."""
        exc = ValueError("Invalid input")
        mapped = map_exception_to_error(exc)
        
        assert isinstance(mapped, ValidationError)
        assert "Invalid input" in mapped.message

    def test_map_generic_exception(self) -> None:
        """Test mapping generic exception to InternalError."""
        exc = RuntimeError("Something went wrong")
        mapped = map_exception_to_error(exc)
        
        assert isinstance(mapped, InternalError)
        assert "Something went wrong" in mapped.message
        assert "original_error" in mapped.data
        assert mapped.data["original_error"] == "RuntimeError"
