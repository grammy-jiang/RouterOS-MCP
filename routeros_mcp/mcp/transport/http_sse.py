"""HTTP/SSE transport implementation using FastMCP's built-in HTTP support.

This module provides a transport class that delegates to FastMCP's native
HTTP/SSE transport via run_http_async(). Unlike the http.py module which
implements a custom Starlette-based transport, this leverages FastMCP's
built-in capabilities.

See docs/14-mcp-protocol-integration-and-transport-design.md
"""

import logging
from typing import Any

from routeros_mcp.config import Settings

logger = logging.getLogger(__name__)


class HTTPSSETransport:
    """HTTP/SSE transport using FastMCP's built-in HTTP support.

    This transport delegates to FastMCP's run_http_async() method which
    provides SSE (Server-Sent Events) support out of the box.

    The transport integrates with the RouterOS MCP server and uses
    configuration settings to determine host, port, and path.
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
        )

    async def stop(self) -> None:
        """Stop the HTTP/SSE transport server.

        Note: FastMCP's run_http_async handles cleanup automatically
        when the server is stopped.
        """
        logger.info("Stopping HTTP/SSE transport server")
        # FastMCP handles cleanup in run_http_async


__all__ = ["HTTPSSETransport"]
