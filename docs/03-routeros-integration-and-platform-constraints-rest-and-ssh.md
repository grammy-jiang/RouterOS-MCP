# RouterOS Integration & Platform Constraints (REST & SSH)

## Purpose

Specify how the service interacts with RouterOS v7 via REST API as the primary channel and SSH/CLI as tightly-scoped fallback, including error handling, idempotency, capability coverage, and RouterOS-specific constraints and quirks.

---

## RouterOS REST client design (HTTP library, retries, timeouts, auth)

- **HTTP client responsibilities**:
  - Handle HTTP(S) connections to RouterOS `/rest/...` endpoints.  
  - Enforce timeouts, retries, backoff, and per-device concurrency limits.  
  - Map low-level HTTP/network errors into domain-level error types for MCP tools.

- **Authentication**:
  - Use basic auth or RouterOS API tokens per device, based on configured credentials.  
  - Credentials are retrieved from the secrets store, decrypted in-memory, and never logged.

- **Timeouts & retries**:
  - Conservative timeouts for each REST call, configurable per deployment.  
  - Retries with exponential backoff for transient network or 5xx errors.  
  - No retries on clear 4xx errors (auth failure, forbidden, validation errors).

- **Per-device concurrency and rate limiting**:
  - Centralized per-device concurrency control: at most N in-flight REST calls per device (N default 2–3).  
  - Per-device rate limiting to avoid overwhelming small routers, especially for health checks and metrics.

---

## Endpoint Mapping for Core Topics

### System Topic

**Endpoints:**

| Operation | Method | Path | Purpose | MCP Tool Tier |
|-----------|--------|------|---------|---------------|
| Get system resources | GET | `/rest/system/resource` | CPU, memory, uptime, version | Fundamental |
| Get system identity | GET | `/rest/system/identity` | Device name/identity | Fundamental |
| Set system identity | PUT/PATCH | `/rest/system/identity` | Change device name | Advanced |
| Get routerboard info | GET | `/rest/system/routerboard` | Hardware model, serial number | Fundamental |
| Get system package | GET | `/rest/system/package` | Installed packages and versions | Fundamental |
| Get system clock | GET | `/rest/system/clock` | Current time and timezone | Fundamental |

**Field Mappings:**

```python
# /rest/system/resource response
{
    "uptime": "1w2d3h4m5s",          # → uptime_seconds: int
    "version": "7.10.1 (stable)",     # → routeros_version: str
    "cpu-load": 5,                    # → cpu_usage_percent: float
    "free-memory": 123456789,         # → memory_free_bytes: int
    "total-memory": 536870912,        # → memory_total_bytes: int
    "board-name": "RB5009UG+S+",      # → hardware_model: str
}

# /rest/system/identity response
{
    "name": "router-lab-01"           # → system_identity: str
}

# /rest/system/routerboard response
{
    "model": "RB5009UG+S+",           # → hardware_model: str
    "serial-number": "ABC12345678",   # → serial_number: str
    "firmware": "7.10"                # → firmware_version: str
}
```

---

### Interface Topic

**Endpoints:**

| Operation | Method | Path | Purpose | MCP Tool Tier |
|-----------|--------|------|---------|---------------|
| List all interfaces | GET | `/rest/interface` | Get all interfaces | Fundamental |
| Get interface by ID | GET | `/rest/interface/{id}` | Get specific interface | Fundamental |
| Update interface | PATCH | `/rest/interface/{id}` | Modify interface (comment, disable) | Advanced |
| Get interface stats | GET | `/rest/interface/monitor-traffic` | Real-time traffic stats | Fundamental |

**Field Mappings:**

```python
# /rest/interface response
{
    ".id": "*1",                      # → interface_id: str
    "name": "ether1",                 # → name: str
    "type": "ether",                  # → type: str (ether, bridge, vlan, etc.)
    "running": true,                  # → running: bool
    "disabled": false,                # → disabled: bool
    "comment": "WAN uplink",          # → comment: str
    "mtu": 1500,                      # → mtu: int
    "mac-address": "AA:BB:CC:DD:EE:FF" # → mac_address: str
}

# Allowed operations (Advanced tier - Phase 2):
# - Set comment: PATCH /rest/interface/{id} {"comment": "..."}
# - Enable/disable: PATCH /rest/interface/{id} {"disabled": true/false}
#
# Higher-risk operations (Phase 3):
# - Delete interfaces
# - MTU changes
# - Admin down (use disable instead)
```

---

### IP Address Topic

**Endpoints:**

| Operation | Method | Path | Purpose | MCP Tool Tier |
|-----------|--------|------|---------|---------------|
| List IP addresses | GET | `/rest/ip/address` | Get all IP addresses | Fundamental |
| Get address by ID | GET | `/rest/ip/address/{id}` | Get specific address | Fundamental |
| Add IP address | PUT | `/rest/ip/address` | Add new IP address | Advanced |
| Remove IP address | DELETE | `/rest/ip/address/{id}` | Remove IP address | Professional |
| Get ARP entries | GET | `/rest/ip/arp` | ARP table | Fundamental |

**Field Mappings:**

```python
# /rest/ip/address response
{
    ".id": "*2",                      # → address_id: str
    "address": "192.168.1.1/24",      # → address: str (CIDR notation)
    "network": "192.168.1.0",         # → network: str
    "interface": "ether1",            # → interface: str
    "disabled": false,                # → disabled: bool
    "comment": "LAN gateway"          # → comment: str
}

# Add secondary IP (Advanced tier):
# PUT /rest/ip/address
# {
#     "address": "192.168.1.2/24",
#     "interface": "ether1",
#     "comment": "Secondary IP"
# }
```

---

### IP DNS Topic

**Endpoints:**

| Operation | Method | Path | Purpose | MCP Tool Tier |
|-----------|--------|------|---------|---------------|
| Get DNS settings | GET | `/rest/ip/dns` | DNS server configuration | Fundamental |
| Set DNS servers | PUT/PATCH | `/rest/ip/dns` | Update DNS servers | Advanced |
| Get DNS cache | GET | `/rest/ip/dns/cache` | View DNS cache | Fundamental |
| Flush DNS cache | POST | `/rest/ip/dns/cache/flush` | Clear DNS cache | Advanced |

**Field Mappings:**

```python
# /rest/ip/dns response
{
    "servers": "8.8.8.8,8.8.4.4",     # → dns_servers: list[str]
    "allow-remote-requests": true,     # → allow_remote_requests: bool
    "cache-size": 2048,                # → cache_size_kb: int
    "cache-used": 156                  # → cache_used_kb: int
}

# Set DNS servers (Advanced tier, lab/staging only by default):
# PATCH /rest/ip/dns
# {
#     "servers": "1.1.1.1,1.0.0.1"
# }
```

---

### System NTP Client Topic

**Endpoints:**

| Operation | Method | Path | Purpose | MCP Tool Tier |
|-----------|--------|------|---------|---------------|
| Get NTP client config | GET | `/rest/system/ntp/client` | NTP configuration | Fundamental |
| Set NTP servers | PUT/PATCH | `/rest/system/ntp/client` | Update NTP servers | Advanced |
| Get NTP client status | GET | `/rest/system/ntp/client/monitor` | NTP sync status | Fundamental |

**Field Mappings:**

```python
# /rest/system/ntp/client response
{
    "enabled": true,                   # → enabled: bool
    "servers": "time.cloudflare.com,pool.ntp.org", # → ntp_servers: list[str]
    "mode": "unicast"                  # → mode: str
}

# /rest/system/ntp/client/monitor response
{
    "status": "synchronized",          # → status: str
    "stratum": 2,                      # → stratum: int
    "offset": "-0.002s"                # → offset_ms: float
}

# Set NTP servers (Advanced tier, lab/staging only by default):
# PATCH /rest/system/ntp/client
# {
#     "enabled": true,
#     "servers": "time.cloudflare.com"
# }
```

---

### IP Route Topic

**Endpoints:**

| Operation | Method | Path | Purpose | MCP Tool Tier |
|-----------|--------|------|---------|---------------|
| List routes | GET | `/rest/ip/route` | Routing table | Fundamental |
| Get route by ID | GET | `/rest/ip/route/{id}` | Specific route | Fundamental |
| Add static route | PUT | `/rest/ip/route` | Add route | Professional |
| Remove route | DELETE | `/rest/ip/route/{id}` | Delete route | Professional |

**Field Mappings:**

```python
# /rest/ip/route response
{
    ".id": "*3",                       # → route_id: str
    "dst-address": "0.0.0.0/0",        # → dst_address: str
    "gateway": "192.168.1.254",        # → gateway: str
    "distance": 1,                     # → distance: int (admin distance)
    "scope": 30,                       # → scope: int
    "target-scope": 10,                # → target_scope: int
    "comment": "Default route"         # → comment: str
}

# Note: Route manipulation is Professional tier (high risk)
```

---

### IP Firewall Topic

**Endpoints:**

| Operation | Method | Path | Purpose | MCP Tool Tier |
|-----------|--------|------|---------|---------------|
| List filter rules | GET | `/rest/ip/firewall/filter` | Firewall filter rules | Fundamental |
| List NAT rules | GET | `/rest/ip/firewall/nat` | NAT rules | Fundamental |
| List address lists | GET | `/rest/ip/firewall/address-list` | Address lists | Fundamental |
| Add address-list entry | PUT | `/rest/ip/firewall/address-list` | Add to address list | Advanced |
| Remove address-list entry | DELETE | `/rest/ip/firewall/address-list/{id}` | Remove from list | Advanced |

**Field Mappings:**

```python
# /rest/ip/firewall/filter response
{
    ".id": "*4",                       # → rule_id: str
    "chain": "input",                  # → chain: str
    "action": "accept",                # → action: str
    "protocol": "tcp",                 # → protocol: str
    "dst-port": "22,8080",             # → dst_port: str
    "comment": "Allow SSH and HTTP",   # → comment: str
    "disabled": false                  # → disabled: bool
}

# /rest/ip/firewall/address-list response
{
    ".id": "*5",                       # → entry_id: str
    "list": "mcp-managed-hosts",       # → list_name: str
    "address": "10.0.1.100",           # → address: str
    "comment": "MCP server",           # → comment: str
    "timeout": "1d"                    # → timeout: str (optional)
}

# Note: Only MCP-owned address lists (prefix: "mcp-") can be modified
# Filter/NAT rule changes are Professional tier or disabled
```

---

### System Logging Topic

**Endpoints:**

| Operation | Method | Path | Purpose | MCP Tool Tier |
|-----------|--------|------|---------|---------------|
| Get log entries | GET | `/rest/log` | System logs | Fundamental (bounded) |
| Get log topics | GET | `/rest/system/logging` | Logging configuration | Fundamental |

**Field Mappings:**

```python
# /rest/log response (with query params for filtering)
{
    ".id": "*6",                       # → log_id: str
    "time": "jan/15/2024 10:30:45",    # → timestamp: datetime
    "topics": "system,info",           # → topics: list[str]
    "message": "System started"        # → message: str
}

# Query parameters for bounded reads:
# GET /rest/log?limit=100&topics=system,error
# - limit: Max 1000 entries (MCP enforced)
# - topics: Filter by topics
# - No free-form log streaming (use bounded tail)
```

---

### Tool (Diagnostics) Topic

**Endpoints:**

| Operation | Method | Path | Purpose | MCP Tool Tier |
|-----------|--------|------|---------|---------------|
| Ping | POST | `/rest/tool/ping` | ICMP ping | Fundamental |
| Traceroute | POST | `/rest/tool/traceroute` | Network traceroute | Fundamental |
| Bandwidth test | POST | `/rest/tool/bandwidth-test` | Speed test | Fundamental |

**Field Mappings:**

```python
# POST /rest/tool/ping request
{
    "address": "8.8.8.8",              # Target IP/hostname
    "count": 4,                        # Number of pings (max 10)
    "interval": "1s"                   # Interval between pings
}

# Response (streaming or final summary)
{
    "host": "8.8.8.8",                 # → host: str
    "sent": 4,                         # → packets_sent: int
    "received": 4,                     # → packets_received: int
    "packet-loss": 0,                  # → packet_loss_percent: int
    "min-rtt": "10ms",                 # → min_rtt_ms: float
    "avg-rtt": "12ms",                 # → avg_rtt_ms: float
    "max-rtt": "15ms"                  # → max_rtt_ms: float
}

# POST /rest/tool/traceroute request
{
    "address": "8.8.8.8",              # Target IP/hostname
    "count": 1                         # Probes per hop (max 3)
}

# Note: Diagnostics are bounded (max 10 pings, max 30 hops for traceroute)
```

---

### Field Mapping Strategy

**General Principles:**

1. **Normalize field names**: RouterOS uses kebab-case (`cpu-load`), Python uses snake_case (`cpu_load`)
2. **Type conversion**: RouterOS strings → Python types (durations to seconds, percentages to floats)
3. **Hide internal fields**: Fields starting with `.` (except `.id`) are internal and not exposed
4. **Enrich with metadata**: Add device context, timestamps, environment tags
5. **Validate ranges**: Enforce MCP-specific bounds (max log entries, max ping count)

**Implementation Pattern:**

```python
class SystemMapper:
    """Map RouterOS system responses to domain models."""

    @staticmethod
    def map_resource(ros_data: dict) -> SystemResource:
        """Map /rest/system/resource response."""
        return SystemResource(
            uptime_seconds=parse_duration(ros_data["uptime"]),
            routeros_version=ros_data["version"],
            cpu_usage_percent=float(ros_data["cpu-load"]),
            memory_free_bytes=int(ros_data["free-memory"]),
            memory_total_bytes=int(ros_data["total-memory"]),
            hardware_model=ros_data.get("board-name"),
        )

    @staticmethod
    def map_identity(ros_data: dict) -> str:
        """Map /rest/system/identity response."""
        return ros_data["name"]
```

Each domain service (system, interface, ip, dns, etc.) uses these mappers so that MCP tools work with clean, typed domain models instead of raw RouterOS dictionaries.

---

## RouterOS platform constraints (resource usage, API rate limits, connection limits, timeouts)

The integration must respect RouterOS device constraints:

- **CPU & memory limits**:
  - Avoid heavy polling; prefer **metrics collection jobs** with reasonable intervals and jitter.  
  - Diagnostics (ping/traceroute) and logs retrieval must be bounded in time and volume.

- **API and connection limits**:
  - Some devices may have lower capabilities; per-device concurrency limits ensure we do not saturate API handlers.  
  - The integration should be prepared for RouterOS to close idle or long-running connections; keep connections short-lived or properly pooled.

- **Timeout behavior**:
  - RouterOS may time out long-running commands; REST client should treat timeouts as first-class errors and not spin.

These constraints influence:

- The maximum frequency and volume of health checks and metrics pulls.  
- The design of multi-device workflows (e.g., staggering changes across devices).

---

## Known /rest quirks (pagination behavior, common error patterns, status codes)

While exact details depend on RouterOS version, the integration should anticipate:

- **Pagination**:
  - Some endpoints may paginate results or limit the number of returned items.  
  - The client must handle pagination or query parameters if applicable (e.g., offsets, `?numbers=` filters).

- **Error responses**:
  - RouterOS may return error details in response bodies; client should parse and surface them as structured error objects.  
  - Distinguish between:
    - Authentication/authorization issues.  
    - Validation errors (bad parameters).  
    - Operational errors (e.g., resource busy, unknown item).

- **Status codes**:
  - Validate that 2xx / 4xx / 5xx codes are handled consistently; do not rely solely on code—also parse body.  
  - Certain API inconsistencies (e.g., non-2xx with useful body) should be normalized internally.

The design should explicitly record any RouterOS `/rest` quirks discovered during testing and encode them in the client layer, not in higher-level services.

---

## SSH/CLI Integration Strategy

### When SSH is Used

**SSH as last resort** for operations not available via REST API:

- **Export operations**: `/export` command for full config backups
- **Specific diagnostics**: Commands not exposed via `/rest/tool`
- **Feature gaps**: RouterOS features without REST API parity (rare in v7.10+)

**SSH should never be used as a general "escape hatch" for arbitrary commands.**

### Phase 1: Code-Based Command Templates

**For Phase 1, SSH command templates are defined in code, not via web GUI:**

```python
# routeros_mcp/infra/routeros/ssh_templates.py

from typing import Dict, Any
from pydantic import BaseModel, Field

class SSHCommandTemplate(BaseModel):
    """SSH command template definition."""

    id: str = Field(..., description="Unique command identifier")
    name: str = Field(..., description="Human-readable command name")
    description: str = Field(..., description="What this command does")
    template: str = Field(..., description="Command template with {placeholders}")
    tier: str = Field(..., description="fundamental/advanced/professional")
    allowed_environments: list[str] = Field(..., description="lab/staging/prod")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameter definitions")
    timeout_seconds: int = Field(default=30, description="Command timeout")


# Pre-defined templates (Phase 1)
SSH_COMMAND_TEMPLATES = {
    "export_full_config": SSHCommandTemplate(
        id="export_full_config",
        name="Export Full Configuration",
        description="Export complete RouterOS configuration to .rsc format",
        template="/export file={filename}",
        tier="fundamental",
        allowed_environments=["lab", "staging", "prod"],
        parameters={
            "filename": {
                "type": "str",
                "pattern": r"^[a-zA-Z0-9_-]+$",  # Alphanumeric, underscore, hyphen only
                "max_length": 64,
                "description": "Output filename (without .rsc extension)"
            }
        },
        timeout_seconds=60
    ),

    "export_compact_config": SSHCommandTemplate(
        id="export_compact_config",
        name="Export Compact Configuration",
        description="Export configuration in compact format (minimal output)",
        template="/export compact file={filename}",
        tier="fundamental",
        allowed_environments=["lab", "staging", "prod"],
        parameters={
            "filename": {
                "type": "str",
                "pattern": r"^[a-zA-Z0-9_-]+$",
                "max_length": 64
            }
        },
        timeout_seconds=60
    ),

    "system_backup": SSHCommandTemplate(
        id="system_backup",
        name="Create System Backup",
        description="Create binary system backup file",
        template="/system backup save name={filename}",
        tier="advanced",
        allowed_environments=["lab", "staging", "prod"],
        parameters={
            "filename": {
                "type": "str",
                "pattern": r"^[a-zA-Z0-9_-]+$",
                "max_length": 64,
                "description": "Backup filename (without .backup extension)"
            }
        },
        timeout_seconds=120
    ),

    "fetch_url": SSHCommandTemplate(
        id="fetch_url",
        name="Fetch File from URL",
        description="Download file from HTTP/HTTPS URL (lab/staging only)",
        template="/tool fetch url={url} dst-path={dst_path}",
        tier="advanced",
        allowed_environments=["lab", "staging"],  # NOT allowed in prod
        parameters={
            "url": {
                "type": "str",
                "pattern": r"^https?://[a-zA-Z0-9.-]+(/.*)?$",  # HTTP/HTTPS only
                "max_length": 256,
                "description": "Source URL (http:// or https://)"
            },
            "dst_path": {
                "type": "str",
                "pattern": r"^[a-zA-Z0-9_/-]+\.[a-z]+$",
                "max_length": 128,
                "description": "Destination path on router"
            }
        },
        timeout_seconds=300
    )
}
```

### Command Template Validation

**Before executing any SSH command, validate parameters:**

```python
import re
from typing import Any

def validate_ssh_parameters(
    template: SSHCommandTemplate,
    params: dict[str, Any]
) -> dict[str, Any]:
    """Validate and sanitize SSH command parameters.

    Args:
        template: Command template definition
        params: User-provided parameters

    Returns:
        Validated and sanitized parameters

    Raises:
        ValueError: If validation fails
    """
    validated = {}

    for param_name, param_def in template.parameters.items():
        # Check required parameters
        if param_name not in params:
            raise ValueError(f"Missing required parameter: {param_name}")

        value = params[param_name]

        # Type check
        if param_def["type"] == "str" and not isinstance(value, str):
            raise ValueError(f"Parameter {param_name} must be string")

        # Pattern validation (prevent injection)
        if "pattern" in param_def:
            if not re.match(param_def["pattern"], value):
                raise ValueError(
                    f"Parameter {param_name} does not match required pattern"
                )

        # Length validation
        if "max_length" in param_def:
            if len(value) > param_def["max_length"]:
                raise ValueError(
                    f"Parameter {param_name} exceeds max length "
                    f"{param_def['max_length']}"
                )

        validated[param_name] = value

    return validated


def render_ssh_command(
    template: SSHCommandTemplate,
    params: dict[str, Any]
) -> str:
    """Render SSH command from template with validated parameters.

    Args:
        template: Command template
        params: Validated parameters

    Returns:
        Rendered command string
    """
    # Validate parameters first
    validated_params = validate_ssh_parameters(template, params)

    # Render template (safe - params are validated)
    return template.template.format(**validated_params)
```

### Command Execution Flow

```python
async def execute_ssh_command(
    device: Device,
    command_id: str,
    params: dict[str, Any]
) -> str:
    """Execute whitelisted SSH command on device.

    Args:
        device: Target RouterOS device
        command_id: SSH command template ID
        params: Command parameters

    Returns:
        Command output

    Raises:
        ValueError: If command not found or parameters invalid
        AuthorizationError: If command not allowed for device
        SSHError: If command execution fails
    """
    # 1. Get template
    template = SSH_COMMAND_TEMPLATES.get(command_id)
    if not template:
        raise ValueError(f"Unknown SSH command: {command_id}")

    # 2. Check authorization
    check_ssh_command_access(device, template)

    # 3. Validate and render command
    command = render_ssh_command(template, params)

    # 4. Execute via SSH client
    ssh_client = get_ssh_client(device)
    result = await ssh_client.execute(command, timeout=template.timeout_seconds)

    # 5. Audit log
    audit_ssh_command(device, template, command, result)

    return result
```

---

## Phase 1: Code-Based Template Management

**For Phase 1 (single-user), SSH command templates are code-based:**

✅ **Advantages:**
- **Security**: Templates reviewed in code review process
- **Version control**: All changes tracked in git
- **No runtime modification**: Prevents accidental template corruption
- **Type safety**: Pydantic validation at load time

**Implemented in Later Phases:**
- Web GUI for adding/modifying templates (Phase 4)
- Runtime template modification (Phase 2-3)
- User-defined custom commands (Phase 3)

### Future: Phase 2-3 Template Management

**Phase 2-3 may add configuration-file-based templates:**

```yaml
# config/ssh_templates.yaml (Phase 2+)
ssh_templates:
  - id: export_dns_config
    name: Export DNS Configuration
    template: "/ip dns export file={filename}"
    tier: fundamental
    allowed_environments: [lab, staging, prod]
    parameters:
      filename:
        type: str
        pattern: "^[a-zA-Z0-9_-]+$"
        max_length: 64
```

**Phase 4 may add web GUI for admin users:**
- CRUD operations on SSH templates
- Template testing in lab environment
- Approval workflow for new templates
- Template usage audit trail

**But for Phase 1**: Templates are hardcoded in `ssh_templates.py` and require code changes to add/modify.

---

## SSH Command Audit Strategy

### Audit Logging (Phase 1)

**Every SSH operation is logged:**

```python
def audit_ssh_command(
    device: Device,
    template: SSHCommandTemplate,
    rendered_command: str,
    result: str
) -> None:
    """Log SSH command execution for audit trail.

    Args:
        device: Target device
        template: Command template used
        rendered_command: Actual command executed
        result: Command output (may be truncated)
    """
    audit_event = AuditEvent(
        id=generate_id(),
        timestamp=datetime.utcnow(),
        device_id=device.id,
        environment=device.environment,
        action="SSH_COMMAND",
        tool_name=f"ssh/{template.id}",
        tool_tier=template.tier,
        result="SUCCESS" if result else "FAILURE",
        metadata={
            "command_id": template.id,
            "command_name": template.name,
            "rendered_command": rendered_command,  # May mask sensitive params
            "output_length": len(result),
            "timeout_seconds": template.timeout_seconds
        }
    )

    # Save to audit_events table
    save_audit_event(audit_event)
```

### SSH Command Restrictions

**Additional safety measures:**

1. **Environment restrictions**: Some commands only allowed in lab/staging
2. **Device capability flags**: SSH commands require `allow_ssh_commands` flag (default: false)
3. **Tier-based access**: Advanced/Professional SSH commands follow same tier rules
4. **No shell access**: Commands are executed via `/system script run`, not interactive shell
5. **Output limits**: Command output truncated to 10MB to prevent resource exhaustion

---

## Summary: SSH Integration (Phase 1)

✅ **What Phase 1 Has:**
- Pre-defined SSH command templates in code
- Parameter validation and injection prevention
- Environment and tier-based restrictions
- Comprehensive audit logging
- Support for config export and backups

**Deferred to Later Phases:**
- Web GUI for template management (Phase 4)
- Runtime template modification (Phase 2-3)
- User-defined custom commands (Phase 3)
- Interactive SSH shell access (never - security risk)

**Rationale**: Code-based templates provide maximum security and auditability for single-user deployments. Template management features are implemented in Phase 4 when multi-user access control is in place.

---

## Idempotency, change detection, and read-modify-write patterns

- **Idempotent tools**:
  - Tools must be designed so that repeatedly applying the same desired state yields the same result (no unintended side effects).  
  - For example, setting a system identity to the same value should return `changed=false`.

- **Read-modify-write**:
  - Before changing configuration, the integration:
    - Reads the current state from RouterOS.  
    - Computes the desired changes relative to the current state.  
    - Applies the minimal set of changes required.

- **Change detection**:
  - Tools must explicitly report whether a change was applied (`changed=true/false`).  
  - Out-of-band changes on RouterOS are handled by always re-reading and not assuming previous writes succeeded.

This pattern is critical for safe multi-device orchestration and drift handling.

---

## Handling version differences and feature detection per device

- **Minimum supported version**:
  - The MCP service assumes RouterOS v7 with a configured minimum minor version (e.g. ≥ 7.xx LTS).

- **Feature detection**:
  - At registration or on-demand, the service queries device capabilities (version, installed packages, available endpoints).  
  - Certain tools or features may be disabled for devices that do not meet requirements.

- **Degraded behavior**:
  - If a feature is missing:
    - Tools may degrade to read-only mode (e.g., read DNS config but not modify).  
    - Or return a clear “unsupported” error.

---

## Performance considerations (batching, pagination, rate limiting per device)

- **Batching**:
  - Where possible, combine related reads into fewer REST calls (e.g., fetch multiple interfaces in one request).  
  - Avoid over-batching for large fleets; per-device and global limits still apply.

- **Pagination**:
  - Large result sets (e.g., logs, large routing tables) should be paginated by the MCP tools and integration layer, not dumped wholesale.

- **Rate limiting**:
  - Per-device:
    - Capped QPS and concurrency, with backoff on repeated failures.  
  - Global:
    - Limits to protect the MCP service and upstream dependencies from overload.

These considerations are especially important for metrics collection and multi-device plan/apply workflows.

---

## Testing against lab devices and simulation / “dry-run” patterns

- **Lab devices**:
  - A small, representative set of RouterOS devices in `lab` environment must be available for:  
    - Integration testing.  
    - Validating new tools and features.  
    - Exercising high-risk operations under controlled conditions.

- **Simulation / mocks**:
  - For CI and unit tests, use simulated RouterOS responses or mocks that mirror REST/SSH behavior.  
  - Simulated scenarios should include:
    - Success paths.  
    - Common error cases.  
    - Timeouts and rate-limiting behaviors.

- **Dry-run mode**:
  - Where feasible, tools should support “dry-run” or “plan” operations:
    - Compute and report intended RouterOS changes without applying them.  
    - This dovetails with the plan/apply pattern in MCP tools.
