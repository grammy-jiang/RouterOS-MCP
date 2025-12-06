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
- As an SRE, I want to safely allow `read_only` users to call all fundamental tools (read-only and diagnostics), such as `system.get_overview`, `interface.list_interfaces`, and `tool.ping`, without worrying that any configuration might be changed.  
- As a network engineer, I want to use advanced tools on a single device to safely change low-risk configuration items (such as system identity, interface comments, and DNS/NTP in lab environments), and I want each execution to clearly indicate whether the state actually changed.  
- As a senior operations engineer, I want all multi-device DNS/NTP rollouts or shared address-list synchronizations to always start with a plan tool that creates an immutable plan object, and only allow an admin to execute the apply tool by explicitly referencing the `plan_id` after review.

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
