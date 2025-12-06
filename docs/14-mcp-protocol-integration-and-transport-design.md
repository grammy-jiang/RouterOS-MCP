# MCP Protocol Integration & Transport Design

## Purpose

Define how the RouterOS MCP service implements the Model Context Protocol (MCP) specification, including transport layer choices (stdio vs. HTTP/SSE), protocol lifecycle management, message handling, tool/resource/prompt registration, and integration with the official Python MCP SDK (FastMCP). This document bridges the generic API design in earlier docs with MCP-specific implementation patterns.

---

## MCP Protocol Overview and Compliance

### Protocol Version

This service targets **MCP Specification 2025-11-25** (latest stable).

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

MCP host configuration (e.g., Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "routeros-mcp": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "routeros_mcp.mcp_server",
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

| Factor | Stdio | HTTP/SSE |
|--------|-------|----------|
| **Deployment** | Local process | Remote server |
| **Users** | Single user | Multi-user |
| **Auth** | Environment/config | OAuth 2.1 |
| **Security** | OS-level permissions | Network + OAuth |
| **Scalability** | Not applicable | Horizontal scaling |
| **Development** | Fast iteration | Production-ready |
| **Debugging** | Direct logs | Distributed tracing |

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

| Code Range | Meaning | Usage |
|------------|---------|-------|
| -32700 | Parse error | Invalid JSON |
| -32600 | Invalid request | Malformed JSON-RPC |
| -32601 | Method not found | Unknown tool/method |
| -32602 | Invalid params | Parameter validation failure |
| -32603 | Internal error | Server-side error |
| -32000 to -32099 | Server error | Application-specific errors |

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
# routeros_mcp/mcp_server.py

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
mcp_transport: stdio  # or "http"
mcp_description: "RouterOS MCP Service - Lab Environment"

# HTTP transport settings (if mcp_transport=http)
mcp_http_host: "0.0.0.0"
mcp_http_port: 8080
mcp_http_base_path: "/mcp"

# Logging
log_level: DEBUG  # DEBUG for development, INFO for production

# Environment
environment: lab

# Database
database_url: "postgresql://user:pass@localhost/routeros_mcp_lab"

# OIDC (for HTTP transport with OAuth)
oidc_enabled: false  # true for HTTP transport in production
oidc_issuer: "https://idp.example.com"
oidc_client_id: "routeros-mcp-client"
oidc_client_secret: "${OIDC_CLIENT_SECRET}"

# RouterOS integration
routeros_rest_timeout_seconds: 5.0
routeros_max_concurrent_requests_per_device: 3
```

---

## Summary and Implementation Checklist

### MCP Compliance Checklist

- [ ] FastMCP SDK integrated
- [ ] Stdio transport implemented with stderr logging
- [ ] HTTP/SSE transport implemented with OAuth
- [ ] JSON-RPC 2.0 error handling compliant
- [ ] Tools registered with complete schemas
- [ ] Resources defined with URI patterns
- [ ] Prompts created for common workflows
- [ ] MCP Inspector testing integrated
- [ ] Authorization middleware for all tools
- [ ] Configuration-driven transport selection

### Key Takeaways

1. **Use FastMCP SDK**: Don't reimplement MCP protocol
2. **Stdio Safety**: Never write to stdout in stdio mode
3. **Tool Schemas**: Generated from type hints and docstrings
4. **Authorization**: Middleware on every tool
5. **Error Handling**: JSON-RPC 2.0 compliant error codes
6. **Resources**: Provide device data as resources
7. **Prompts**: Guide users through complex workflows
8. **Testing**: Use MCP Inspector for interactive testing
9. **Transport**: Support both stdio (dev) and HTTP/SSE (prod)
10. **Configuration**: Environment-driven transport selection

---

This design ensures full MCP protocol compliance while maintaining the security, operational, and architectural rigor defined in earlier documents.
