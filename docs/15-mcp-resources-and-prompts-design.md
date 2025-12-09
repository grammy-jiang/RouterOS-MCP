# MCP Resources & Prompts Design

## Purpose

Define the MCP resource patterns for exposing RouterOS device data and configuration, and prompt templates for guiding users through common workflows. Resources provide read-only contextual data, while prompts offer reusable instruction templates that help users discover and execute complex operations safely.

---

## MCP Resources Overview

### Resource Concept in MCP

**Resources** are read-only data sources that provide context to AI models and users:

- Application-driven (host controls when to retrieve)
- Flexible retrieval (selective or complete)
- Support subscriptions for real-time updates
- URI-based addressing with consistent schemas

### Use Cases for RouterOS Resources

1. **Device Configuration Snapshots** - Current or historical device configurations
2. **Real-time System Metrics** - CPU, memory, interface stats
3. **Fleet Health Summaries** - Aggregated health across devices
4. **Audit Logs** - Historical operation logs for compliance
5. **Plan Documents** - Detailed change plans for review

---

## Resource URI Scheme Design

### URI Namespace Structure

```
device://{device_id}/{resource_type}
fleet://{resource_type}
plan://{plan_id}/{resource_type}
audit://{resource_type}
```

### Device Resources

**System and Configuration**

```
device://{device_id}/overview
device://{device_id}/config
device://{device_id}/identity
device://{device_id}/health
device://{device_id}/resource-usage
```

**Network and Interfaces**

```
device://{device_id}/interfaces
device://{device_id}/interfaces/{interface_name}
device://{device_id}/ip-addresses
device://{device_id}/ip-addresses/{address_id}
device://{device_id}/routes
device://{device_id}/routes/summary
```

**Services and Status**

```
device://{device_id}/dns
device://{device_id}/ntp
device://{device_id}/dhcp-server
device://{device_id}/wireless
device://{device_id}/wireless/clients
```

**Diagnostics and Logs**

```
device://{device_id}/logs
device://{device_id}/logs/recent
device://{device_id}/diagnostics/ping-results
device://{device_id}/diagnostics/traceroute-results
```

### Fleet Resources

**Health and Status**

```
fleet://health-summary
fleet://devices
fleet://devices/{environment}
fleet://devices/{environment}/{tag}
fleet://metrics/cpu-usage
fleet://metrics/memory-usage
fleet://alerts/active
```

**Configuration Drift**

```
fleet://drift/summary
fleet://drift/devices-out-of-compliance
```

### Plan Resources

**Change Plans and Execution**

```
plan://{plan_id}/summary
plan://{plan_id}/details
plan://{plan_id}/devices
plan://{plan_id}/execution-log
plan://{plan_id}/rollback-plan
```

### Audit Resources

**Audit and Compliance**

```
audit://events/recent
audit://events/by-user/{user_sub}
audit://events/by-device/{device_id}
audit://events/by-tool/{tool_name}
audit://write-operations/recent
```

---

## Resource Implementation Patterns

### Basic Resource Pattern

```python
from fastmcp import FastMCP
import json

@mcp.resource("device://{device_id}/overview")
async def device_overview(device_id: str) -> str:
    """Current system overview for a RouterOS device.

    Provides comprehensive system information including:
    - RouterOS version
    - Uptime
    - CPU and memory usage
    - System health metrics (temperature, voltage)
    - System identity and board info

    Args:
        device_id: Internal device identifier

    Returns:
        JSON-formatted system overview
    """
    # Authorization check
    user = get_current_user()
    await check_resource_access(user, device_id, "overview")

    # Fetch data
    system_service = get_system_service()
    overview = await system_service.get_overview(device_id)

    # Return as formatted JSON
    return json.dumps(overview, indent=2)
```

### Resource with Metadata

```python
from fastmcp import FastMCP
from fastmcp.resources import Resource

@mcp.resource(
    uri="device://{device_id}/config",
    name="RouterOS Configuration",
    description="Current device configuration export",
    mime_type="text/x-routeros-script"
)
async def device_config(device_id: str) -> str:
    """RouterOS configuration export in native format.

    Returns the current device configuration as a RouterOS script.
    Suitable for backup, comparison, or documentation purposes.

    Args:
        device_id: Device identifier

    Returns:
        RouterOS configuration script
    """
    user = get_current_user()
    await check_resource_access(user, device_id, "config")

    snapshot_service = get_snapshot_service()
    config = await snapshot_service.get_current_config(device_id)

    return config
```

### Subscribable Resource

```python
@mcp.resource(
    uri="device://{device_id}/health",
    name="Device Health Metrics",
    description="Real-time device health status and metrics",
    subscribe=True
)
async def device_health(device_id: str) -> str:
    """Real-time device health metrics (subscribable).

    Provides current health status including:
    - Overall health state (healthy/warning/critical)
    - CPU usage percentage
    - Memory usage
    - Temperature and voltage
    - Interface states
    - Last health check timestamp

    Supports subscriptions for real-time updates when health changes.

    Args:
        device_id: Device identifier

    Returns:
        JSON-formatted health metrics
    """
    user = get_current_user()
    await check_resource_access(user, device_id, "health")

    health_service = get_health_service()
    health = await health_service.get_current_health(device_id)

    return json.dumps(health, indent=2)

# Notification on health change
async def on_health_check_complete(device_id: str, health_status: str):
    """Notify subscribers when health status changes."""
    await mcp.notify_resource_updated(f"device://{device_id}/health")

    # Also notify fleet summary if health changed
    if health_status in ["warning", "critical"]:
        await mcp.notify_resource_updated("fleet://health-summary")
```

### Parameterized Resource

```python
@mcp.resource("device://{device_id}/logs")
async def device_logs(
    device_id: str,
    since: str | None = None,
    level: str | None = None,
    limit: int = 100
) -> str:
    """Device system logs with filtering.

    Args:
        device_id: Device identifier
        since: ISO8601 timestamp for log start (optional)
        level: Filter by log level (info/warning/error/critical)
        limit: Maximum number of log entries (default 100, max 1000)

    Returns:
        JSON array of log entries
    """
    user = get_current_user()
    await check_resource_access(user, device_id, "logs")

    # Validate parameters
    if limit > 1000:
        raise ValueError("Limit cannot exceed 1000 entries")

    # Fetch logs
    log_service = get_log_service()
    logs = await log_service.get_device_logs(
        device_id=device_id,
        since=since,
        level=level,
        limit=limit
    )

    return json.dumps({"logs": logs, "count": len(logs)}, indent=2)
```

### List Resource

```python
@mcp.resource("fleet://devices")
async def fleet_devices(
    environment: str | None = None,
    status: str | None = None,
    tag: str | None = None
) -> str:
    """List of all managed devices with optional filtering.

    Args:
        environment: Filter by environment (lab/staging/prod)
        status: Filter by health status (healthy/degraded/unreachable)
        tag: Filter by device tag

    Returns:
        JSON array of device summaries
    """
    user = get_current_user()

    device_service = get_device_service()
    devices = await device_service.list_devices(
        user=user,
        environment=environment,
        status=status,
        tag=tag
    )

    # Return summary view
    device_summaries = [
        {
            "device_id": d.id,
            "name": d.name,
            "environment": d.environment,
            "status": d.status,
            "management_address": d.management_address,
            "tags": d.tags
        }
        for d in devices
    ]

    return json.dumps({"devices": device_summaries, "count": len(device_summaries)}, indent=2)
```

### Aggregated Resource

```python
@mcp.resource("fleet://health-summary")
async def fleet_health_summary() -> str:
    """Fleet-wide health summary with aggregated metrics.

    Provides:
    - Total device count
    - Health status distribution
    - Average CPU/memory usage
    - Devices requiring attention
    - Recent health trends

    Returns:
        JSON-formatted fleet health summary
    """
    user = get_current_user()

    health_service = get_health_service()
    summary = await health_service.get_fleet_summary(user=user)

    return json.dumps(summary, indent=2)
```

---

## Phase-1 Fallback Tools for Resources

### Overview

For MCP clients that support **tools-only** (e.g., ChatGPT, Mistral AI), Phase-1 fallback tools provide access to resource data through the tools interface.

These tools mirror the functionality of Phase-2 resources and include `resource_uri` hints to enable future migration to resource-based workflows.

### Device Resources - Phase-1 Fallback Tools

| Resource URI | Fallback Tool | Documentation |
|--------------|---------------|---------------|
| `device://{id}/health` | `device/get-health-data` | [Doc 04](04-mcp-tools-interface-and-json-schema-specification.md#deviceget-health-data) |
| `device://{id}/config` | `device/get-config-snapshot` | [Doc 04](04-mcp-tools-interface-and-json-schema-specification.md#deviceget-config-snapshot) |

**Example: Device Health**

```python
# Phase-2: Resource-based (Claude Desktop, supported clients)
health_resource = await mcp.read_resource("device://dev-lab-01/health")

# Phase-1: Tool-based fallback (ChatGPT, Mistral)
health_data = await mcp.call_tool("device/get-health-data", {"device_id": "dev-lab-01"})
# Response includes: {"resource_uri": "device://dev-lab-01/health", ...}
```

### Fleet Resources - Phase-1 Fallback Tools

| Resource URI | Fallback Tool | Documentation |
|--------------|---------------|---------------|
| `fleet://{env}/summary` | `fleet/get-summary` | [Doc 04](04-mcp-tools-interface-and-json-schema-specification.md#fleetget-summary) |

**Example: Fleet Summary**

```python
# Phase-2: Resource-based
fleet_summary = await mcp.read_resource("fleet://lab/summary")

# Phase-1: Tool-based fallback
fleet_data = await mcp.call_tool("fleet/get-summary", {"environment": "lab"})
```

### Plan & Audit Resources - Phase-1 Fallback Tools

| Resource URI | Fallback Tool | Documentation |
|--------------|---------------|---------------|
| `plan://{id}` | `plan/get-details` | [Doc 04](04-mcp-tools-interface-and-json-schema-specification.md#planget-details) |
| `audit://{id}?filters` | `audit/get-events` | [Doc 04](04-mcp-tools-interface-and-json-schema-specification.md#auditget-events) |

### Snapshot Resources - Phase-1 Fallback Tools

| Resource URI | Fallback Tool | Documentation |
|--------------|---------------|---------------|
| `snapshot://{id}` | `snapshot/get-content` | [Doc 04](04-mcp-tools-interface-and-json-schema-specification.md#snapshotget-content) |

### Migration Path

**Current (Phase 1):** Tools-only clients use fallback tools
**Future (Phase 2):** Clients migrate to resource-based workflows
**Compatibility:** Fallback tools include `resource_uri` for discovery

```python
# Tool response includes migration hint
{
  "resource_uri": "device://dev-lab-01/health",  # Future migration path
  "device_id": "dev-lab-01",
  "health_status": "healthy",
  # ... health data
}
```

---

## Resource Metadata Enhancement

### Overview

Following MCP best practices, all resources include comprehensive metadata to enable clients to make informed decisions about context loading and resource usage.

### Resource Metadata Structure

Resources MUST return structured metadata using the `Resource` type:

```python
from fastmcp.resources import Resource
from datetime import datetime

@mcp.resource("device://{device_id}/config")
async def device_config_resource(device_id: str) -> Resource:
    """RouterOS configuration export with full metadata."""

    # Fetch configuration
    content = await snapshot_service.get_current_config(device_id)
    device = await device_service.get_device(device_id)

    return Resource(
        uri=f"device://{device_id}/config",
        name=f"Configuration: {device.name}",
        description=f"Complete RouterOS configuration export for {device.name} ({device.environment}). "
                    f"Includes all system settings, interfaces, routing, firewall rules. "
                    f"Use for configuration analysis, backup, or comparison.",
        mime_type="text/x-routeros-script",
        text=content,

        # Metadata for client decision-making
        metadata={
            "device_id": device_id,
            "device_name": device.name,
            "environment": device.environment,
            "routeros_version": device.routeros_version,
            "size_bytes": len(content),
            "size_hint_kb": round(len(content) / 1024, 2),
            "snapshot_timestamp": datetime.utcnow().isoformat(),
            "format": "routeros_script",
            "content_sections": [
                "system", "interfaces", "ip", "routing",
                "firewall", "services", "wireless"
            ],
            "estimated_tokens": estimate_tokens(content),  # Approx token count
            "safe_for_context": len(content) < 50000,  # Under 50KB safe for most models
        }
    )
```

### Metadata Fields Standard

All resources SHOULD include these metadata fields:

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `uri` | string | ✅ Yes | Unique resource identifier |
| `name` | string | ✅ Yes | Human-readable title |
| `description` | string | ✅ Yes | What the resource contains and when to use it |
| `mime_type` | string | ✅ Yes | Content type (text/plain, application/json, etc.) |
| `metadata.size_bytes` | integer | ✅ Yes | Exact content size |
| `metadata.size_hint_kb` | float | ⚠️ Recommended | Size in KB for quick assessment |
| `metadata.estimated_tokens` | integer | ⚠️ Recommended | Approximate token count for context planning |
| `metadata.safe_for_context` | boolean | ⚠️ Recommended | Whether safe to load into typical context windows |
| `metadata.snapshot_timestamp` | string | ⚠️ Recommended | When data was captured (ISO 8601) |
| `metadata.content_sections` | array | Optional | Logical sections/topics in content |

### Token Estimation

Implement a token estimator for accurate context planning:

```python
def estimate_tokens(text: str) -> int:
    """Estimate token count for text content.

    Uses a simple heuristic: ~4 characters per token for English text.
    For more accuracy, integrate with tiktoken library for specific models.

    Args:
        text: Content to estimate tokens for

    Returns:
        Estimated token count
    """
    # Simple estimation (4 chars/token average)
    return len(text) // 4

    # OR use tiktoken for accuracy:
    # import tiktoken
    # encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
    # return len(encoding.encode(text))
```

### Discovery Strategy

#### Static Resources

Resources that always exist regardless of dynamic data:

```python
@mcp.resource("fleet://lab/schema")
async def fleet_schema() -> Resource:
    """Schema definition for lab environment (static resource)."""
    schema = {
        "device_schema": {...},
        "tag_schema": {...}
    }

    content = json.dumps(schema, indent=2)

    return Resource(
        uri="fleet://lab/schema",
        name="Lab Fleet Schema",
        description="Schema definitions for lab environment devices and metadata",
        mime_type="application/json",
        text=content,
        metadata={
            "type": "static",
            "version": "1.0",
            "size_bytes": len(content),
            "size_hint_kb": round(len(content) / 1024, 2),
            "estimated_tokens": estimate_tokens(content),
            "safe_for_context": True
        }
    )
```

#### Dynamic Resources (URI Templates)

Resources created on-demand based on parameters:

```python
@mcp.resource("device://{device_id}/health")
async def device_health_resource(device_id: str) -> Resource:
    """Dynamic health resource per device."""
    health_data = await health_service.get_health(device_id)
    content = json.dumps(health_data, indent=2)

    return Resource(
        uri=f"device://{device_id}/health",
        name=f"Health: {health_data['device_name']}",
        description=f"Current health metrics and status for {health_data['device_name']}",
        mime_type="application/json",
        text=content,
        metadata={
            "type": "dynamic",
            "device_id": device_id,
            "health_status": health_data["status"],
            "last_check": health_data["last_check_timestamp"],
            "size_bytes": len(content),
            "size_hint_kb": round(len(content) / 1024, 2),
            "estimated_tokens": estimate_tokens(content),
            "safe_for_context": True  # Health data is always small
        }
    )
```

#### Resource List Response

When clients call `resources/list`, return metadata to aid discovery:

```json
{
  "resources": [
    {
      "uri": "device://{device_id}/config",
      "name": "Device Configuration",
      "description": "RouterOS configuration export. Use for backup, analysis, or documentation.",
      "mime_type": "text/x-routeros-script",
      "metadata": {
        "type": "dynamic",
        "template": true,
        "typical_size_kb": "20-100",
        "safe_for_context": true
      }
    },
    {
      "uri": "fleet://lab/summary",
      "name": "Lab Fleet Summary",
      "description": "Aggregated health and status for all lab devices",
      "mime_type": "application/json",
      "metadata": {
        "type": "static",
        "size_bytes": 2048,
        "safe_for_context": true
      }
    }
  ]
}
```

### Client Usage Example

Clients can use metadata to make informed decisions:

```python
# Client-side logic
async def smart_resource_load(resource_uri: str):
    """Load resource intelligently based on metadata."""

    # Get resource metadata without fetching content
    resource_list = await mcp.list_resources()
    resource_meta = next(r for r in resource_list if r["uri"] == resource_uri)

    # Check if safe for context
    if not resource_meta["metadata"].get("safe_for_context", True):
        logger.warning(
            f"Resource {resource_uri} is large "
            f"({resource_meta['metadata']['size_hint_kb']} KB). "
            "Consider filtering or pagination."
        )

        # Prompt user or use filtered version
        return await mcp.read_resource(resource_uri + "?limit=100")

    # Safe to load fully
    return await mcp.read_resource(resource_uri)
```

### Implementation Checklist

- [ ] All resources return `Resource` type with metadata
- [ ] Include `size_bytes`, `size_hint_kb`, `estimated_tokens` for all resources
- [ ] Mark `safe_for_context` based on size thresholds
- [ ] Distinguish static vs dynamic resources in metadata
- [ ] Implement token estimation function
- [ ] Provide resource list with metadata for discovery
- [ ] Document typical size ranges for dynamic resources

---

## Resource Access Control

### Resource Authorization Pattern

```python
async def check_resource_access(user: User, device_id: str, resource_type: str):
    """Verify user has permission to access device resource.

    Args:
        user: Current user from MCP context
        device_id: Target device
        resource_type: Type of resource being accessed

    Raises:
        McpError: If access is denied
    """
    device_service = get_device_service()
    authz_service = get_authz_service()

    # Get device
    try:
        device = await device_service.get_device(device_id)
    except DeviceNotFoundError:
        raise McpError(
            code=-32000,
            message="Device not found",
            data={"device_id": device_id}
        )

    # Check device scope
    if not authz_service.device_in_scope(user, device):
        raise McpError(
            code=-32002,
            message="Access denied: device out of scope",
            data={"device_id": device_id}
        )

    # Check resource-specific permissions
    # Sensitive resources may require higher privileges
    if resource_type in ["config", "logs"] and user.role == "read_only":
        raise McpError(
            code=-32002,
            message="Access denied: insufficient permissions for resource",
            data={"device_id": device_id, "resource_type": resource_type}
        )

    # Audit log for sensitive resource access
    if resource_type in ["config", "logs", "audit"]:
        audit_service = get_audit_service()
        await audit_service.log_resource_access(
            user=user,
            device_id=device_id,
            resource_type=resource_type
        )
```

---

## MCP Prompts Overview

### Prompt Concept in MCP

**Prompts** are reusable templates that guide users through workflows:

- User-controlled (explicitly invoked by users)
- Parameterized for flexibility
- Provide step-by-step instructions
- Help discover valid parameter values
- Document best practices

### Use Cases for RouterOS Prompts

1. **Workflow Guides** - Step-by-step instructions for complex operations
2. **Troubleshooting** - Diagnostic procedures for common issues
3. **Best Practices** - Security and operational guidance
4. **Onboarding** - New device registration workflows
5. **Change Management** - Plan/apply workflow templates

---

## Prompt Template Design

### Workflow Prompt Pattern

```python
from fastmcp import FastMCP
from typing import Literal

@mcp.prompt(
    name="dns-ntp-rollout",
    description="Step-by-step guide for rolling out DNS/NTP changes across devices"
)
async def dns_ntp_rollout_workflow(
    environment: Literal["lab", "staging", "prod"] = "lab",
    dry_run: bool = True
) -> str:
    """DNS/NTP configuration rollout workflow guide.

    Provides detailed steps for safely rolling out DNS and NTP server
    changes across a fleet of RouterOS devices, with environment-specific
    guidance and safety checks.

    Args:
        environment: Target environment for rollout
        dry_run: Whether to recommend dry-run first (default: true)

    Returns:
        Formatted workflow guide
    """
    # Fetch context
    device_service = get_device_service()
    devices = await device_service.list_devices(environment=environment)
    device_count = len(devices)

    # Get capability flags for environment
    capabilities = await get_environment_capabilities(environment)

    safety_note = ""
    if environment == "prod":
        safety_note = """
⚠️  PRODUCTION ENVIRONMENT ALERT ⚠️
- Changes require admin role
- Plan/apply workflow is MANDATORY
- Human approval token required
- Devices must have allow_advanced_writes=true
- Post-change monitoring required
"""

    dry_run_recommendation = ""
    if dry_run:
        dry_run_recommendation = """
### Dry Run First
Before applying changes, use dry_run=true to preview:
- What will change on each device
- Current vs. new values
- Any validation warnings
"""

    return f"""
# DNS/NTP Rollout Workflow for {environment.upper()}

## Overview
Rolling out DNS/NTP changes to **{device_count} devices** in {environment} environment.

{safety_note}

## Prerequisites
- [ ] User role: {'admin' if environment == 'prod' else 'ops_rw or admin'}
- [ ] Environment: {environment}
- [ ] Devices have allow_advanced_writes={capabilities.get('allow_advanced_writes', False)}
- [ ] Backup current DNS/NTP config (optional but recommended)

## Workflow Steps

### 1. List Target Devices
**Tool:** `device.list_devices`

**Parameters:**
```json
{{
  "environment": "{environment}"
}}
```

**Action:** Review device list, verify all intended devices are included.

---

### 2. Create Rollout Plan
**Tool:** `config.plan_dns_ntp_rollout`

**Parameters:**
```json
{{
  "device_ids": ["dev-001", "dev-002", ...],
  "dns_servers": ["8.8.8.8", "8.8.4.4"],
  "ntp_servers": ["time.cloudflare.com", "time.google.com"],
  "description": "DNS/NTP update for {environment} - YYYY-MM-DD"
}}
```

**Action:** System creates an immutable plan with per-device change details.

{dry_run_recommendation}

---

### 3. Review Plan Details
**Resource:** `plan://{{plan_id}}/details`

**Review checklist:**
- [ ] All intended devices included
- [ ] Current DNS/NTP values are correct
- [ ] New values are correct
- [ ] Risk levels are acceptable
- [ ] No precondition failures
- [ ] Change windows appropriate

**Action:** Verify plan is correct before proceeding.

---

### 4. Obtain Approval {'(Required for Production)' if environment == 'prod' else '(Optional for Lab/Staging)'}
{'**For production only:**' if environment == 'prod' else '**For audit trail:**'}

- Navigate to admin UI approval page
- Review plan summary
- Generate short-lived approval token
- Token is bound to plan_id and your user identity

**Action:** Save approval token for next step.

---

### 5. Apply Changes
**Tool:** `config.apply_dns_ntp_rollout`

**Parameters:**
```json
{{
  "plan_id": "<plan_id from step 2>",
  {"approval_token": "<token from step 4>"," if environment == 'prod' else ""}
  "batch_size": 5,
  "pause_between_batches_seconds": 30
}}
```

**Action:** System applies changes in batches with health checks.

**Monitoring:** Watch apply progress and health status.

---

### 6. Verify Success
**Post-apply checklist:**
- [ ] All devices show changed=true (or false if no actual change)
- [ ] Health checks remain green
- [ ] Sample DNS/NTP queries work correctly
- [ ] Audit log shows successful completion

**Tools for verification:**
- `device.check_connectivity` - Verify device reachability
- `dns.get_status` - Check DNS configuration
- `ntp.get_status` - Verify NTP sync
- `system.get_overview` - Overall health

---

## Rollback Procedure
If issues occur after apply:

1. **Assess Impact:** Check health summary and failed device count
2. **Use Rollback Tool:** `config.rollback_plan` with plan_id
3. **Or Manual Revert:** Use `dns.update_servers` and `ntp.update_servers` per device

**Rollback resource:** `plan://{{plan_id}}/rollback-plan`

---

## Safety Notes
- Always test in **lab** environment first
- Use **staging** for final validation before production
- Production changes require **admin approval**
- Monitor **health checks** for 5-10 minutes post-change
- Have **rollback plan** ready before applying to production

---

## Troubleshooting Common Issues

**Issue:** Precondition check fails
- **Solution:** Review device capability flags, verify devices allow advanced writes

**Issue:** DNS resolution fails post-change
- **Solution:** Verify DNS servers are reachable, check firewall rules

**Issue:** NTP sync fails
- **Solution:** Ensure NTP port 123/UDP is allowed, verify server reachability

**Issue:** Device becomes unreachable during apply
- **Solution:** Apply will pause; investigate network issue, resume or rollback

---

## Additional Resources
- `troubleshoot-device` prompt for device-specific diagnostics
- `fleet://health-summary` resource for overall health
- `audit://events/recent` for operation logs
"""
```

### Troubleshooting Prompt Pattern

```python
@mcp.prompt(
    name="troubleshoot-device",
    description="Device troubleshooting diagnostic workflow"
)
async def troubleshoot_device_guide(
    device_id: str | None = None,
    issue_type: Literal["connectivity", "performance", "health", "config"] | None = None
) -> str:
    """Device troubleshooting workflow with diagnostics.

    Args:
        device_id: Specific device to troubleshoot (optional)
        issue_type: Type of issue being investigated

    Returns:
        Diagnostic workflow guide
    """
    if not device_id:
        return """
# Device Troubleshooting Guide

## Getting Started
To get device-specific troubleshooting, provide a `device_id` parameter.

### Find Devices
**Tool:** `device.list_devices`

Filter by status:
- `status: "unreachable"` - Devices that cannot be contacted
- `status: "degraded"` - Devices with health warnings
- `status: "healthy"` - Normal devices

Once you have a device_id, re-run this prompt with that parameter.

## General Troubleshooting Steps

### 1. Check Device List
Verify device is registered and has correct management address.

### 2. Test Connectivity
Use `device.check_connectivity` to verify basic reachability.

### 3. Review Recent Health
Check `device://{device_id}/health` resource for health history.

### 4. Check Audit Logs
Review `audit://events/by-device/{device_id}` for recent operations.

### 5. System Overview
Use `system.get_overview` for current system state.
"""

    # Device-specific guidance
    device_service = get_device_service()
    device = await device_service.get_device(device_id)

    health_service = get_health_service()
    health = await health_service.get_current_health(device_id)

    # Determine likely issues
    diagnostics = await generate_diagnostic_recommendations(device, health, issue_type)

    return f"""
# Troubleshooting Device: {device.name}

## Device Information
- **ID:** {device_id}
- **Environment:** {device.environment}
- **Management Address:** {device.management_address}
- **Status:** {device.status}
- **Last Health Check:** {health.last_check_timestamp}
- **Current Health:** {health.status}

## Quick Diagnostics

### 1. Connectivity Check
**Tool:** `device.check_connectivity`

```json
{{ "device_id": "{device_id}" }}
```

**Expected:** Should respond within 2-5 seconds with identity information.

---

### 2. System Overview
**Tool:** `system.get_overview`

```json
{{ "device_id": "{device_id}" }}
```

**Review:**
- CPU usage (high = potential overload)
- Memory usage (high = potential issue)
- Uptime (recent reboot?)
- Temperature (overheat warning?)

---

### 3. Interface Status
**Tool:** `interface.list_interfaces`

```json
{{ "device_id": "{device_id}" }}
```

**Check:**
- Management interface is UP
- Expected interfaces are present
- No unexpected DOWN interfaces

---

### 4. Recent Logs
**Resource:** `device://{device_id}/logs/recent`

**Look for:**
- Error messages
- Connection failures
- Configuration changes

---

### 5. DNS/NTP Status
**Tools:**
- `dns.get_status` - Verify DNS resolution
- `ntp.get_status` - Check time sync

---

{diagnostics}

## Common Issues and Solutions

### Device Unreachable
**Symptoms:** Cannot contact device via REST API

**Diagnostic steps:**
1. Verify network connectivity (ping management IP)
2. Check firewall rules (allow REST API port)
3. Verify RouterOS REST API service is running
4. Check MCP stored credentials are correct

**Resolution:**
- Fix network connectivity
- Update management address if changed
- Rotate credentials if auth failed

---

### High CPU Usage
**Symptoms:** CPU > 80% sustained

**Diagnostic steps:**
1. Check `system.get_overview` for CPU details
2. Review processes via RouterOS CLI (if permitted)
3. Check for traffic spikes in interface stats

**Resolution:**
- Reduce polling frequency
- Investigate traffic anomalies
- Consider hardware upgrade

---

### Configuration Drift
**Symptoms:** Device config differs from expected

**Diagnostic steps:**
1. Fetch current config: `device://{device_id}/config`
2. Compare with baseline or last known good
3. Review audit logs for manual changes

**Resolution:**
- Document expected changes
- Revert unwanted changes
- Update baseline if intentional

---

### DNS Resolution Failing
**Symptoms:** DNS queries not working

**Diagnostic steps:**
1. Check DNS server configuration
2. Verify DNS servers are reachable
3. Test DNS resolution with `tool.ping` to known hostname

**Resolution:**
- Update DNS servers
- Check firewall rules for port 53
- Verify upstream DNS is operational

---

## Next Steps
- Document findings in ticket/issue
- If issue persists, escalate with diagnostic results
- Consider creating health alert rule for this device

## Related Prompts
- `dns-ntp-rollout` - If DNS/NTP changes needed
- `device-onboarding` - If device needs re-registration
"""
```

### Onboarding Prompt Pattern

```python
@mcp.prompt(
    name="device-onboarding",
    description="Guide for registering a new RouterOS device"
)
async def device_onboarding_guide(
    environment: Literal["lab", "staging", "prod"] = "lab",
    automated: bool = False
) -> str:
    """Device onboarding workflow for registering new RouterOS devices.

    Args:
        environment: Target environment for device
        automated: Whether to use automated onboarding (Phase 3+)

    Returns:
        Step-by-step onboarding guide
    """
    method = "automated" if automated else "manual"

    return f"""
# Device Onboarding Guide

## Overview
Register a new RouterOS v7 device in the {environment} environment using {method} method.

## Prerequisites
- [ ] RouterOS v7.x device (minimum version 7.10 recommended)
- [ ] Device accessible via network
- [ ] REST API enabled on device
- [ ] Admin credentials for initial setup
- [ ] Device static IP or reserved DHCP (recommended)

---

## {method.upper()} Onboarding Process

{"### Automated Onboarding (Phase 3+)" if automated else "### Manual Onboarding"}

{_generate_onboarding_steps(environment, automated)}

---

## Post-Onboarding Verification

### 1. Check Device Registration
**Tool:** `device.list_devices`

**Verify:**
- Device appears in list
- Environment is correct
- Capability flags are set appropriately

---

### 2. Test Connectivity
**Tool:** `device.check_connectivity`

**Expected:** Successful connection with identity returned

---

### 3. Fetch System Overview
**Tool:** `system.get_overview`

**Verify:**
- All metrics populate correctly
- No connection errors
- Health status is healthy

---

### 4. Review Capabilities
**Resource:** `device://{{device_id}}/overview`

**Check:**
- RouterOS version compatible
- Features available match expectations
- No missing required packages

---

## Security Checklist
- [ ] Service account created with least privilege
- [ ] Credentials stored encrypted
- [ ] Management network access restricted
- [ ] Device capability flags set appropriately
- [ ] Audit logging enabled for device

---

## Troubleshooting

**Cannot connect to device:**
- Verify management IP is correct
- Check REST API is enabled: `/ip/service/print`
- Verify port is accessible (default 80/443)
- Test with curl: `curl http://device-ip/rest/system/identity`

**Credential errors:**
- Verify username/password correct
- Check service account exists on device
- Ensure account has appropriate permissions

**Device registration fails:**
- Check for duplicate device_id or management address
- Verify environment tag is valid
- Review MCP server logs for details

---

## Next Steps
- Set up health check monitoring
- Configure alerts for device
- Test read-only tools
- If advanced writes needed, update capability flags
- Add device tags for organization (site, role, etc.)

## Related Resources
- Device management docs: https://wiki.mikrotik.com/wiki/Manual:REST_API
- Security best practices: [internal wiki]
- Capability flags reference: `docs/02-security-oauth-integration-and-access-control.md`
"""

def _generate_onboarding_steps(environment: str, automated: bool) -> str:
    """Generate environment-specific onboarding steps."""
    if automated:
        return """
1. **Run Bootstrap Script on RouterOS Device**

   Upload and execute the bootstrap script:
   ```routeros
   /system script add name=mcp-bootstrap source=[/file get mcp-bootstrap.rsc contents]
   /system script run mcp-bootstrap
   ```

   The script will:
   - Create MCP service account with appropriate permissions
   - Enable REST API if not already enabled
   - Generate registration token
   - Call MCP registration API

2. **Verify Auto-Registration**

   Check device appears in MCP:
   **Tool:** `device.list_devices`

3. **Validate Credentials**

   MCP automatically stores credentials from bootstrap.

4. **Set Capability Flags**

   **Tool:** `device.update_metadata`
   Set environment-appropriate flags.
"""
    else:
        return f"""
1. **Create RouterOS Service Account**

   On the RouterOS device, create a dedicated service account:
   ```routeros
   /user group add name=mcp-readonly policy=read,api,rest-api,sensitive
   /user add name=mcp-readonly group=mcp-readonly password="<secure-password>"
   ```

   For devices allowing writes (lab/staging):
   ```routeros
   /user group add name=mcp-ops policy=read,write,api,rest-api,policy,sensitive
   /user add name=mcp-ops group=mcp-ops password="<secure-password>"
   ```

2. **Enable REST API (if not already enabled)**

   ```routeros
   /ip service enable api-ssl
   /ip service set api-ssl port=443
   ```

3. **Register Device in MCP**

   **API Endpoint:** `POST /admin/devices/register` (secured admin API)

   **Request:**
   ```json
   {{
     "name": "lab-router-01",
     "management_address": "192.168.1.1:443",
     "environment": "{environment}",
     "tags": ["site:main", "role:edge"],
     "credentials": {{
       "username": "mcp-readonly",
       "password": "<secure-password>"
     }},
     "capability_flags": {{
       "allow_advanced_writes": {"true" if environment == "lab" else "false"},
       "allow_professional_workflows": false
     }}
   }}
   ```

   **Response:**
   ```json
   {{
     "device_id": "dev-001",
     "status": "registered",
     "next_steps": ["verify connectivity", "run health check"]
   }}
   ```

4. **Verify Registration**

   **Tool:** `device.list_devices`

   Or use resource:
   **Resource:** `fleet://devices/{environment}`
"""
```

### Parameter Completion Pattern

```python
@mcp.prompt(
    name="create-address-list-entry",
    description="Guide for adding entries to MCP-managed address lists"
)
async def address_list_entry_guide(
    device_id: str | None = None,
    address_list_name: str | None = None
) -> str:
    """Guide for adding entries to address lists with parameter suggestions.

    Args:
        device_id: Target device (provides list completion)
        address_list_name: Address list name (provides list completion)

    Returns:
        Workflow guide with parameter suggestions
    """
    # Provide parameter completion suggestions
    if not device_id:
        devices = await device_service.list_devices()
        device_list = "\n".join([f"- {d.id}: {d.name} ({d.environment})" for d in devices[:10]])

        return f"""
# Add Address List Entry Guide

## Step 1: Select Device

Available devices (showing first 10):

{device_list}

Re-run this prompt with `device_id` parameter to continue.
"""

    if not address_list_name:
        # Fetch address lists for device
        lists = await ip_service.list_address_lists(device_id)
        mcp_managed = [l for l in lists if l.get("comment", "").startswith("MCP-managed")]

        list_display = "\n".join([f"- {l['name']}: {l.get('comment', 'No description')}" for l in mcp_managed])

        return f"""
# Add Address List Entry for Device {device_id}

## Step 2: Select Address List

MCP-managed address lists on this device:

{list_display}

Re-run this prompt with both `device_id` and `address_list_name` to see full workflow.
"""

    # Full workflow with both parameters
    return f"""
# Add Address List Entry

## Configuration
- **Device:** {device_id}
- **Address List:** {address_list_name}

## Workflow

### 1. Add Entry
**Tool:** `ip.add_address_list_entry`

**Parameters:**
```json
{{
  "device_id": "{device_id}",
  "list_name": "{address_list_name}",
  "address": "10.0.1.5",
  "comment": "Application server - added YYYY-MM-DD",
  "timeout": "1d"
}}
```

**Options:**
- `address`: IP address or subnet (CIDR notation)
- `comment`: Description (recommended)
- `timeout`: Auto-expiry (optional, e.g., "1d", "1h", "00:30:00")

### 2. Verify Entry
**Tool:** `ip.list_address_list_entries`

**Check:** Entry appears in list with correct details

### 3. Test (if applicable)
If address list is used in firewall rules, verify:
- Traffic is allowed/denied as expected
- Logs show rule hits (if logging enabled)

## Safety Notes
- Only MCP-managed address lists can be modified
- Changes take effect immediately
- For production, consider using plan/apply workflow
- Always add descriptive comments for audit trail

## Remove Entry Later
**Tool:** `ip.remove_address_list_entry`

**Parameters:**
```json
{{
  "device_id": "{device_id}",
  "list_name": "{address_list_name}",
  "address": "10.0.1.5"
}}
```
"""
```

---

## Integration with Tools and Resources

### Cross-Reference Pattern

Prompts should reference tools and resources:

```python
@mcp.prompt(name="comprehensive-device-review")
async def comprehensive_review(device_id: str) -> str:
    """Comprehensive device review workflow using multiple tools and resources."""

    return f"""
# Comprehensive Device Review: {device_id}

This workflow uses multiple tools and resources to get a complete picture.

## 1. System Overview
**Resource:** `device://{device_id}/overview`

Review for:
- RouterOS version and uptime
- CPU and memory usage trends
- System health (temperature, voltage)

---

## 2. Configuration Snapshot
**Resource:** `device://{device_id}/config`

Save current configuration:
1. Fetch resource
2. Save to version control or backup location
3. Compare with previous version to detect drift

---

## 3. Network Interfaces
**Tool:** `interface.list_interfaces`

Check:
- All interfaces up/down status correct
- Traffic counters for utilization
- No unexpected errors

---

## 4. IP Addressing
**Tool:** `ip.list_addresses`

Verify:
- Management IP is correct
- All expected IPs are present
- No conflicts or duplicates

---

## 5. Services Status
**Tools:**
- `dns.get_status` - DNS resolution working
- `ntp.get_status` - Time sync accurate

---

## 6. Recent Logs
**Resource:** `device://{device_id}/logs/recent`

Look for:
- Error messages in last 24 hours
- Configuration changes
- Connection issues

---

## 7. Health History
**Resource:** `device://{device_id}/health`

Review:
- Current health status
- Recent health check results
- Trend analysis

---

## 8. Audit Trail
**Resource:** `audit://events/by-device/{device_id}`

Review:
- Recent operations via MCP
- Who made changes and when
- Success/failure patterns

---

## Summary Checklist
After review, verify:
- [ ] Device is healthy and stable
- [ ] Configuration matches expected state
- [ ] No recent errors or issues
- [ ] Services running correctly
- [ ] No security concerns

## Next Steps
- Document any findings
- Create tickets for issues
- Schedule maintenance if needed
- Update device tags/metadata if appropriate
"""
```

---

## Resource Versioning and Caching

### ETag-Based Resource Versioning

Implement ETags for efficient resource caching and change detection:

```python
import hashlib
from fastmcp import FastMCP
from fastmcp.resources import ResourceResponse

@mcp.resource("device://{device_id}/config")
async def device_config(device_id: str) -> ResourceResponse:
    """RouterOS configuration with ETag support."""

    # Fetch config
    snapshot_service = get_snapshot_service()
    config = await snapshot_service.get_current_config(device_id)

    # Generate ETag from content hash
    etag = hashlib.sha256(config.encode()).hexdigest()[:16]

    # Check if client has current version
    context = get_context()
    if_none_match = context.get_header("If-None-Match")

    if if_none_match == etag:
        # Client has current version
        return ResourceResponse(
            status=304,  # Not Modified
            headers={"ETag": etag}
        )

    # Return config with ETag
    return ResourceResponse(
        content=config,
        headers={
            "ETag": etag,
            "Cache-Control": "max-age=300",  # Cache for 5 minutes
            "Last-Modified": snapshot_service.last_snapshot_time.isoformat()
        },
        mime_type="text/x-routeros-script"
    )
```

### Last-Modified Timestamp Pattern

```python
from datetime import datetime

@mcp.resource("device://{device_id}/health")
async def device_health(device_id: str) -> ResourceResponse:
    """Health metrics with last-modified timestamp."""

    health_service = get_health_service()
    health = await health_service.get_current_health(device_id)

    last_check = health.get("last_check_timestamp")

    # Check if-modified-since header
    context = get_context()
    if_modified_since = context.get_header("If-Modified-Since")

    if if_modified_since:
        if_modified_dt = datetime.fromisoformat(if_modified_since)
        last_check_dt = datetime.fromisoformat(last_check)

        if last_check_dt <= if_modified_dt:
            return ResourceResponse(status=304)  # Not Modified

    return ResourceResponse(
        content=json.dumps(health, indent=2),
        headers={
            "Last-Modified": last_check,
            "Cache-Control": "max-age=60",  # Cache for 1 minute
            "X-Health-Status": health["status"]
        },
        mime_type="application/json"
    )
```

---

## Resource Pagination and Filtering

### Cursor-Based Pagination

Implement cursor-based pagination for large resource collections:

```python
from pydantic import BaseModel
from typing import Optional
import base64
import json

class PaginationCursor(BaseModel):
    """Cursor for pagination."""
    last_id: str
    timestamp: str
    offset: int

@mcp.resource("audit://events/recent")
async def audit_events_recent(
    limit: int = 50,
    cursor: Optional[str] = None,
    event_type: Optional[str] = None
) -> str:
    """Recent audit events with cursor-based pagination.

    Args:
        limit: Number of events to return (max 500)
        cursor: Pagination cursor from previous response
        event_type: Filter by event type (tool_call, config_change, etc.)

    Returns:
        JSON with events and next cursor
    """
    if limit > 500:
        limit = 500

    # Decode cursor
    decoded_cursor = None
    if cursor:
        try:
            cursor_data = base64.b64decode(cursor).decode()
            decoded_cursor = PaginationCursor(**json.loads(cursor_data))
        except Exception:
            raise ValueError("Invalid pagination cursor")

    # Fetch events
    audit_service = get_audit_service()
    events = await audit_service.get_recent_events(
        limit=limit,
        after_id=decoded_cursor.last_id if decoded_cursor else None,
        event_type=event_type
    )

    # Generate next cursor
    next_cursor = None
    if len(events) == limit:
        # More results available
        last_event = events[-1]
        cursor_obj = PaginationCursor(
            last_id=last_event["id"],
            timestamp=last_event["timestamp"],
            offset=decoded_cursor.offset + limit if decoded_cursor else limit
        )
        cursor_json = json.dumps(cursor_obj.model_dump())
        next_cursor = base64.b64encode(cursor_json.encode()).decode()

    result = {
        "events": events,
        "count": len(events),
        "pagination": {
            "cursor": next_cursor,
            "has_more": next_cursor is not None,
            "limit": limit
        }
    }

    return json.dumps(result, indent=2)
```

### Filtering and Search Patterns

```python
@mcp.resource("device://{device_id}/interfaces")
async def device_interfaces(
    device_id: str,
    status: Optional[str] = None,  # Filter: up, down, disabled
    type: Optional[str] = None,    # Filter: ether, wlan, bridge, vlan
    search: Optional[str] = None   # Search by name
) -> str:
    """Device interfaces with filtering and search.

    Args:
        device_id: Device identifier
        status: Filter by interface status
        type: Filter by interface type
        search: Search interface names (case-insensitive)

    Returns:
        Filtered interface list
    """
    interface_service = get_interface_service()
    interfaces = await interface_service.list_interfaces(device_id)

    # Apply filters
    if status:
        interfaces = [i for i in interfaces if i.get("running") == (status == "up")]

    if type:
        interfaces = [i for i in interfaces if i.get("type") == type]

    if search:
        search_lower = search.lower()
        interfaces = [i for i in interfaces if search_lower in i.get("name", "").lower()]

    return json.dumps({
        "interfaces": interfaces,
        "count": len(interfaces),
        "filters": {
            "status": status,
            "type": type,
            "search": search
        }
    }, indent=2)
```

---

## Resource Subscription Management

### Subscription Lifecycle

Implement robust subscription management:

```python
from dataclasses import dataclass, field
from typing import Set
from uuid import uuid4

@dataclass
class ResourceSubscription:
    """Resource subscription state."""
    subscription_id: str = field(default_factory=lambda: str(uuid4()))
    resource_uri: str
    session_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_notification: Optional[datetime] = None
    notification_count: int = 0

class ResourceSubscriptionManager:
    """Manage resource subscriptions."""

    def __init__(self):
        # uri -> set of subscriptions
        self._subscriptions: dict[str, Set[ResourceSubscription]] = defaultdict(set)

        # subscription_id -> subscription
        self._subscription_map: dict[str, ResourceSubscription] = {}

    async def subscribe(
        self,
        resource_uri: str,
        session_id: str
    ) -> ResourceSubscription:
        """Subscribe to resource updates."""
        subscription = ResourceSubscription(
            resource_uri=resource_uri,
            session_id=session_id
        )

        self._subscriptions[resource_uri].add(subscription)
        self._subscription_map[subscription.subscription_id] = subscription

        logger.info(
            "Resource subscription created",
            extra={
                "subscription_id": subscription.subscription_id,
                "resource_uri": resource_uri,
                "session_id": session_id
            }
        )

        return subscription

    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from resource updates."""
        subscription = self._subscription_map.pop(subscription_id, None)
        if not subscription:
            return

        self._subscriptions[subscription.resource_uri].discard(subscription)

        logger.info(
            "Resource subscription removed",
            extra={
                "subscription_id": subscription_id,
                "resource_uri": subscription.resource_uri,
                "notifications_sent": subscription.notification_count
            }
        )

    async def notify_subscribers(self, resource_uri: str) -> None:
        """Notify all subscribers of resource update."""
        subscriptions = self._subscriptions.get(resource_uri, set())

        if not subscriptions:
            return

        logger.info(
            f"Notifying {len(subscriptions)} subscribers of resource update",
            extra={"resource_uri": resource_uri}
        )

        for subscription in subscriptions:
            try:
                await mcp.send_notification(
                    session_id=subscription.session_id,
                    method="notifications/resources/updated",
                    params={"uri": resource_uri}
                )

                subscription.last_notification = datetime.utcnow()
                subscription.notification_count += 1

            except Exception as e:
                logger.error(
                    f"Failed to notify subscriber: {e}",
                    extra={
                        "subscription_id": subscription.subscription_id,
                        "resource_uri": resource_uri
                    }
                )

    async def cleanup_session_subscriptions(self, session_id: str) -> None:
        """Remove all subscriptions for a closed session."""
        to_remove = [
            sub for sub in self._subscription_map.values()
            if sub.session_id == session_id
        ]

        for subscription in to_remove:
            await self.unsubscribe(subscription.subscription_id)

        logger.info(
            f"Cleaned up {len(to_remove)} subscriptions for closed session",
            extra={"session_id": session_id}
        )

# Global subscription manager
subscription_manager = ResourceSubscriptionManager()

# Integration with session lifecycle
@mcp.on_close
async def on_session_close():
    """Clean up subscriptions when session closes."""
    context = get_context()
    session_id = context.get("session_id")

    if session_id:
        await subscription_manager.cleanup_session_subscriptions(session_id)
```

---

## Resource Error Handling Patterns

### Partial Failure Handling

Handle scenarios where some data is unavailable:

```python
@mcp.resource("fleet://health-summary")
async def fleet_health_summary() -> str:
    """Fleet health with graceful degradation for unreachable devices."""

    device_service = get_device_service()
    health_service = get_health_service()

    devices = await device_service.list_devices()

    successful = []
    failed = []

    # Fetch health for each device (with timeout)
    for device in devices:
        try:
            health = await asyncio.wait_for(
                health_service.get_current_health(device.id),
                timeout=2.0
            )
            successful.append({
                "device_id": device.id,
                "name": device.name,
                "health": health
            })

        except asyncio.TimeoutError:
            failed.append({
                "device_id": device.id,
                "name": device.name,
                "error": "timeout"
            })

        except Exception as e:
            failed.append({
                "device_id": device.id,
                "name": device.name,
                "error": str(e)
            })

    # Compute aggregates from successful devices only
    total_cpu = sum(d["health"]["cpu_usage"] for d in successful)
    avg_cpu = total_cpu / len(successful) if successful else 0

    result = {
        "summary": {
            "total_devices": len(devices),
            "healthy_devices": len(successful),
            "unreachable_devices": len(failed),
            "average_cpu_usage": avg_cpu
        },
        "healthy_devices": successful,
        "unreachable_devices": failed if failed else None,
        "_meta": {
            "partial_failure": len(failed) > 0,
            "completeness_percentage": (len(successful) / len(devices)) * 100
        }
    }

    return json.dumps(result, indent=2)
```

### Resource-Specific Error Codes

```python
class ResourceError(McpError):
    """Base error for resource operations."""
    pass

class ResourceNotFoundError(ResourceError):
    """Resource does not exist."""
    code = -32000
    message = "Resource not found"

class ResourceUnavailableError(ResourceError):
    """Resource temporarily unavailable."""
    code = -32001
    message = "Resource unavailable"

class ResourceAuthorizationError(ResourceError):
    """User not authorized to access resource."""
    code = -32002
    message = "Access denied"

@mcp.resource("device://{device_id}/config")
async def device_config(device_id: str) -> str:
    """Config with specific error handling."""

    try:
        device = await device_service.get_device(device_id)
    except DeviceNotFoundError:
        raise ResourceNotFoundError(
            data={"device_id": device_id, "resource_uri": f"device://{device_id}/config"}
        )

    try:
        config = await snapshot_service.get_current_config(device_id)
    except DeviceUnreachableError:
        raise ResourceUnavailableError(
            message="Device unreachable, cannot fetch config",
            data={
                "device_id": device_id,
                "suggested_action": "Check device connectivity and try again"
            }
        )

    return config
```

---

## Resource Performance and Caching

### In-Memory Resource Caching

```python
from functools import lru_cache
from datetime import timedelta
import asyncio

class ResourceCache:
    """Simple TTL cache for resource data."""

    def __init__(self, default_ttl: int = 300):
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._default_ttl = default_ttl

    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable,
        ttl: Optional[int] = None
    ) -> Any:
        """Get cached value or compute if expired."""
        ttl = ttl or self._default_ttl

        # Check cache
        if key in self._cache:
            value, expires_at = self._cache[key]
            if datetime.utcnow() < expires_at:
                return value

        # Compute new value
        value = await compute_fn()

        # Cache with expiry
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        self._cache[key] = (value, expires_at)

        return value

    def invalidate(self, key: str) -> None:
        """Invalidate cache entry."""
        self._cache.pop(key, None)

# Global cache
resource_cache = ResourceCache(default_ttl=300)

@mcp.resource("fleet://health-summary")
async def fleet_health_summary() -> str:
    """Fleet health with caching."""

    cache_key = "fleet:health:summary"

    async def compute_health_summary():
        health_service = get_health_service()
        return await health_service.get_fleet_summary()

    summary = await resource_cache.get_or_compute(
        cache_key,
        compute_health_summary,
        ttl=60  # Cache for 1 minute
    )

    return json.dumps(summary, indent=2)

# Invalidate cache when health changes
async def on_health_check_complete(device_id: str):
    """Invalidate caches when health changes."""
    # Invalidate device-specific cache
    resource_cache.invalidate(f"device:{device_id}:health")

    # Invalidate fleet summary cache
    resource_cache.invalidate("fleet:health:summary")

    # Notify subscribers
    await mcp.notify_resource_updated(f"device://{device_id}/health")
    await mcp.notify_resource_updated("fleet://health-summary")
```

---

## Testing Patterns for Resources and Prompts

### Resource Testing

```python
import pytest
from fastmcp.testing import MCPTestClient

@pytest.mark.asyncio
async def test_device_overview_resource(mcp_client, mock_device_service):
    """Test device overview resource."""
    await mcp_client.initialize()

    # Mock device data
    mock_device_service.get_overview.return_value = {
        "routeros_version": "7.16",
        "uptime_seconds": 86400,
        "cpu_usage": 15.5
    }

    # Fetch resource
    content = await mcp_client.read_resource("device://test-device-123/overview")

    # Verify content
    assert "routeros_version" in content
    assert "7.16" in content
    assert "uptime_seconds" in content

@pytest.mark.asyncio
async def test_resource_authorization(mcp_client, unauthorized_user):
    """Test resource access control."""
    await mcp_client.initialize(user=unauthorized_user)

    # Attempt to access restricted resource
    with pytest.raises(Exception) as exc_info:
        await mcp_client.read_resource("device://test-device/config")

    error = exc_info.value
    assert error.code == -32002  # Access denied
    assert "access denied" in error.message.lower()

@pytest.mark.asyncio
async def test_resource_subscription(mcp_client, mock_health_service):
    """Test resource subscription and notifications."""
    await mcp_client.initialize()

    # Subscribe to resource
    await mcp_client.subscribe_resource("device://test-device/health")

    # Trigger health update
    await mock_health_service.update_health("test-device", {"status": "warning"})

    # Wait for notification
    notification = await mcp_client.wait_for_notification(timeout=5.0)

    assert notification["method"] == "notifications/resources/updated"
    assert notification["params"]["uri"] == "device://test-device/health"

@pytest.mark.asyncio
async def test_resource_pagination(mcp_client):
    """Test resource pagination."""
    await mcp_client.initialize()

    # Fetch first page
    page1 = await mcp_client.read_resource("audit://events/recent?limit=10")
    page1_data = json.loads(page1)

    assert len(page1_data["events"]) <= 10
    assert "pagination" in page1_data
    cursor = page1_data["pagination"]["cursor"]

    # Fetch next page
    page2 = await mcp_client.read_resource(f"audit://events/recent?limit=10&cursor={cursor}")
    page2_data = json.loads(page2)

    # Verify different results
    assert page1_data["events"] != page2_data["events"]
```

### Prompt Testing

```python
@pytest.mark.asyncio
async def test_workflow_prompt(mcp_client):
    """Test workflow prompt generation."""
    await mcp_client.initialize()

    # Get prompt
    prompt_result = await mcp_client.get_prompt(
        "dns-ntp-rollout",
        arguments={"environment": "lab", "dry_run": True}
    )

    # Verify structure
    assert "DNS/NTP Rollout Workflow" in prompt_result
    assert "Prerequisites" in prompt_result
    assert "Workflow Steps" in prompt_result
    assert "tool:" in prompt_result.lower()  # References tools

@pytest.mark.asyncio
async def test_troubleshooting_prompt_with_device(mcp_client, mock_device):
    """Test troubleshooting prompt with device context."""
    await mcp_client.initialize()

    prompt_result = await mcp_client.get_prompt(
        "troubleshoot-device",
        arguments={"device_id": "test-device-123"}
    )

    # Verify device-specific content
    assert "test-device-123" in prompt_result
    assert "Connectivity Check" in prompt_result
    assert "System Overview" in prompt_result

@pytest.mark.asyncio
async def test_parameter_completion_prompt(mcp_client):
    """Test prompt parameter completion flow."""
    await mcp_client.initialize()

    # Call without device_id
    step1 = await mcp_client.get_prompt("create-address-list-entry")

    # Should show device list
    assert "Select Device" in step1
    assert "Available devices" in step1

    # Call with device_id
    step2 = await mcp_client.get_prompt(
        "create-address-list-entry",
        arguments={"device_id": "dev-001"}
    )

    # Should show address list selection
    assert "Select Address List" in step2
    assert "MCP-managed address lists" in step2
```

---

## Resource and Prompt Metrics

### Observability for Resources

```python
from prometheus_client import Counter, Histogram

# Resource metrics
resource_access_total = Counter(
    "mcp_resource_access_total",
    "Total resource accesses",
    ["resource_uri", "status"]  # status: success, not_found, unauthorized, error
)

resource_access_duration_seconds = Histogram(
    "mcp_resource_access_duration_seconds",
    "Resource access duration",
    ["resource_uri"]
)

# Prompt metrics
prompt_invocation_total = Counter(
    "mcp_prompt_invocation_total",
    "Total prompt invocations",
    ["prompt_name"]
)

# Middleware for resource metrics
async def track_resource_access(resource_uri: str, handler: Callable):
    """Track resource access metrics."""
    start_time = time.time()
    status = "success"

    try:
        result = await handler()
        return result

    except ResourceNotFoundError:
        status = "not_found"
        raise

    except ResourceAuthorizationError:
        status = "unauthorized"
        raise

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.time() - start_time
        resource_access_total.labels(resource_uri=resource_uri, status=status).inc()
        resource_access_duration_seconds.labels(resource_uri=resource_uri).observe(duration)

@mcp.resource("device://{device_id}/overview")
async def device_overview(device_id: str) -> str:
    """Device overview with metrics tracking."""
    async def handler():
        overview = await system_service.get_overview(device_id)
        return json.dumps(overview, indent=2)

    return await track_resource_access(f"device://{device_id}/overview", handler)
```

---

## Summary and Best Practices

### Resource Design Principles

1. **Consistent URI Schemes** - Predictable patterns for discovery
2. **Read-Only by Design** - Resources never mutate state
3. **Authorization Enforced** - Check access on every resource retrieval
4. **Subscribable for Real-Time** - Use for frequently changing data
5. **Audit Sensitive Access** - Log access to config, logs, audit data

### Prompt Design Principles

1. **Clear Parameterization** - Help users discover valid values
2. **Step-by-Step Guidance** - Break down complex workflows
3. **Safety Emphasis** - Highlight risks and precautions
4. **Tool/Resource References** - Link to specific tools and resources
5. **Environment-Aware** - Tailor guidance to lab/staging/prod

### Integration Checklist

- [ ] All resources have clear URI schemes
- [ ] Resources return proper MIME types
- [ ] Authorization enforced on sensitive resources
- [ ] Subscriptions implemented for real-time data
- [ ] Prompts reference specific tools and resources
- [ ] Prompts provide parameter completion guidance
- [ ] Workflow prompts include safety notes
- [ ] Troubleshooting prompts cover common issues
- [ ] Onboarding prompts match actual implementation phase

---

This design ensures RouterOS MCP service provides rich contextual resources and helpful workflow guidance while maintaining security and operational rigor.
