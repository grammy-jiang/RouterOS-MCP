"""Tests for HTTP/SSE transport implementation."""

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp.transport.http_sse import HTTPSSETransport


@pytest.mark.asyncio
async def test_http_sse_transport_initialization() -> None:
    """Test HTTPSSETransport initializes correctly."""
    settings = Settings(
        mcp_transport="http",
        mcp_http_host="0.0.0.0",
        mcp_http_port=8080,
        mcp_http_base_path="/mcp",
    )
    mock_mcp = MagicMock()

    transport = HTTPSSETransport(settings, mock_mcp)

    assert transport.settings == settings
    assert transport.mcp_instance == mock_mcp


@pytest.mark.asyncio
async def test_http_sse_transport_run_success() -> None:
    """Test HTTPSSETransport.run() calls FastMCP's run_http_async."""
    settings = Settings(
        mcp_transport="http",
        mcp_http_host="127.0.0.1",
        mcp_http_port=9090,
        mcp_http_base_path="/api/mcp",
        log_level="DEBUG",
        environment="lab",
    )

    # Create mock with async run_http_async method
    mock_mcp = MagicMock()
    mock_mcp.run_http_async = AsyncMock()

    transport = HTTPSSETransport(settings, mock_mcp)
    await transport.run()

    # Verify run_http_async was called with correct parameters
    mock_mcp.run_http_async.assert_awaited_once_with(
        transport="sse",
        host="127.0.0.1",
        port=9090,
        path="/api/mcp",
        log_level="debug",
        show_banner=True,
    )


@pytest.mark.asyncio
async def test_http_sse_transport_run_missing_method() -> None:
    """Test HTTPSSETransport.run() raises error if run_http_async is missing."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock(spec=[])  # Empty spec, no run_http_async

    transport = HTTPSSETransport(settings, mock_mcp)

    with pytest.raises(RuntimeError, match="does not support HTTP transport"):
        await transport.run()


@pytest.mark.asyncio
async def test_http_sse_transport_stop() -> None:
    """Test HTTPSSETransport.stop() completes successfully."""
    settings = Settings(mcp_transport="http")
    mock_mcp = MagicMock()

    transport = HTTPSSETransport(settings, mock_mcp)
    await transport.stop()

    # Stop should complete without error (cleanup handled by FastMCP)


@pytest.mark.asyncio
async def test_http_sse_transport_uses_config_values() -> None:
    """Test HTTPSSETransport respects all configuration values."""
    settings = Settings(
        mcp_transport="http",
        mcp_http_host="192.168.1.100",
        mcp_http_port=3000,
        mcp_http_base_path="/custom/path",
        log_level="WARNING",
    )

    mock_mcp = MagicMock()
    mock_mcp.run_http_async = AsyncMock()

    transport = HTTPSSETransport(settings, mock_mcp)
    await transport.run()

    # Verify all config values are passed correctly
    call_kwargs = mock_mcp.run_http_async.call_args.kwargs
    assert call_kwargs["host"] == "192.168.1.100"
    assert call_kwargs["port"] == 3000
    assert call_kwargs["path"] == "/custom/path"
    assert call_kwargs["log_level"] == "warning"
    assert call_kwargs["transport"] == "sse"


@pytest.mark.asyncio
async def test_http_sse_transport_default_settings() -> None:
    """Test HTTPSSETransport works with default settings."""
    settings = Settings()  # All defaults
    assert settings.mcp_transport == "stdio"  # Default is stdio

    # Override for HTTP
    settings = Settings(mcp_transport="http")

    mock_mcp = MagicMock()
    mock_mcp.run_http_async = AsyncMock()

    transport = HTTPSSETransport(settings, mock_mcp)
    await transport.run()

    # Verify defaults are used
    call_kwargs = mock_mcp.run_http_async.call_args.kwargs
    assert call_kwargs["host"] == "127.0.0.1"  # Default from config
    assert call_kwargs["port"] == 8080  # Default from config
    assert call_kwargs["path"] == "/mcp"  # Default from config
