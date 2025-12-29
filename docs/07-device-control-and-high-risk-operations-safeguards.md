# Device Control & High-Risk Operations Safeguards

## Purpose

Define which high-risk operations exist on RouterOS (e.g., reboot, upgrade, reset configuration, interface shutdown on WAN, major routing and firewall changes), how and whether they are exposed via MCP, and what guardrails, approvals, and rollbacks are required to keep usage safe. This document serves as the “safety bible” for adding or changing MCP tools that can impact device reachability or production traffic.

## **Phasing Note**: Phase 2 introduced read-only visibility enhancements (wireless, DHCP, bridge, CAPsMAN tools). Phase 3 (COMPLETED) introduces single-device writes including system identity, DNS/NTP, secondary IPs, firewall address-lists/rules, DHCP pools, bridge ports, and wireless SSID/RF configuration as **single-device, lab/staging-focused operations** with mandatory plan/apply workflows and HMAC-signed approval tokens. Multi-device coordination and diagnostics (ping/traceroute/bandwidth-test) are deferred to Phase 4+. Phase 5 extends to multi-user RBAC and approval workflow engines.

## Catalog of high-risk actions (reboot, system upgrade, reset, interface disable on WAN, routing/firewall changes, wireless RF changes)

The following categories of actions are considered **high risk** because they can impact reachability, security, or large portions of traffic:

- **Device lifecycle & control**:

  - `system reboot` or shutdown.
  - `system upgrade` (RouterOS package upgrades).
  - `system reset` or restore from backups.

- **Management plane & access**:

  - Changing management IP addresses or gateways.
  - Changing access control lists that protect management interfaces.
  - Modifying RouterOS users, authentication methods, certificates, VPN, remote access.

- **Forwarding plane: firewall & NAT**:

  - Editing rules in default chains (`INPUT`, `FORWARD`, `OUTPUT`).
  - Creating, reordering, or removing NAT rules.
  - Modifying mangle rules that affect routing or classification.

- **Routing & bridging**:

  - Adding/removing core static routes (especially for management or backbone networks).
  - Changing routing policies, protocol filters (BGP/OSPF), or timers.
  - Bridge VLAN filtering changes on production segments.
  - STP/RSTP/MSTP parameters (priority, enabling/disabling STP) that can create loops or outages.

- **DHCP & addressing**:

  - DHCP server configuration on production networks.
  - Changing address pools or options that affect many clients.
  - Modifying IP addressing or masks on key interfaces.

- **Wireless & RF**:
  - Changing SSIDs or security on production APs.
  - Changing frequencies, channels, or TX power on production APs.

---

## Exposure policy (not exposed, human approval required, plan-then-apply workflows)

For each high-risk category, we define v1 exposure:

- **Out of scope for 1.x (no write exposure)**:

  - RouterOS user management, authentication, certificates.
  - VPN and remote access configuration.
  - System upgrade/reset/factory defaults.
  - NAT configuration (all writes).
  - Bridge VLAN filtering and STP on production devices.

- **Professional-only, lab/staging only by default**:

  - Certain routing changes (non-core static routes).
  - DHCP changes on lab/staging networks.
  - Wireless SSID and RF changes on lab/staging APs.

- **Professional-only, optional for controlled production clusters**:
  - Templated firewall rule changes in MCP-owned chains.
  - Selected static routes in non-core paths, after simulation and strict checks.
  - Interface admin up/down on non-management interfaces, when redundant paths are confirmed.

All high-risk operations that are exposed via MCP must:

- Be **professional-tier** tools.
- Use **plan/apply** workflows (no single-step apply).
- Require human approval tokens for the apply step.
- Obey environment tags and capability flags (prod typically disabled or heavily restricted).

Many deployments are expected and recommended to keep these capabilities **permanently disabled** in production, even if the code exists.

---

## Guardrails and safety mechanisms (pre-checks, dry-run plans, “safe mode” rollbacks)

For any high-risk tool that is enabled:

- **Pre-checks**:

  - Verify that:
    - Target devices are in allowed environments (often `lab`/`staging`).
    - Device capability flags permit professional workflows and the specific topic.
    - Management path will remain reachable (where possible).
    - Proposed changes do not violate obvious invariants (e.g., creating overlapping subnets).

- **Dry-run / plan**:

  - Plan step:
    - Computes a detailed preview of changes (per device), including:
      - Before/after summaries.
      - Risk classification (e.g., “may affect management path”).
    - Does not apply any changes.

- **Apply with staged rollout**:

  - Changes are applied:
    - In small batches of devices.
    - With pauses and health checks between batches.
  - Failure or degradation triggers:
    - Halt of further batches.
    - Optional automatic rollback for affected devices where feasible.

- **Safe-mode rollback** (where possible):
  - For certain operations (e.g., adding a static route, modifying DNS/NTP):
    - Keep a snapshot of the previous configuration.
    - If post-change checks fail, revert to the snapshot.
  - Not all operations are trivially reversible (e.g., stateful firewall changes or STP tweaks), so rollbacks must be carefully designed per topic.

---

## Risk classification per topic and mapping to MCP capability tiers

We classify topics and operations into approximate risk levels:

- **Low risk** (advanced tier, potentially prod):

  - System identity/comment, interface descriptions.
  - Non-impactful metadata (tags, comments).

- **Medium risk** (advanced tier, often lab/staging first):

  - DNS/NTP changes on non-critical devices.
  - Secondary IPs on non-management interfaces.
  - DHCP/bridge changes on lab/staging only.

- **High risk** (professional tier, often lab-only or opt-in prod):

  - Firewall rule changes in MCP-owned chains.
  - Static routes on production devices.
  - Interface admin up/down on non-core ports.
  - Wireless SSID/RF tweaks on production APs.

- **Extreme risk** (out-of-scope or future major version only):
  - NAT changes.
  - Bridge VLAN filtering and STP core parameters on production networks.
  - User management, VPN, remote access changes.
  - System upgrade/reset/factory defaults.

Mapping to MCP tiers:

- **Fundamental**: read-only and diagnostics across all topics, including high-risk ones.
- **Advanced**: low/medium risk writes on appropriately flagged devices/environments.
- **Professional**: high-risk writes and all multi-device workflows; mandatory plan/apply and approvals.

---

## Auditability and governance (who can change safeguards, how changes are reviewed)

- **Governance of safeguards**:

  - Only `admin` users with specific elevated privileges (and possibly out-of-band approvals) can change:
    - Device environment tags (`lab`/`staging`/`prod`).
    - Device capability flags (`allow_advanced_writes`, `allow_professional_workflows`, topic-specific flags).
    - Global configuration that enables/disables high-risk tools.

- **Change management**:

  - Any change to safeguard configuration is:
    - Logged as an `AuditEvent` with clear markers.
    - Potentially gated by an internal process (e.g., code review, configuration review).

- **Audit requirements**:

  - All high-risk tool invocations must:
    - Reference a `plan_id` (from Doc 05 Plan entity).
    - Include `correlation_id` linking to the originating MCP request for end-to-end tracing.
    - Record the approval token and approver identity.
    - Include before/after snapshots where supported (Doc 05 Snapshot entity: `snapshot_type="pre_change"` and `snapshot_type="post_change"`).
  - Audit logs should make it clear:
    - Who initiated a change and who approved it.
    - Which devices were affected and what the outcomes were.
    - Whether any rollbacks were automatically or manually triggered.
    - Full correlation path: `mcp_request_id` → `plan_id` → `job_id` → `snapshot_id`

- **Review and continuous improvement**:
  - Periodic reviews of:
    - High-risk tool usage patterns.
    - Incidents or near-misses linked to MCP operations.
  - Resulting in updates to:
    - Safeguard policies.
    - Default capability flags.
    - Which tools are enabled by default in which environments.

---

## Plan/Apply Workflow Implementation (MCP Integration)

### Two-Phase Workflow for High-Risk Operations

All high-risk operations follow a mandatory two-phase workflow exposed via separate MCP tools:

**Phase 1: Plan (Validation & Preview)**

- Tool naming: `{topic}/plan-{operation}` (e.g., `firewall/plan-add-rule`, `routing/plan-static-routes`)
- Creates a `Plan` entity (Doc 05) with `risk_level` assessment
- Performs all validations without applying changes
- Returns detailed preview with `estimated_tokens` warning if large
- Generates approval token that must be used in Phase 2

**Phase 2: Apply (Execution with Approval)**

- Tool naming: `{topic}/apply-plan`
- Requires `plan_id` and valid `approval_token`
- Creates `Job` entity (Doc 05) linked to Plan
- Executes changes with health checks and rollback support
- Returns execution results with correlation tracking

### MCP Tool Schema Example: Firewall Rule Planning

**Tool: `firewall/plan-add-rule`** (Professional tier)

```json
{
  "jsonrpc": "2.0",
  "id": "req-fw-plan-001",
  "method": "tools/call",
  "params": {
    "name": "firewall/plan-add-rule",
    "arguments": {
      "device_ids": ["dev-lab-01", "dev-lab-02"],
      "chain": "forward",
      "action": "accept",
      "src_address": "192.168.1.0/24",
      "dst_address": "10.0.0.0/8",
      "protocol": "tcp",
      "dst_port": "443",
      "comment": "Allow internal to app subnet HTTPS"
    }
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": "req-fw-plan-001",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Firewall rule plan created successfully.\n\nRisk Level: HIGH\nDevices: 2\nEstimated duration: 15 seconds\n\nTo apply this plan, use firewall/apply-plan with:\n  plan_id: plan-fw-20250115-001\n  approval_token: approve-fw-a1b2c3d4"
      }
    ],
    "isError": false,
    "_meta": {
      "correlation_id": "corr-req-fw-plan-001",
      "plan_id": "plan-fw-20250115-001",
      "approval_token": "approve-fw-a1b2c3d4",
      "approval_expires_at": "2025-01-15T10:15:00Z",
      "risk_level": "high",
      "tool_name": "firewall/plan-add-rule",
      "device_count": 2,
      "devices": [
        {
          "device_id": "dev-lab-01",
          "name": "router-lab-01",
          "environment": "lab",
          "pre_check_status": "passed",
          "preview": {
            "operation": "add_firewall_rule",
            "chain": "forward",
            "position": "auto",
            "rule_spec": "chain=forward action=accept src-address=192.168.1.0/24 dst-address=10.0.0.0/8 protocol=tcp dst-port=443",
            "estimated_impact": "Low - rule added to end of chain, existing connections unaffected"
          }
        },
        {
          "device_id": "dev-lab-02",
          "name": "router-lab-02",
          "environment": "lab",
          "pre_check_status": "passed",
          "preview": {
            "operation": "add_firewall_rule",
            "chain": "forward",
            "position": "auto",
            "rule_spec": "chain=forward action=accept src-address=192.168.1.0/24 dst-address=10.0.0.0/8 protocol=tcp dst-port=443",
            "estimated_impact": "Low - rule added to end of chain, existing connections unaffected"
          }
        }
      ],
      "validations": {
        "environment_check": "passed - all devices in 'lab' environment",
        "capability_check": "passed - all devices allow professional workflows",
        "health_check": "passed - all devices healthy",
        "conflict_check": "passed - no conflicting rules detected"
      },
      "estimated_tokens": 450,
      "warnings": []
    }
  }
}
```

**Tool: `firewall/apply-plan`** (Professional tier)

```json
{
  "jsonrpc": "2.0",
  "id": "req-fw-apply-001",
  "method": "tools/call",
  "params": {
    "name": "firewall/apply-plan",
    "arguments": {
      "plan_id": "plan-fw-20250115-001",
      "approval_token": "approve-fw-a1b2c3d4"
    }
  }
}

// Response (success)
{
  "jsonrpc": "2.0",
  "id": "req-fw-apply-001",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Plan applied successfully.\n\nJob ID: job-fw-20250115-001\nDevices affected: 2/2 successful\nDuration: 12.4 seconds\n\nAll devices passed post-change health checks."
      }
    ],
    "isError": false,
    "_meta": {
      "correlation_id": "corr-req-fw-apply-001",
      "plan_id": "plan-fw-20250115-001",
      "job_id": "job-fw-20250115-001",
      "status": "completed",
      "total_devices": 2,
      "successful": 2,
      "failed": 0,
      "execution_time_ms": 12400,
      "results": [
        {
          "device_id": "dev-lab-01",
          "status": "success",
          "pre_snapshot_id": "snap-dev-lab-01-20250115-001-pre",
          "post_snapshot_id": "snap-dev-lab-01-20250115-001-post",
          "health_check_before": "healthy",
          "health_check_after": "healthy",
          "changes_applied": ["firewall_rule_added"],
          "execution_time_ms": 5200
        },
        {
          "device_id": "dev-lab-02",
          "status": "success",
          "pre_snapshot_id": "snap-dev-lab-02-20250115-001-pre",
          "post_snapshot_id": "snap-dev-lab-02-20250115-001-post",
          "health_check_before": "healthy",
          "health_check_after": "healthy",
          "changes_applied": ["firewall_rule_added"],
          "execution_time_ms": 7200
        }
      ]
    }
  }
}

// Response (partial failure with rollback)
{
  "jsonrpc": "2.0",
  "id": "req-fw-apply-001",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Plan applied with failures - rollback initiated.\n\nJob ID: job-fw-20250115-001\nDevices affected: 1/2 successful, 1 failed\n\ndev-lab-02 failed post-change health check - automatically rolled back.\ndev-lab-01 changes retained (healthy)."
      }
    ],
    "isError": true,
    "_meta": {
      "correlation_id": "corr-req-fw-apply-001",
      "plan_id": "plan-fw-20250115-001",
      "job_id": "job-fw-20250115-001",
      "status": "partial_failure",
      "total_devices": 2,
      "successful": 1,
      "failed": 1,
      "rolled_back": 1,
      "results": [
        {
          "device_id": "dev-lab-01",
          "status": "success",
          "pre_snapshot_id": "snap-dev-lab-01-20250115-001-pre",
          "post_snapshot_id": "snap-dev-lab-01-20250115-001-post",
          "health_check_before": "healthy",
          "health_check_after": "healthy",
          "changes_applied": ["firewall_rule_added"]
        },
        {
          "device_id": "dev-lab-02",
          "status": "rolled_back",
          "pre_snapshot_id": "snap-dev-lab-02-20250115-001-pre",
          "health_check_before": "healthy",
          "health_check_after": "critical",
          "error": "Post-change health check failed: CPU usage critical (98%)",
          "error_code": "POST_CHANGE_HEALTH_FAILED",
          "rollback_status": "success",
          "rollback_snapshot_id": "snap-dev-lab-02-20250115-001-pre"
        }
      ]
    }
  }
}
```

### Approval Token Format and Validation

**Approval Token Structure**:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
import hmac
import hashlib
import secrets

@dataclass
class ApprovalToken:
    """Approval token for high-risk plan execution."""

    token: str              # "approve-{topic}-{random}"
    plan_id: str            # Associated plan ID
    created_at: datetime    # Token creation time
    expires_at: datetime    # Expiration time (default: 10 minutes)
    signature: str          # HMAC signature to prevent tampering

def generate_approval_token(plan_id: str, secret_key: bytes) -> ApprovalToken:
    """Generate approval token for a plan."""
    # Extract topic from plan_id (e.g., "plan-fw-..." -> "fw")
    topic = plan_id.split("-")[1] if "-" in plan_id else "op"

    # Generate random token component
    random_part = secrets.token_hex(4)  # 8 characters
    token = f"approve-{topic}-{random_part}"

    # Set expiration (10 minutes from now)
    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(minutes=10)

    # Generate HMAC signature
    message = f"{token}:{plan_id}:{created_at.isoformat()}:{expires_at.isoformat()}"
    signature = hmac.new(
        secret_key,
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    return ApprovalToken(
        token=token,
        plan_id=plan_id,
        created_at=created_at,
        expires_at=expires_at,
        signature=signature
    )

def validate_approval_token(
    token: str,
    plan_id: str,
    signature: str,
    expires_at: datetime,
    secret_key: bytes
) -> bool:
    """Validate approval token before plan execution."""
    # Check expiration
    if datetime.utcnow() > expires_at:
        raise ApprovalTokenExpiredError(
            f"Approval token expired at {expires_at.isoformat()}"
        )

    # Verify signature
    message = f"{token}:{plan_id}:{created_at.isoformat()}:{expires_at.isoformat()}"
    expected_signature = hmac.new(
        secret_key,
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        raise ApprovalTokenInvalidError(
            "Approval token signature validation failed"
        )

    return True
```

### Health Check Integration (Pre/Post Change Validation)

**Pre-Change Health Validation** (from Doc 06):

```python
async def validate_device_before_high_risk_change(
    device_id: str,
    correlation_id: str,
    operation: str
) -> dict:
    """Validate device health before high-risk operation.

    Rejects changes if device is unhealthy or unreachable.

    Returns:
        Validation result dict
    """
    # Trigger on-demand health check
    await metrics_collector.execute_health_check(
        device_id=device_id,
        correlation_id=correlation_id,
        trigger="plan_validation"
    )

    # Get latest health check
    health = await health_check_repo.get_latest(device_id)

    # Reject if critical or error
    if health.status in ["critical", "error"]:
        raise DeviceHealthCheckFailedError(
            f"Device {device_id} is {health.status}, cannot execute {operation}",
            error_code="PRE_CHANGE_HEALTH_FAILED",
            device_id=device_id,
            health_status=health.status,
            cpu_usage=health.cpu_usage_percent,
            memory_usage=health.memory_usage_percent
        )

    # Warn if degraded
    warnings = []
    if health.status == "warning":
        warnings.append({
            "level": "warning",
            "message": f"Device {device_id} health is {health.status}",
            "cpu_usage_percent": health.cpu_usage_percent,
            "memory_usage_percent": health.memory_usage_percent,
            "recommendation": "Proceed with caution - device may be under load"
        })

    return {
        "status": "passed" if not warnings else "passed_with_warnings",
        "health_status": health.status,
        "health_check_id": health.id,
        "warnings": warnings
    }
```

**Post-Change Health Validation** (from Doc 06):

```python
async def validate_device_after_high_risk_change(
    device_id: str,
    correlation_id: str,
    pre_change_health: HealthCheck,
    operation: str,
    wait_seconds: int = 65
) -> dict:
    """Validate device health after high-risk operation.

    Triggers rollback if health degraded significantly.

    Returns:
        Validation result dict with rollback recommendation
    """
    # Wait for next scheduled health check to run
    logger.info(
        "Waiting for post-change health check",
        correlation_id=correlation_id,
        device_id=device_id,
        wait_seconds=wait_seconds
    )
    await asyncio.sleep(wait_seconds)

    # Get post-change health
    post_health = await health_check_repo.get_latest(device_id)

    # Check for critical degradation
    critical_issues = []

    # CPU usage increased >30%
    if post_health.cpu_usage_percent > pre_change_health.cpu_usage_percent + 30:
        critical_issues.append({
            "metric": "cpu_usage",
            "before": pre_change_health.cpu_usage_percent,
            "after": post_health.cpu_usage_percent,
            "increase": post_health.cpu_usage_percent - pre_change_health.cpu_usage_percent
        })

    # Memory usage increased >20%
    if post_health.memory_usage_percent > pre_change_health.memory_usage_percent + 20:
        critical_issues.append({
            "metric": "memory_usage",
            "before": pre_change_health.memory_usage_percent,
            "after": post_health.memory_usage_percent,
            "increase": post_health.memory_usage_percent - pre_change_health.memory_usage_percent
        })

    # Device became critical or error
    if post_health.status in ["critical", "error"] and pre_change_health.status not in ["critical", "error"]:
        critical_issues.append({
            "metric": "health_status",
            "before": pre_change_health.status,
            "after": post_health.status
        })

    # Recommend rollback if critical issues detected
    if critical_issues:
        logger.error(
            "Post-change health check failed - critical degradation detected",
            correlation_id=correlation_id,
            device_id=device_id,
            operation=operation,
            issues=critical_issues
        )

        return {
            "status": "failed",
            "health_status": post_health.status,
            "health_check_id": post_health.id,
            "critical_issues": critical_issues,
            "rollback_recommended": True,
            "error_code": "POST_CHANGE_HEALTH_FAILED"
        }

    return {
        "status": "passed",
        "health_status": post_health.status,
        "health_check_id": post_health.id,
        "critical_issues": [],
        "rollback_recommended": False
    }
```

### Snapshot Strategy (Pre/Post Change)

**Snapshot Types** (from Doc 05):

```python
# Snapshot types for high-risk operations
snapshot_types = {
    "pre_change": "Configuration before high-risk change (used for rollback)",
    "post_change": "Configuration after high-risk change (for validation and audit)",
    "rollback": "Configuration restored during rollback operation"
}

async def create_pre_change_snapshot(
    device_id: str,
    plan_id: str,
    correlation_id: str,
    operation: str
) -> Snapshot:
    """Create pre-change snapshot before high-risk operation."""
    # Fetch full device configuration
    config_export = await routeros_client.export_configuration(
        device_id=device_id,
        format="rsc"  # RouterOS script format
    )

    # Create snapshot entity
    snapshot = Snapshot(
        id=f"snap-{device_id}-{plan_id}-pre",
        device_id=device_id,
        timestamp=datetime.utcnow(),
        kind="config_full",
        snapshot_type="pre_change",
        trigger=f"plan_apply:{plan_id}",
        payload_ref=f"s3://backups/{device_id}/{plan_id}-pre.rsc",  # Or local file path
        size_bytes=len(config_export.encode()),
        compressed=False,
        correlation_id=correlation_id,
        estimated_tokens=estimate_snapshot_tokens(len(config_export)),
        metadata={
            "plan_id": plan_id,
            "operation": operation,
            "device_name": device.name,
            "routeros_version": device.routeros_version,
            "purpose": "rollback_source"
        }
    )

    # Store snapshot
    await snapshot_repo.create(snapshot)

    # Store payload to disk/S3
    await storage.write(snapshot.payload_ref, config_export)

    logger.info(
        "Pre-change snapshot created",
        correlation_id=correlation_id,
        device_id=device_id,
        snapshot_id=snapshot.id,
        size_bytes=snapshot.size_bytes
    )

    return snapshot
```

### Rollback Job Implementation

**Automatic Rollback on Health Failure**:

```python
async def execute_rollback(
    device_id: str,
    plan_id: str,
    job_id: str,
    pre_change_snapshot: Snapshot,
    correlation_id: str,
    reason: str
) -> dict:
    """Execute automatic rollback to pre-change snapshot.

    Args:
        device_id: Target device
        plan_id: Plan that triggered the change
        job_id: Job that executed the change
        pre_change_snapshot: Snapshot to restore
        correlation_id: Request correlation ID
        reason: Reason for rollback (e.g., "POST_CHANGE_HEALTH_FAILED")

    Returns:
        Rollback result dict
    """
    logger.warning(
        "Initiating automatic rollback",
        correlation_id=correlation_id,
        device_id=device_id,
        plan_id=plan_id,
        job_id=job_id,
        reason=reason
    )

    # 1. Load pre-change configuration from snapshot
    config_rsc = await storage.read(pre_change_snapshot.payload_ref)

    # 2. Create rollback job
    rollback_job = Job(
        id=f"job-rollback-{job_id}",
        plan_id=plan_id,
        created_at=datetime.utcnow(),
        job_type="rollback",
        device_ids=[device_id],
        status="in_progress",
        correlation_id=correlation_id,
        metadata={
            "original_job_id": job_id,
            "rollback_reason": reason,
            "snapshot_id": pre_change_snapshot.id
        }
    )
    await job_repo.create(rollback_job)

    try:
        # 3. Apply rollback configuration via SSH (RouterOS import)
        await routeros_client.import_configuration(
            device_id=device_id,
            config_rsc=config_rsc,
            mode="replace"  # Replace affected sections only
        )

        # 4. Wait and verify health
        await asyncio.sleep(30)
        post_rollback_health = await health_check_repo.get_latest(device_id)

        # 5. Create rollback snapshot for audit
        rollback_snapshot = await create_snapshot(
            device_id=device_id,
            snapshot_type="rollback",
            trigger=f"rollback:{rollback_job.id}",
            correlation_id=correlation_id
        )

        # 6. Update rollback job status
        rollback_job.status = "completed"
        rollback_job.completed_at = datetime.utcnow()
        rollback_job.result = {
            "status": "success",
            "device_id": device_id,
            "health_after_rollback": post_rollback_health.status,
            "rollback_snapshot_id": rollback_snapshot.id
        }
        await job_repo.update(rollback_job)

        logger.info(
            "Rollback completed successfully",
            correlation_id=correlation_id,
            device_id=device_id,
            rollback_job_id=rollback_job.id,
            health_status=post_rollback_health.status
        )

        return {
            "status": "success",
            "rollback_job_id": rollback_job.id,
            "rollback_snapshot_id": rollback_snapshot.id,
            "health_after_rollback": post_rollback_health.status
        }

    except Exception as e:
        # Rollback failed - critical situation
        logger.critical(
            "Rollback failed - manual intervention required",
            correlation_id=correlation_id,
            device_id=device_id,
            error=str(e)
        )

        rollback_job.status = "failed"
        rollback_job.result = {
            "status": "failed",
            "error": str(e),
            "error_code": "ROLLBACK_FAILED",
            "manual_intervention_required": True
        }
        await job_repo.update(rollback_job)

        return {
            "status": "failed",
            "error": str(e),
            "error_code": "ROLLBACK_FAILED",
            "manual_intervention_required": True
        }
```

### Error Code Mappings for Validation Failures

**High-Risk Operation Error Codes** (extends Doc 19):

| Error Code                      | HTTP Status | Description                                              | Retry?       |
| ------------------------------- | ----------- | -------------------------------------------------------- | ------------ |
| `DEVICE_ENVIRONMENT_RESTRICTED` | 403         | Device in 'prod' environment, operation not allowed      | No           |
| `DEVICE_CAPABILITY_MISSING`     | 403         | Device lacks required capability flag                    | No           |
| `PRE_CHANGE_HEALTH_FAILED`      | 412         | Pre-change health check failed                           | Wait & Retry |
| `POST_CHANGE_HEALTH_FAILED`     | 500         | Post-change health check failed (triggers rollback)      | No           |
| `APPROVAL_TOKEN_EXPIRED`        | 403         | Approval token expired (>10 minutes old)                 | Re-plan      |
| `APPROVAL_TOKEN_INVALID`        | 403         | Approval token signature validation failed               | No           |
| `PLAN_NOT_FOUND`                | 404         | Plan ID not found in database                            | No           |
| `PLAN_ALREADY_APPLIED`          | 409         | Plan has already been executed                           | No           |
| `SNAPSHOT_CREATE_FAILED`        | 500         | Failed to create pre-change snapshot                     | Retry        |
| `ROLLBACK_FAILED`               | 500         | Automatic rollback failed - manual intervention required | No           |

**Example Error Response**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fw-apply-001",
  "error": {
    "code": -32000,
    "message": "PRE_CHANGE_HEALTH_FAILED",
    "data": {
      "error_code": "PRE_CHANGE_HEALTH_FAILED",
      "correlation_id": "corr-req-fw-apply-001",
      "device_id": "dev-lab-02",
      "health_status": "critical",
      "cpu_usage_percent": 98.5,
      "memory_usage_percent": 92.1,
      "message": "Device dev-lab-02 is critical, cannot execute firewall/add-rule",
      "retry": false,
      "recommendation": "Investigate device health issues before retrying"
    }
  }
}
```

---

## Token Budget Warnings for Large Plan Previews

**Token Estimation for Plan Previews**:

```python
def estimate_plan_preview_tokens(plan: Plan, device_count: int) -> int:
    """Estimate token count for plan preview response.

    Args:
        plan: Plan entity
        device_count: Number of devices affected

    Returns:
        Estimated token count
    """
    # Base plan metadata: ~200 tokens
    base_tokens = 200

    # Per-device preview: ~150 tokens (operation details, validation results)
    per_device_tokens = 150

    # Risk assessment and warnings: ~100 tokens
    risk_tokens = 100

    total_tokens = base_tokens + (per_device_tokens * device_count) + risk_tokens

    return total_tokens

async def create_plan_with_token_warning(
    plan_data: dict,
    device_ids: list[str],
    correlation_id: str
) -> dict:
    """Create plan and check token budget.

    Returns plan result with token warning if necessary.
    """
    device_count = len(device_ids)
    estimated_tokens = estimate_plan_preview_tokens(plan_data, device_count)

    # Create plan entity
    plan = Plan(
        id=generate_plan_id(),
        created_at=datetime.utcnow(),
        tool_name=plan_data["tool_name"],
        risk_level=plan_data["risk_level"],
        device_ids=device_ids,
        correlation_id=correlation_id,
        # ... other fields
    )
    await plan_repo.create(plan)

    # Check token budget
    token_warning = None
    if estimated_tokens > 5000:
        token_warning = {
            "warning": "large_plan_preview",
            "estimated_tokens": estimated_tokens,
            "device_count": device_count,
            "recommendation": "Consider splitting into smaller batches or reviewing devices selectively"
        }

    return {
        "plan_id": plan.id,
        "estimated_tokens": estimated_tokens,
        "token_warning": token_warning
    }
```
