"""Run RouterOS-MCP using HTTP/SSE transport (developer utility).

Purpose:
        Convenience launcher for MCP over HTTP/SSE ("streamable HTTP") when integrating
        with editors or tools that expect a network endpoint rather than stdio.
        This bypasses the stdio entrypoint and starts FastMCP's HTTP server directly.

Notes:
        - Tools, resources, and prompts are registered at server init.
        - Database session manager is initialized before registering dynamic resources.
        - Transport is forced to ``http`` for this launcher regardless of config.

Security & production guidance:
        - In production, enable OAuth/OIDC (see docs/02) and run behind a secure ingress.
        - For lab/staging, this can run without OAuth, but treat it as trusted only on localhost or
            a secure network segment.

Usage example:
        python scripts/run_mcp_streamable_http.py --config config/lab.yaml \
                --mcp-host 127.0.0.1 --mcp-port 8765
"""

from __future__ import annotations

import asyncio
import sys


async def _amain() -> int:
    # Reuse the existing CLI config loader so env/config precedence stays consistent.
    from routeros_mcp.cli import load_config_from_cli
    from routeros_mcp.config import set_settings
    from routeros_mcp.infra.db.session import initialize_session_manager
    from routeros_mcp.mcp_resources import (
        register_audit_resources,
        register_device_resources,
        register_fleet_resources,
        register_plan_resources,
    )
    from routeros_mcp.mcp.server import RouterOSMCPServer

    settings = load_config_from_cli()

    # Ensure transport is HTTP (this launcher is specifically for HTTP streaming).
    # We don't call routeros_mcp.main; we start FastMCP's Streamable HTTP server directly.
    settings.mcp_transport = "http"
    set_settings(settings)

    srv = RouterOSMCPServer(settings)

    session_factory = await initialize_session_manager(settings)

    # Register resources (FastMCP keeps resource templates even if dynamic)
    register_device_resources(srv.mcp, session_factory, settings)
    register_fleet_resources(srv.mcp, session_factory, settings)
    register_plan_resources(srv.mcp, session_factory, settings)
    register_audit_resources(srv.mcp, session_factory, settings)

    host = settings.mcp_http_host
    port = settings.mcp_http_port
    path = settings.mcp_http_base_path
    log_level = settings.log_level.lower()

    # FastMCP 2.3.2+ deprecates run_streamable_http_async in favor of run_http_async.
    await srv.mcp.run_http_async(
        host=host,
        port=port,
        path=path,
        log_level=log_level,
    )
    return 0


def main() -> int:
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
