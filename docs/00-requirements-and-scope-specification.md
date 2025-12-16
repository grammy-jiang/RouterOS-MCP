# Requirements & Scope Specification

## Purpose

Define exactly what this RouterOS MCP service is supposed to do and not do: target users, use cases, out-of-scope operations (e.g. no full firewall mangling in v1), non-functional requirements (latency, scale, reliability). This document is the authoritative reference for scope decisions for the 1.x line of the project.

---

## Problem statement & goals

Operating fleets of MikroTik RouterOS v7 devices is operationally complex and error-prone. Human operators must log into each device individually, remember RouterOS syntax, and carefully stage changes to avoid outages. AI assistants (e.g. ChatGPT) can help with reasoning, but raw access to RouterOS via SSH or REST is too dangerous without strict guardrails. We need a middle layer that:

- Exposes **safe, well-typed, audited operations** over RouterOS to AI tools and human operators.
- Centralizes device metadata, health, and configuration visibility.
- Enforces **least privilege**, **environment separation** (lab/staging/prod), and **strong approvals** for high-risk changes.

**High-level goals**

- Provide a **RouterOS-aware MCP service** that AI clients can call safely.
- Support device lifecycle: registration, metadata, credential rotation, decommissioning.
- Offer strong **read-only visibility** and **lightweight diagnostics** as the default posture.
- Introduce **write capabilities gradually**, starting from clearly low-risk operations.
- Make all high-risk and multi-device operations **plan/apply + human-approved**, with clear blast-radius controls.

**MCP Protocol Integration**

This service leverages the three core MCP primitives to provide safe, ergonomic RouterOS management:

- **Tools** (Model-controlled, dynamic queries and operations):

  - Fundamental tier: Read-only queries (`device/list-devices`, `dns/get-status`; network diagnostics such as ping/traceroute are deferred to Phase 4)
  - Advanced tier: Single-device low-risk writes (`dns/update-servers`, `system/set-identity`)
  - Professional tier: Multi-device orchestration (`config/plan-dns-ntp-rollout`, `config/apply-dns-ntp-rollout`)
  - Target: 40 tools in Phase 1, organized by category (device, dns, ntp, firewall, logs, system, tool, config, audit)

- **Resources** (Application-controlled, read-only context):

  - Device-specific: `device://{id}/health`, `device://{id}/config`, `device://{id}/interfaces`
  - Fleet-wide: `fleet://{env}/summary`, `fleet://{env}/health-overview`
  - Operational: `plan://{id}`, `audit://events`, `snapshot://{id}`
  - Introduced in Phase 2 for clients supporting resource URIs (Claude Desktop, VS Code Copilot)
  - Phase-1 fallback tools provided for universal client compatibility (ChatGPT, tools-only clients)

- **Prompts** (User-controlled, workflow templates):
  - Troubleshooting: `troubleshoot_dns_ntp`, `troubleshoot_device`
  - Operational workflows: `dns_ntp_rollout`, `fleet_health_review`, `address_list_sync`
  - Onboarding: `device_onboarding`
  - Security: `security_audit`, `comprehensive_device_review`
  - Introduced in Phase 2 alongside resources

**Phased rollout strategy (revised):**

- Phase 1 (COMPLETED): Tools + Resources + Prompts + STDIO transport + OS-level security
  - Full local MCP client support (Claude Desktop, VS Code)
  - 39 tools, 12+ resource URIs, 8 prompts
  - STDIO transport fully functional
- Phase 2 (CURRENT): HTTP/SSE transport completion + read-only feature expansion
  - Complete HTTP/SSE transport implementation (currently scaffold only)
  - OAuth/OIDC integration for remote access
  - Additional read-only tools (wireless, DHCP, bridge visibility)
  - Resource caching and performance optimization
- Phase 3: Admin UI/CLI, single-device advanced writes, Advanced Expert Workflows (lab/staging). Diagnostics and SSH key auth postponed.
- Phase 4: Coordinated multi-device workflows, automated approval tokens, diagnostics (ping/traceroute/bandwidth-test) and SSH key auth/client compatibility.
- Phase 5: Multi-user RBAC, approval workflow engine, per-user device scopes, enterprise governance & observability.

This approach ensures local deployments work fully in Phase 1, while Phase 2 enables remote/enterprise deployments and expands read-only visibility.

---

## Out-of-scope & explicit non-goals

**Out-of-scope for the 1.x line**

The following areas are explicitly out of scope for MCP **write** operations in the entire 1.x series:

- RouterOS **user management**, authentication settings, certificates, VPN configuration, and remote access methods.
- Global firewall rewrites, default chain (INPUT/FORWARD/OUTPUT) rule editing or reordering, free-form firewall/NAT rule manipulation.
- NAT configuration changes, except potentially very narrow, template-based lab scenarios in Phase 4-5.
- Bridge VLAN filtering and STP core parameters on production devices.
- Automatic RouterOS upgrades, system resets, or factory defaults via MCP.
- Multi-tenant operation within a single MCP deployment (1.x is single-tenant per deployment).

Read-only visibility into many of these areas (e.g., firewall, routing, wireless) is **in scope**, but writes are not.

---

## Primary use cases & user stories

**Target users**

- Network / infrastructure engineers responsible for fleets of RouterOS devices.
- SRE / NOC engineers needing centralized diagnostics and health views.
- AI operators using tools like ChatGPT to reason about and assist with network tasks, via MCP.

**Representative user stories**

_00 – Requirements & Scope_

- As an operator, I want to register a new RouterOS device with its management address, environment (`lab` / `staging` / `prod`), and credentials, so that I can manage it centrally via MCP.
- As an engineer, I want to ask an AI assistant for the current health and interface status of a router, without risking any configuration change.
- As an engineer, I want to safely rename devices and add or update interface descriptions across the fleet, without impacting traffic or reachability.
- As an operator, I want to roll out DNS/NTP changes to a group of lab routers via a plan/preview workflow, and have MCP automatically roll them back if post-change checks fail.
- As a security engineer, I want to see an audit log that records all sensitive reads and all write operations, including who initiated them, which devices were affected, and what was changed.

**Workflow example: DNS/NTP rollout**

When an operator uses the `dns_ntp_rollout` prompt to update DNS servers fleet-wide:

1. **Discovery**: Prompt invokes `device/list-devices` with `environment=lab` → returns 5 devices
2. **Planning**: Operator calls `config/plan-dns-ntp-rollout` with device IDs and new DNS servers → creates `plan_id=plan-abc123`
3. **Review**: Operator (or AI assistant) calls `plan/get-details` with `plan_id=plan-abc123` → shows per-device change summary
4. **Approval**: For production, operator generates approval token via UI → obtains `approval_token` valid for 5 minutes
5. **Execution**: Operator calls `config/apply-dns-ntp-rollout` with `plan_id` and `approval_token` → MCP applies changes sequentially
6. **Verification**: MCP automatically runs `dns/get-status` on each device → verifies DNS servers match expected configuration
7. **Rollback** (if needed): If verification fails, MCP automatically calls `config/rollback-plan` with `plan_id` → restores previous DNS configuration

**Success metrics for this workflow:**

- Time from plan creation to completion: < 5 minutes for 10 devices
- Automatic rollback success rate: > 99%
- Zero manual intervention for successful rollouts
- Complete audit trail with correlation ID linking all steps

**Workflow example: Troubleshooting DNS/NTP issues**

When an engineer uses the `troubleshoot_dns_ntp` prompt for a device with DNS problems:

1. **Phase 1 - Current State**: Prompt guides AI to call `dns/get-status` + `ntp/get-status` → identifies no DNS servers configured
2. **Phase 2 - Connectivity**: (Deferred to Phase 4) AI would call `tool/ping` with `address=1.1.1.1` → verifies upstream connectivity works
3. **Phase 4 - Firewall**: AI calls `firewall/list-filter-rules` → finds no blocking rules
4. **Phase 4 - Logs**: AI calls `logs/get-recent` with `topics=["system", "error"]` → finds "DNS server list empty" warning
5. **Phase 5 - Resolution**: AI recommends `dns/update-servers` with Cloudflare DNS → operator approves, DNS configured
6. **Verification**: AI re-runs `dns/get-status` → confirms DNS servers now configured, cache active

**Success metrics for this workflow:**

- Issue identified within 5 diagnostic steps: 90% of cases
- Time to resolution: < 10 minutes for common issues
- Clear root cause documented in audit log
- Zero configuration damage during diagnostics (all reads are safe)

_01 – Architecture & Deployment_

- As a platform engineer, I want the MCP service to be deployable as either a container or a systemd service on Linux, and be horizontally scalable by adding instances, without large code changes.
- As a network architect, I want MCP to expose its entrypoint only via Cloudflare Tunnel, and for only the Tunnel and internal management networks to reach the MCP origin, so that the attack surface is minimized.
- As an operations manager, I want to run multiple MCP instances in a single region behind a load balancer with health checks, so that the failure of any one instance does not make the management plane unavailable.

_02 – Security & Access Control_

- As a security owner, I want to map groups or roles from our existing OIDC identity provider (such as Azure AD or Okta) to the internal MCP roles `read_only`, `ops_rw`, and `admin`, so that I can precisely control who can do what.
- As an operations lead, I want to configure device scopes by device or device group so that a given operator can only invoke MCP tools on specific sites or tagged devices, rather than seeing every device.
- As a security engineer, I want all write operations and sensitive reads to require a valid OIDC token, and for high-risk professional tools to also require an additional short-lived human approval token, so that even a misbehaving AI client cannot bypass server-side safety controls.
- As a secrets manager, I want RouterOS credentials and OIDC client secrets to be stored only in encrypted form, and I want to be able to rotate the master encryption key during a maintenance window without manually re-entering every password.

_03 – RouterOS Integration & Platform Constraints (REST & SSH)_

- As a network engineer, I want MCP to automatically handle timeouts, retries, and rate limiting when calling RouterOS `/rest` APIs, so that a temporarily slow device or brief network issue does not cause MCP to overload that device.
- As an engineer, I want MCP to always read the current device configuration via REST before performing write operations, then compute the minimal change set and do a read‑modify‑write, to minimize the risk of overwriting manual changes.
- As a security engineer, I want SSH/CLI to be used only in the rare cases where REST cannot support a necessary operation, and I want all SSH commands to come from whitelisted templates, with every executed command and its result captured in audit logs.
- As a test engineer, I want to be able to regress test common RouterOS `/rest` error cases, pagination behavior, and version differences in a lab environment, and encode the “gotchas” into the RouterOS client library instead of scattering them across business logic.

_04 – MCP Tools Interface & JSON Schemas_

- As an AI integration engineer, I want all MCP tools to share a standard request/response envelope (`tool`, `params`, `success`, `error`, `result`) and have clear JSON Schemas, so that clients can validate calls and generate appropriate prompts for different tools.
- As an SRE, I want to safely allow `read_only` users to call all fundamental tools (read-only diagnostics deferred), such as `system.get_overview` and `interface.list_interfaces`, without worrying that any configuration might be changed.
- As a network engineer, I want to use advanced tools on a single device to safely change low-risk configuration items (such as system identity, interface comments, and DNS/NTP in lab environments), and I want each execution to clearly indicate whether the state actually changed.
- As a senior operations engineer, I want all multi-device DNS/NTP rollouts or shared address-list synchronizations to always start with a plan tool that creates an immutable plan object, and only allow an admin to execute the apply tool by explicitly referencing the `plan_id` after review.

**Tool count targets by phase and tier**

| Phase   | Tier         | Tool Count | Examples                                                                                                                                                                                                                                              | Client Support                        |
| ------- | ------------ | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| Phase 1 | Fundamental  | ~14 tools  | `device/list-devices`, `dns/get-status`, `ntp/get-status`, `interface/list-interfaces`, `firewall/list-filter-rules`, `logs/get-recent`, `system/get-overview`, `system/get-clock`, `device/get-health-data`, `fleet/get-summary`, `audit/get-events` | All MCP clients (100%)                |
| Phase 1 | Advanced     | ~10 tools  | `dns/update-servers`, `ntp/update-servers`, `dns/flush-cache`, `system/set-identity`, `interface/update-comment`, `device/get-config-snapshot`, `snapshot/get-content`                                                                                | All MCP clients (100%)                |
| Phase 1 | Professional | ~8 tools   | `config/plan-dns-ntp-rollout`, `config/apply-dns-ntp-rollout`, `config/rollback-plan`, `plan/get-details`, `addresslist/plan-sync`, `addresslist/apply-sync`                                                                                          | All MCP clients (100%)                |
| Phase 1 | Fallbacks    | ~6 tools   | Resource fallback tools for universal compatibility (`device/get-health-data`, `device/get-config-snapshot`, `fleet/get-summary`, `plan/get-details`, `audit/get-events`, `snapshot/get-content`)                                                     | All MCP clients (100%)                |
| Phase 1 | Resources    | 12 URIs    | `device://{id}/health`, `device://{id}/config`, `fleet://{env}/summary`, `plan://{id}`, `audit://events` (COMPLETED)                                                                                                                                  | All MCP clients with resource support |
| Phase 1 | Prompts      | 8 prompts  | `dns_ntp_rollout`, `troubleshoot_dns_ntp`, `troubleshoot_device`, `fleet_health_review`, `device_onboarding`, `address_list_sync`, `comprehensive_device_review`, `security_audit` (COMPLETED)                                                        | All MCP clients with prompt support   |
| Phase 2 | Transport    | HTTP/SSE   | Complete HTTP/SSE transport implementation with OAuth/OIDC (scaffold exists, not functional)                                                                                                                                                          | Remote/enterprise deployments         |
| Phase 2 | Read Tools   | +6 tools   | `wireless/get-interfaces`, `wireless/get-clients`, `dhcp/get-server-status`, `dhcp/get-leases`, `bridge/list-bridges`, `bridge/list-ports`                                                                                                            | All MCP clients                       |

**Phase 2 feature set (planned/mandatory):**

- Complete HTTP/SSE transport with OAuth/OIDC authentication and resource subscriptions (SSE)
- Add 6 read-only visibility tools (wireless, DHCP, bridge)
- Extend resources with wireless, DHCP, bridge URIs and caching with TTL + invalidation
- Keep diagnostics (ping/traceroute/bandwidth-test) deferred to Phase 4
- Keep SSH key auth and client compatibility modes deferred to Phase 4

**Total Phase 1 tool count: ~39 tools** (14 fundamental + 10 advanced + 8 professional + 6 fallbacks + 1 admin onboarding tool; diagnostics deferred to Phase 4)

**Design principles for tool count:**

- **Fewer, composable tools** over many specialized tools (avoids overwhelming LLM context windows)
- **Clear tier boundaries** so authorization rules are unambiguous
- **Phase-1 fallbacks** ensure tools-only clients can access Phase-2 resource data
- **Intent-based descriptions** help LLMs select the right tool (e.g., "Use when user asks about DNS configuration" vs just "Returns DNS status")

_05 – Domain Model, Persistence & Jobs_

- As a platform engineer, I want the `Device` entity to record each device’s environment (`lab` / `staging` / `prod`), capability flags (such as `allow_advanced_writes`, `allow_professional_workflows`), and tags (such as site and role), so that authorization and orchestration can use this information consistently.
- As an SRE, I want `HealthCheck` and `Snapshot` entities to record the results of each health check, key metrics, and pre/post-change configuration snapshots, so that I can quickly compare state before and after a problem occurs.
- As a change manager, I want all cross-device configuration changes to be driven by Plan and Job entities, where the Plan provides a reviewable change list and the Job is responsible for executing and retrying those changes, leaving a clear outcome record.
- As a compliance officer, I want the `AuditEvent` table to make it easy to query, for any time period, which users ran which MCP tools on which devices, what the results were, and whether any rollbacks occurred.

_06 – System Information & Metrics Collection_

- As an SRE, I want MCP to periodically pull metrics from `/system/resource`, `/system/health`, `/interface`, and `/ip/address` endpoints, normalize them into metric samples labeled with `device_id` and other tags, so that I can compare the health of multiple devices on a single graph.
- As a performance engineer, I want to obtain CPU utilization, interface bandwidth usage, and route counts from MCP’s metrics interface—without stress-testing the devices directly—and use this data for capacity planning.
- As a network engineer, I want to query MCP for a device’s recent health trends over the last N minutes instead of repeatedly running diagnostics directly on the device, so that I reduce the ad-hoc load on that device.

_07 – Device Control & High-Risk Operations Safeguards_

- As a security architect, I want operations such as NAT changes, user management, VPN/remote access configuration, and production bridge VLAN/STP changes to be explicitly marked as “no write support” in 1.x, so that even if code exists, these writes remain disabled by default in production.
- As a senior operations engineer, I want high-risk production changes (such as deploying firewall templates, adding/removing static routes on production routers, or toggling admin state on certain interfaces) to be available only through professional-tier tools, always via a plan/apply workflow with human approval and staged rollout.
- As a change approver, I want a UI where I can see all devices and per-device change summaries for a high-risk plan, then generate a short-lived approval token in my own name to authorize the apply step for that specific `plan_id`.

_08 – Observability, Logging, Metrics & Diagnostics_

- As an SRE, I want every MCP tool invocation to include standard fields in logs such as `correlation_id`, `tool_name`, `user_sub`, and `device_id`, so that when something goes wrong I can correlate API logs, RouterOS call logs, and audit logs with a single query.
- As an operations lead, I want dashboards that show which tools have high error rates, which devices exhibit abnormal RouterOS REST latency, and whether job queues are backing up, so I can quickly determine whether an issue is in MCP itself, a particular tool, or specific devices.
- As a frontline on-call engineer, I want RouterOS call failures to produce logs with clear diagnostic information (device ID, REST path, RouterOS error, number of retries), and I want MCP diagnostic tools to let me inspect recent failures for a device as a starting point for troubleshooting.

_09 – Operations, Deployment, Self-Update & Rollback_

- As a platform operations engineer, I want MCP configuration to be managed via environment variables and standardized configuration files, with different default safety policies based on `MCP_ENV=lab|staging|prod`, so that multi-environment deployments are consistent and manageable.
- As a CI/CD owner, I want a pipeline that builds code, runs unit tests, builds container images, applies DB migrations, and then progressively deploys MCP through lab → staging → prod environments, with the ability to quickly roll back to the last known-good version if issues arise.
- As a database administrator, I want CI/CD to automatically take backups before destructive schema changes, and, when necessary, to restore the MCP database to the pre-migration state—even at the cost of some downtime—to avoid irrecoverable data corruption.
- As an on-call SRE, I want runbooks that clearly describe how MCP should fail safely when IdP is down, Cloudflare Tunnel is misconfigured, or the database is read-only, and how to use the break-glass path to restore basic read-only management capabilities.
- As an operator, I want to be able to onboard devices and enter RouterOS credentials via a secured admin HTTP API in the early phases, so that we can start using MCP safely without waiting for a full UI.
- As an operator, I want a simple CLI and web-based admin console in Phase 2-4 that wrap the same admin API, so that day-to-day device registration and credential rotation are easy to perform without hand-crafting HTTP requests.
- As a network engineer in a large environment, I want an optional automated onboarding path (for example, a RouterOS bootstrap script that creates MCP service accounts and calls the MCP registration API), so that we can bring many devices under MCP management with minimal manual steps while retaining control and auditability.

_10 – Testing, Validation, Sandbox Strategy & Safety Nets_

- As a developer, I want to use pytest and pytest-asyncio to unit test domain logic (such as plan generation, authorization decisions, and RouterOS mapping) locally without needing real RouterOS devices.
- As a test engineer, I want a CI process that automatically brings up lab RouterOS instances for end-to-end tests (including OIDC flows, MCP API calls, and actual RouterOS responses) on each change, to ensure new versions do not break core functionality.
- As an operations lead, I want any new advanced or professional capabilities to be enabled in production only after they have passed a predefined set of smoke and regression tests in lab and staging, with the tested MCP and RouterOS versions recorded in a compatibility matrix.
- As a change initiator, I want to run high-risk write tools in dry-run or plan-only mode to get a preview, then apply them to staging or canary devices in small batches and monitor metrics and health checks, only rolling out more broadly once I see no issues.

_11 / 12 / 13 – Implementation Architecture, Dev Environment & Coding Standards_

- As a backend developer, I want the MCP codebase to follow a consistent module layout (`routeros_mcp/api`, `routeros_mcp/domain`, `routeros_mcp/infra`, etc.), and for all team members to add new modules according to the same structure, so that the code is easy to navigate and understand.
- As a developer, I want to use `uv` to quickly create virtual environments and install runtime and development dependencies via `uv pip install -e .[dev]`, and then run `uv run tox` to execute tests, linting, type checking, and coverage checks in a single command, reducing local setup friction.
- As a code reviewer, I want all new code to follow unified Python coding standards: fully typed functions and classes, linted with `ruff`, formatted with `black`, RouterOS calls implemented asynchronously, and no secrets logged, so that I can focus review time on business logic rather than style inconsistencies.

---

## Non-functional requirements (performance, availability, scale)

**Scale & performance assumptions**

- v1 target fleet size: **10–100 devices**.
- Health-check frequency: default **~60 seconds per device with jitter**, configurable per deployment.
- Per-device concurrency: by default at most **2–3 concurrent REST calls** per device.
- If a deployment exceeds **~200–300 devices**, architecture and scheduling strategies must be revisited.

These values are defaults, not hard-coded; they must be configurable per deployment, with the option to use stricter limits for low-powered devices.

**Availability & reliability**

- The MCP service should be designed for **high availability** within a single region (no single-process assumptions).
- External dependencies (IdP, Cloudflare Tunnel, DB, secrets store) must be monitored; their outages should fail safely (e.g. deny writes, maintain read-only where possible).
- A documented **break-glass path** must exist for operators to regain access if IdP or Cloudflare are unavailable.

**Latency expectations**

- For typical read-only operations (inventory, health, metrics), end-to-end latency via MCP should be on the order of **hundreds of milliseconds to a few seconds**, depending on RouterOS response and network.
- For plan/apply workflows, users must expect multi-second to multi-minute flows (especially for multi-device rollouts).

---

## Assumptions & constraints (v7-only, REST-first, SSH as last resort)

**Key assumptions**

- All managed devices run **RouterOS v7**, with a documented minimum minor (e.g. ≥ 7.xx LTS).
- The RouterOS **REST API is the primary interface**; SSH/CLI is used only where REST lacks essential functionality.
- The service is **single-tenant per deployment**: one organization/operator per instance.
- MCP treats all clients (including AI/LLM-based clients) as **untrusted**: all safety is enforced server-side, not via prompts.

**Constraints**

- No feature may assume direct database access by clients; all interactions must go through well-defined MCP tools.
- No MCP tool may assume well-behaved clients; request validation and guardrails are mandatory.
- High-risk topics (firewall, NAT, routing policy, DHCP, bridge, interface admin, wireless RF) **must** respect environment tags and device capability flags, even for admin users.

**Non-negotiable security requirements (MCP-specific)**

The following security requirements are **mandatory** for MCP integration, enforced server-side, and must never be bypassed:

1. **Server-side validation only**: All safety controls (authorization, environment checks, device capability flags, approval tokens) are enforced on the MCP server. Client-side prompts and AI instructions are **untrusted** and provide zero security guarantees.

2. **Zero trust for LLM clients**: MCP clients (including AI assistants) are assumed to be:

   - Potentially compromised or malicious
   - Capable of ignoring system prompts
   - Able to generate arbitrary tool calls
   - Unable to enforce security policies

   Therefore, **every** tool invocation must be validated server-side as if it came from an adversary.

3. **Approval token requirements**: High-risk professional tools (plan/apply workflows on production devices) require:

   - Valid OIDC token proving user identity
   - Short-lived (5-minute TTL) approval token generated by human via secure UI
   - Approval token bound to specific `plan_id` (cannot be reused for different plans)
   - Both tokens validated on **every** apply operation, with no caching

4. **Environment and capability enforcement**:

   - Production write operations (even low-risk ones like DNS/NTP) require device `allow_advanced_writes=true` flag
   - Professional workflows require device `allow_professional_workflows=true` flag
   - Environment tags (`lab`/`staging`/`prod`) must be immutable after device registration (prevents accidental environment escalation)
   - Device scope restrictions (user can only see/operate on assigned devices) enforced at every tool invocation

5. **Audit requirements**:

   - Every tool invocation logged with: `correlation_id`, `user_sub`, `device_id`, `tool_name`, `params`, `result`, `timestamp`
   - Sensitive reads (credentials, full configs) logged with `sensitive=true` flag
   - Audit log writes are **non-blocking** but failures trigger alerts (audit log integrity is critical for compliance)

6. **Blast radius controls**:

   - Multi-device operations (professional tools) must:
     - Show per-device change preview before execution
     - Execute sequentially (not parallel) to limit simultaneous failures
     - Halt on first device failure (unless explicitly configured otherwise)
     - Support automatic rollback when post-change verification fails
   - No tool may accept unbounded device lists (enforce maximum batch size, e.g., 50 devices per plan)

7. **Secrets management**:
   - RouterOS credentials encrypted at rest with master key
   - OIDC client secrets never logged, even in debug mode
   - No secrets in tool responses (mask passwords, API keys in returned configs)
   - Credential rotation supported without service restart

**Rationale**: MCP exposes RouterOS management to AI systems. Unlike human operators, LLMs cannot be trusted to "read carefully" or "use best judgment." All safety must be cryptographically and programmatically enforced, with no reliance on prompt engineering.

---

## Success criteria

**Success criteria v1**

- Operators can onboard 10–100 RouterOS v7 devices, assign environment tags and capability flags, and manage credentials centrally.
- AI/human users can:
  - Safely query inventory, health, and diagnostics without any configuration writes.
  - Perform clearly low-risk writes in production (e.g. identity and interface comments) without causing outages.
- Run plan/apply workflows on **lab/staging** devices for DNS/NTP and similar changes, with automatic rollback when checks fail.
- All writes and sensitive reads are captured in audit logs with user, device, tool, and plan IDs (where applicable).
- The system can be safely deployed behind Cloudflare Tunnel, integrated with an OIDC provider, and operated by an on-call team using documented runbooks.

**MCP protocol compliance & operational metrics**

Beyond functional success, v1 must demonstrate MCP best practice compliance:

- **Tool discovery**: All 40 tools discoverable via MCP protocol `tools/list` with intent-based descriptions (e.g., "Use when: user asks about DNS configuration")
- **Resource efficiency**:
  - Tool responses < 100KB for 95th percentile (to fit in LLM context windows)
  - Large data (logs, full configs) surfaced via resources or paginated results
  - Token budget estimation for all large responses (warn if >80% of 400KB MCP limit)
- **Client compatibility**:
  - Phase 1 (tools-only) works in ChatGPT, Claude, Mistral, Zed, Continue.dev (tools-only clients)
  - Phase 2 (resources + prompts) works in Claude Desktop, VS Code Copilot (full MCP clients)
  - Phase 1 fallback tools provide 100% feature parity for tools-only clients
- **Latency SLOs**:
  - Tool invocation overhead: < 100ms (MCP protocol processing, not RouterOS REST)
  - Read-only tools (fundamental tier): < 2 seconds end-to-end (95th percentile)
  - Write tools (advanced tier): < 5 seconds for single-device operations
  - Professional tools (multi-device): < 30 seconds per device
- **Versioning & deprecation**:
  - MCP server version exposed in `initialize` response (semantic versioning)
  - Tool deprecation policy: 6-month notice before removal, with replacement tool documented
  - Backward compatibility: No breaking changes to tool schemas within 1.x line
- **Observability**:
  - Prometheus metrics for all tools: `mcp_tool_calls_total{tool_name, status}`, `mcp_tool_duration_seconds{tool_name}`
  - Request correlation: Every tool invocation includes `correlation_id` in logs, linking MCP request → domain logic → RouterOS REST calls → audit log
  - Health check: MCP server exposes `/health` endpoint for load balancer checks
- **Testing coverage**:
  - Unit tests: at least 95% code coverage for core domain modules and at least 85% coverage for all other modules
  - Integration tests: All 40 tools tested with mock RouterOS responses
  - LLM-in-the-loop tests: Automated tests with real LLM clients invoking tools
  - E2E tests: Full workflows (device registration → DNS rollout → verification) tested in lab environment

**Post-v1 success indicators (3 months after deployment)**

- Median time to onboard a new device: < 5 minutes (via `device_onboarding` prompt)
- DNS/NTP rollout completion rate: > 95% without manual intervention
- False positive rate for automatic rollbacks: < 5% (rollback only when truly necessary)
- AI assistant queries successfully answered without human escalation: > 80%
- Security incidents due to unauthorized MCP access: 0 (OIDC + approval tokens + audit logs)
