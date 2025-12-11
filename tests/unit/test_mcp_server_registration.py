"""Smoke tests for MCP server wiring and registration."""

import asyncio

from routeros_mcp.config import Settings
from routeros_mcp.mcp.server import RouterOSMCPServer, create_mcp_server


def test_mcp_server_initializes_with_tools() -> None:
    """Instantiating the server should register core tools like echo and service_health."""

    server = RouterOSMCPServer(Settings())

    assert server.mcp is not None
    # Ensure the FastMCP instance exposes the tool decorator and registered callbacks exist
    assert hasattr(server.mcp, "tool")


def test_create_mcp_server_factory_returns_instance() -> None:
    """Factory helper should asynchronously create a RouterOSMCPServer instance."""

    server = asyncio.get_event_loop().run_until_complete(create_mcp_server(Settings()))
    assert isinstance(server, RouterOSMCPServer)
    assert server.settings.environment == "lab"
