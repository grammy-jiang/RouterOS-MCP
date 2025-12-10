"""HTTP/SSE transport for MCP protocol.

Implements HTTP endpoints for MCP JSON-RPC and Server-Sent Events
for streaming responses and notifications.

See docs/14-mcp-protocol-integration-and-transport-design.md for
detailed requirements.
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route
from sse_starlette import EventSourceResponse

from routeros_mcp.config import Settings
from routeros_mcp.infra.observability import get_correlation_id, set_correlation_id

logger = logging.getLogger(__name__)


class MCPHTTPTransport:
    """HTTP/SSE transport for MCP protocol.

    Provides:
    - HTTP POST endpoint for MCP JSON-RPC requests
    - Server-Sent Events (SSE) endpoint for streaming
    - Connection lifecycle management
    - Correlation ID propagation from HTTP headers

    The transport handles authentication via middleware and delegates
    actual MCP request processing to the MCP server.
    """

    def __init__(
        self,
        settings: Settings,
        mcp_handler: Any,  # The actual MCP server/handler
    ) -> None:
        """Initialize HTTP transport.

        Args:
            settings: Application settings
            mcp_handler: MCP request handler (FastMCP instance or compatible)
        """
        self.settings = settings
        self.mcp_handler = mcp_handler
        self.app = self._create_app()

    def _create_app(self) -> Starlette:
        """Create Starlette application with routes.

        Returns:
            Starlette app
        """
        routes = [
            Route(
                f"{self.settings.mcp_http_base_path}/rpc",
                self.handle_jsonrpc,
                methods=["POST"],
            ),
            Route(
                f"{self.settings.mcp_http_base_path}/sse",
                self.handle_sse,
                methods=["GET"],
            ),
            Route(
                f"{self.settings.mcp_http_base_path}/health",
                self.handle_health,
                methods=["GET"],
            ),
        ]

        app = Starlette(debug=self.settings.debug, routes=routes)
        return app

    async def handle_jsonrpc(self, request: Request) -> JSONResponse:
        """Handle MCP JSON-RPC request over HTTP POST.

        Processes a single JSON-RPC request and returns the response.

        Args:
            request: HTTP request

        Returns:
            JSON-RPC response
        """
        # Extract correlation ID from header or generate new one
        correlation_id = request.headers.get("X-Correlation-ID", get_correlation_id())
        set_correlation_id(correlation_id)

        logger.info(
            "Received MCP JSON-RPC request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "correlation_id": correlation_id,
            },
        )

        try:
            # Parse JSON-RPC request
            body = await request.json()

            # Validate basic JSON-RPC structure
            if not isinstance(body, dict):
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32600,
                            "message": "Invalid Request",
                            "data": {"detail": "Request body must be a JSON object"},
                        },
                    },
                    status_code=400,
                )

            # Add user context from auth middleware (if available)
            user_context = getattr(request.state, "user", None)
            if user_context:
                body["_user"] = user_context

            # Process MCP request
            # Note: This is a simplified handler. Real implementation would
            # need to integrate with FastMCP's internal request handling
            response = await self._process_mcp_request(body)

            return JSONResponse(
                response,
                headers={
                    "X-Correlation-ID": correlation_id,
                },
            )

        except json.JSONDecodeError:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Parse error",
                        "data": {"detail": "Invalid JSON in request body"},
                    },
                },
                status_code=400,
                headers={"X-Correlation-ID": correlation_id},
            )

        except Exception as e:
            logger.error(f"Error processing MCP request: {e}", exc_info=True)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": body.get("id") if isinstance(body, dict) else None,
                    "error": {
                        "code": -32603,
                        "message": "Internal error",
                        "data": {"detail": str(e)},
                    },
                },
                status_code=500,
                headers={"X-Correlation-ID": correlation_id},
            )

    async def handle_sse(self, request: Request) -> EventSourceResponse:
        """Handle Server-Sent Events connection for streaming.

        Establishes a persistent connection for streaming MCP events
        and responses to the client.

        Args:
            request: HTTP request

        Returns:
            SSE event stream
        """
        correlation_id = request.headers.get("X-Correlation-ID", get_correlation_id())
        set_correlation_id(correlation_id)

        logger.info(
            "SSE connection established",
            extra={
                "path": request.url.path,
                "correlation_id": correlation_id,
            },
        )

        async def event_generator() -> AsyncIterator[dict[str, str]]:
            """Generate SSE events."""
            try:
                # Send initial connection event
                yield {
                    "event": "connected",
                    "data": json.dumps(
                        {
                            "correlation_id": correlation_id,
                            "server": "routeros-mcp",
                            "version": "0.1.0",
                        }
                    ),
                }

                # Keep connection alive with periodic pings
                while True:
                    await asyncio.sleep(30)
                    yield {
                        "event": "ping",
                        "data": json.dumps({"timestamp": asyncio.get_event_loop().time()}),
                    }

            except asyncio.CancelledError:
                logger.info(
                    "SSE connection closed",
                    extra={"correlation_id": correlation_id},
                )
                raise

        return EventSourceResponse(
            event_generator(),
            headers={
                "X-Correlation-ID": correlation_id,
                "Cache-Control": "no-cache",
            },
        )

    async def handle_health(self, request: Request) -> JSONResponse:
        """Handle health check endpoint.

        Args:
            request: HTTP request

        Returns:
            Health status
        """
        return JSONResponse(
            {
                "status": "healthy",
                "transport": "http",
                "environment": self.settings.environment,
            }
        )

    async def _process_mcp_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Process MCP JSON-RPC request.

        This is a placeholder that would integrate with FastMCP's
        internal request handling in the actual implementation.

        Args:
            request: JSON-RPC request

        Returns:
            JSON-RPC response
        """
        # For now, return a basic response structure
        # Real implementation would call into FastMCP's handler
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        logger.info(
            f"Processing MCP method: {method}",
            extra={
                "method": method,
                "request_id": request_id,
            },
        )

        # This would be replaced with actual MCP processing
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "HTTP transport placeholder - method processing not yet implemented",
                    }
                ],
                "_meta": {
                    "method": method,
                    "transport": "http",
                },
            },
        }


__all__ = ["MCPHTTPTransport"]
