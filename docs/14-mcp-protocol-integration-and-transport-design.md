# MCP Protocol Integration & Transport Design

## Purpose

Define how the RouterOS MCP service implements the Model Context Protocol (MCP) specification, including transport layer choices (stdio vs. HTTP/SSE), protocol lifecycle management, message handling, tool/resource/prompt registration, and integration with the official Python MCP SDK (FastMCP). This document bridges the generic API design in earlier docs with MCP-specific implementation patterns.

---

## MCP Protocol Overview and Compliance

### Protocol Version

This service targets **MCP Specification 2024-11-05** (current stable version).

**Version Negotiation:**

- Server declares support for `2024-11-05` in initialization response
- Client proposes version in initialization request
- Server must respond with same version if supported, or error if unsupported
- Future versions: Maintain backward compatibility where possible

### Core MCP Concepts

The Model Context Protocol enables standardized communication between:

- **MCP Host**: AI application (e.g., Claude Desktop, custom AI agents)
- **MCP Client**: Connection manager within the host
- **MCP Server**: This RouterOS management service

### MCP Architecture Layers

**Data Layer**: JSON-RPC 2.0 messages for:

- Lifecycle management (initialize, ping, notifications)
- Capability negotiation (protocol version, supported features)
- Core primitives (tools, resources, prompts)

**Transport Layer**: Communication channels:

- **Stdio**: For local process integration (development, single-user)
- **HTTP/SSE**: For remote access with OAuth 2.1 (production, multi-user)

---

## Transport Mode Selection and Configuration

### Stdio Transport

**Use Cases:**

- Local development and testing
- Single-user desktop integration with Claude Desktop
- Direct process control and debugging
- Lab environment experimentation

**Configuration Pattern:**

MCP host configuration (e.g., Claude Desktop `claude_desktop_config.json` or VS Code MCP settings):

```json
{
  "mcpServers": {
    "routeros-mcp": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "routeros_mcp.main",
        "--config",
        "/absolute/path/to/config.yaml"
      ],
      "env": {
        "ROUTEROS_MCP_ENVIRONMENT": "lab",
        "ROUTEROS_MCP_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

**Critical Stdio Constraints:**

⚠️ **NEVER write to stdout in stdio mode** - this corrupts JSON-RPC messages.

- Use `stderr` for all logging output
- Configure Python logging to stderr only
- Redirect MCP protocol messages exclusively to stdout
- Use file-based logging for persistent records

**Implementation Pattern:**

```python
import sys
import logging

# Configure logging to stderr only
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# MCP messages go to stdout via SDK
# Never use print() or sys.stdout.write() directly
```

### HTTP/SSE Transport

**Use Cases:**

- Production multi-user deployments
- Remote access via Cloudflare Tunnel
- Centralized server architecture
- Enterprise environments with OAuth/OIDC

**Configuration Pattern:**

Server-side configuration:

```yaml
# config.yaml
mcp:
  transport: http
  http:
    host: 0.0.0.0
    port: 8080
    base_path: /mcp
  sse:
    enabled: true
    endpoint: /mcp/sse
```

MCP host configuration:

```json
{
  "mcpServers": {
    "routeros-mcp": {
      "url": "https://routeros-mcp.example.com/mcp",
      "transport": "sse",
      "auth": {
        "type": "oauth2",
        "authorization_url": "https://idp.example.com/oauth/authorize",
        "token_url": "https://idp.example.com/oauth/token",
        "client_id": "mcp-client-id",
        "client_secret": "***",
        "scopes": ["mcp:tools:read", "mcp:tools:execute"]
      }
    }
  }
}
```

**HTTP/SSE Implementation Requirements:**

- **HTTPS in production** (TLS 1.2+ required)
- **OAuth 2.1 authorization** for authentication
- **Server-Sent Events** for server-to-client notifications
- **CORS headers** if browser-based clients supported
- **Connection pooling** for efficiency

### Transport Decision Matrix

| Factor          | Stdio                | HTTP/SSE            |
| --------------- | -------------------- | ------------------- |
| **Deployment**  | Local process        | Remote server       |
| **Users**       | Single user          | Multi-user          |
| **Auth**        | Environment/config   | OAuth 2.1           |
| **Security**    | OS-level permissions | Network + OAuth     |
| **Scalability** | Not applicable       | Horizontal scaling  |
| **Development** | Fast iteration       | Production-ready    |
| **Debugging**   | Direct logs          | Distributed tracing |

**Recommendation for RouterOS MCP:**

- **Phase 0-1**: Stdio for development and local testing
- **Phase 2+**: HTTP/SSE for production with Cloudflare Tunnel
- **Support both** with configuration-driven selection

---

## MCP SDK Integration (FastMCP for Python)

### Why FastMCP?

The official Python MCP SDK (FastMCP) provides:

1. **Zero-boilerplate tool registration** via decorators
2. **Automatic schema generation** from type hints and docstrings
3. **Built-in protocol compliance** (JSON-RPC 2.0, MCP lifecycle)
4. **Transport abstraction** (stdio and HTTP/SSE support)
5. **Development tools** integration (MCP Inspector compatibility)

### FastMCP Installation

Add to `pyproject.toml`:

```toml
[project]
dependencies = [
    "fastmcp>=0.1.0",
    # ... existing dependencies
]
```

### Basic Server Structure

```python
from fastmcp import FastMCP
from pydantic import BaseModel

# Initialize MCP server
mcp = FastMCP(
    name="routeros-mcp",
    version="1.0.0",
    description="MCP service for managing MikroTik RouterOS v7 devices"
)

# Tool registration with decorators
@mcp.tool()
async def system_get_overview(device_id: str) -> dict:
    """Fetch system overview for a RouterOS device.

    Args:
        device_id: Internal MCP device identifier

    Returns:
        System overview including CPU, memory, uptime, health
    """
    # Implementation delegates to domain services
    device_service = get_device_service()
    system_service = get_system_service()

    device = await device_service.get_device(device_id)
    overview = await system_service.get_overview(device)

    return overview

# Run server (transport auto-detected or configured)
if __name__ == "__main__":
    mcp.run()
```

### Key Patterns

**1. Declarative Tool Definition**

```python
from typing import Literal
from pydantic import BaseModel, Field

class SystemOverviewResult(BaseModel):
    device_id: str
    routeros_version: str
    uptime_seconds: int
    cpu_usage_percent: float
    memory_total_bytes: int
    memory_used_bytes: int
    temperature_celsius: float | None

@mcp.tool()
async def system_get_overview(device_id: str) -> SystemOverviewResult:
    """Fetch comprehensive system overview.

    Args:
        device_id: Device ID from device registry

    Returns:
        Complete system metrics and health status
    """
    # Implementation
    return SystemOverviewResult(...)
```

**2. Resource Definition**

```python
@mcp.resource("device://{device_id}/config")
async def device_config(device_id: str) -> str:
    """RouterOS device configuration snapshot.

    Args:
        device_id: Device identifier

    Returns:
        Configuration export in RouterOS format
    """
    # Fetch config from device or snapshot
    return config_text
```

**3. Prompt Templates**

```python
@mcp.prompt()
async def dns_ntp_rollout_guide(
    environment: Literal["lab", "staging", "prod"] = "lab"
) -> str:
    """Guide for rolling out DNS/NTP changes across devices.

    Args:
        environment: Target environment for rollout

    Returns:
        Step-by-step prompt for DNS/NTP rollout workflow
    """
    return f"""
    DNS/NTP Rollout Guide for {environment} environment:

    1. List devices in {environment}: Use device.list_devices
    2. Plan changes: Use config.plan_dns_ntp_rollout
    3. Review plan output carefully
    4. Obtain approval token (admin users only)
    5. Apply changes: Use config.apply_dns_ntp_rollout with plan_id
    6. Monitor results and health checks

    Always test in lab before staging or production.
    """
```

---

## MCP Protocol Lifecycle Implementation

### 1. Initialization Phase

**Client → Server: Initialize Request**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-11-25",
    "capabilities": {
      "sampling": {},
      "roots": {
        "listChanged": true
      }
    },
    "clientInfo": {
      "name": "claude-desktop",
      "version": "1.0.0"
    }
  }
}
```

**Server → Client: Initialize Response**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-11-25",
    "capabilities": {
      "tools": {},
      "resources": {
        "subscribe": true,
        "listChanged": true
      },
      "prompts": {
        "listChanged": true
      },
      "logging": {}
    },
    "serverInfo": {
      "name": "routeros-mcp",
      "version": "1.0.0"
    }
  }
}
```

**Implementation with FastMCP:**

FastMCP handles initialization automatically. Configuration:

```python
from fastmcp import FastMCP

mcp = FastMCP(
    name="routeros-mcp",
    version="1.0.0",
    description="RouterOS management via MCP",
    capabilities={
        "tools": {},
        "resources": {"subscribe": True, "listChanged": True},
        "prompts": {"listChanged": True},
        "logging": {}
    }
)
```

### 2. Discovery Phase

**Tools List Request:**

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

**Tools List Response:**

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "system_get_overview",
        "description": "Fetch system overview for a RouterOS device",
        "inputSchema": {
          "type": "object",
          "properties": {
            "device_id": {
              "type": "string",
              "description": "Internal MCP device identifier"
            }
          },
          "required": ["device_id"]
        }
      }
      // ... more tools
    ]
  }
}
```

**Implementation:**

FastMCP auto-generates tool schemas from decorated functions and type hints.

### 3. Execution Phase

**Tool Call Request:**

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "system_get_overview",
    "arguments": {
      "device_id": "dev-001"
    }
  }
}
```

**Tool Call Response (Success):**

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"device_id\":\"dev-001\",\"routeros_version\":\"7.15\",\"uptime_seconds\":86400,...}"
      }
    ],
    "isError": false
  }
}
```

**Tool Call Response (Error):**

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "error": {
    "code": -32000,
    "message": "Device unreachable",
    "data": {
      "device_id": "dev-001",
      "error_code": "DEVICE_UNREACHABLE",
      "details": "Connection timeout after 5 seconds"
    }
  }
}
```

**Implementation Pattern:**

```python
from fastmcp import FastMCP
from fastmcp.exceptions import McpError

@mcp.tool()
async def system_get_overview(device_id: str) -> dict:
    try:
        # Authorization check
        await check_authorization(current_user(), device_id, "system.get_overview")

        # Execute operation
        device = await device_service.get_device(device_id)
        overview = await system_service.get_overview(device)

        return overview

    except DeviceNotFoundError as e:
        raise McpError(
            code=-32000,
            message="Device not found",
            data={"device_id": device_id, "error_code": "DEVICE_NOT_FOUND"}
        )
    except DeviceUnreachableError as e:
        raise McpError(
            code=-32000,
            message="Device unreachable",
            data={"device_id": device_id, "error_code": "DEVICE_UNREACHABLE"}
        )
```

### 4. Notifications

**Server → Client: Resource Update Notification**

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/resources/updated",
  "params": {
    "uri": "device://dev-001/config"
  }
}
```

**Implementation:**

```python
@mcp.resource("device://{device_id}/config")
async def device_config(device_id: str) -> str:
    # Return config
    return config

# When config changes, notify subscribers
await mcp.notify_resource_updated(f"device://{device_id}/config")
```

---

## Message Handling and Routing Architecture

### MCP Message Flow

```
┌─────────────────────────────────────────────────┐
│         MCP Client (Claude Desktop)             │
└──────────────────┬──────────────────────────────┘
                   │ JSON-RPC 2.0 over stdio/HTTP
                   ▼
┌─────────────────────────────────────────────────┐
│           FastMCP SDK (Protocol Layer)          │
│  - Initialize handling                          │
│  - Tools/resources/prompts discovery            │
│  - Message routing                              │
│  - Schema validation                            │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│       RouterOS MCP Application Layer            │
│  - Authorization middleware                     │
│  - Tool implementation handlers                 │
│  - Resource providers                           │
│  - Prompt templates                             │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│          Domain Services Layer                  │
│  - DeviceService                                │
│  - SystemService                                │
│  - InterfaceService                             │
│  - etc.                                         │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│      Infrastructure Layer (RouterOS)            │
│  - RouterOSRestClient                           │
│  - RouterOSSshClient                            │
│  - Database                                     │
└─────────────────────────────────────────────────┘
```

### Authorization Middleware for MCP Tools

Every MCP tool must enforce authorization before execution:

```python
from functools import wraps
from fastmcp import FastMCP, get_context

def require_authorization(tier: str):
    """Decorator to enforce authorization for MCP tools."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get current user from MCP context (from OAuth token)
            context = get_context()
            user = context.get("user")

            if not user:
                raise McpError(code=-32001, message="Unauthorized: No user context")

            # Extract device_id from arguments
            device_id = kwargs.get("device_id")
            if not device_id:
                raise McpError(code=-32602, message="Missing required parameter: device_id")

            # Authorization check
            authz_service = get_authz_service()
            device = await device_service.get_device(device_id)

            tool_name = func.__name__
            authz_service.check_tool_access(
                user=user,
                device=device,
                tool_name=tool_name,
                tool_tier=tier
            )

            # Audit logging
            audit_service = get_audit_service()
            await audit_service.log_tool_invocation(
                user=user,
                tool_name=tool_name,
                device_id=device_id,
                tier=tier
            )

            # Execute tool
            return await func(*args, **kwargs)

        return wrapper
    return decorator

# Usage
@mcp.tool()
@require_authorization(tier="advanced")
async def system_update_identity(device_id: str, identity: str) -> dict:
    """Update system identity on a RouterOS device."""
    # Implementation
    ...
```

---

## Tool Registration Patterns

### Tool Organization by Topic

Organize tools into topic modules matching the domain structure:

```python
# routeros_mcp/mcp_tools/system.py

from fastmcp import FastMCP

def register_system_tools(mcp: FastMCP):
    """Register all system-related MCP tools."""

    @mcp.tool()
    @require_authorization(tier="fundamental")
    async def system_get_overview(device_id: str) -> dict:
        """Fetch system overview including CPU, memory, uptime."""
        # Implementation
        ...

    @mcp.tool()
    @require_authorization(tier="advanced")
    async def system_update_identity(
        device_id: str,
        identity: str,
        dry_run: bool = False
    ) -> dict:
        """Update system identity."""
        # Implementation
        ...
```

```python
# routeros_mcp/mcp_tools/__init__.py

from fastmcp import FastMCP
from .system import register_system_tools
from .interface import register_interface_tools
from .ip import register_ip_tools
# ... more topics

def register_all_tools(mcp: FastMCP):
    """Register all MCP tools organized by topic."""
    register_system_tools(mcp)
    register_interface_tools(mcp)
    register_ip_tools(mcp)
    # ... more registrations
```

### Tool Metadata and Annotations

Enhance tool definitions with rich metadata:

```python
from fastmcp import FastMCP
from pydantic import BaseModel, Field

class SystemIdentityUpdate(BaseModel):
    """Result of system identity update operation."""
    device_id: str
    changed: bool = Field(description="Whether configuration actually changed")
    old_identity: str | None
    new_identity: str
    timestamp: str

@mcp.tool(
    description="Update RouterOS system identity with audit logging",
    tags=["system", "advanced", "write"],
    examples=[
        {
            "device_id": "dev-001",
            "identity": "lab-router-01",
            "dry_run": False
        }
    ]
)
@require_authorization(tier="advanced")
async def system_update_identity(
    device_id: str = Field(description="Device ID from registry"),
    identity: str = Field(description="New system identity string", max_length=64),
    dry_run: bool = Field(default=False, description="Preview changes without applying")
) -> SystemIdentityUpdate:
    """Update system identity on a RouterOS device.

    This tool changes the device's system identity (hostname equivalent).
    It is classified as 'advanced' tier and requires ops_rw or admin role.
    Changes are audited and require device to allow advanced writes.

    Args:
        device_id: Internal device identifier
        identity: New identity string (max 64 chars)
        dry_run: If true, compute changes without applying

    Returns:
        Update result with before/after values and change flag
    """
    # Implementation
    ...
```

---

## Resource Patterns for Device Data

### Resource URI Scheme

Define consistent URI patterns for RouterOS device resources:

```
device://{device_id}/overview          # System overview
device://{device_id}/config            # Configuration export
device://{device_id}/interfaces        # Interface list
device://{device_id}/health            # Health metrics
device://{device_id}/logs              # System logs (bounded)

fleet://health-summary                 # Fleet-wide health
fleet://devices                        # All devices list
```

### Resource Implementation

```python
from fastmcp import FastMCP

@mcp.resource("device://{device_id}/overview")
async def device_overview(device_id: str) -> str:
    """Current system overview for a device.

    Returns JSON-formatted system metrics including CPU, memory,
    uptime, and health status.
    """
    overview = await system_service.get_overview(device_id)
    return json.dumps(overview, indent=2)

@mcp.resource("device://{device_id}/config")
async def device_config(device_id: str) -> str:
    """Current RouterOS configuration export.

    Returns RouterOS-format configuration suitable for
    backup or analysis. Read-only access.
    """
    config = await snapshot_service.get_current_config(device_id)
    return config

@mcp.resource("fleet://health-summary")
async def fleet_health() -> str:
    """Fleet-wide health summary.

    Returns aggregated health metrics across all managed devices.
    """
    summary = await health_service.get_fleet_summary()
    return json.dumps(summary, indent=2)
```

### Resource Subscriptions

For resources that change frequently, support subscriptions:

```python
@mcp.resource("device://{device_id}/health", subscribe=True)
async def device_health(device_id: str) -> str:
    """Real-time device health metrics (subscribable)."""
    health = await health_service.get_current_health(device_id)
    return json.dumps(health, indent=2)

# When health changes, notify subscribers
async def on_health_check_complete(device_id: str):
    """Called after periodic health check."""
    await mcp.notify_resource_updated(f"device://{device_id}/health")
```

#### Phase 2.1 implementation details: subscriptions over HTTP/SSE

In RouterOS-MCP, subscriptions are an optimization layer for clients that want to react to change without polling.
The subscription signal is deliberately lightweight: **the server notifies that a resource changed**, and the client
then re-reads the resource (`resources/read`) to fetch the current snapshot.

**Subscribable resources (Phase 2.1 baseline):**

- `device://{device_id}/health` (primary)
- `fleet://health-summary` (optional; only if we already compute and cache it)

**Update triggers:**

- Periodic health checks (scheduler-driven)
- Device reachability state transitions (healthy → unreachable, etc.)
- Explicit refreshes (e.g., an operator-triggered health probe)

**Notification payload contract:**

- Notifications MUST include the updated resource URI (e.g., `device://core-RB5009/health`).
- Notifications SHOULD include best-effort version hints when available:
  - `etag` (content hash)
  - `last_modified` (ISO 8601)
- Notifications MUST NOT include large resource bodies; the body is retrieved via a subsequent `resources/read`.

**Coalescing / debounce:**

- Multiple updates within a short window SHOULD be coalesced to a single notification per resource.
- Recommended debounce window: 250–1000ms (enough to avoid “storm” behavior when many metrics update at once).

**Backpressure and limits (safety defaults):**

- Per-connection maximum subscriptions (recommended): 200
- Per-device maximum active subscriptions (recommended): 100
- If a client exceeds limits, the server returns a protocol error to the subscribe request and MUST NOT create
  the subscription.
- If a client connection cannot keep up (write buffer grows), the server SHOULD disconnect the SSE stream to
  protect service health.

**Heartbeat / keepalive:**

- SSE streams SHOULD emit periodic keepalive messages (e.g., comment lines) so intermediaries (proxies/tunnels)
  do not close idle connections.
- Recommended heartbeat interval: 15–30s.

---

## Prompt Templates for Common Workflows

### Workflow Prompts

```python
@mcp.prompt("dns-ntp-rollout")
async def dns_ntp_rollout_workflow(
    environment: Literal["lab", "staging", "prod"] = "lab",
    device_count: int | None = None
) -> str:
    """Step-by-step DNS/NTP rollout workflow guide.

    Args:
        environment: Target environment
        device_count: Expected number of devices (optional)
    """
    devices = await device_service.list_devices(environment=environment)
    actual_count = len(devices)

    return f"""
# DNS/NTP Rollout Workflow for {environment}

## Overview
You are rolling out DNS/NTP changes to {actual_count} devices in {environment}.

## Prerequisites
- [ ] User role: ops_rw or admin
- [ ] Environment: {environment}
- [ ] Devices must have allow_advanced_writes=true (for lab/staging)

## Steps

### 1. List Target Devices
Use: `device.list_devices` with environment filter

### 2. Create Rollout Plan
Use: `config.plan_dns_ntp_rollout`
- Provide device IDs from step 1
- Specify new DNS servers (array of IPs)
- Specify new NTP servers (array of hostnames/IPs)
- Review plan output carefully

### 3. Review Plan Details
Check plan summary for:
- Devices included
- Current vs. new DNS/NTP values
- Risk level per device
- Any warnings or precondition failures

### 4. Obtain Approval (admin only for prod)
- For production: obtain approval token
- For lab/staging: proceed with plan_id

### 5. Apply Changes
Use: `config.apply_dns_ntp_rollout`
- Provide plan_id from step 2
- Include approval_token if required
- Monitor apply progress

### 6. Verify Success
- Check health status after apply
- Verify DNS/NTP on sample devices
- Review audit logs

## Rollback
If issues occur:
- Use rollback_plan tool (if implemented)
- Or manually revert via system tools

## Safety Notes
- Always test in lab first
- Use staging for final validation
- Production changes require admin approval
- Monitor health checks post-change
"""

@mcp.prompt("troubleshoot-device")
async def troubleshoot_device_guide(device_id: str | None = None) -> str:
    """Device troubleshooting workflow."""

    if device_id:
        device = await device_service.get_device(device_id)
        health = await health_service.get_current_health(device_id)

        return f"""
# Troubleshooting Device: {device.name} ({device_id})

## Current Status
- Environment: {device.environment}
- Health: {health.status}
- Last Contact: {health.last_check_timestamp}

## Diagnostic Steps

### 1. Check Connectivity
Use: `device.check_connectivity` with device_id={device_id}

### 2. Get System Overview
Use: `system.get_overview` with device_id={device_id}

### 3. Review Recent Logs
Use: `logs.get_recent` with device_id={device_id}

### 4. Check Interface Status
Use: `interface.list_interfaces` with device_id={device_id}

### 5. Verify DNS/NTP
Use: `dns.get_status` and `ntp.get_status`

## Common Issues
{_generate_common_issues_for_device(health)}
"""
    else:
        return """
# Device Troubleshooting Guide

Please provide a device_id parameter to get device-specific guidance.

To find devices:
1. Use `device.list_devices` to see all devices
2. Filter by environment or status
3. Re-run this prompt with the device_id
"""
```

---

## Error Handling and MCP Compliance

**For complete JSON-RPC 2.0 error code taxonomy, detailed error specifications, and protocol compliance requirements, see [docs/19-json-rpc-error-codes-and-mcp-protocol-specification.md](19-json-rpc-error-codes-and-mcp-protocol-specification.md).**

### JSON-RPC 2.0 Error Codes

MCP follows JSON-RPC 2.0 error code conventions:

| Code Range       | Meaning          | Usage                        |
| ---------------- | ---------------- | ---------------------------- |
| -32700           | Parse error      | Invalid JSON                 |
| -32600           | Invalid request  | Malformed JSON-RPC           |
| -32601           | Method not found | Unknown tool/method          |
| -32602           | Invalid params   | Parameter validation failure |
| -32603           | Internal error   | Server-side error            |
| -32000 to -32099 | Server error     | Application-specific errors  |

### Application-Specific Error Codes

Define consistent error codes for RouterOS operations:

```python
class ErrorCodes:
    """MCP error codes for RouterOS operations."""

    # Authorization errors
    UNAUTHORIZED = -32001
    FORBIDDEN = -32002
    INSUFFICIENT_PERMISSIONS = -32003

    # Device errors
    DEVICE_NOT_FOUND = -32010
    DEVICE_UNREACHABLE = -32011
    DEVICE_TIMEOUT = -32012
    DEVICE_AUTH_FAILED = -32013

    # Validation errors (use -32602 for JSON-RPC compliance)
    INVALID_DEVICE_ID = -32602
    INVALID_PARAMETER = -32602

    # Operation errors
    OPERATION_FAILED = -32020
    PRECONDITION_FAILED = -32021
    OPERATION_TIMEOUT = -32022

    # Plan/apply errors
    PLAN_NOT_FOUND = -32030
    PLAN_ALREADY_APPLIED = -32031
    APPROVAL_REQUIRED = -32032
    APPROVAL_INVALID = -32033
```

### Error Response Pattern

```python
from fastmcp.exceptions import McpError

class DeviceUnreachableError(McpError):
    """Device cannot be contacted via REST or SSH."""

    def __init__(self, device_id: str, details: str | None = None):
        super().__init__(
            code=ErrorCodes.DEVICE_UNREACHABLE,
            message="Device unreachable",
            data={
                "device_id": device_id,
                "error_code": "DEVICE_UNREACHABLE",
                "details": details or "Connection timeout",
                "suggested_action": "Check device network connectivity and RouterOS REST API status"
            }
        )

# Usage in tool
@mcp.tool()
async def system_get_overview(device_id: str) -> dict:
    try:
        device = await device_service.get_device(device_id)
    except DeviceNotFoundError:
        raise McpError(
            code=ErrorCodes.DEVICE_NOT_FOUND,
            message="Device not found",
            data={"device_id": device_id, "error_code": "DEVICE_NOT_FOUND"}
        )

    try:
        overview = await system_service.get_overview(device)
        return overview
    except RouterOSConnectionError as e:
        raise DeviceUnreachableError(device_id, str(e))
```

---

## MCP Inspector Testing Strategy

### MCP Inspector Overview

The MCP Inspector is an interactive developer tool for testing MCP servers without connecting to a full AI client.

### Installation and Usage

```bash
# Install globally
npm install -g @modelcontextprotocol/inspector

# Inspect local stdio server
npx @modelcontextprotocol/inspector uv run python -m routeros_mcp.mcp_server --config config.yaml

# Or inspect remote HTTP server
npx @modelcontextprotocol/inspector --url http://localhost:8080/mcp
```

### Testing Workflow with Inspector

**1. Launch Inspector**

Start the server in stdio mode via Inspector:

```bash
npx @modelcontextprotocol/inspector uv run python -m routeros_mcp.mcp_server \
    --config config/lab.yaml \
    --log-level DEBUG
```

**2. Verify Initialization**

Inspector displays:

- Protocol version negotiation
- Server capabilities (tools, resources, prompts)
- Connection status

**3. Explore Tools**

In the **Tools** tab:

- View all registered tools
- Inspect tool schemas
- See parameter requirements
- View examples

**4. Test Tool Execution**

- Select a tool (e.g., `system_get_overview`)
- Fill in parameters (e.g., `device_id: "dev-001"`)
- Click "Call Tool"
- View response (success or error)

**5. Test Resources**

In the **Resources** tab:

- List all resources
- View resource URIs
- Subscribe to resources
- Fetch resource content

**6. Test Prompts**

In the **Prompts** tab:

- View available prompts
- Provide prompt arguments
- View generated prompt output

**7. Monitor Logs**

In the **Notifications** pane:

- Server logs (via stderr)
- MCP notifications
- Error messages
- Debug output

### Integration Testing Checklist

Use Inspector to verify:

- [ ] All tools appear in tools list
- [ ] Tool schemas are complete and correct
- [ ] Tool parameters validate correctly
- [ ] Tool execution returns expected results
- [ ] Errors return proper error codes and messages
- [ ] Resources are accessible
- [ ] Resource subscriptions work
- [ ] Prompts generate correct output
- [ ] Authorization is enforced (when applicable)
- [ ] Logging output goes to stderr only (stdio mode)

---

## Configuration-Driven Transport Selection

### Unified Server Entrypoint

```python
# Legacy illustrative example (original design sketch)

import sys
import logging
from fastmcp import FastMCP
from routeros_mcp.config import get_settings
from routeros_mcp.mcp_tools import register_all_tools

def create_mcp_server() -> FastMCP:
    """Create and configure MCP server instance."""

    settings = get_settings()

    # Configure logging based on transport
    if settings.mcp_transport == "stdio":
        # Critical: log to stderr only for stdio
        logging.basicConfig(
            stream=sys.stderr,
            level=getattr(logging, settings.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    else:
        # HTTP mode: can use standard logging
        logging.basicConfig(
            level=getattr(logging, settings.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    # Create MCP server
    mcp = FastMCP(
        name="routeros-mcp",
        version="1.0.0",
        description=settings.mcp_description
    )

    # Register all tools, resources, prompts
    register_all_tools(mcp)
    register_all_resources(mcp)
    register_all_prompts(mcp)

    return mcp

def main():
    """Main entrypoint for MCP server."""
    settings = get_settings()
    mcp = create_mcp_server()

    # Run with appropriate transport
    if settings.mcp_transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport="sse",
            host=settings.mcp_http_host,
            port=settings.mcp_http_port
        )

if __name__ == "__main__":
    main()
```

### Configuration Schema

```yaml
# config/lab.yaml

# MCP transport configuration
mcp_transport: stdio # or "http"
mcp_description: "RouterOS MCP Service - Lab Environment"

# HTTP transport settings (if mcp_transport=http)
mcp_http_host: "0.0.0.0"
mcp_http_port: 8080
mcp_http_base_path: "/mcp"

# Logging
log_level: DEBUG # DEBUG for development, INFO for production

# Environment
environment: lab

# Database
database_url: "postgresql://user:pass@localhost/routeros_mcp_lab"

# OIDC (for HTTP transport with OAuth)
oidc_enabled: false # true for HTTP transport in production
oidc_issuer: "https://idp.example.com"
oidc_client_id: "routeros-mcp-client"
oidc_client_secret: "${OIDC_CLIENT_SECRET}"

# RouterOS integration
routeros_rest_timeout_seconds: 5.0
routeros_max_concurrent_requests_per_device: 3
```

---

## Token Budget Management for MCP Tools

### Token Estimation Pattern

All MCP tools MUST estimate and report token counts in responses to help clients manage context budgets:

```python
from routeros_mcp.mcp.token_estimation import estimate_tokens

@mcp.tool()
async def system_get_overview(device_id: str) -> dict:
    """Fetch system overview with token estimation."""

    overview = await system_service.get_overview(device_id)

    # Format response text
    response_text = format_system_overview(overview)

    # Estimate tokens (approximately 4 chars per token)
    estimated_tokens = estimate_tokens(response_text)

    return {
        "content": [
            {
                "type": "text",
                "text": response_text
            }
        ],
        "_meta": {
            "estimated_tokens": estimated_tokens,
            "routeros_version": overview["routeros_version"],
            "device_uptime_seconds": overview["uptime_seconds"]
        }
    }
```

### Token Budget Middleware

Implement middleware to warn/error on large responses:

```python
from fastmcp import FastMCP, get_context
from routeros_mcp.mcp.exceptions import TokenBudgetExceededError

TOKEN_WARNING_THRESHOLD = 5_000
TOKEN_ERROR_THRESHOLD = 50_000

async def token_budget_middleware(tool_name: str, result: dict) -> dict:
    """Check token budget and warn/error on large responses."""

    estimated_tokens = result.get("_meta", {}).get("estimated_tokens", 0)

    if estimated_tokens > TOKEN_ERROR_THRESHOLD:
        # This response is too large - error out
        raise TokenBudgetExceededError(
            code=-32000,
            message="Response exceeds token budget",
            data={
                "tool_name": tool_name,
                "estimated_tokens": estimated_tokens,
                "threshold": TOKEN_ERROR_THRESHOLD,
                "suggested_action": "Use pagination or filtering parameters to reduce response size"
            }
        )

    if estimated_tokens > TOKEN_WARNING_THRESHOLD:
        # Add warning to metadata
        result["_meta"]["token_warning"] = (
            f"Response size ({estimated_tokens} tokens) exceeds recommended limit "
            f"({TOKEN_WARNING_THRESHOLD} tokens). Consider using pagination."
        )

    return result
```

### Pagination Support for Large Results

Tools that may return large result sets should support pagination:

```python
from pydantic import BaseModel, Field

class InterfaceListResult(BaseModel):
    """Paginated interface list result."""
    interfaces: list[dict]
    total_count: int
    limit: int
    offset: int
    has_more: bool

@mcp.tool()
async def interface_list_interfaces(
    device_id: str,
    limit: int = Field(default=50, ge=1, le=500, description="Maximum results to return"),
    offset: int = Field(default=0, ge=0, description="Number of results to skip")
) -> InterfaceListResult:
    """List interfaces with pagination support.

    Args:
        device_id: Device identifier
        limit: Maximum number of interfaces to return (1-500)
        offset: Number of interfaces to skip

    Returns:
        Paginated interface list with pagination metadata
    """
    interfaces = await interface_service.list_interfaces(
        device_id=device_id,
        limit=limit,
        offset=offset
    )

    total_count = await interface_service.count_interfaces(device_id)
    has_more = (offset + len(interfaces)) < total_count

    response_text = format_interface_list(interfaces, total_count, limit, offset)

    return {
        "content": [
            {
                "type": "text",
                "text": response_text
            }
        ],
        "_meta": {
            "estimated_tokens": estimate_tokens(response_text),
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "pagination_hint": f"Use offset={offset + limit} to get next page" if has_more else None
        }
    }
```

---

## Session Lifecycle and State Management

### Session Tracking Pattern

Track MCP client sessions for metrics and resource cleanup:

```python
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

@dataclass
class MCPSession:
    """MCP client session state."""
    session_id: str = field(default_factory=lambda: str(uuid4()))
    client_info: dict[str, str] = field(default_factory=dict)
    protocol_version: str = "2024-11-05"
    capabilities: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)

    # Statistics
    total_tool_calls: int = 0
    total_tokens: int = 0
    total_errors: int = 0

    # User context (from OAuth in HTTP/SSE mode)
    user_sub: str | None = None
    user_roles: list[str] = field(default_factory=list)

class MCPSessionManager:
    """Manage MCP client sessions."""

    def __init__(self):
        self._sessions: dict[str, MCPSession] = {}

    async def create_session(
        self,
        client_info: dict[str, str],
        protocol_version: str,
        capabilities: dict[str, Any],
        user_sub: str | None = None,
        user_roles: list[str] | None = None
    ) -> MCPSession:
        """Create new MCP session."""
        session = MCPSession(
            client_info=client_info,
            protocol_version=protocol_version,
            capabilities=capabilities,
            user_sub=user_sub,
            user_roles=user_roles or []
        )

        self._sessions[session.session_id] = session

        logger.info(
            "MCP session created",
            extra={
                "session_id": session.session_id,
                "client_name": client_info.get("name"),
                "client_version": client_info.get("version"),
                "user_sub": user_sub
            }
        )

        return session

    async def update_activity(
        self,
        session_id: str,
        *,
        tool_called: bool = False,
        tokens: int = 0,
        error: bool = False
    ) -> None:
        """Update session activity statistics."""
        session = self._sessions.get(session_id)
        if not session:
            return

        session.last_activity = datetime.utcnow()

        if tool_called:
            session.total_tool_calls += 1
        if tokens > 0:
            session.total_tokens += tokens
        if error:
            session.total_errors += 1

    async def close_session(self, session_id: str) -> None:
        """Close MCP session and log statistics."""
        session = self._sessions.pop(session_id, None)
        if not session:
            return

        duration = (datetime.utcnow() - session.created_at).total_seconds()

        logger.info(
            "MCP session closed",
            extra={
                "session_id": session_id,
                "duration_seconds": duration,
                "total_tool_calls": session.total_tool_calls,
                "total_tokens": session.total_tokens,
                "total_errors": session.total_errors,
                "client_name": session.client_info.get("name")
            }
        )
```

### Integration with FastMCP

Use FastMCP context to track session:

```python
from fastmcp import FastMCP, get_context, set_context

session_manager = MCPSessionManager()

@mcp.on_initialize
async def on_initialize(params: dict) -> None:
    """Handle MCP initialization - create session."""
    session = await session_manager.create_session(
        client_info=params["clientInfo"],
        protocol_version=params["protocolVersion"],
        capabilities=params.get("capabilities", {})
    )

    # Store session ID in context for all tool calls
    set_context("session_id", session.session_id)

@mcp.on_close
async def on_close() -> None:
    """Handle MCP connection close - cleanup session."""
    context = get_context()
    session_id = context.get("session_id")

    if session_id:
        await session_manager.close_session(session_id)

@mcp.tool()
async def system_get_overview(device_id: str) -> dict:
    """Tool with session tracking."""
    context = get_context()
    session_id = context.get("session_id")

    try:
        result = await _execute_tool(device_id)

        # Update session stats
        tokens = result.get("_meta", {}).get("estimated_tokens", 0)
        await session_manager.update_activity(
            session_id,
            tool_called=True,
            tokens=tokens
        )

        return result

    except Exception:
        await session_manager.update_activity(session_id, error=True)
        raise
```

---

## Rate Limiting and Concurrency Control

### Per-Session Rate Limiting

Implement rate limiting per MCP session to prevent abuse:

```python
from datetime import datetime, timedelta
from collections import defaultdict

class MCPRateLimiter:
    """Rate limiter for MCP tool calls per session."""

    def __init__(self):
        # session_id -> list of timestamps
        self._call_history: dict[str, list[datetime]] = defaultdict(list)

        # Rate limits by tier
        self._limits = {
            "free": 100,      # 100 calls per hour
            "basic": 500,     # 500 calls per hour
            "professional": 2000  # 2000 calls per hour
        }

    async def check_rate_limit(
        self,
        session_id: str,
        user_tier: str = "free"
    ) -> None:
        """Check if session has exceeded rate limit."""
        limit = self._limits.get(user_tier, 100)
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)

        # Remove old timestamps
        self._call_history[session_id] = [
            ts for ts in self._call_history[session_id]
            if ts > one_hour_ago
        ]

        # Check limit
        if len(self._call_history[session_id]) >= limit:
            raise McpError(
                code=-32000,
                message="Rate limit exceeded",
                data={
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "limit": limit,
                    "window": "1 hour",
                    "tier": user_tier,
                    "retry_after_seconds": 3600
                }
            )

        # Record this call
        self._call_history[session_id].append(now)

# Global rate limiter
rate_limiter = MCPRateLimiter()

@mcp.tool()
async def system_get_overview(device_id: str) -> dict:
    """Tool with rate limiting."""
    context = get_context()
    session_id = context.get("session_id")
    user_tier = context.get("user_tier", "free")

    # Check rate limit before executing
    await rate_limiter.check_rate_limit(session_id, user_tier)

    # Execute tool
    return await _execute_tool(device_id)
```

### Concurrent Tool Execution Limiting

Limit concurrent tool executions to prevent resource exhaustion:

```python
import asyncio

class MCPConcurrencyLimiter:
    """Limit concurrent MCP tool executions."""

    def __init__(self, max_concurrent: int = 10):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_calls: dict[str, int] = defaultdict(int)

    async def execute_with_limit(
        self,
        tool_name: str,
        coro: Coroutine
    ) -> Any:
        """Execute tool with concurrency limiting."""
        async with self._semaphore:
            self._active_calls[tool_name] += 1

            try:
                logger.debug(
                    f"Executing tool {tool_name}",
                    extra={"active_calls": self._active_calls[tool_name]}
                )
                result = await coro
                return result

            finally:
                self._active_calls[tool_name] -= 1

# Global concurrency limiter
concurrency_limiter = MCPConcurrencyLimiter(max_concurrent=10)

@mcp.tool()
async def system_get_overview(device_id: str) -> dict:
    """Tool with concurrency limiting."""
    return await concurrency_limiter.execute_with_limit(
        "system_get_overview",
        _execute_tool(device_id)
    )
```

---

## Graceful Shutdown and In-Flight Request Handling

### Shutdown Handler

Ensure all in-flight tool calls complete before shutting down:

```python
import signal
from typing import Set
import asyncio

class MCPServerShutdownHandler:
    """Handle graceful shutdown of MCP server."""

    def __init__(self, timeout: float = 30.0):
        self._shutdown_event = asyncio.Event()
        self._in_flight_calls: Set[asyncio.Task] = set()
        self._timeout = timeout

    def register_call(self, task: asyncio.Task) -> None:
        """Register an in-flight tool call."""
        self._in_flight_calls.add(task)
        task.add_done_callback(lambda t: self._in_flight_calls.discard(t))

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()

    async def shutdown(self) -> None:
        """Initiate graceful shutdown."""
        logger.info(
            "MCP server shutting down gracefully",
            extra={"in_flight_calls": len(self._in_flight_calls)}
        )

        self._shutdown_event.set()

        # Wait for in-flight calls to complete
        if self._in_flight_calls:
            logger.info(
                f"Waiting for {len(self._in_flight_calls)} in-flight calls to complete"
            )

            done, pending = await asyncio.wait(
                self._in_flight_calls,
                timeout=self._timeout
            )

            if pending:
                logger.warning(
                    f"Canceling {len(pending)} calls that didn't complete in {self._timeout}s"
                )
                for task in pending:
                    task.cancel()

# Global shutdown handler
shutdown_handler = MCPServerShutdownHandler()

# Register signal handlers
def handle_signal(signum, frame):
    """Handle shutdown signals."""
    asyncio.create_task(shutdown_handler.shutdown())

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

@mcp.tool()
async def system_get_overview(device_id: str) -> dict:
    """Tool with shutdown tracking."""
    task = asyncio.current_task()
    if task:
        shutdown_handler.register_call(task)

    # Execute tool
    return await _execute_tool(device_id)
```

---

## Correlation ID and Distributed Tracing

### Correlation ID Propagation

Propagate correlation IDs through MCP tool calls for end-to-end tracing:

```python
from contextvars import ContextVar
from uuid import uuid4

# Context variable for correlation ID
correlation_id_var: ContextVar[str] = ContextVar("correlation_id")

@mcp.on_request
async def on_request(request: dict) -> None:
    """Generate correlation ID for each request."""
    correlation_id = str(uuid4())
    correlation_id_var.set(correlation_id)

    logger.info(
        "MCP request received",
        extra={
            "correlation_id": correlation_id,
            "method": request.get("method"),
            "request_id": request.get("id")
        }
    )

@mcp.tool()
async def system_get_overview(device_id: str) -> dict:
    """Tool with correlation ID in logs."""
    correlation_id = correlation_id_var.get()

    logger.info(
        "Executing system.get_overview",
        extra={
            "correlation_id": correlation_id,
            "device_id": device_id
        }
    )

    # Correlation ID is automatically included in all logs
    result = await _execute_tool(device_id)

    # Include in response metadata
    result["_meta"]["correlation_id"] = correlation_id

    return result
```

### OpenTelemetry Integration

Integrate OpenTelemetry spans for distributed tracing:

```python
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)

@mcp.tool()
async def system_get_overview(device_id: str) -> dict:
    """Tool with OpenTelemetry tracing."""
    correlation_id = correlation_id_var.get()

    with tracer.start_as_current_span(
        "mcp.tool.system_get_overview",
        attributes={
            "mcp.tool.name": "system_get_overview",
            "mcp.device.id": device_id,
            "mcp.correlation_id": correlation_id
        }
    ) as span:
        try:
            result = await _execute_tool(device_id)

            # Add result metadata to span
            tokens = result.get("_meta", {}).get("estimated_tokens", 0)
            span.set_attribute("mcp.response.tokens", tokens)
            span.set_status(Status(StatusCode.OK))

            return result

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise
```

---

## Automated Protocol Compliance Testing

### Pytest Examples for MCP Protocol

```python
import pytest
from fastmcp.testing import MCPTestClient

@pytest.fixture
async def mcp_client():
    """Create test MCP client."""
    from routeros_mcp.mcp_server import create_mcp_server

    mcp = create_mcp_server()
    async with MCPTestClient(mcp) as client:
        yield client

@pytest.mark.asyncio
async def test_mcp_initialize_handshake(mcp_client):
    """Test MCP initialization handshake."""
    response = await mcp_client.initialize(
        protocol_version="2024-11-05",
        capabilities={"tools": {}},
        client_info={"name": "test-client", "version": "1.0.0"}
    )

    assert response["protocolVersion"] == "2024-11-05"
    assert "serverInfo" in response
    assert response["serverInfo"]["name"] == "routeros-mcp"
    assert "capabilities" in response
    assert "tools" in response["capabilities"]

@pytest.mark.asyncio
async def test_mcp_tools_list(mcp_client):
    """Test tools/list request."""
    await mcp_client.initialize()

    tools = await mcp_client.list_tools()

    assert len(tools) > 0
    assert any(t["name"] == "system_get_overview" for t in tools)

    # Verify schema completeness
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"

@pytest.mark.asyncio
async def test_mcp_tool_call_success(mcp_client, mock_device_service):
    """Test successful tool execution."""
    await mcp_client.initialize()

    result = await mcp_client.call_tool(
        "system_get_overview",
        {"device_id": "test-device-123"}
    )

    assert "content" in result
    assert len(result["content"]) > 0
    assert result["content"][0]["type"] == "text"
    assert result.get("isError") is False

@pytest.mark.asyncio
async def test_mcp_tool_call_error(mcp_client):
    """Test tool execution error handling."""
    await mcp_client.initialize()

    with pytest.raises(Exception) as exc_info:
        await mcp_client.call_tool(
            "system_get_overview",
            {"device_id": "nonexistent-device"}
        )

    # Verify JSON-RPC error format
    error = exc_info.value
    assert hasattr(error, "code")
    assert hasattr(error, "message")
    assert hasattr(error, "data")

@pytest.mark.asyncio
async def test_mcp_rate_limiting(mcp_client):
    """Test rate limiting enforcement."""
    await mcp_client.initialize()

    # Make calls up to rate limit
    for i in range(100):
        await mcp_client.call_tool("system_get_overview", {"device_id": f"dev-{i}"})

    # 101st call should fail with rate limit error
    with pytest.raises(Exception) as exc_info:
        await mcp_client.call_tool("system_get_overview", {"device_id": "dev-101"})

    assert "rate limit" in str(exc_info.value).lower()

@pytest.mark.asyncio
async def test_mcp_token_budget_warning(mcp_client, large_response_mock):
    """Test token budget warning on large responses."""
    await mcp_client.initialize()

    result = await mcp_client.call_tool(
        "interface_list_interfaces",
        {"device_id": "test-device", "limit": 500}
    )

    # Check for token warning in metadata
    meta = result.get("_meta", {})
    if meta.get("estimated_tokens", 0) > 5000:
        assert "token_warning" in meta
```

### CI Integration Pattern

```yaml
# .github/workflows/mcp-protocol-tests.yml

name: MCP Protocol Compliance Tests

on: [push, pull_request]

jobs:
  mcp-protocol-tests:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install uv
          uv sync

      - name: Run MCP protocol compliance tests
        run: |
          uv run pytest tests/mcp/test_protocol_compliance.py -v

      - name: Run MCP Inspector validation
        run: |
          npm install -g @modelcontextprotocol/inspector
          uv run python scripts/validate_mcp_inspector.py

      - name: Validate tool schemas
        run: |
          uv run python -m routeros_mcp.mcp.validate_schemas
```

---

## Versioning & Capability Negotiation

### Overview

Following MCP best practices, the RouterOS MCP Server implements semantic versioning and advertises capabilities during protocol initialization to enable graceful degradation and backward compatibility.

### Semantic Versioning

Server follows semantic versioning (MAJOR.MINOR.PATCH):

```
MAJOR.MINOR.PATCH

Example: 1.2.3
- MAJOR (1): Breaking changes to tool schemas, removal of tools
- MINOR (2): New tools, new resources, new prompts, backward-compatible changes
- PATCH (3): Bug fixes, documentation updates, no schema changes
```

**Current Version:** `1.0.0`

**Version History:**

- `1.0.0` (2025-01-15): Initial Phase 1-3 release (Phase 1-3 MCP tools registered; diagnostics tools excluded and planned for later phases)
- `1.1.0` (planned): Phase 4 (HTTP transport + multi-device coordination + subscriptions)
- `1.2.0` (planned): Security and auth enhancements for HTTP transport (OAuth 2.1)
- `2.0.0` (planned): Breaking changes (if needed for RouterOS API changes)

### Version Declaration

Declare version in server initialization:

```python
from fastmcp import FastMCP

mcp = FastMCP(
    name="RouterOS MCP Server",
    version="1.0.0",  # Semantic version
    description="MikroTik RouterOS management via MCP protocol"
)
```

### Capability Advertisement

Server advertises capabilities during MCP initialize handshake:

```python
# routeros_mcp/mcp/server.py

from fastmcp.protocol import InitializeRequest, InitializeResponse

async def handle_initialize(request: InitializeRequest) -> InitializeResponse:
    """Handle MCP initialize request with capability advertisement."""
    return InitializeResponse(
        protocol_version="2024-11-05",  # MCP protocol version
        server_info={
            "name": "RouterOS MCP Server",
            "version": "1.0.0"
        },
        capabilities={
            # Phase 1 capabilities (CURRENT)
            "tools": {
                "supported": True,
                "tier_support": {
                    "fundamental": True,   # 23 read-only tools
                    "advanced": True,      # 8 single-device write tools
                    "professional": True   # 9 multi-device orchestration tools
                }
            },

            # Phase 2 capabilities (PLANNED)
            "resources": {
                "supported": True,
                "subscribe": True,        # Supports resource subscriptions
                "list_changed": True      # Notifies when resource list changes
            },

            "prompts": {
                "supported": True,
                "list_changed": False     # Prompts are static (from YAML files)
            },

            # Not applicable for network devices
            "roots": {
                "supported": False        # RouterOS devices don't have filesystem roots
            },

            # Phase 3+ capabilities (FUTURE)
            "sampling": {
                "supported": False        # Not implemented yet
            },

            "elicitation": {
                "supported": False        # Not implemented yet
            },

            # Custom capabilities (RouterOS-specific)
            "custom": {
                # Environment support
                "environments": ["lab", "staging", "prod"],

                # Plan system limits
                "max_devices_per_plan": 50,
                "plan_expiry_hours": 24,
                "supports_dry_run": True,
                "supports_plan_apply": True,

                # Security requirements
                "oauth_required_for_http": True,
                "credential_encryption": True,

                # RouterOS compatibility
                "routeros_versions_supported": ["7.x"],
                "rest_api_required": True,
                "ssh_optional": True
            }
        }
    )
```

### Client Capability Detection

Clients can check server capabilities before using features:

```python
# Client-side capability check

async def check_server_capabilities(mcp_client):
    """Check what server supports and adapt workflows."""
    init_response = await mcp_client.initialize()
    caps = init_response.capabilities

    # Check resource support
    if caps.get("resources", {}).get("supported"):
        print("✅ Server supports resources - use resource-based workflows")
        # Use device://{id}/health, fleet://summary, etc.
    else:
        print("⚠️  Server is tools-only - use fallback tools")
        # Use device/get-health-data tool instead

    # Check prompt support
    if caps.get("prompts", {}).get("supported"):
        print("✅ Server has workflow prompts")
        prompts = await mcp_client.list_prompts()
        # Use guided workflows
    else:
        print("⚠️  No prompt support - use manual workflows")

    # Check tier support
    tool_caps = caps.get("tools", {}).get("tier_support", {})
    if tool_caps.get("professional"):
        print("✅ Professional tier available (multi-device operations)")
    elif tool_caps.get("advanced"):
        print("⚠️  Only fundamental + advanced tiers available")
    else:
        print("⚠️  Read-only mode (fundamental tier only)")

    # Check custom capabilities
    custom = caps.get("custom", {})
    environments = custom.get("environments", [])
    print(f"Available environments: {', '.join(environments)}")

    max_devices = custom.get("max_devices_per_plan", "unknown")
    print(f"Max devices per plan: {max_devices}")
```

### Tool Versioning and Deprecation

#### Backward-Compatible Changes

When adding new optional parameters:

```python
# Version 1.0.0
@mcp.tool()
async def system_get_overview(device_id: str) -> dict:
    """Get system overview."""
    return await system_service.get_overview(device_id)


# Version 1.1.0 (backward compatible - new optional parameter)
@mcp.tool()
async def system_get_overview(
    device_id: str,
    include_packages: bool = True  # New optional parameter with default
) -> dict:
    """Get system overview with optional package information."""
    overview = await system_service.get_overview(device_id)

    if include_packages:
        overview["packages"] = await system_service.get_packages(device_id)

    return overview
```

#### Breaking Changes (New Tool Version)

When breaking changes are required:

```python
# Original tool (1.0.0)
@mcp.tool()
async def interface_list(device_id: str) -> list[dict]:
    """List all interfaces."""
    return await interface_service.list_interfaces(device_id)


# New version with breaking changes (2.0.0)
@mcp.tool()
async def interface_list_v2(
    device_id: str,
    include_stats: bool = True,  # New required behavior
    format: str = "detailed"      # New response format
) -> dict:  # Changed return type
    """List interfaces with enhanced statistics (V2).

    Breaking changes from v1:
    - Returns dict instead of list
    - Always includes statistics
    - New 'format' parameter
    """
    return await interface_service.list_interfaces_v2(
        device_id,
        include_stats=include_stats,
        format=format
    )


# Mark old version as deprecated (keep for 6 months)
@mcp.tool(
    deprecated=True,
    replacement="interface/list-v2"
)
async def interface_list(device_id: str) -> list[dict]:
    """DEPRECATED: Use interface/list-v2 instead.

    This tool will be removed in version 3.0.0.
    Migration guide: https://docs.example.com/migration/interface-list-v2
    """
    return await interface_service.list_interfaces(device_id)
```

#### Deprecation Metadata

Include deprecation information in tool schema:

```json
{
  "name": "interface/list",
  "description": "DEPRECATED: Use interface/list-v2 instead...",
  "inputSchema": {...},
  "deprecated": true,
  "deprecation": {
    "since_version": "2.0.0",
    "removal_version": "3.0.0",
    "replacement_tool": "interface/list-v2",
    "migration_guide": "https://docs.example.com/migration/interface-list-v2",
    "reason": "New version provides enhanced statistics and better response structure"
  }
}
```

### Backward Compatibility Rules

Following MCP best practices, maintain backward compatibility:

1. **Optional Parameters Only**: New parameters MUST have defaults

   ```python
   # ✅ GOOD: Optional parameter with default
   async def tool(device_id: str, new_param: bool = False):
       pass

   # ❌ BAD: Required parameter breaks compatibility
   async def tool(device_id: str, new_param: bool):
       pass
   ```

2. **Additive Changes**: Add new response fields, don't remove existing

   ```python
   # ✅ GOOD: Add new field
   return {
       "existing_field": "value",
       "new_field": "value"  # New field added
   }

   # ❌ BAD: Remove existing field
   return {
       # "existing_field": "removed"  # Breaking change!
       "new_field": "value"
   }
   ```

3. **Graceful Degradation**: Old clients MUST work with new servers
4. **6-Month Deprecation Window**: Maintain deprecated tools for 6 months minimum
5. **Clear Migration Paths**: Document upgrade path from old to new

### Version Negotiation Example

```python
# Server-side version check

from packaging import version

def check_client_compatibility(client_version: str) -> bool:
    """Check if client version is compatible with server.

    Args:
        client_version: Client's reported version (e.g., "1.0.0")

    Returns:
        True if compatible, False otherwise
    """
    server_version = version.parse("1.0.0")
    client_ver = version.parse(client_version)

    # Major version must match
    if server_version.major != client_ver.major:
        return False

    # Server minor version must be >= client minor version
    if server_version.minor < client_ver.minor:
        return False

    return True


# Usage in initialize handler
async def handle_initialize(request: InitializeRequest) -> InitializeResponse:
    client_info = request.client_info
    client_version = client_info.get("version", "0.0.0")

    if not check_client_compatibility(client_version):
        raise McpError(
            -32600,
            f"Client version {client_version} incompatible with server 1.0.0"
        )

    # Return capabilities
    return InitializeResponse(...)
```

### Capability Evolution

**Phase 1-3 (Completed - v1.0.0):**

```python
capabilities = {
    "tools": {"supported": True},           # 62 tools implemented
    "resources": {"supported": True},       # 12+ resource URIs implemented
    "prompts": {"supported": True}          # 8 prompts implemented
}
transport = "stdio"  # Fully functional STDIO transport only
```

**Phase 4 (Planned - v1.2.0 target):**

```python
capabilities = {
    "tools": {"supported": True},                      # + wireless/DHCP/bridge read tools
    "resources": {"supported": True, "subscribe": True},  # + resource subscriptions via SSE
    "prompts": {"supported": True}                     # + wireless/DHCP troubleshooting prompts
}
transport = "stdio" | "http"  # Both transports fully functional
# HTTP/SSE transport with OAuth/OIDC authentication
```

**Phase 3+ (Future - v1.2.0+):**

```python
capabilities = {
    "tools": {"supported": True},                      # + diagnostics (ping/traceroute)
    "resources": {"supported": True, "subscribe": True},
    "prompts": {"supported": True},
    "custom": {
        "diagnostics_tools": True,
        "ssh_key_auth": True,
        "advanced_firewall_writes": True
    }
}
```

### Deprecation Policy

**Timeline:**

- **Announcement**: Deprecation announced in release notes
- **Warning Period**: Tool marked deprecated, warnings logged
- **Migration Window**: 6 months minimum
- **Removal**: Tool removed in next major version

**Process:**

1. Mark tool as deprecated with `@mcp.tool(deprecated=True)`
2. Add deprecation notice to description
3. Log warning on each deprecated tool call
4. Provide replacement tool reference
5. Document migration in release notes
6. Remove after 6 months + major version bump

**Example Deprecation Log:**

```python
import logging

logger = logging.getLogger(__name__)

@mcp.tool(deprecated=True, replacement="interface/list-v2")
async def interface_list(device_id: str) -> list[dict]:
    """DEPRECATED: Use interface/list-v2 instead."""

    # Log deprecation warning
    logger.warning(
        "deprecated_tool_call",
        extra={
            "tool": "interface/list",
            "replacement": "interface/list-v2",
            "removal_version": "3.0.0",
            "device_id": device_id
        }
    )

    # Continue to work as before
    return await interface_service.list_interfaces(device_id)
```

---

## Summary and Implementation Checklist

### Phase 1-3 Status (COMPLETED)

- [x] FastMCP SDK integrated
- [x] Stdio transport fully implemented with stderr logging
- [x] JSON-RPC 2.0 error handling compliant
- [x] 38 tools registered with complete schemas (14 fundamental, 21 advanced, 3 professional); 2 diagnostics tools defined for later phases
- [x] 12+ resources defined with URI patterns
- [x] 8 prompts created for common workflows
- [x] Authorization middleware for all tools
- [x] Configuration-driven transport selection
- [x] Admin CLI for device management and plan approval
- [x] Plan/apply framework with HMAC-signed approval tokens
- [x] Single-device write operations (firewall, DHCP, bridge, wireless)

### Phase 4 Requirements (HTTP/SSE Transport & Multi-Device Coordination)

**Transport Implementation:**

- [ ] Add `sse-starlette` to `pyproject.toml` dependencies
- [ ] Implement `_process_mcp_request()` in `http.py` to integrate with FastMCP
- [ ] Wire HTTP mode in `mcp/server.py` (remove `NotImplementedError`)
- [ ] Add OAuth/OIDC middleware for authentication
- [ ] Implement resource subscription via SSE
- [ ] HTTP/SSE E2E testing with real MCP clients

**New Read-Only Tools:**

- [ ] `wireless/get-interfaces` - List wireless interfaces
- [ ] `wireless/get-clients` - Connected wireless clients
- [ ] `dhcp/get-server-status` - DHCP server configuration
- [ ] `dhcp/get-leases` - Active DHCP leases
- [ ] `bridge/list-bridges` - Bridge configuration
- [ ] `bridge/list-ports` - Bridge ports and VLANs

**Resource Optimization:**

- [ ] Resource cache implementation with TTL
- [ ] Cache invalidation on device state changes
- [ ] Resource subscription support via SSE
- [ ] Performance benchmarking

**Documentation:**

- [ ] HTTP/SSE deployment guide
- [ ] Resource subscription tutorial
- [ ] OAuth/OIDC setup guide
- [ ] Wireless/DHCP/bridge troubleshooting prompts

### Phase 3+ (Deferred)

- Diagnostics tools (ping/traceroute/bandwidth-test)
- SSH key authentication
- Client compatibility modes
- Advanced firewall write operations
- Routing table modifications

### Key Takeaways

1. **Use FastMCP SDK**: Don't reimplement MCP protocol
2. **Stdio Safety**: Never write to stdout in stdio mode (COMPLETED in Phase 1)
3. **Tool Schemas**: Generated from type hints and docstrings (COMPLETED in Phase 1)
4. **Authorization**: Middleware on every tool (COMPLETED in Phase 1)
5. **Error Handling**: JSON-RPC 2.0 compliant error codes (COMPLETED in Phase 1)
6. **Resources**: Provide device data as resources (COMPLETED in Phase 1)
7. **Prompts**: Guide users through complex workflows (COMPLETED in Phase 1)
8. **Testing**: Use MCP Inspector for interactive testing
9. **Transport**: STDIO complete, HTTP/SSE in Phase 2
10. **Configuration**: Environment-driven transport selection (COMPLETED in Phase 1)

---

This design ensures full MCP protocol compliance while maintaining the security, operational, and architectural rigor defined in earlier documents.
