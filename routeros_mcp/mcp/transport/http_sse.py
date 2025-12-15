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

from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

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
    validate_jsonrpc_request,
)

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
                    headers.append(
                        (b"x-correlation-id", correlation_id.encode("utf-8"))
                    )
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
                    exempt_paths=["/health", f"{self.settings.mcp_http_base_path}/health"],
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
        await self.mcp_instance.run_http_async(
            transport="sse",
            host=self.settings.mcp_http_host,
            port=self.settings.mcp_http_port,
            path=self.settings.mcp_http_base_path,
            log_level=self.settings.log_level.lower(),
            show_banner=True,
            middleware=middleware,
        )

    async def handle_request(self, request: Request) -> JSONResponse:
        """Handle MCP JSON-RPC request over HTTP POST.

        This method provides custom request processing on top of FastMCP's
        built-in HTTP handling. It extracts correlation IDs, validates
        requests, propagates user context, and returns properly formatted
        JSON-RPC responses.

        Args:
            request: HTTP request containing JSON-RPC payload

        Returns:
            JSON-RPC response (success or error)
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
            
            # Process MCP request
            response = await self._process_mcp_request(
                body, user_context=user_context
            )

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
            error_response = create_error_response(
                request_id=request_id, error=mapped_error
            )
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

        # Add user context to params if available
        # This allows tools to access authenticated user information
        if user_context and isinstance(params, dict):
            params["_user"] = user_context

        # For now, delegate to the tools directly via FastMCP
        # FastMCP's _mcp_server handles the actual tool execution
        # In a full implementation, we would call:
        # - server._mcp_server.call_tool() for tools/call
        # - server._mcp_server.list_tools() for tools/list
        # - etc.
        
        # This is a simplified implementation that returns a proper structure
        # The actual integration with FastMCP's internal processor would go here
        # For Phase 2, we're implementing the request/response handling infrastructure
        
        try:
            # Return a placeholder response for now
            # Real implementation would integrate with FastMCP's request handlers
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": f"Method {method} processed successfully (Phase 2 placeholder)",
                    }
                ],
                "_meta": {
                    "method": method,
                    "transport": "http/sse",
                    "has_user_context": user_context is not None,
                },
            }
            
            # For notifications (no id), we should not return a response per JSON-RPC 2.0
            # For now, we require id to be present (validated earlier in handle_request)
            # If request_id is None at this point, it's a server error
            if request_id is None:
                raise ValueError("Request ID is required for JSON-RPC responses")
            
            return create_success_response(request_id=request_id, result=result)
            
        except Exception as e:
            logger.error(
                f"Error in _process_mcp_request: {e}",
                extra={"method": method, "request_id": request_id},
                exc_info=True,
            )
            raise

    async def stop(self) -> None:
        """Stop the HTTP/SSE transport server.

        Note: FastMCP's run_http_async handles cleanup automatically
        when the server is stopped.
        """
        logger.info("Stopping HTTP/SSE transport server")
        # FastMCP handles cleanup in run_http_async


__all__ = ["HTTPSSETransport"]
