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
