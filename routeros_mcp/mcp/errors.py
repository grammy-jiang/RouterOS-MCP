"""MCP-specific exception classes and error codes.

Implements JSON-RPC 2.0 error code taxonomy and MCP error conventions.
Maps domain/infrastructure exceptions to JSON-RPC error responses.

See docs/19-json-rpc-error-codes-and-mcp-protocol-specification.md
"""

from typing import Any


# JSON-RPC 2.0 Standard Error Codes
# See: https://www.jsonrpc.org/specification#error_object
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

# MCP-Specific Error Codes (Application-defined, -32000 to -32099)
MCP_DEVICE_NOT_FOUND = -32000
MCP_DEVICE_UNREACHABLE = -32001
MCP_AUTHENTICATION_FAILED = -32002
MCP_AUTHORIZATION_FAILED = -32003
MCP_VALIDATION_ERROR = -32004
MCP_TIMEOUT_ERROR = -32005
MCP_ROUTEROS_ERROR = -32006
MCP_CAPABILITY_REQUIRED = -32007
MCP_ENVIRONMENT_MISMATCH = -32008
MCP_RATE_LIMIT_EXCEEDED = -32009


class MCPError(Exception):
    """Base exception for all MCP errors.
    
    Attributes:
        code: JSON-RPC error code
        message: Human-readable error message
        data: Additional error details (optional)
    """
    
    code: int = JSONRPC_INTERNAL_ERROR
    message: str = "Internal server error"
    
    def __init__(
        self,
        message: str | None = None,
        *,
        data: dict[str, Any] | None = None,
        code: int | None = None,
    ) -> None:
        """Initialize MCP error.
        
        Args:
            message: Override default error message
            data: Additional structured error data
            code: Override default error code
        """
        self.message = message or self.__class__.message
        self.data = data or {}
        if code is not None:
            self.code = code
        super().__init__(self.message)
    
    def to_jsonrpc_error(self) -> dict[str, Any]:
        """Convert to JSON-RPC 2.0 error object.
        
        Returns:
            Dictionary with code, message, and optional data fields
        """
        error_obj: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.data:
            error_obj["data"] = self.data
        return error_obj


class ParseError(MCPError):
    """Invalid JSON was received by the server."""
    
    code = JSONRPC_PARSE_ERROR
    message = "Parse error"


class InvalidRequestError(MCPError):
    """The JSON sent is not a valid Request object."""
    
    code = JSONRPC_INVALID_REQUEST
    message = "Invalid request"


class MethodNotFoundError(MCPError):
    """The method does not exist or is not available."""
    
    code = JSONRPC_METHOD_NOT_FOUND
    message = "Method not found"


class InvalidParamsError(MCPError):
    """Invalid method parameter(s)."""
    
    code = JSONRPC_INVALID_PARAMS
    message = "Invalid params"


class InternalError(MCPError):
    """Internal JSON-RPC error."""
    
    code = JSONRPC_INTERNAL_ERROR
    message = "Internal error"


class DeviceNotFoundError(MCPError):
    """Device not found in registry."""
    
    code = MCP_DEVICE_NOT_FOUND
    message = "Device not found"


class DeviceUnreachableError(MCPError):
    """Device is not reachable or not responding."""
    
    code = MCP_DEVICE_UNREACHABLE
    message = "Device unreachable"


class AuthenticationError(MCPError):
    """Authentication failed (invalid credentials)."""
    
    code = MCP_AUTHENTICATION_FAILED
    message = "Authentication failed"


class AuthorizationError(MCPError):
    """Authorization failed (insufficient permissions)."""
    
    code = MCP_AUTHORIZATION_FAILED
    message = "Authorization failed"


class ValidationError(MCPError):
    """Input validation failed."""
    
    code = MCP_VALIDATION_ERROR
    message = "Validation error"


class TimeoutError(MCPError):
    """Operation timed out."""
    
    code = MCP_TIMEOUT_ERROR
    message = "Operation timed out"


class RouterOSError(MCPError):
    """RouterOS API returned an error."""
    
    code = MCP_ROUTEROS_ERROR
    message = "RouterOS error"


class CapabilityRequiredError(MCPError):
    """Operation requires a capability flag not enabled on device."""
    
    code = MCP_CAPABILITY_REQUIRED
    message = "Capability required"


class EnvironmentMismatchError(MCPError):
    """Device environment does not match service environment."""
    
    code = MCP_ENVIRONMENT_MISMATCH
    message = "Environment mismatch"


class RateLimitExceededError(MCPError):
    """Rate limit exceeded for device operations."""
    
    code = MCP_RATE_LIMIT_EXCEEDED
    message = "Rate limit exceeded"


def map_exception_to_error(exc: Exception) -> MCPError:
    """Map Python exception to MCP error.
    
    Args:
        exc: Python exception to map
        
    Returns:
        Appropriate MCPError subclass
        
    Example:
        try:
            device = await device_service.get_device("dev-123")
        except Exception as e:
            error = map_exception_to_error(e)
            return error.to_jsonrpc_error()
    """
    # Already an MCP error
    if isinstance(exc, MCPError):
        return exc
    
    # Import here to avoid circular dependencies
    from routeros_mcp.infra.routeros.exceptions import (
        RouterOSAuthenticationError as InfraAuthError,
        RouterOSAuthorizationError as InfraAuthzError,
        RouterOSClientError,
        RouterOSNetworkError,
        RouterOSNotFoundError,
        RouterOSServerError,
        RouterOSTimeoutError as InfraTimeoutError,
        RouterOSValidationError as InfraValidationError,
    )
    
    # Map infrastructure exceptions
    if isinstance(exc, InfraAuthError):
        return AuthenticationError(
            str(exc),
            data={"original_error": exc.__class__.__name__}
        )
    
    if isinstance(exc, InfraAuthzError):
        return AuthorizationError(
            str(exc),
            data={"original_error": exc.__class__.__name__}
        )
    
    if isinstance(exc, InfraTimeoutError):
        return TimeoutError(
            str(exc),
            data={"original_error": exc.__class__.__name__}
        )
    
    if isinstance(exc, InfraValidationError):
        return ValidationError(
            str(exc),
            data={"original_error": exc.__class__.__name__}
        )
    
    if isinstance(exc, RouterOSNetworkError):
        return DeviceUnreachableError(
            str(exc),
            data={"original_error": exc.__class__.__name__}
        )
    
    if isinstance(exc, RouterOSNotFoundError):
        return DeviceNotFoundError(
            str(exc),
            data={"original_error": exc.__class__.__name__}
        )
    
    if isinstance(exc, (RouterOSClientError, RouterOSServerError)):
        return RouterOSError(
            str(exc),
            data={"original_error": exc.__class__.__name__}
        )
    
    # Generic ValueError -> ValidationError
    if isinstance(exc, ValueError):
        return ValidationError(str(exc))
    
    # Default to internal error
    return InternalError(
        str(exc),
        data={
            "original_error": exc.__class__.__name__,
            "traceback": str(exc),
        }
    )
