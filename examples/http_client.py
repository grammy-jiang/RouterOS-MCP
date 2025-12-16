#!/usr/bin/env python3
"""
HTTP client example for RouterOS MCP service.

This script demonstrates how to:
1. Obtain OAuth access token from OIDC provider
2. Initialize MCP session over HTTP
3. Call MCP tools (e.g., system/get-overview)
4. Subscribe to SSE resource updates (optional)

Requirements:
    pip install httpx authlib

Usage:
    # Configure environment
    export MCP_BASE_URL=https://mcp.example.com
    export OIDC_PROVIDER_URL=https://your-oidc-provider.com
    export OIDC_CLIENT_ID=your-client-id
    export OIDC_CLIENT_SECRET=your-client-secret

    # Run script
    python examples/http_client.py

    # Or with inline config
    python examples/http_client.py --mcp-url https://mcp.example.com --device-id dev-001
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import httpx


class MCPHTTPClient:
    """HTTP client for RouterOS MCP service."""

    def __init__(
        self,
        mcp_url: str,
        oidc_provider_url: str,
        client_id: str,
        client_secret: str,
        audience: str | None = None,
    ):
        """Initialize MCP HTTP client.

        Args:
            mcp_url: Base URL of MCP service (e.g., https://mcp.example.com)
            oidc_provider_url: OIDC provider URL (e.g., https://auth0.example.com)
            client_id: OAuth client ID
            client_secret: OAuth client secret
            audience: Optional audience (API identifier)
        """
        self.mcp_url = mcp_url.rstrip("/")
        self.oidc_provider_url = oidc_provider_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.audience = audience or mcp_url
        self.access_token: str | None = None
        self.session_id: int = 0
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.client.aclose()

    async def get_access_token(self) -> str:
        """Obtain OAuth access token using client credentials flow.

        Returns:
            Access token string

        Raises:
            httpx.HTTPError: If token request fails
        """
        print(f"🔑 Requesting access token from {self.oidc_provider_url}...")

        # Determine token endpoint based on provider
        if "auth0.com" in self.oidc_provider_url:
            token_url = f"{self.oidc_provider_url}/oauth/token"
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "audience": self.audience,
                "grant_type": "client_credentials",
            }
            headers = {"Content-Type": "application/json"}
            response = await self.client.post(token_url, json=data, headers=headers)
        elif "okta.com" in self.oidc_provider_url:
            token_url = f"{self.oidc_provider_url}/v1/token"
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
                "scope": "mcp:access",
            }
            response = await self.client.post(
                token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
        else:
            # Generic OIDC (Azure AD, others)
            token_url = f"{self.oidc_provider_url}/token"
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
                "scope": f"{self.audience}/.default",
            }
            response = await self.client.post(
                token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

        response.raise_for_status()
        token_data = response.json()
        self.access_token = token_data["access_token"]
        print(f"✅ Access token obtained (expires in {token_data.get('expires_in', 'unknown')}s)")
        return self.access_token

    async def initialize_session(self) -> dict[str, Any]:
        """Initialize MCP session.

        Returns:
            Server capabilities and info

        Raises:
            httpx.HTTPError: If initialization fails
        """
        if not self.access_token:
            await self.get_access_token()

        print(f"🔌 Initializing MCP session with {self.mcp_url}...")

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {"subscribe": True},
                    "prompts": {},
                },
                "clientInfo": {"name": "http-client-example", "version": "1.0.0"},
            },
        }

        response = await self._call_mcp(request)
        print(f"✅ Session initialized: {response['result']['serverInfo']['name']}")
        return response["result"]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call MCP tool.

        Args:
            tool_name: Tool name (e.g., "system/get-overview")
            arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            httpx.HTTPError: If tool call fails
        """
        print(f"🔧 Calling tool: {tool_name}")

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        response = await self._call_mcp(request)
        print(f"✅ Tool result received ({len(json.dumps(response['result']))} bytes)")
        return response["result"]

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available MCP tools.

        Returns:
            List of tool definitions
        """
        print("📋 Listing available tools...")

        request = {"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/list", "params": {}}

        response = await self._call_mcp(request)
        tools = response["result"]["tools"]
        print(f"✅ Found {len(tools)} tools")
        return tools

    async def get_resource(self, uri: str) -> dict[str, Any]:
        """Get MCP resource.

        Args:
            uri: Resource URI (e.g., "device://dev-001/overview")

        Returns:
            Resource contents
        """
        print(f"📦 Getting resource: {uri}")

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "resources/read",
            "params": {"uri": uri},
        }

        response = await self._call_mcp(request)
        print(f"✅ Resource received")
        return response["result"]

    async def _call_mcp(self, request: dict[str, Any]) -> dict[str, Any]:
        """Make JSON-RPC call to MCP server.

        Args:
            request: JSON-RPC request

        Returns:
            JSON-RPC response

        Raises:
            httpx.HTTPError: If request fails
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

        response = await self.client.post(f"{self.mcp_url}/mcp", json=request, headers=headers)
        response.raise_for_status()

        result = response.json()

        # Check for JSON-RPC error
        if "error" in result:
            error = result["error"]
            raise RuntimeError(f"MCP Error {error['code']}: {error['message']}")

        return result

    def _next_id(self) -> int:
        """Generate next request ID."""
        self.session_id += 1
        return self.session_id


async def main():
    """Main example workflow."""
    parser = argparse.ArgumentParser(description="RouterOS MCP HTTP Client Example")
    parser.add_argument(
        "--mcp-url",
        default=os.getenv("MCP_BASE_URL", "http://localhost:8080"),
        help="MCP service base URL",
    )
    parser.add_argument(
        "--oidc-provider",
        default=os.getenv("OIDC_PROVIDER_URL"),
        help="OIDC provider URL",
    )
    parser.add_argument(
        "--client-id",
        default=os.getenv("OIDC_CLIENT_ID"),
        help="OAuth client ID",
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("OIDC_CLIENT_SECRET"),
        help="OAuth client secret",
    )
    parser.add_argument(
        "--audience",
        default=os.getenv("OIDC_AUDIENCE"),
        help="OAuth audience (optional)",
    )
    parser.add_argument(
        "--device-id",
        default="dev-001",
        help="Device ID for examples",
    )
    args = parser.parse_args()

    # Validate required args
    if not args.oidc_provider or not args.client_id or not args.client_secret:
        print("❌ Error: Missing required OAuth configuration", file=sys.stderr)
        print("", file=sys.stderr)
        print("Set environment variables:", file=sys.stderr)
        print("  export OIDC_PROVIDER_URL=https://your-provider.com", file=sys.stderr)
        print("  export OIDC_CLIENT_ID=your-client-id", file=sys.stderr)
        print("  export OIDC_CLIENT_SECRET=your-client-secret", file=sys.stderr)
        print("", file=sys.stderr)
        print("Or pass as arguments: --oidc-provider --client-id --client-secret", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("RouterOS MCP HTTP Client Example")
    print("=" * 60)
    print()

    try:
        async with MCPHTTPClient(
            mcp_url=args.mcp_url,
            oidc_provider_url=args.oidc_provider,
            client_id=args.client_id,
            client_secret=args.client_secret,
            audience=args.audience,
        ) as client:
            # Step 1: Initialize session
            server_info = await client.initialize_session()
            print()
            print(f"Server: {server_info['serverInfo']['name']} v{server_info['serverInfo']['version']}")
            print(f"Protocol: {server_info['protocolVersion']}")
            print()

            # Step 2: List available tools
            tools = await client.list_tools()
            print()
            print("Available tools:")
            for tool in tools[:10]:  # Show first 10
                print(f"  - {tool['name']}: {tool['description'][:60]}...")
            if len(tools) > 10:
                print(f"  ... and {len(tools) - 10} more")
            print()

            # Step 3: Call a tool (system/get-overview)
            try:
                result = await client.call_tool(
                    "system/get-overview", {"device_id": args.device_id}
                )
                print()
                print(f"System overview for device {args.device_id}:")
                print(json.dumps(result, indent=2))
                print()
            except RuntimeError as e:
                print(f"⚠️  Tool call failed: {e}")
                print()

            # Step 4: Get a resource
            try:
                resource = await client.get_resource(f"device://{args.device_id}/overview")
                print()
                print(f"Resource device://{args.device_id}/overview:")
                print(json.dumps(resource, indent=2))
                print()
            except RuntimeError as e:
                print(f"⚠️  Resource fetch failed: {e}")
                print()

        print("=" * 60)
        print("✅ Example completed successfully")
        print("=" * 60)

    except httpx.HTTPError as e:
        print(f"❌ HTTP Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
