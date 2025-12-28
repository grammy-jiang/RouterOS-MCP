"""CLI module for RouterOS MCP admin tools."""

# Re-export base CLI functionality for backward compatibility
from routeros_mcp.cli.base import create_argument_parser, load_config_from_cli

__all__ = ["admin", "create_argument_parser", "load_config_from_cli"]
