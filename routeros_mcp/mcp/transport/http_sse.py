"""HTTP/SSE transport implementation using FastMCP's built-in HTTP support.

This module provides a transport class that delegates to FastMCP's native
HTTP/SSE transport via run_http_async(). Unlike the http.py module which
implements a custom Starlette-based transport, this leverages FastMCP's
built-in capabilities.

See docs/14-mcp-protocol-integration-and-transport-design.md
"""

import json
import logging
from typing import Any
from collections.abc import AsyncIterator

from sse_starlette import EventSourceResponse
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from routeros_mcp.config import Settings
from routeros_mcp.infra.observability import get_correlation_id, set_correlation_id
from routeros_mcp.mcp.errors import (
    InvalidRequestError,
    MCPError,
    ParseError,
    map_exception_to_error,
)
from routeros_mcp.mcp.protocol.jsonrpc import (
    create_error_response,
    create_success_response,
    is_streaming_request,
    validate_jsonrpc_request,
)
from routeros_mcp.mcp.transport.sse_manager import SSEManager

logger = logging.getLogger(__name__)


class CorrelationIDMiddleware:
    """Middleware to extract and propagate correlation IDs."""

    def __init__(self, app: Any) -> None:
        """Initialize middleware.

        Args:
            app: ASGI application
        """
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """Process request and add correlation ID.

        Args:
            scope: ASGI scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        if scope["type"] == "http":
            # Extract correlation ID from headers or generate new one
            headers = dict(scope.get("headers", []))
            correlation_id_bytes = headers.get(b"x-correlation-id")

            if correlation_id_bytes:
                correlation_id = correlation_id_bytes.decode("utf-8")
            else:
                correlation_id = get_correlation_id()

            # Set correlation ID in context
            set_correlation_id(correlation_id)

            # Add correlation ID to response headers
            async def send_with_correlation_id(message: dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    headers = message.get("headers", [])
                    # Add correlation ID header
                    headers.append((b"x-correlation-id", correlation_id.encode("utf-8")))
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_with_correlation_id)
        else:
            await self.app(scope, receive, send)


class HTTPSSETransport:
    """HTTP/SSE transport using FastMCP's built-in HTTP support.

    This transport delegates to FastMCP's run_http_async() method which
    provides SSE (Server-Sent Events) support out of the box.

    The transport integrates with the RouterOS MCP server and uses
    configuration settings to determine host, port, and path.

    Additionally provides:
    - JSON-RPC request processing with validation
    - Correlation ID propagation via X-Correlation-ID header
    - User context extraction from request.state.user
    - Comprehensive error handling per JSON-RPC 2.0 spec
    """

    def __init__(self, settings: Settings, mcp_instance: Any) -> None:
        """Initialize HTTP/SSE transport.

        Args:
            settings: Application settings containing HTTP configuration
            mcp_instance: FastMCP instance to run with HTTP transport
        """
        self.settings = settings
        self.mcp_instance = mcp_instance

        # Initialize SSE subscription manager
        self.sse_manager = SSEManager(
            max_subscriptions_per_device=settings.sse_max_subscriptions_per_device,
            client_timeout_seconds=settings.sse_client_timeout_seconds,
            update_batch_interval_seconds=settings.sse_update_batch_interval_seconds,
        )

        # Register SSE manager globally so health service can broadcast updates
        from routeros_mcp.mcp.server import set_sse_manager
        set_sse_manager(self.sse_manager)

        # Expose subscription endpoint so clients can register for updates
        self._register_subscription_route()

        logger.info(
            "Initialized HTTP/SSE transport",
            extra={
                "host": settings.mcp_http_host,
                "port": settings.mcp_http_port,
                "base_path": settings.mcp_http_base_path,
            },
        )

    async def run(self) -> None:
        """Run the HTTP/SSE transport server.

        Delegates to FastMCP's run_http_async() which handles:
        - SSE endpoint for streaming
        - HTTP endpoints for JSON-RPC
        - Uvicorn ASGI server lifecycle

        Raises:
            RuntimeError: If mcp_instance doesn't support run_http_async
        """
        if not hasattr(self.mcp_instance, "run_http_async"):
            raise RuntimeError(
                "MCP instance does not support HTTP transport. "
                "Ensure you're using a compatible FastMCP version."
            )

        logger.info(
            "Starting HTTP/SSE transport server",
            extra={
                "host": self.settings.mcp_http_host,
                "port": self.settings.mcp_http_port,
                "base_path": self.settings.mcp_http_base_path,
                "environment": self.settings.environment,
                "oidc_enabled": self.settings.oidc_enabled,
            },
        )

        # Create middleware for correlation ID handling
        middleware = [
            Middleware(CorrelationIDMiddleware),
        ]

        # Add auth middleware if OIDC is enabled
        if self.settings.oidc_enabled:
            from routeros_mcp.mcp.transport.auth_middleware import AuthMiddleware
            from routeros_mcp.security.oidc import OIDCValidator

            # Create OIDC validator
            validator = OIDCValidator(
                provider_url=self.settings.oidc_provider_url,
                client_id=self.settings.oidc_client_id,
                audience=self.settings.oidc_audience,
                skip_verification=self.settings.oidc_skip_verification,
            )

            # Add auth middleware to stack
            middleware.append(
                Middleware(
                    AuthMiddleware,
                    validator=validator,
                    # Exempt health endpoints with and without base path, and with/without trailing slash
                    exempt_paths=[
                        "/health",
                        "/health/",
                        f"{self.settings.mcp_http_base_path.rstrip('/')}/health",
                        f"{self.settings.mcp_http_base_path.rstrip('/')}/health/",
                    ],
                )
            )

            logger.info(
                "OIDC authentication middleware enabled",
                extra={
                    "provider_url": self.settings.oidc_provider_url,
                    "client_id": self.settings.oidc_client_id,
                    "skip_verification": self.settings.oidc_skip_verification,
                },
            )

        # Run FastMCP with SSE transport
        # FastMCP's run_http_async handles the actual HTTP/SSE server
        # Note: Admin API routes need to be integrated through FastMCP's custom_route
        # decorator or by modifying how the transport creates its internal app.
        # The admin router is defined in routeros_mcp/api/admin.py with prefix="/admin"
        # and routes like "/api/plans", resulting in paths at "/admin/api/plans".
        await self.mcp_instance.run_http_async(
            transport="sse",
            host=self.settings.mcp_http_host,
            port=self.settings.mcp_http_port,
            path=self.settings.mcp_http_base_path,
            log_level=self.settings.log_level.lower(),
            show_banner=True,
            middleware=middleware,
        )

    async def handle_request(self, request: Request) -> JSONResponse | EventSourceResponse:
        """Handle MCP JSON-RPC request over HTTP POST.

        This method provides custom request processing on top of FastMCP's
        built-in HTTP handling. It extracts correlation IDs, validates
        requests, propagates user context, and returns properly formatted
        JSON-RPC responses.

        For streaming requests (stream_progress=true), returns an
        EventSourceResponse with progress events and final result.
        For non-streaming requests, returns a standard JSONResponse.

        Args:
            request: HTTP request containing JSON-RPC payload

        Returns:
            JSON-RPC response (success or error) or SSE event stream
        """
        # Extract correlation ID (already set by middleware)
        correlation_id = get_correlation_id()

        logger.info(
            "Received MCP JSON-RPC request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "correlation_id": correlation_id,
            },
        )

        body: dict[str, Any] = {}
        request_id = None

        try:
            # Parse JSON-RPC request
            body = await request.json()
            request_id = body.get("id") if isinstance(body, dict) else None

            # Validate JSON-RPC structure
            valid, error_msg = validate_jsonrpc_request(body)
            if not valid:
                logger.warning(
                    f"Invalid JSON-RPC request: {error_msg}",
                    extra={"correlation_id": correlation_id},
                )
                error_response = create_error_response(
                    request_id=request_id,
                    error=InvalidRequestError(error_msg, data={"detail": error_msg}),
                )
                return JSONResponse(
                    error_response,
                    status_code=400,
                    headers={"X-Correlation-ID": correlation_id},
                )

            # Extract user context from auth middleware (if available)
            user_context = getattr(getattr(request, "state", None), "user", None)

            # Check if streaming is requested
            params = body.get("params", {})
            if is_streaming_request(params):
                # Return SSE stream for streaming requests
                logger.info(
                    "Processing streaming request",
                    extra={"correlation_id": correlation_id, "request_id": request_id},
                )
                return await self._handle_streaming_request(
                    body, user_context, correlation_id
                )

            # Process MCP request (non-streaming)
            response = await self._process_mcp_request(body, user_context=user_context)

            return JSONResponse(
                response,
                headers={"X-Correlation-ID": correlation_id},
            )

        except json.JSONDecodeError as e:
            logger.warning(
                f"JSON parse error: {e}",
                extra={"correlation_id": correlation_id},
            )
            error_response = create_error_response(
                request_id=None,
                error=ParseError(
                    "Invalid JSON in request body",
                    data={"detail": str(e)},
                ),
            )
            return JSONResponse(
                error_response,
                status_code=400,
                headers={"X-Correlation-ID": correlation_id},
            )

        except MCPError as e:
            logger.error(
                f"MCP error processing request: {e}",
                extra={
                    "correlation_id": correlation_id,
                    "error_code": e.code,
                },
                exc_info=True,
            )
            error_response = create_error_response(request_id=request_id, error=e)
            return JSONResponse(
                error_response,
                status_code=500,
                headers={"X-Correlation-ID": correlation_id},
            )

        except Exception as e:
            logger.error(
                f"Unexpected error processing MCP request: {e}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            mapped_error = map_exception_to_error(e)
            error_response = create_error_response(request_id=request_id, error=mapped_error)
            return JSONResponse(
                error_response,
                status_code=500,
                headers={"X-Correlation-ID": correlation_id},
            )

    async def _process_mcp_request(
        self,
        request: dict[str, Any],
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process MCP JSON-RPC request using FastMCP's internal handler.

        This method integrates with FastMCP's internal request processing
        while adding support for correlation IDs and user context propagation.

        Args:
            request: JSON-RPC request dictionary
            user_context: Optional user context from authentication middleware

        Returns:
            JSON-RPC response dictionary

        Raises:
            MethodNotFoundError: If method is not found
            InvalidParamsError: If params are invalid
            MCPError: For other MCP-specific errors
        """
        from routeros_mcp.mcp.errors import (
            InvalidParamsError,
            MethodNotFoundError,
        )

        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params", {})

        logger.info(
            f"Processing MCP method: {method}",
            extra={
                "method": method,
                "request_id": request_id,
                "has_user_context": user_context is not None,
            },
        )

        # For notifications (no id), we should not return a response per JSON-RPC 2.0
        # For now, we require id to be present (validated earlier in handle_request)
        # If request_id is None at this point, it's a server error
        if request_id is None:
            raise ValueError("Request ID is required for JSON-RPC responses")

        try:
            # Route to appropriate FastMCP internal handler based on method
            if method == "tools/call":
                # Extract tool name and arguments
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if not tool_name:
                    raise InvalidParamsError(
                        "Missing required parameter: name",
                        data={"field": "name", "details": "Tool name is required"},
                    )

                # Add user context to arguments if available
                # This allows tools to access authenticated user information
                if user_context and isinstance(arguments, dict):
                    arguments = dict(arguments)  # Create a copy to avoid modifying original
                    arguments["_user"] = user_context

                # Call FastMCP's internal tool handler
                tool_result = await self.mcp_instance._call_tool_mcp(tool_name, arguments)

                # Convert FastMCP result to MCP format
                result = self._format_tool_result(tool_result)

            elif method == "tools/list":
                # List all available tools
                tools = await self.mcp_instance._list_tools_mcp()

                # Convert to MCP format
                result = {
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "inputSchema": tool.inputSchema,
                        }
                        for tool in tools
                    ]
                }

            elif method == "resources/read":
                # Read a resource
                uri = params.get("uri")
                if not uri:
                    raise InvalidParamsError(
                        "Missing required parameter: uri",
                        data={"field": "uri", "details": "Resource URI is required"},
                    )

                # Call FastMCP's internal resource handler
                resource_contents = await self.mcp_instance._read_resource_mcp(uri)

                # Convert to MCP format
                result = {
                    "contents": [
                        {
                            "uri": str(content.uri),
                            "mimeType": content.mimeType or "text/plain",
                            **({"text": content.text} if content.text else {}),
                            **({"blob": content.blob} if content.blob else {}),
                        }
                        for content in resource_contents
                    ]
                }

            elif method == "resources/list":
                # List all available resources
                resources = await self.mcp_instance._list_resources_mcp()

                # Convert to MCP format
                result = {
                    "resources": [
                        {
                            "uri": str(resource.uri),
                            "name": resource.name,
                            "description": resource.description or "",
                            "mimeType": resource.mimeType or "text/plain",
                        }
                        for resource in resources
                    ]
                }

            elif method == "prompts/get":
                # Get a specific prompt
                name = params.get("name")
                arguments = params.get("arguments", {})

                if not name:
                    raise InvalidParamsError(
                        "Missing required parameter: name",
                        data={"field": "name", "details": "Prompt name is required"},
                    )

                # Call FastMCP's internal prompt handler
                prompt_result = await self.mcp_instance._get_prompt_mcp(name, arguments)

                # Convert to MCP format
                result = {
                    "description": prompt_result.description or "",
                    "messages": [
                        {
                            "role": msg.role,
                            "content": {
                                "type": msg.content.type,
                                **({"text": msg.content.text} if hasattr(msg.content, "text") else {}),
                            },
                        }
                        for msg in prompt_result.messages
                    ],
                }

            elif method == "prompts/list":
                # List all available prompts
                prompts = await self.mcp_instance._list_prompts_mcp()

                # Convert to MCP format
                result = {
                    "prompts": [
                        {
                            "name": prompt.name,
                            "description": prompt.description or "",
                            "arguments": prompt.arguments or [],
                        }
                        for prompt in prompts
                    ]
                }

            elif method == "initialize":
                # Handle initialize (should be handled by FastMCP but provide fallback)
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "resources": {"subscribe": True, "listChanged": True},
                        "prompts": {"listChanged": True},
                        "logging": {},
                    },
                    "serverInfo": {
                        "name": self.mcp_instance.name,
                        "version": self.mcp_instance.version,
                    },
                }

            else:
                # Unknown method
                raise MethodNotFoundError(
                    f"Method '{method}' not found",
                    data={"method": method, "supported_methods": [
                        "initialize",
                        "tools/call",
                        "tools/list",
                        "resources/read",
                        "resources/list",
                        "prompts/get",
                        "prompts/list",
                    ]},
                )

            return create_success_response(request_id=request_id, result=result)

        except (MethodNotFoundError, InvalidParamsError):
            # Re-raise MCP errors as-is
            raise

        except Exception as e:
            logger.error(
                f"Error in _process_mcp_request: {e}",
                extra={"method": method, "request_id": request_id},
                exc_info=True,
            )
            # Map generic exceptions to MCP errors
            raise map_exception_to_error(e)

    async def _handle_streaming_request(
        self,
        request: dict[str, Any],
        user_context: dict[str, Any] | None,
        correlation_id: str,
    ) -> EventSourceResponse:
        """Handle streaming MCP request with progress updates via SSE.

        For streaming requests (stream_progress=true), this method:
        1. Calls the tool which may yield progress dictionaries
        2. Sends each progress as an SSE event: event: progress
        3. Sends the final result as an SSE event: event: result

        Args:
            request: JSON-RPC request dictionary
            user_context: Optional user context from authentication
            correlation_id: Request correlation ID

        Returns:
            EventSourceResponse with progress and result events

        Raises:
            MethodNotFoundError: If method is not found
            InvalidParamsError: If params are invalid
            MCPError: For other MCP-specific errors
        """
        from routeros_mcp.mcp.errors import InvalidParamsError, MethodNotFoundError

        method = request.get("method")
        request_id: str | int | None = request.get("id")
        params = request.get("params", {})

        logger.info(
            f"Processing streaming MCP method: {method}",
            extra={
                "method": method,
                "request_id": request_id,
                "has_user_context": user_context is not None,
                "correlation_id": correlation_id,
            },
        )

        async def event_generator() -> AsyncIterator[dict[str, str]]:
            """Generate SSE events for streaming tool execution."""
            try:
                # Only tools/call supports streaming currently
                if method != "tools/call":
                    # Send error as SSE event
                    error_response = create_error_response(
                        request_id=request_id,
                        error=MethodNotFoundError(
                            f"Streaming not supported for method '{method}'",
                            data={"method": method},
                        ),
                    )
                    yield {
                        "event": "error",
                        "data": json.dumps(error_response),
                    }
                    return

                # Extract tool name and arguments
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if not tool_name:
                    error_response = create_error_response(
                        request_id=request_id,
                        error=InvalidParamsError(
                            "Missing required parameter: name",
                            data={"field": "name", "details": "Tool name is required"},
                        ),
                    )
                    yield {
                        "event": "error",
                        "data": json.dumps(error_response),
                    }
                    return

                # Add user context to arguments if available
                if user_context and isinstance(arguments, dict):
                    arguments = dict(arguments)
                    arguments["_user"] = user_context

                # Call FastMCP's internal tool handler
                tool_result = await self.mcp_instance._call_tool_mcp(tool_name, arguments)

                # Check if result is a generator (streaming tool)
                if hasattr(tool_result, "__aiter__"):
                    # Async generator - stream progress events
                    # Note: Tools should yield progress messages followed by exactly one final result.
                    # If multiple non-progress items are yielded, only the last one will be sent.
                    final_result = None
                    async for item in tool_result:
                        if isinstance(item, dict) and item.get("type") == "progress":
                            # Progress event
                            yield {
                                "event": "progress",
                                "data": json.dumps(item),
                            }
                        else:
                            # Final result (only last non-progress item is kept)
                            final_result = item

                    # Send final result
                    if final_result is not None:
                        result = self._format_tool_result(final_result)
                        if request_id is not None:
                            response = create_success_response(
                                request_id=request_id, result=result
                            )
                            yield {
                                "event": "result",
                                "data": json.dumps(response),
                            }
                    else:
                        # Streaming tool must yield at least one non-progress result
                        error_response = create_error_response(
                            request_id=request_id,
                            error=InvalidParamsError(
                                "Streaming tool must yield at least one non-progress result",
                                data={"tool_name": tool_name},
                            ),
                        )
                        yield {
                            "event": "error",
                            "data": json.dumps(error_response),
                        }
                else:
                    # Non-streaming result - send as single result event
                    result = self._format_tool_result(tool_result)
                    if request_id is not None:
                        response = create_success_response(request_id=request_id, result=result)
                        yield {
                            "event": "result",
                            "data": json.dumps(response),
                        }

            except (MethodNotFoundError, InvalidParamsError) as e:
                logger.error(
                    f"MCP error in streaming request: {e}",
                    extra={"correlation_id": correlation_id},
                    exc_info=True,
                )
                error_response = create_error_response(request_id=request_id, error=e)
                yield {
                    "event": "error",
                    "data": json.dumps(error_response),
                }

            except MCPError as e:
                logger.error(
                    f"MCP error in streaming request: {e}",
                    extra={"correlation_id": correlation_id},
                    exc_info=True,
                )
                error_response = create_error_response(request_id=request_id, error=e)
                yield {
                    "event": "error",
                    "data": json.dumps(error_response),
                }

            except Exception as e:
                logger.error(
                    f"Unexpected error in streaming request: {e}",
                    extra={"correlation_id": correlation_id},
                    exc_info=True,
                )
                mapped_error = map_exception_to_error(e)
                error_response = create_error_response(request_id=request_id, error=mapped_error)
                yield {
                    "event": "error",
                    "data": json.dumps(error_response),
                }

        return EventSourceResponse(
            event_generator(),
            headers={
                "X-Correlation-ID": correlation_id,
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    def _format_tool_result(self, tool_result: Any) -> dict[str, Any]:
        """Format tool result into MCP result structure.

        Handles different result types from FastMCP tools.

        Args:
            tool_result: Result from FastMCP tool call

        Returns:
            Formatted MCP result dictionary
        """
        if hasattr(tool_result, "content"):
            # CallToolResult object
            return {
                "content": [
                    {"type": item.type, **item.model_dump(exclude={"type"})}
                    for item in tool_result.content
                ],
                "isError": getattr(tool_result, "isError", False),
            }
        elif isinstance(tool_result, tuple):
            # Tuple of (content, metadata)
            content_list, metadata = tool_result
            return {
                "content": [
                    {"type": item.type, **item.model_dump(exclude={"type"})}
                    for item in content_list
                ],
                "isError": False,
                "_meta": metadata,
            }
        else:
            # List of content blocks
            return {
                "content": [
                    {"type": item.type, **item.model_dump(exclude={"type"})}
                    for item in tool_result
                ],
                "isError": False,
            }

    async def stop(self) -> None:
        """Stop the HTTP/SSE transport server.

        Note: FastMCP's run_http_async handles cleanup automatically
        when the server is stopped.
        """
        logger.info("Stopping HTTP/SSE transport server")
        # FastMCP handles cleanup in run_http_async

    def _register_subscription_route(self) -> None:
        """Register SSE subscription endpoint with FastMCP if supported."""
        subscribe_path = f"{self.settings.mcp_http_base_path.rstrip('/')}/subscribe"

        custom_route = getattr(self.mcp_instance, "custom_route", None)
        if not callable(custom_route):
            logger.warning(
                "FastMCP instance does not support custom routes; SSE subscriptions unavailable",
                extra={"path": subscribe_path},
            )
            return

        @custom_route(subscribe_path, methods=["POST"])
        async def _subscription_handler(
            request: Request,
        ) -> EventSourceResponse | JSONResponse:
            return await self.handle_subscribe(request)

        logger.info(
            "Registered SSE subscription route",
            extra={"path": subscribe_path},
        )

    async def handle_subscribe(
        self, request: Request
    ) -> EventSourceResponse | JSONResponse:
        """Handle SSE subscription request.

        POST /mcp/subscribe with JSON body:
        {
            "resource_uri": "device://dev-001/health"
        }

        Returns:
            SSE event stream with resource updates
        """
        correlation_id = get_correlation_id()

        try:
            # Parse subscription request
            body = await request.json()
            resource_uri = body.get("resource_uri")

            if not resource_uri:
                return JSONResponse(
                    {
                        "error": "Missing required field: resource_uri",
                        "code": "INVALID_REQUEST",
                    },
                    status_code=400,
                    headers={"X-Correlation-ID": correlation_id},
                )

            # Extract client ID from auth context or generate
            user_context = getattr(getattr(request, "state", None), "user", None)
            client_id = (
                user_context.get("sub") if user_context else f"anonymous-{correlation_id[:8]}"
            )

            logger.info(
                "SSE subscription request received",
                extra={
                    "client_id": client_id,
                    "resource_uri": resource_uri,
                    "correlation_id": correlation_id,
                },
            )

            # Create subscription
            try:
                subscription = await self.sse_manager.subscribe(
                    client_id=client_id,
                    resource_uri=resource_uri,
                )
            except ValueError as e:
                # Subscription limit exceeded
                return JSONResponse(
                    {
                        "error": str(e),
                        "code": "SUBSCRIPTION_LIMIT_EXCEEDED",
                    },
                    status_code=429,
                    headers={"X-Correlation-ID": correlation_id},
                )

            # Stream events to client
            async def event_generator() -> AsyncIterator[dict[str, str]]:
                """Generate SSE events for this subscription."""
                async for event in self.sse_manager.stream_events(subscription):
                    # Format as SSE event
                    yield {
                        "event": event.get("event", "update"),
                        "data": json.dumps(event.get("data", {})),
                    }

            return EventSourceResponse(
                event_generator(),
                headers={
                    "X-Correlation-ID": correlation_id,
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                },
            )

        except json.JSONDecodeError:
            return JSONResponse(
                {
                    "error": "Invalid JSON in request body",
                    "code": "PARSE_ERROR",
                },
                status_code=400,
                headers={"X-Correlation-ID": correlation_id},
            )
        except Exception as e:
            logger.error(
                f"Error handling SSE subscription: {e}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            return JSONResponse(
                {
                    "error": "Internal server error",
                    "code": "INTERNAL_ERROR",
                    "detail": str(e),
                },
                status_code=500,
                headers={"X-Correlation-ID": correlation_id},
            )


__all__ = ["HTTPSSETransport"]
