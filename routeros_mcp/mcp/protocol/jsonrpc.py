"""JSON-RPC 2.0 protocol helpers and message formatting.

Implements JSON-RPC 2.0 message construction, error response formatting,
and protocol-level utilities for the MCP server.

Streaming Protocol Support (Phase 4):
--------------------------------------
Tools can stream progress updates by yielding progress dictionaries when
`stream_progress=true` is passed in tool arguments. This enables real-time
feedback for long-running operations like ping, traceroute, and bandwidth tests.

Progress Message Format:
    {
        "type": "progress",
        "message": "Reply from 8.8.8.8: 25ms",
        "percent": 25  # Optional: 0-100
    }

Transport-Specific Behavior:
    - HTTP/SSE Transport: Progress messages sent as SSE events:
        event: progress
        data: {"type":"progress","message":"...","percent":25}

        event: result
        data: {"result": {...}}

    - STDIO Transport: Progress messages collected but not streamed.
        Only final result returned (backward compatible).

See docs/19-json-rpc-error-codes-and-mcp-protocol-specification.md
"""

from typing import Any

from routeros_mcp.mcp.errors import MCPError, map_exception_to_error


def create_success_response(
    request_id: str | int,
    result: Any,
) -> dict[str, Any]:
    """Create JSON-RPC 2.0 success response.

    Args:
        request_id: Request identifier from the original request
        result: Result data to return

    Returns:
        JSON-RPC 2.0 response dictionary

    Example:
        response = create_success_response(
            request_id="req-123",
            result={
                "content": [{"type": "text", "text": "Success"}],
                "isError": False,
            }
        )
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def create_error_response(
    request_id: str | int | None,
    error: MCPError | Exception,
) -> dict[str, Any]:
    """Create JSON-RPC 2.0 error response.

    Args:
        request_id: Request identifier (None for notification errors)
        error: Error to format (MCPError or generic Exception)

    Returns:
        JSON-RPC 2.0 error response dictionary

    Example:
        response = create_error_response(
            request_id="req-123",
            error=DeviceNotFoundError(
                "Device dev-123 not found",
                data={"device_id": "dev-123"}
            )
        )
    """
    # Map generic exceptions to MCP errors
    if not isinstance(error, MCPError):
        error = map_exception_to_error(error)

    response: dict[str, Any] = {
        "jsonrpc": "2.0",
        "error": error.to_jsonrpc_error(),
    }

    # Include ID if provided (omit for notification errors per JSON-RPC spec)
    if request_id is not None:
        response["id"] = request_id

    return response


def validate_jsonrpc_request(request: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate JSON-RPC 2.0 request structure.

    Args:
        request: Request dictionary to validate

    Returns:
        Tuple of (is_valid, error_message)

    Example:
        valid, error = validate_jsonrpc_request(request)
        if not valid:
            return create_error_response(
                request_id=None,
                error=InvalidRequestError(error)
            )
    """
    # Check required fields
    if not isinstance(request, dict):
        return False, "Request must be a JSON object"

    # Check jsonrpc version
    if request.get("jsonrpc") != "2.0":
        return False, "jsonrpc field must be '2.0'"

    # Check method field
    if "method" not in request:
        return False, "method field is required"

    if not isinstance(request["method"], str):
        return False, "method must be a string"

    # Check id field (optional, but must be string/number/null if present)
    if "id" in request:
        request_id = request["id"]
        if not isinstance(request_id, (str, int, type(None))):
            return False, "id must be a string, number, or null"

    # Check params field (optional, but must be object/array if present)
    if "params" in request:
        params = request["params"]
        if not isinstance(params, (dict, list)):
            return False, "params must be an object or array"

    return True, None


def format_tool_result(
    content: list[dict[str, Any]] | dict[str, Any] | str,
    is_error: bool = False,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Format tool call result according to MCP conventions.

    Args:
        content: Tool result content (text, structured data, etc.)
        is_error: Whether this is an error result
        meta: Additional metadata to include

    Returns:
        Formatted tool result dictionary

    Example:
        # Text result
        result = format_tool_result(
            content="System is healthy",
            meta={"device_id": "dev-123"}
        )

        # Structured result
        result = format_tool_result(
            content=[
                {"type": "text", "text": "Device overview:"},
                {"type": "resource", "resource": {"uri": "device://dev-123"}}
            ],
            meta={"cpu_usage": 5.2}
        )
    """
    # Normalize content to list of content items
    if isinstance(content, str):
        content_list = [{"type": "text", "text": content}]
    elif isinstance(content, dict):
        content_list = [content]
    else:
        content_list = content

    result: dict[str, Any] = {
        "content": content_list,
        "isError": is_error,
    }

    # Add metadata if provided
    if meta:
        result["_meta"] = meta

    return result


def extract_tool_arguments(
    params: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Extract tool name and arguments from MCP tool call params.

    Args:
        params: Tool call params from JSON-RPC request

    Returns:
        Tuple of (tool_name, arguments)

    Raises:
        ValueError: If params structure is invalid

    Example:
        params = {
            "name": "system/get-overview",
            "arguments": {"device_id": "dev-123"}
        }
        tool_name, args = extract_tool_arguments(params)
    """
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    if "name" not in params:
        raise ValueError("params.name is required")

    tool_name = params["name"]
    if not isinstance(tool_name, str):
        raise ValueError("params.name must be a string")

    # Arguments are optional
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ValueError("params.arguments must be an object")

    return tool_name, arguments


def create_progress_message(
    message: str,
    percent: int | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a progress message for streaming operations.

    Progress messages are yielded by tools during long-running operations
    to provide real-time feedback. These are sent as SSE events in HTTP
    transport, or collected silently in STDIO transport.

    Args:
        message: Human-readable progress message
        percent: Optional completion percentage (0-100)
        data: Optional additional progress data

    Returns:
        Progress message dictionary

    Example:
        # Simple progress message
        progress = create_progress_message("Pinging host...")

        # Progress with percentage
        progress = create_progress_message("Reply from 8.8.8.8", percent=25)

        # Progress with additional data
        progress = create_progress_message(
            "Hop 3 reached",
            percent=30,
            data={"hop": 3, "latency_ms": 15}
        )
    """
    progress: dict[str, Any] = {
        "type": "progress",
        "message": message,
    }

    if percent is not None:
        if not (0 <= percent <= 100):
            raise ValueError("percent must be between 0 and 100")
        progress["percent"] = percent

    if data:
        progress["data"] = data

    return progress


def is_streaming_request(params: dict[str, Any]) -> bool:
    """Check if a request should use streaming protocol.

    Streaming is enabled when the `stream_progress` parameter is set to True
    in the tool arguments.

    Args:
        params: Tool call params from JSON-RPC request

    Returns:
        True if streaming is requested, False otherwise

    Example:
        params = {
            "name": "diagnostics/ping",
            "arguments": {
                "device_id": "dev-001",
                "target": "8.8.8.8",
                "stream_progress": True
            }
        }
        is_streaming = is_streaming_request(params)  # True
    """
    if not isinstance(params, dict):
        return False

    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return False

    return arguments.get("stream_progress", False) is True
