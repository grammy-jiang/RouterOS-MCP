# Device Control & High-Risk Operations Safeguards

## Purpose

Define which high-risk operations exist on RouterOS (e.g., reboot, upgrade, reset configuration, interface shutdown on WAN, major routing and firewall changes), how and whether they are exposed via MCP, and what guardrails, approvals, and rollbacks are required to keep usage safe. This document serves as the “safety bible” for adding or changing MCP tools that can impact device reachability or production traffic.

---

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
    - Reference a `plan_id`.  
    - Record the approval token and approver identity.  
    - Include before/after snapshots where supported.  
  - Audit logs should make it clear:
    - Who initiated a change and who approved it.  
    - Which devices were affected and what the outcomes were.  
    - Whether any rollbacks were automatically or manually triggered.

- **Review and continuous improvement**:
  - Periodic reviews of:
    - High-risk tool usage patterns.  
    - Incidents or near-misses linked to MCP operations.  
  - Resulting in updates to:
    - Safeguard policies.  
    - Default capability flags.  
    - Which tools are enabled by default in which environments.

