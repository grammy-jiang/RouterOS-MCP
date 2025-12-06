# Domain Model, Persistence & Task/Job Model

## Purpose

Describe the internal domain model, task/job execution model, and data storage for devices, credentials, metadata, audit logs, collected metrics, and configuration snapshots used by the MCP service. This document defines how information is represented, domain business rules, and persistence patterns.

**Related Documents:**
- [Doc 18: Database Schema & ORM Specification](18-database-schema-and-orm-specification.md) - Complete SQLAlchemy models with type hints
- [Doc 17: Configuration Specification](17-configuration-specification.md) - Service configuration
- [Doc 04: MCP Tools Interface](04-mcp-tools-interface-and-json-schema-specification.md) - Tool catalog

---

## Domain Entities Overview

This section describes the **domain logic, business rules, and responsibilities** of each entity. For **complete database schema and ORM models**, see [Doc 18](18-database-schema-and-orm-specification.md).

---

### Device

**Purpose**: Represents a MikroTik RouterOS device managed by the MCP service.

**Key Responsibilities:**
- Store device identity and connection information
- Track operational status and health
- Enforce capability-based access control
- Maintain device metadata and tags for organization

**Core Fields:**
- `id` (str): Unique identifier (e.g., "dev-lab-01")
- `name` (str): Human-friendly name (e.g., "router-lab-01")
- `management_address` (str): Connection endpoint (e.g., "192.168.1.1:443")
- `environment` (str): Environment classifier ("lab", "staging", "prod")
- `status` (str): Current operational status ("healthy", "degraded", "unreachable")
- `tags` (dict): Arbitrary key-value pairs for organization (e.g., {"site": "main", "role": "edge"})

**Capability Flags** (Control tool access):
- `allow_advanced_writes` (bool): Enable Advanced tier write operations (Phase 2)
- `allow_professional_workflows` (bool): Enable Professional tier multi-device workflows (Phase 4)
- `allow_ssh_commands` (bool): Enable SSH command execution (default: false)

**RouterOS Metadata** (Auto-populated from device):
- `routeros_version` (str): Last observed version (e.g., "7.10.1")
- `system_identity` (str): RouterOS identity from `/system/identity`
- `hardware_model` (str): Hardware model (e.g., "RB5009UG+S+")
- `serial_number` (str, optional): Device serial number
- `firmware_version` (str, optional): Firmware version

**Status Values:**
- `healthy`: Device is reachable and responding normally
- `degraded`: Device is reachable but health checks show warnings (high CPU, memory, etc.)
- `unreachable`: Device is not responding to connection attempts
- `pending`: Device registered but not yet verified
- `decommissioned`: Device removed from active management

**Business Rules:**

1. **Environment Isolation**: Tools can only operate on devices in the same environment as the service
   ```python
   if device.environment != settings.environment:
       raise AuthorizationError("Environment mismatch")
   ```

2. **Tier-Based Access Control**:
   - Fundamental tier: Always allowed (read-only)
   - Advanced tier: Requires `allow_advanced_writes=true`
   - Professional tier: Requires `allow_professional_workflows=true`

3. **Status Transitions**:
   - `pending` → `healthy` (after successful connection)
   - `healthy` ↔ `degraded` (based on health checks)
   - `healthy`/`degraded` ↔ `unreachable` (based on connectivity)
   - Any status → `decommissioned` (manual action)

4. **Name Uniqueness**: Device names must be unique across all environments

5. **Tag Schema Validation**: Tags should use consistent key naming conventions
   - Recommended: `site`, `role`, `region`, `tier`, `owner`
   - Values should be lowercase, alphanumeric with hyphens

**Relationships:**
- 1:N with `Credential` - Device can have multiple credentials (REST, SSH)
- 1:N with `HealthCheck` - Historical health check results
- 1:N with `Snapshot` - Configuration snapshots
- 1:N with `AuditEvent` - Operations performed on device
- M:N with `Plan` - Devices can be targets of multiple plans

---

### Credential

**Purpose**: Store encrypted per-device authentication credentials for RouterOS access.

**Key Responsibilities:**
- Securely store device credentials (username, password, API tokens)
- Support credential rotation
- Track credential lifecycle
- Prevent credential exposure in logs/audit

**Core Fields:**
- `id` (str): Unique credential identifier
- `device_id` (str): Associated device
- `kind` (str): Credential type ("routeros_rest", "routeros_ssh")
- `username` (str): RouterOS username
- `encrypted_secret` (bytes): AES-256 encrypted password/token
- `active` (bool): Whether this credential is currently active
- `rotated_at` (datetime, optional): Last rotation timestamp

**Credential Types:**
- `routeros_rest`: Username/password for REST API access (HTTPS)
- `routeros_ssh`: Username/password for SSH access

**Business Rules:**

1. **Encryption**: All secrets encrypted with application encryption key
   ```python
   from cryptography.fernet import Fernet

   def encrypt_secret(plaintext: str, key: bytes) -> bytes:
       f = Fernet(key)
       return f.encrypt(plaintext.encode())

   def decrypt_secret(ciphertext: bytes, key: bytes) -> str:
       f = Fernet(key)
       return f.decrypt(ciphertext).decode()
   ```

2. **Credential Rotation**:
   - Old credential marked as `active=false`
   - New credential created with new secret
   - Old credential retained for audit (configurable retention period)

3. **Access Control**:
   - Only infrastructure layer (RouterOS clients) can decrypt credentials
   - Credentials never exposed in API responses or logs
   - Audit events log credential usage but not the secrets

4. **Default Credential**: Each device should have exactly one active credential per kind

5. **Validation**:
   - Username: 1-64 characters, alphanumeric + underscore/hyphen
   - Password: Minimum 8 characters (enforced at creation)

**Security Considerations:**
- Encryption key stored in environment variable or secrets manager
- Database compromise does not expose plaintext credentials
- Credential access is audited (who decrypted when)
- Failed authentication attempts tracked per device

---

### HealthCheck

**Purpose**: Record periodic health assessment results for devices.

**Key Responsibilities:**
- Track device health over time
- Detect degradation trends
- Provide historical health data for troubleshooting
- Trigger alerts on status changes

**Core Fields:**
- `id` (str): Unique check identifier
- `device_id` (str): Target device
- `timestamp` (datetime): When check was performed
- `status` (str): Health status ("healthy", "warning", "critical", "error")
- `response_time_ms` (float): Connection response time
- `check_type` (str): Type of check ("connectivity", "resource", "comprehensive")

**Health Metrics** (Optional, based on check_type):
- `cpu_usage_percent` (float): CPU utilization (0-100)
- `memory_usage_percent` (float): Memory utilization (0-100)
- `temperature_celsius` (float, optional): Device temperature
- `voltage` (float, optional): Power supply voltage
- `uptime_seconds` (int): Device uptime

**Interface Status** (JSON field):
```python
{
    "ether1": {"running": true, "tx_rate_mbps": 50, "rx_rate_mbps": 30},
    "ether2": {"running": false, "disabled": true}
}
```

**Error Details** (if status == "error"):
```python
{
    "error_type": "connection_timeout",
    "error_message": "Failed to connect to 192.168.1.1:443",
    "exception": "TimeoutError"
}
```

**Health Status Thresholds:**
- `healthy`: All metrics within normal range
- `warning`: One or more metrics approaching limits
  - CPU > 80%, Memory > 85%, Temperature > 70°C
- `critical`: One or more metrics exceeding safe limits
  - CPU > 95%, Memory > 95%, Temperature > 80°C
- `error`: Health check failed (connection error, timeout)

**Business Rules:**

1. **Check Frequency**:
   - Phase 1: Configurable interval (default: 60 seconds)
   - Checks jittered to prevent thundering herd
   - Failed checks trigger immediate retry (max 3 attempts)

2. **Status Transition**:
   - 3 consecutive failures → device status becomes `unreachable`
   - 3 consecutive successes → device status returns to `healthy`
   - Single `critical` check → device status becomes `degraded`

3. **Retention**:
   - Keep last 1000 checks per device (configurable)
   - Aggregate older data (daily/hourly summaries)
   - Prune checks older than 30 days

4. **Alert Triggers**:
   - Status change from `healthy` to `degraded`/`unreachable`
   - Critical threshold exceeded
   - Consecutive failures > 3

---

### Snapshot

**Purpose**: Capture point-in-time configuration state for comparison and rollback.

**Key Responsibilities:**
- Store configuration snapshots before changes
- Enable before/after comparison
- Support rollback operations (where feasible)
- Provide historical configuration audit trail

**Core Fields:**
- `id` (str): Unique snapshot identifier
- `device_id` (str): Target device
- `timestamp` (datetime): When snapshot was taken
- `kind` (str): Snapshot type
- `payload_ref` (str): Reference to stored configuration data
- `size_bytes` (int): Uncompressed payload size
- `compressed` (bool): Whether payload is compressed

**Snapshot Types (`kind`):**
- `config_full`: Complete configuration export (`/export`)
- `config_compact`: Compact configuration export (`/export compact`)
- `system_backup`: Binary system backup (`.backup` file)
- `dns_ntp`: DNS and NTP configuration snapshot
- `firewall_rules`: Firewall filter/NAT rules snapshot
- `ip_addresses`: IP address configuration snapshot
- `pre_change`: Snapshot taken before applying changes
- `post_change`: Snapshot taken after applying changes

**Payload Storage:**
- Small payloads (< 1MB): Stored directly in `payload_ref` as JSON
- Large payloads (> 1MB): Stored in object storage (S3-compatible), `payload_ref` contains URL

**Example Payload (dns_ntp):**
```json
{
    "dns_servers": ["8.8.8.8", "8.8.4.4"],
    "allow_remote_requests": true,
    "cache_size_kb": 2048,
    "ntp_enabled": true,
    "ntp_servers": ["time.cloudflare.com"],
    "ntp_mode": "unicast"
}
```

**Business Rules:**

1. **Pre-Change Snapshots**: Required for all Advanced/Professional tier writes
   ```python
   async def execute_write_operation(device: Device, operation: str):
       # Take pre-change snapshot
       pre_snapshot = await create_snapshot(device, kind="pre_change")

       try:
           # Execute operation
           result = await perform_operation(device, operation)

           # Take post-change snapshot
           post_snapshot = await create_snapshot(device, kind="post_change")

           return result
       except Exception as e:
           # Snapshot available for troubleshooting
           raise
   ```

2. **Retention Policies**:
   - `pre_change`/`post_change`: 30 days minimum (configurable per environment)
   - `config_full`: Keep last 7 per device
   - `system_backup`: Keep last 3 per device
   - Topic-specific snapshots: Keep last 7 days

3. **Snapshot Comparison**:
   - Provide diff between pre/post snapshots
   - Highlight changed fields
   - Detect drift from expected configuration

4. **Rollback Support**:
   - Limited rollback support via snapshot restore
   - Not all changes are reversible (e.g., deleted data)
   - Rollback creates new plan requiring approval

---

### Plan

**Purpose**: Model plan/apply workflow for multi-device and high-risk operations.

**Key Responsibilities:**
- Define intended changes across one or more devices
- Provide human-reviewable change summary
- Track approval status
- Serve as execution blueprint for jobs

**Core Fields:**
- `id` (str): Unique plan identifier (e.g., "plan-20250115-001")
- `created_at` (datetime): Plan creation timestamp
- `created_by` (str): User identifier (Phase 4) or "system" (Phase 1)
- `tool_name` (str): MCP tool that created plan (e.g., "config/plan-dns-ntp-rollout")
- `status` (str): Plan lifecycle status
- `summary` (str): Human-readable description
- `risk_level` (str): Risk assessment ("low", "medium", "high")

**Plan Targets** (JSON field):
```python
[
    {
        "device_id": "dev-lab-01",
        "environment": "lab",
        "changes": [
            {
                "topic": "dns",
                "action": "update_servers",
                "current": {"servers": ["8.8.8.8", "8.8.4.4"]},
                "desired": {"servers": ["1.1.1.1", "1.0.0.1"]}
            }
        ]
    }
]
```

**Plan Status Values:**
- `draft`: Plan created, not yet finalized
- `pending_approval`: Plan awaiting human approval (Phase 4)
- `approved`: Plan approved, ready to execute
- `executing`: Plan currently being executed
- `completed`: Plan execution succeeded
- `failed`: Plan execution failed
- `cancelled`: Plan cancelled before execution
- `expired`: Plan expired (not executed within time window)

**Business Rules:**

1. **Immutability**: Plans become immutable after `pending_approval` status
   - Changes require creating a new plan
   - Original plan marked as `cancelled`

2. **Expiration**:
   - Plans expire after 24 hours (configurable)
   - Expired plans cannot be executed
   - Re-planning required if expired

3. **Risk Assessment**:
   - `low`: Read-only, diagnostics, single device low-risk writes
   - `medium`: Single device advanced writes, limited impact
   - `high`: Multi-device writes, routing changes, professional tier

4. **Approval Requirements** (Phase 4):
   - `low` risk: Auto-approved
   - `medium` risk: Requires `ops_rw` role approval
   - `high` risk: Requires `admin` role approval + human review

5. **Phase 1 Behavior**: All plans auto-approved (single-user, OS-level trust)

---

### Job

**Purpose**: Represent executable unit of work, often tied to a Plan.

**Key Responsibilities:**
- Execute planned operations
- Track execution progress and status
- Handle retries on transient failures
- Provide detailed execution results

**Core Fields:**
- `id` (str): Unique job identifier (e.g., "job-20250115-001")
- `plan_id` (str, optional): Associated plan
- `type` (str): Job type
- `status` (str): Execution status
- `priority` (int): Execution priority (0-10, default 5)
- `device_ids` (list[str]): Target devices
- `scheduled_at` (datetime): When job should run
- `started_at` (datetime, optional): Actual start time
- `completed_at` (datetime, optional): Actual completion time

**Job Types:**
- `apply_plan`: Execute approved plan
- `health_check`: Perform health assessment
- `metrics_collection`: Gather system metrics
- `config_backup`: Create configuration snapshots
- `drift_detection`: Compare expected vs actual state
- `cleanup`: Prune old data

**Job Status Values:**
- `pending`: Job queued, not yet started
- `scheduled`: Job scheduled for future execution
- `running`: Job currently executing
- `success`: Job completed successfully
- `failed`: Job failed after retries exhausted
- `cancelled`: Job cancelled by user/system
- `timeout`: Job exceeded maximum execution time

**Retry Strategy**:
```python
{
    "attempts": 0,
    "max_attempts": 3,
    "retry_delay_seconds": 60,
    "backoff_multiplier": 2.0  # Exponential backoff
}
```

**Execution Results** (JSON field):
```python
{
    "total_devices": 3,
    "successful": 2,
    "failed": 1,
    "results": [
        {
            "device_id": "dev-lab-01",
            "status": "success",
            "changed": true,
            "execution_time_ms": 450,
            "changes_applied": ["dns_servers_updated"]
        },
        {
            "device_id": "dev-lab-02",
            "status": "failed",
            "error": "Device unreachable",
            "error_code": "DEVICE_UNREACHABLE"
        }
    ]
}
```

**Business Rules:**

1. **Execution Priority**:
   - Priority 10: Critical (health checks for unreachable devices)
   - Priority 5: Normal (scheduled tasks, user operations)
   - Priority 0: Low (cleanup, maintenance)

2. **Retry Logic**:
   - Transient errors (network timeout, rate limit): Retry with backoff
   - Permanent errors (auth failure, validation error): Fail immediately
   - Max 3 retry attempts

3. **Timeout Limits**:
   - Simple jobs (health check): 30 seconds
   - Standard jobs (apply plan): 5 minutes
   - Long-running jobs (backup): 15 minutes

4. **Concurrency Control**:
   - Max 3 concurrent jobs per device
   - Jobs queued if device is busy
   - Priority queue ensures critical jobs run first

5. **Job Cleanup**:
   - Completed jobs retained for 7 days
   - Failed jobs retained for 30 days (for debugging)
   - Job logs archived after retention period

---

### AuditEvent

**Purpose**: Immutable record of security-relevant events and operations.

**Key Responsibilities:**
- Track all write operations
- Log sensitive read operations
- Record authorization decisions (allowed/denied)
- Provide compliance audit trail

**Core Fields (Phase 1 - Single User):**
- `id` (str): Unique event identifier
- `timestamp` (datetime): Event occurrence time
- `device_id` (str, optional): Target device (if device-specific)
- `environment` (str, optional): Device environment
- `action` (str): Event action type
- `tool_name` (str): MCP tool invoked
- `tool_tier` (str): Tool tier ("fundamental", "advanced", "professional")
- `plan_id` (str, optional): Associated plan
- `job_id` (str, optional): Associated job
- `result` (str): Operation result ("success", "failure")
- `error_message` (str, optional): Error details if failed
- `metadata` (dict): Additional context

**Action Types:**
- `WRITE`: Configuration write operation
- `READ_SENSITIVE`: Sensitive data access (credentials, etc.)
- `AUTHZ_ALLOWED`: Authorization check passed
- `AUTHZ_DENIED`: Authorization check failed
- `DEVICE_REGISTERED`: New device added
- `DEVICE_DECOMMISSIONED`: Device removed
- `CREDENTIAL_ROTATED`: Credential updated
- `SSH_COMMAND`: SSH command executed

**Metadata Examples:**

**Write Operation:**
```json
{
    "tool_name": "dns/update-servers",
    "old_value": ["8.8.8.8", "8.8.4.4"],
    "new_value": ["1.1.1.1", "1.0.0.1"],
    "changed": true,
    "dry_run": false
}
```

**Authorization Denied:**
```json
{
    "tool_name": "routing/add-static-route",
    "tool_tier": "professional",
    "deny_reason": "Device does not allow professional workflows",
    "required_flag": "allow_professional_workflows",
    "device_flag_value": false
}
```

**Business Rules:**

1. **Immutability**: Audit events never modified or deleted
   - Append-only log
   - No UPDATE or DELETE operations

2. **Retention**: Configurable per environment
   - Development: 30 days
   - Staging: 90 days
   - Production: 365 days minimum (compliance requirement)

3. **What Gets Audited**:
   - ✅ All Advanced/Professional tier tools
   - ✅ Fundamental tier tools that access sensitive data
   - ✅ Authorization failures
   - ✅ Device registration/decommission
   - ✅ Credential rotation
   - ❌ Routine health checks (too noisy)
   - ❌ Metrics collection (not security-relevant)

4. **Audit Query Patterns**:
   ```python
   # Find all writes to a device
   events = await audit_repo.find(
       device_id="dev-prod-01",
       action="WRITE",
       start_time=datetime.now() - timedelta(days=7)
   )

   # Find all authorization denials
   denials = await audit_repo.find(
       action="AUTHZ_DENIED",
       tool_tier="professional"
   )
   ```

5. **Phase 4 Extension**: Will add user tracking
   - `user_sub`: OIDC user subject
   - `user_email`: User email address
   - `user_role`: User role at time of operation

---

## Logical Data Model and Relationships

### Entity Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                        Device                               │
│  - id, name, management_address                             │
│  - environment, status, tags                                │
│  - capability flags, RouterOS metadata                      │
└────┬─────────────┬─────────────┬─────────────┬─────────────┘
     │ 1:N         │ 1:N         │ 1:N         │ 1:N
     ▼             ▼             ▼             ▼
┌──────────┐ ┌──────────────┐ ┌──────────┐ ┌──────────────┐
│Credential│ │ HealthCheck  │ │ Snapshot │ │ AuditEvent   │
│- username│ │ - status     │ │- kind    │ │- action      │
│- secret  │ │ - metrics    │ │- payload │ │- result      │
└──────────┘ └──────────────┘ └──────────┘ └──────────────┘


┌─────────────────────────────────────────┐
│              Plan                       │
│  - id, summary, status, risk_level      │
│  - targets (JSON: devices + changes)    │
└────────────┬────────────────────────────┘
             │ 1:N
             ▼
     ┌────────────────┐
     │      Job       │
     │  - type        │
     │  - status      │
     │  - results     │
     └────────────────┘
```

### Relationship Rules

1. **Device → Credential** (1:N):
   - Each device can have multiple credentials (REST, SSH)
   - Exactly one active credential per kind
   - Cascade: Soft-delete device → inactive credentials

2. **Device → HealthCheck** (1:N):
   - One device, many health checks over time
   - Cascade: Delete device → archive health checks

3. **Device → Snapshot** (1:N):
   - One device, many snapshots
   - Cascade: Delete device → retain snapshots for audit

4. **Device → AuditEvent** (1:N):
   - One device, many audit events
   - Cascade: Delete device → retain audit events (immutable)

5. **Plan → Job** (1:N):
   - One plan can spawn multiple jobs (per device)
   - Jobs can exist without plans (health checks, etc.)
   - Cascade: Archive plan → archive related jobs

6. **Plan → Device** (M:N):
   - Plans can target multiple devices
   - Devices can be in multiple plans (historical)
   - Relationship stored in Plan.targets JSON field

---

## Physical Storage Strategy

**For complete database schema, see [Doc 18](18-database-schema-and-orm-specification.md).**

### Storage Tiers

**Primary Metadata Store** (SQL/Relational):
- **Phase 1**: SQLite (`sqlite:///./routeros_mcp.db`)
  - Single-file database
  - Embedded in application
  - No separate database server
  - Suitable for < 10 devices

- **Phase 4**: PostgreSQL (`postgresql+asyncpg://...`)
  - Client-server architecture
  - Concurrent writes
  - Horizontal scaling
  - Full-text search

**What Goes in Primary Store:**
- Device registry and metadata
- Credentials (encrypted)
- Plans and jobs
- Health check summaries
- Snapshot metadata
- Audit events

**Secrets Storage:**
- Encrypted credentials stored in primary database
- Application-level encryption (AES-256 via Fernet)
- Encryption key from environment variable (`ROUTEROS_MCP_ENCRYPTION_KEY`)
- Database compromise does not reveal secrets

**Object Storage** (Optional, Phase 2+):
- Large configuration snapshots (> 1MB)
- Binary system backups
- S3-compatible storage
- Snapshot records contain references (`payload_ref`)

**Time-Series Store** (Optional, Phase 3+):
- Detailed metrics (Prometheus, InfluxDB)
- High-frequency health data
- Interface statistics over time
- Primary DB keeps only aggregates

---

## Data Lifecycle Management

### Creation Workflows

**Device Registration:**
```python
async def register_device(
    name: str,
    management_address: str,
    environment: str,
    credentials: dict
) -> Device:
    # 1. Create device record
    device = Device(
        id=generate_device_id(),
        name=name,
        management_address=management_address,
        environment=environment,
        status="pending",
        allow_advanced_writes=False,  # Default: safe
        allow_professional_workflows=False
    )

    # 2. Encrypt and store credentials
    credential = Credential(
        id=generate_credential_id(),
        device_id=device.id,
        kind="routeros_rest",
        username=credentials["username"],
        encrypted_secret=encrypt_secret(
            credentials["password"],
            settings.encryption_key
        ),
        active=True
    )

    # 3. Save to database
    async with session_manager.session() as session:
        session.add(device)
        session.add(credential)
        await session.commit()

    # 4. Audit event
    await audit_repo.create(
        action="DEVICE_REGISTERED",
        device_id=device.id,
        tool_name="device/register-device",
        tool_tier="advanced",
        result="success",
        metadata={"environment": environment}
    )

    # 5. Schedule initial health check
    await job_scheduler.schedule(
        type="health_check",
        device_ids=[device.id],
        priority=10  # High priority for new device
    )

    return device
```

**Health Check Execution:**
```python
async def execute_health_check(device: Device) -> HealthCheck:
    try:
        # 1. Connect to device
        client = await get_routeros_client(device)

        # 2. Fetch system resource info
        resource = await client.get("/rest/system/resource")

        # 3. Parse metrics
        cpu_usage = float(resource["cpu-load"])
        memory_total = int(resource["total-memory"])
        memory_free = int(resource["free-memory"])
        memory_usage_pct = (1 - memory_free / memory_total) * 100

        # 4. Determine status
        if cpu_usage > 95 or memory_usage_pct > 95:
            status = "critical"
        elif cpu_usage > 80 or memory_usage_pct > 85:
            status = "warning"
        else:
            status = "healthy"

        # 5. Create health check record
        health_check = HealthCheck(
            id=generate_id(),
            device_id=device.id,
            timestamp=datetime.utcnow(),
            status=status,
            response_time_ms=client.last_response_time_ms,
            cpu_usage_percent=cpu_usage,
            memory_usage_percent=memory_usage_pct,
            uptime_seconds=parse_duration(resource["uptime"])
        )

        # 6. Update device status if changed
        if device.status != status and status in ["degraded", "unreachable"]:
            device.status = status
            await device_repo.update(device)

        return health_check

    except ConnectionError as e:
        # Mark device as unreachable
        device.status = "unreachable"
        await device_repo.update(device)

        return HealthCheck(
            device_id=device.id,
            status="error",
            error_details={"error_type": "connection_error", "message": str(e)}
        )
```

### Update Workflows

**Credential Rotation:**
```python
async def rotate_credential(device_id: str, new_password: str):
    # 1. Get current active credential
    current_cred = await credential_repo.find_active(
        device_id=device_id,
        kind="routeros_rest"
    )

    # 2. Mark current as inactive
    current_cred.active = False
    current_cred.rotated_at = datetime.utcnow()

    # 3. Create new credential
    new_cred = Credential(
        id=generate_id(),
        device_id=device_id,
        kind="routeros_rest",
        username=current_cred.username,
        encrypted_secret=encrypt_secret(new_password, settings.encryption_key),
        active=True
    )

    # 4. Save changes
    async with session_manager.session() as session:
        session.add(current_cred)
        session.add(new_cred)
        await session.commit()

    # 5. Audit event
    await audit_repo.create(
        action="CREDENTIAL_ROTATED",
        device_id=device_id,
        tool_name="device/rotate-credential",
        tool_tier="advanced",
        result="success"
    )
```

### Archival and Deletion

**Data Retention Policies:**

| Entity | Retention Period | Action After Expiry |
|--------|------------------|---------------------|
| **Device** | Until decommissioned | Soft-delete, retain audit trail |
| **Credential** (inactive) | 90 days | Hard delete |
| **HealthCheck** | 30 days (per device) | Keep last 1000, delete older |
| **Snapshot** (routine) | 7 days | Delete payload, keep metadata for 30 days |
| **Snapshot** (change-related) | 30 days | Delete payload, keep metadata for 90 days |
| **Plan** | 90 days | Archive to object storage |
| **Job** (completed) | 7 days | Delete |
| **Job** (failed) | 30 days | Delete |
| **AuditEvent** | 365 days (prod) | Archive to object storage, never delete |

**Cleanup Job:**
```python
async def cleanup_old_data():
    """Periodic cleanup job to enforce retention policies."""
    cutoff_date = datetime.utcnow() - timedelta(days=30)

    # Prune old health checks
    await health_check_repo.delete_older_than(cutoff_date)

    # Prune old snapshots
    await snapshot_repo.delete_routine_older_than(
        cutoff_date - timedelta(days=7)
    )

    # Archive completed jobs
    await job_repo.archive_completed_older_than(
        cutoff_date - timedelta(days=7)
    )

    logger.info("Cleanup job completed", cutoff_date=cutoff_date)
```

---

## Consistency Guarantees and Caching

### Consistency Model

**Strong Consistency** (required):
- Device capability flags
- Credential active status
- Plan approval status
- Authorization decisions

**Eventual Consistency** (acceptable):
- Health check metrics
- Device RouterOS version metadata
- Snapshot availability

### Caching Strategy

**In-Memory Cache:**
```python
from cachetools import TTLCache

# Device metadata cache (5 minute TTL)
device_cache = TTLCache(maxsize=100, ttl=300)

async def get_device(device_id: str) -> Device:
    if device_id in device_cache:
        return device_cache[device_id]

    device = await device_repo.find_by_id(device_id)
    device_cache[device_id] = device
    return device
```

**Cache Invalidation:**
```python
async def update_device(device: Device):
    await device_repo.update(device)

    # Invalidate cache
    if device.id in device_cache:
        del device_cache[device.id]
```

**Never Cache:**
- Credentials (always fetch fresh and decrypt)
- Authorization tokens (Phase 4)
- Audit events (immutable, no need to cache)

### Out-of-Band Change Detection

**Drift Detection:**
```python
async def detect_config_drift(device: Device):
    # 1. Get expected config (from last snapshot)
    expected_snapshot = await snapshot_repo.find_latest(
        device_id=device.id,
        kind="dns_ntp"
    )

    # 2. Fetch current config from device
    client = await get_routeros_client(device)
    current_dns = await client.get("/rest/ip/dns")
    current_ntp = await client.get("/rest/system/ntp/client")

    # 3. Compare
    drift_detected = (
        current_dns["servers"] != expected_snapshot.payload["dns_servers"] or
        current_ntp["servers"] != expected_snapshot.payload["ntp_servers"]
    )

    # 4. Alert if drift detected
    if drift_detected:
        logger.warning(
            "Configuration drift detected",
            device_id=device.id,
            expected=expected_snapshot.payload,
            current={"dns": current_dns, "ntp": current_ntp}
        )
```

---

## Task/Job Execution Model

### Job Scheduler Architecture

**Components:**
1. **Job Queue**: Priority queue for pending jobs
2. **Worker Pool**: Async workers that execute jobs
3. **Retry Manager**: Handles failed job retries
4. **Status Tracker**: Monitors job progress

**Scheduler Implementation:**
```python
class JobScheduler:
    """Asynchronous job scheduler with priority queue."""

    def __init__(self):
        self.queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.workers: list[asyncio.Task] = []
        self.running_jobs: dict[str, Job] = {}

    async def schedule(
        self,
        type: str,
        device_ids: list[str],
        priority: int = 5,
        scheduled_at: datetime | None = None
    ) -> str:
        """Schedule a new job."""
        job = Job(
            id=generate_job_id(),
            type=type,
            device_ids=device_ids,
            priority=priority,
            status="pending",
            scheduled_at=scheduled_at or datetime.utcnow()
        )

        await job_repo.create(job)
        await self.queue.put((priority, job.id))

        return job.id

    async def worker(self):
        """Job worker coroutine."""
        while True:
            priority, job_id = await self.queue.get()

            try:
                job = await job_repo.find_by_id(job_id)
                await self.execute_job(job)
            except Exception as e:
                logger.error("Job execution failed", job_id=job_id, error=str(e))
            finally:
                self.queue.task_done()

    async def execute_job(self, job: Job):
        """Execute a job."""
        self.running_jobs[job.id] = job
        job.status = "running"
        job.started_at = datetime.utcnow()

        try:
            if job.type == "health_check":
                await self.execute_health_check(job)
            elif job.type == "apply_plan":
                await self.execute_apply_plan(job)
            elif job.type == "config_backup":
                await self.execute_config_backup(job)

            job.status = "success"
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)

            # Retry if attempts remaining
            if job.attempts < job.max_attempts:
                await self.schedule_retry(job)
        finally:
            job.completed_at = datetime.utcnow()
            await job_repo.update(job)
            del self.running_jobs[job.id]
```

### Job Types

**1. Health Check Job:**
```python
async def execute_health_check(job: Job):
    results = []

    for device_id in job.device_ids:
        device = await device_repo.find_by_id(device_id)
        health_check = await execute_health_check(device)
        results.append({
            "device_id": device_id,
            "status": health_check.status
        })

    job.result_summary = json.dumps(results)
```

**2. Apply Plan Job:**
```python
async def execute_apply_plan(job: Job):
    plan = await plan_repo.find_by_id(job.plan_id)

    if plan.status != "approved":
        raise ValueError("Plan not approved")

    plan.status = "executing"
    await plan_repo.update(plan)

    results = []
    for target in plan.targets:
        device = await device_repo.find_by_id(target["device_id"])

        # Take pre-change snapshot
        pre_snapshot = await create_snapshot(device, kind="pre_change")

        try:
            # Apply changes
            for change in target["changes"]:
                await apply_change(device, change)

            # Take post-change snapshot
            post_snapshot = await create_snapshot(device, kind="post_change")

            results.append({
                "device_id": device.id,
                "status": "success",
                "pre_snapshot_id": pre_snapshot.id,
                "post_snapshot_id": post_snapshot.id
            })
        except Exception as e:
            results.append({
                "device_id": device.id,
                "status": "failed",
                "error": str(e)
            })

    plan.status = "completed" if all(r["status"] == "success" for r in results) else "failed"
    job.result_summary = json.dumps(results)
```

**3. Config Backup Job:**
```python
async def execute_config_backup(job: Job):
    for device_id in job.device_ids:
        device = await device_repo.find_by_id(device_id)

        # Use SSH to export config
        ssh_client = await get_ssh_client(device)
        config_text = await ssh_client.execute("/export compact")

        # Create snapshot
        snapshot = Snapshot(
            device_id=device.id,
            kind="config_compact",
            payload_ref=config_text,  # Small enough to store inline
            size_bytes=len(config_text),
            compressed=False
        )

        await snapshot_repo.create(snapshot)
```

### Job Safety Controls

**1. Concurrency Limits:**
```python
MAX_CONCURRENT_JOBS_PER_DEVICE = 3

async def can_execute_job(device_id: str) -> bool:
    running_jobs = await job_repo.count_running_for_device(device_id)
    return running_jobs < MAX_CONCURRENT_JOBS_PER_DEVICE
```

**2. Environment Validation:**
```python
async def validate_job_safety(job: Job):
    for device_id in job.device_ids:
        device = await device_repo.find_by_id(device_id)

        # Check environment match
        if device.environment != settings.environment:
            raise ValueError(f"Device environment mismatch: {device.environment}")

        # Check capability flags
        if job.type == "apply_plan":
            plan = await plan_repo.find_by_id(job.plan_id)
            if plan.risk_level == "high" and not device.allow_professional_workflows:
                raise ValueError(f"Device {device.id} does not allow professional workflows")
```

**3. Timeout Enforcement:**
```python
async def execute_job_with_timeout(job: Job, timeout_seconds: int):
    try:
        await asyncio.wait_for(
            execute_job(job),
            timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        job.status = "timeout"
        job.error_message = f"Job exceeded {timeout_seconds}s timeout"
        await job_repo.update(job)
```

---

## ORM Usage Patterns

**For complete ORM models with full type hints, see [Doc 18](18-database-schema-and-orm-specification.md).**

### Session Management

```python
from routeros_mcp.infra.db.session import get_session_manager

# Initialize session manager
session_manager = get_session_manager()
await session_manager.init()

# Use session context manager
async with session_manager.session() as session:
    device = await session.get(Device, "dev-lab-01")
    device.status = "healthy"
    await session.commit()
```

### Repository Pattern

```python
class DeviceRepository:
    """Repository for Device entity operations."""

    async def find_by_id(self, device_id: str) -> Device | None:
        async with session_manager.session() as session:
            return await session.get(Device, device_id)

    async def find_by_environment(self, environment: str) -> list[Device]:
        async with session_manager.session() as session:
            result = await session.execute(
                select(Device).where(Device.environment == environment)
            )
            return result.scalars().all()

    async def create(self, device: Device) -> Device:
        async with session_manager.session() as session:
            session.add(device)
            await session.commit()
            await session.refresh(device)
            return device

    async def update(self, device: Device) -> Device:
        async with session_manager.session() as session:
            device = await session.merge(device)
            await session.commit()
            return device
```

### Query Patterns

```python
# Find devices with specific tags
async def find_devices_by_tag(tag_key: str, tag_value: str) -> list[Device]:
    async with session_manager.session() as session:
        result = await session.execute(
            select(Device).where(
                Device.tags[tag_key].as_string() == tag_value
            )
        )
        return result.scalars().all()

# Find health checks in warning state
async def find_warning_health_checks(since: datetime) -> list[HealthCheck]:
    async with session_manager.session() as session:
        result = await session.execute(
            select(HealthCheck)
            .where(HealthCheck.status == "warning")
            .where(HealthCheck.timestamp >= since)
            .order_by(HealthCheck.timestamp.desc())
        )
        return result.scalars().all()

# Find audit events for a device
async def find_audit_events(
    device_id: str,
    action: str | None = None,
    start_time: datetime | None = None
) -> list[AuditEvent]:
    async with session_manager.session() as session:
        query = select(AuditEvent).where(AuditEvent.device_id == device_id)

        if action:
            query = query.where(AuditEvent.action == action)

        if start_time:
            query = query.where(AuditEvent.timestamp >= start_time)

        query = query.order_by(AuditEvent.timestamp.desc())

        result = await session.execute(query)
        return result.scalars().all()
```

---

## Related Documents

- **[Doc 18: Database Schema & ORM Specification](18-database-schema-and-orm-specification.md)** - Complete SQLAlchemy models
- **[Doc 17: Configuration Specification](17-configuration-specification.md)** - Database configuration
- **[Doc 04: MCP Tools Interface](04-mcp-tools-interface-and-json-schema-specification.md)** - Tools that use these entities
- **[Doc 16: Detailed Module Specifications](16-detailed-module-specifications.md)** - Service and repository implementations

---

**Document Status**: ✅ Complete with Phase 1 focus, ORM emphasis, and real-world operational considerations
