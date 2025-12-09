"""RouterOS MCP Service - Model Context Protocol service for MikroTik RouterOS devices.

This package provides a production-ready MCP service that exposes safe, well-typed,
auditable operations for managing RouterOS v7 devices via their REST API and SSH/CLI.
"""

__version__ = "0.1.0"
__author__ = "RouterOS MCP Contributors"

from routeros_mcp.config import Settings, get_settings, load_settings_from_file, set_settings

__all__ = [
    "Settings",
    "__version__",
    "get_settings",
    "load_settings_from_file",
    "set_settings",
]
