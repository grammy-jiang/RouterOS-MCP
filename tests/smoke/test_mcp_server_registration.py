"""Smoke tests for MCP server wiring and registration."""

import asyncio

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp.server import RouterOSMCPServer, create_mcp_server


pytestmark = pytest.mark.smoke


def test_mcp_server_initializes_with_tools() -> None:
    """Instantiating the server should register core tools like echo and service_health."""

    server = RouterOSMCPServer(Settings())

    assert server.mcp is not None
    # Ensure the FastMCP instance exposes the tool decorator and registered callbacks exist
    assert hasattr(server.mcp, "tool")
    assert callable(getattr(server.mcp, "tool"))

    tools = asyncio.run(server.mcp.get_tools())
    # fastmcp returns a list of tool identifiers (strings)
    names = set(tools)
    assert "echo" in names
    assert "service_health" in names


def test_create_mcp_server_factory_returns_instance() -> None:
    """Factory helper should asynchronously create a RouterOSMCPServer instance."""

    server = asyncio.run(create_mcp_server(Settings()))
    assert isinstance(server, RouterOSMCPServer)
    assert server.settings.environment == "lab"


@pytest.mark.asyncio
async def test_echo_tool_round_trip_smoke() -> None:
    """Echo tool should respond with formatted content and metadata."""

    server = RouterOSMCPServer(Settings())

    tool = await server.mcp.get_tool("echo")
    result = await tool.fn(message="hello")

    assert isinstance(result, dict)
    assert result.get("content", [])[0]["text"].startswith("Echo: hello")
    assert result.get("_meta", {}).get("environment") == "lab"


@pytest.mark.asyncio
async def test_service_health_tool_smoke() -> None:
    """Service health tool should return a healthy status payload."""

    server = RouterOSMCPServer(Settings())

    tool = await server.mcp.get_tool("service_health")
    result = await tool.fn()

    assert result.get("content", [])[0]["text"] == "Service is running"
    assert result.get("_meta", {}).get("transport") == server.settings.mcp_transport
