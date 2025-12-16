# Security & Access Control

## Purpose

Define the security posture, trust boundaries, authentication and authorization model, secrets handling, and least-privilege design for RouterOS operations and MCP exposure. This document encodes the guiding principle that all clients, including AI, are untrusted and all safety is enforced server-side.

**Phase 1 Scope**: Single-user, stdio-only MCP server with OS-level access control. Multi-user OAuth/OIDC authentication is implemented in Phase 5.

---

## Threat Model and Trust Boundaries

### Trust Boundaries

- **MCP Host (Claude Desktop)**
  - Runs on the user's workstation with OS-level access control
  - Single user with filesystem permissions controls access
  - MCP server process inherits user's permissions

- **MCP Service (This Application)**
  - Core of device authentication, authorization, policy enforcement, and audit
  - Implements per-device, per-tool, and per-environment capability checks
  - **Phase 1**: Single implicit admin user (OS-level access control only)
  - **Phase 5**: OAuth/OIDC for multi-user access

- **RouterOS Devices**
  - Treated as semi-trusted network devices; may be misconfigured, overloaded, or manually changed out-of-band
  - RouterOS is the ultimate source of truth for its own configuration and state
  - Each device requires valid credentials (encrypted at rest)

- **Operator/Admin**
  - Single human operator with OS-level access to MCP server
  - Trusted to have good intent, but workflows defend against accidents (plan/apply, approvals)
  - **Phase 1**: Implicit admin role (full access to all tools)

### Threats

- **Unauthorized device access**: Invalid or stolen RouterOS credentials
- **Accidental misconfiguration**: Human error when modifying devices
- **Misuse of high-risk tools**: Firewall, routing, DHCP, bridge, interface admin, wireless RF
- **Data exfiltration**: Logs or mis-scoped reads exposing sensitive information
- **Out-of-band changes**: Manual RouterOS changes leading to unexpected behavior and drift
- **Credential theft**: Exposure of encrypted device credentials from SQLite database

**Design Assumption**: MCP must treat all clients, including AI/LLM callers, as untrusted. No MCP tool may rely on client-side guardrails or prompt engineering for safety; all enforcement happens server-side.

---

## Phase 1: Single-User Authentication Model

### OS-Level Access Control

**Phase 1 uses operating system-level access control instead of application-level authentication:**

1. **Filesystem Permissions**
   - MCP server runs as the user's process
   - Database file (`routeros_mcp.db`) is protected by OS permissions (0600)
   - Configuration file access controlled by filesystem ACLs
   - Each OS user gets isolated data directory (e.g., `~/.local/share/routeros-mcp/`)

2. **Process Isolation**
   - MCP server process inherits user's security context
   - No network exposure (stdio transport only)
   - No HTTP API or remote access in Phase 1
   - **STDIO Transport Security:**
     - Claude Desktop spawns MCP server as child process
     - Process runs with same permissions as Claude Desktop (user's OS permissions)
     - STDIN/STDOUT provides process-level isolation (no network sockets)
     - Multiple OS users on same machine get separate MCP instances (no cross-user access)
     - Operating system enforces process boundaries (kernel-level security)

3. **Implicit Admin User**
   - Single user who can run the MCP server has full admin privileges
   - No role-based access control (RBAC) in Phase 1 (added in Phase 5)
   - All tools available to the operator

**Why STDIO is Secure for Phase 1:**

- **No network exposure**: MCP server cannot be reached remotely (no listening sockets)
- **OS-enforced isolation**: Only the user who started Claude Desktop can access their MCP instance
- **No authentication needed**: OS user authentication is sufficient (already logged into workstation)
- **Process sandboxing**: Claude Desktop can apply additional sandboxing (AppArmor, SELinux) if needed
- **Database isolation**: Each user's database is protected by filesystem permissions (chmod 600)

**Multi-User Scenarios on Same Machine:**

- **User A** runs Claude Desktop → MCP server as User A → Database at `/home/userA/.local/share/routeros-mcp/`
- **User B** runs Claude Desktop → MCP server as User B → Database at `/home/userB/.local/share/routeros-mcp/`
- Users cannot access each other's databases (OS enforces file permissions)
- Each MCP instance is completely isolated (separate processes, separate data)

### Authentication Flow (Phase 1)

```
┌─────────────────────────┐
│  User logs into OS      │
│  (workstation/laptop)   │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  User starts Claude     │
│  Desktop (as their OS   │
│  user account)          │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  Claude Desktop spawns  │
│  MCP server as child    │
│  process (stdio)        │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  MCP server inherits    │
│  user's OS permissions  │
│  → Implicit admin role  │
└─────────────────────────┘
```

### No User Model in Phase 1

Phase 1 **does not** have:
- User accounts or user database table
- OAuth/OIDC integration
- Role-based access control (RBAC)
- Multi-user support
- HTTP transport with bearer tokens

These features are planned for **Phase 5: Enterprise Multi-User**.

---

## Authorization Model

### Device-Level Authorization (Phase 1)

**Phase 1 authorization focuses on device capabilities, not user roles:**

1. **Environment Separation**
   - Devices tagged as `lab`, `staging`, or `prod`
   - Service configured with matching environment
   - Prevents accidental cross-environment operations

2. **Device Capability Flags**
   - `allow_advanced_writes` (bool): Enable advanced-tier tools (default: false)
   - `allow_professional_workflows` (bool): Enable professional-tier tools (default: false)
   - Configured per-device in device registry

3. **Tool Tier Restrictions**
   - **Fundamental tier**: Always allowed (read-only operations)
   - **Advanced tier**: Requires `allow_advanced_writes = true` on device
   - **Professional tier**: Requires `allow_professional_workflows = true` on device

### Authorization Decision Logic (Phase 1)

```python
def check_tool_access(device: Device, tool_name: str, tool_tier: str) -> None:
    """Check if tool can be invoked on device (Phase 1: device-level only).

    Args:
        device: Target RouterOS device
        tool_name: Tool being invoked
        tool_tier: fundamental/advanced/professional

    Raises:
        AuthorizationError: If access denied
    """
    # Check 1: Environment match
    if device.environment != settings.environment:
        raise AuthorizationError(
            f"Device environment {device.environment} does not match "
            f"service environment {settings.environment}"
        )

    # Check 2: Tool tier vs device capabilities
    if tool_tier == "fundamental":
        # Always allowed
        pass
    elif tool_tier == "advanced":
        if not device.allow_advanced_writes:
            raise AuthorizationError(
                f"Device {device.id} does not allow advanced writes"
            )
    elif tool_tier == "professional":
        if not device.allow_professional_workflows:
            raise AuthorizationError(
                f"Device {device.id} does not allow professional workflows"
            )
```

### Tool Taxonomy and Tiers

**For complete tool specifications, authorization rules, and tier assignments for all 40 tools, see [docs/04-mcp-tools-interface-and-json-schema-specification.md](04-mcp-tools-interface-and-json-schema-specification.md).**

**Fundamental Tier** (read-only, always allowed):
- `system/get-overview`
- `interface/list-interfaces`
- `ip/address-list`
- `dns/get-status`
- `ntp/get-status`
- `tool/ping`
- `tool/traceroute`
- `logs/get-recent` (bounded)
- `device/get-health-data` (Phase-1 fallback for resource)
- `fleet/get-summary` (Phase-1 fallback for resource)
- `audit/get-events` (Phase-1 fallback for resource)

**Advanced Tier** (low-risk writes, requires device flag):
- `system/set-identity`
- `interface/update-comment`
- `dns/update-servers` (lab/staging only by default)
- `ntp/update-servers` (lab/staging only by default)
- `dns/flush-cache`
- `device/get-config-snapshot` (Phase-1 fallback for resource)

**Professional Tier** (high-risk, multi-device, requires device flag):
- `config/plan-dns-ntp-rollout` (plan/apply workflow)
- `config/apply-dns-ntp-rollout` (requires approval token)
- `config/rollback-plan`
- `plan/get-details` (Phase-1 fallback for resource)
- `addresslist/plan-sync`
- `addresslist/apply-sync`

---

## MCP Protocol Security

### Protocol-Level Security Controls

The MCP JSON-RPC protocol provides additional security layers beyond OS-level access control:

#### 1. Request Validation

**Every MCP tool invocation is validated before execution:**

```python
async def validate_mcp_request(request: dict) -> None:
    """Validate MCP JSON-RPC request structure and parameters.

    Raises:
        ValidationError: If request is malformed or invalid
    """
    # JSON-RPC 2.0 structure validation
    if request.get("jsonrpc") != "2.0":
        raise ValidationError("Invalid JSON-RPC version")

    if "method" not in request:
        raise ValidationError("Missing method field")

    # Tool name validation
    tool_name = request["method"]
    if tool_name not in REGISTERED_TOOLS:
        raise ValidationError(f"Unknown tool: {tool_name}")

    # Parameter schema validation
    params = request.get("params", {})
    tool_schema = TOOL_SCHEMAS[tool_name]
    jsonschema.validate(params, tool_schema)

    # Device ID existence check
    if "device_id" in params:
        device = await device_service.get_device(params["device_id"])
        if not device:
            raise ValidationError(f"Device not found: {params['device_id']}")

    # Input sanitization (prevent injection)
    for key, value in params.items():
        if isinstance(value, str):
            params[key] = sanitize_input(value)
```

**Validation Steps:**
1. **JSON-RPC Schema**: Validate `jsonrpc`, `method`, `params`, `id` fields
2. **Tool Registration**: Verify tool exists in registered tool list
3. **Parameter Schema**: Validate parameters against JSON Schema for that tool
4. **Entity Existence**: Verify device_id, plan_id exist in database
5. **Input Sanitization**: Remove potentially dangerous characters before passing to RouterOS

#### 2. Approval Token Mechanism (Professional Tools)

**High-risk professional tools require approval tokens in addition to device capability flags:**

**Phase 1 Approach (Self-Approval):**
- Professional tools in Phase 1 do NOT require separate approval tokens
- Device `allow_professional_workflows=true` flag is sufficient
- Operator is implicitly trusted (OS-level authentication)
- All operations still logged in audit trail

**Phase 5 Approach (Multi-User with Approval UI):**

```python
class ApprovalToken:
    """Short-lived approval token for professional tool execution."""

    token_id: str  # UUID
    plan_id: str  # Bound to specific plan
    user_sub: str  # OIDC user identity
    expires_at: datetime  # 5-minute TTL
    used: bool  # Single-use only

@mcp.tool()
async def config_apply_dns_ntp_rollout(
    plan_id: str,
    approval_token: str | None = None  # Required in Phase 4
) -> dict:
    """Apply DNS/NTP rollout plan to devices.

    Phase 1: approval_token is optional (self-approval)
    Phase 4: approval_token is REQUIRED (human approval)
    """
    plan = await plan_service.get_plan(plan_id)

    # Phase 4: Validate approval token
    if settings.phase >= 4:
        if not approval_token:
            raise AuthorizationError("Approval token required for professional tools")

        token = await approval_service.validate_token(approval_token, plan_id)
        if token.used:
            raise AuthorizationError("Approval token already used")
        if token.expires_at < datetime.now():
            raise AuthorizationError("Approval token expired")
        if token.plan_id != plan_id:
            raise AuthorizationError("Approval token not valid for this plan")

        # Mark token as used (single-use)
        await approval_service.mark_token_used(token.token_id)

    # Execute plan
    result = await plan_service.execute_plan(plan_id)
    return result
```

**Approval Token Properties:**
- **Bound to plan_id**: Cannot be reused for different plan
- **5-minute TTL**: Short-lived to prevent token theft
- **Single-use**: Consumed on first apply attempt
- **User-bound**: Generated by specific OIDC user identity
- **Stored in-memory only**: Not persisted to database (ephemeral)

**Approval Workflow (Phase 5):**
1. Operator creates plan via `config/plan-dns-ntp-rollout` → returns `plan_id`
2. Operator reviews plan via `plan/get-details` with `plan_id`
3. Operator uses Admin UI to generate approval token for `plan_id`
4. Admin UI calls approval API: `POST /api/approvals/generate` with `plan_id` and OIDC token
5. Approval service generates short-lived token, returns to operator
6. Operator calls `config/apply-dns-ntp-rollout` with `plan_id` and `approval_token`
7. MCP validates token, executes plan, marks token as used

#### 3. Blast Radius Controls

**Professional tools enforce strict blast radius limits to prevent widespread failures:**

```python
@mcp.tool()
async def config_plan_dns_ntp_rollout(
    device_ids: list[str],
    dns_servers: list[str] | None = None,
    ntp_servers: list[str] | None = None
) -> dict:
    """Create plan for DNS/NTP rollout across multiple devices.

    Blast radius controls:
    - Maximum 50 devices per plan
    - Sequential execution (not parallel)
    - Halt on first failure
    - Automatic rollback on verification failure
    """
    # Blast radius limit
    if len(device_ids) > 50:
        raise ValidationError(
            f"Maximum 50 devices per plan (requested: {len(device_ids)})"
        )

    # Validate all devices exist and have proper capability
    devices = []
    for device_id in device_ids:
        device = await device_service.get_device(device_id)
        if not device:
            raise ValidationError(f"Device not found: {device_id}")

        if not device.allow_professional_workflows:
            raise AuthorizationError(
                f"Device {device_id} does not allow professional workflows"
            )

        devices.append(device)

    # Create plan with per-device change preview
    plan = await plan_service.create_plan(
        devices=devices,
        dns_servers=dns_servers,
        ntp_servers=ntp_servers,
        execution_mode="sequential",  # Not parallel
        halt_on_failure=True,
        auto_rollback=True
    )

    return {
        "plan_id": plan.id,
        "device_count": len(devices),
        "changes_preview": plan.changes_summary,
        "estimated_duration": plan.estimated_duration_seconds
    }
```

**Blast Radius Enforcement:**
1. **Maximum batch size**: 50 devices per plan (configurable, but enforced)
2. **Sequential execution**: Devices processed one at a time (no parallel failures)
3. **Halt on failure**: First device failure stops entire plan (unless explicitly configured otherwise)
4. **Automatic rollback**: Failed devices automatically rolled back to previous configuration
5. **Per-device verification**: Each device verified after change before proceeding to next
6. **Change preview**: Per-device change summary shown before execution
7. **Estimated duration**: Operators know how long multi-device operations will take

#### 4. Request Correlation

**Every MCP request is assigned a correlation ID for end-to-end tracing:**

```python
import contextvars

# Context variable for request correlation
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id")

async def handle_mcp_request(request: dict) -> dict:
    """Handle MCP JSON-RPC request with correlation ID."""
    # Generate correlation ID for this request
    correlation_id = str(uuid.uuid4())
    correlation_id_var.set(correlation_id)

    logger.info(
        "MCP request received",
        extra={
            "correlation_id": correlation_id,
            "method": request.get("method"),
            "params": request.get("params")
        }
    )

    try:
        result = await dispatch_tool_call(request)
        return {"jsonrpc": "2.0", "id": request["id"], "result": result}
    except Exception as e:
        logger.error(
            "MCP request failed",
            extra={
                "correlation_id": correlation_id,
                "error": str(e)
            }
        )
        return {"jsonrpc": "2.0", "id": request["id"], "error": {...}}
```

**Correlation ID Flow:**
1. **MCP Request** arrives → Assign `correlation_id`
2. **API Layer** logs request with `correlation_id`
3. **Domain Layer** inherits `correlation_id` from context variable
4. **RouterOS REST Call** tagged with `correlation_id` in logs
5. **Audit Event** includes `correlation_id`
6. **MCP Response** includes `correlation_id` in logs

**Benefits:**
- Trace single user action through all system layers
- Correlate MCP request → domain logic → RouterOS call → audit log
- Debug issues by searching logs for specific `correlation_id`
- Performance profiling (time spent in each layer)

---

## Device Authentication and Credential Management

### RouterOS Device Credentials

Each device requires credentials for REST API and/or SSH access:

1. **REST API Credentials**
   - Username and password for RouterOS REST API
   - Stored encrypted in `credentials` table
   - Used for all REST operations

2. **SSH Credentials (Optional)**
   - Username and password or SSH key
   - Required only for whitelisted CLI commands
   - Stored encrypted in `credentials` table

### Credential Encryption

**Encryption at Rest:**

```python
from cryptography.fernet import Fernet

class CredentialEncryption:
    """Encrypt/decrypt device credentials using Fernet symmetric encryption."""

    def __init__(self, encryption_key: str):
        """Initialize with base64-encoded encryption key."""
        self.fernet = Fernet(encryption_key.encode())

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext credential."""
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt credential."""
        return self.fernet.decrypt(ciphertext.encode()).decode()
```

**Key Management (Phase 1):**
- Encryption key stored in environment variable `ROUTEROS_MCP_ENCRYPTION_KEY`
- Must be 32-byte base64-encoded Fernet key
- Generated using: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- **Lab environment**: Warning shown if using insecure default
- **Staging/Prod**: Encryption key required (fails to start if missing)

**Credential Storage:**

```sql
CREATE TABLE credentials (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices(id),
    kind TEXT NOT NULL,  -- 'routeros_rest' or 'routeros_ssh'
    username TEXT NOT NULL,  -- Plaintext
    encrypted_secret TEXT NOT NULL,  -- Encrypted password/key
    active BOOLEAN NOT NULL DEFAULT TRUE,
    rotated_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Credential Rotation

**Phase 1 Approach:**
- Manual credential rotation via device management commands
- Old credentials marked `active = false`
- New credentials added with `active = true`
- Audit trail preserved with `rotated_at` timestamp

**Future (Phase 2+):**
- Automated credential rotation workflows
- Integration with secret managers (HashiCorp Vault, AWS Secrets Manager)
- Periodic rotation reminders

---

## Audit Logging

### Phase 1 Audit Model

**Simplified audit logging without user tracking:**

```python
class AuditEvent(Base):
    """Audit event record (Phase 1: single-user deployment, user tracking added in Phase 4)."""

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Request correlation (for end-to-end tracing)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    # Device context
    device_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("devices.id"))
    environment: Mapped[Optional[str]] = mapped_column(String(32))

    # Action details
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # WRITE, READ_SENSITIVE, etc.
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_tier: Mapped[str] = mapped_column(String(32), nullable=False)

    # Plan/Job context
    plan_id: Mapped[Optional[str]] = mapped_column(String(64))
    job_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Result
    result: Mapped[str] = mapped_column(String(32), nullable=False)  # SUCCESS, FAILURE
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Metadata
    metadata: Mapped[dict] = mapped_column(JSON, default=dict)
```

**What Gets Audited:**
- ✅ All write operations (advanced and professional tiers)
- ✅ Sensitive reads (credentials, logs with PII)
- ✅ Authorization failures (tool tier vs device capabilities)
- ✅ Plan creation and approval (even self-approved)
- ✅ Device credential changes
- ✅ Request correlation (correlation_id links MCP request → domain logic → RouterOS call → audit event)
- ❌ Regular read operations (fundamental tier)
- ❌ User information (no users in Phase 1)

**Correlation ID Benefits:**
- Trace entire request lifecycle: MCP client → API layer → domain service → RouterOS → audit log
- Debug failures by searching all logs for single `correlation_id`
- Performance profiling (measure time in each layer)
- Multi-device rollout tracking (all devices in plan share same `correlation_id`)

**Audit Retention:**
- Phase 1: Retained indefinitely in SQLite
- Future: Configurable retention policies and archival

---

## Secrets Management

### Phase 1 Secrets

1. **Encryption Key** (`ROUTEROS_MCP_ENCRYPTION_KEY`)
   - Fernet symmetric key for credential encryption
   - Required in staging/prod, warning in lab
   - Stored in environment variable
   - Never logged or exposed via API

2. **Device Credentials**
   - RouterOS username/password pairs
   - Encrypted at rest in database
   - Decrypted only when needed for API calls
   - Never logged or returned via MCP tools

3. **Configuration Secrets**
   - Can use `${VAR_NAME}` syntax in YAML config
   - Substituted from environment variables
   - Example: `database_url: sqlite:///${DATA_DIR}/routeros_mcp.db`

### Secret Loading Priority

1. Environment variables (highest priority)
2. `.env` file in working directory
3. System environment

### Security Best Practices

**Do:**
- ✅ Use strong encryption keys (32-byte random)
- ✅ Rotate device credentials periodically
- ✅ Protect database file with OS permissions (chmod 600)
- ✅ Use `.env` file for local secrets (gitignored)
- ✅ Review audit logs regularly

**Don't:**
- ❌ Commit secrets to version control
- ❌ Share encryption keys via chat/email
- ❌ Use weak or default passwords for RouterOS devices
- ❌ Run MCP server as root (use unprivileged user)
- ❌ Expose SQLite database file over network

---

## Future: Multi-User Support (Phase 5)

**Phase 1 is designed to evolve into multi-user in Phase 5 without breaking changes:**

### Planned Phase 4 Additions

1. **OAuth/OIDC Authentication**
   - Integration with Auth0, Azure AD, Okta, Keycloak
   - Authorization Code + PKCE flow
   - Bearer token validation

2. **User Model**
   - `users` table with sub, email, roles
   - User → Role → Device Scope mapping
   - Per-user audit trail

3. **Role-Based Access Control (RBAC)**
   - Three roles: `read_only`, `ops_rw`, `admin`
   - Tool tier enforcement by role:
     - `read_only` → Fundamental tier only
     - `ops_rw` → Fundamental + Advanced tiers
     - `admin` → All tiers

4. **HTTP/SSE Transport**
   - Remote access via HTTP with OAuth tokens
   - Server-Sent Events for notifications
   - HTTPS with TLS 1.2+

5. **Device Scoping**
   - Per-user device access lists
   - Team-based device groups
   - Environment-based access restrictions

### Migration Path from Phase 1 to Phase 4

**Database Migration:**
```sql
-- Add users table
CREATE TABLE users (
    sub TEXT PRIMARY KEY,
    email TEXT,
    role TEXT NOT NULL,  -- read_only, ops_rw, admin
    device_scope TEXT,  -- JSON array of device IDs or patterns
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- Add user tracking to audit_events
ALTER TABLE audit_events ADD COLUMN user_sub TEXT REFERENCES users(sub);
ALTER TABLE audit_events ADD COLUMN user_email TEXT;
ALTER TABLE audit_events ADD COLUMN user_role TEXT;
```

**Configuration Migration:**
```yaml
# Phase 1 config (stdio, no auth)
mcp_transport: stdio

# Phase 4 config (HTTP with OAuth)
mcp_transport: http
mcp_http_host: 0.0.0.0
mcp_http_port: 8080

oidc_enabled: true
oidc_issuer: https://idp.example.com
oidc_client_id: routeros-mcp
oidc_client_secret: ${OIDC_CLIENT_SECRET}
oidc_audience: routeros-mcp
```

**Authorization Migration:**
- Phase 1 implicit admin becomes explicit admin user in Phase 4
- Device capability flags remain in place
- Tool tier checks gain user role requirements

---

## Summary

### Phase 1 Security Model

✅ **OS-level access control** (single user, filesystem permissions)
✅ **Device-level authorization** (environment, capability flags, tool tiers)
✅ **Credential encryption** (Fernet, at-rest protection)
✅ **Audit logging** (all writes, sensitive reads, authorization failures)
✅ **Stdio transport** (no network exposure)
✅ **Least privilege** (fundamental tier by default, flags for higher tiers)

❌ **OAuth/OIDC** (Phase 4)
❌ **Multi-user support** (Phase 5)
❌ **HTTP transport** (Phase 4)
❌ **RBAC** (Phase 5 - device capability flags only in Phase 1)

### Key Principle

**All enforcement is server-side.** Device capability flags and tool tier restrictions ensure safety even with untrusted AI clients. Phase 1's single-user model does not compromise security—it simplifies authentication while preserving all safety mechanisms.

---

**Phase 1 provides production-ready security for single-user deployments while preserving a clear migration path to enterprise multi-user in Phase 5.**
