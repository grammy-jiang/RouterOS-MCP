# Overall System Architecture & Deployment Topology

## Purpose

Describe the high-level architecture, components, and deployment topology of the MCP service managing multiple RouterOS v7 devices, including how it integrates with RouterOS, OAuth/OIDC, MCP clients, and Cloudflare Tunnel. This document defines the “boxes and arrows” view that other detailed designs build on.

---

## Context, goals, and non-goals

### Context

- The MCP service runs on a Linux server (bare metal or VM) or as a containerized workload in a cluster.
- It manages many RouterOS v7 devices via RouterOS **REST API** as the primary interface, with tightly-scoped SSH/CLI as a fallback for missing functionality.
- It is exposed to AI tools (e.g. ChatGPT) via the **Model Context Protocol (MCP)**, typically behind Cloudflare Tunnel.
- Authentication is via OAuth/OIDC against an external identity provider; authorization is enforced internally via roles, device scopes, tool tiers, and environment/capability flags.

### Goals

- Provide a strongly-typed, RouterOS-aware **MCP API surface** that is safe for AI and human clients.
- Cleanly separate concerns: API/MCP layer, domain/service layer, and infrastructure layer.
- Support the **phase model** (Phase 0–5) for incremental capability rollout and risk management.
- Make key safety mechanisms (environment tags, capability flags, plan/apply, approvals) first-class citizens in the architecture.
- Fit naturally into standard Linux / container deployment models with minimal operational friction.

### Non-goals

- Multi-tenant isolation in a single instance (v1 is single-tenant per deployment).
- Full network management or orchestration beyond RouterOS devices in scope.
- Providing a general "RouterOS-as-a-service" or full CLI abstraction layer; this is focused on carefully curated operations.

---

## Phased Architecture Evolution

The MCP service architecture evolves across phases, with careful staging of complexity and risk:

### Phase 1: Foundation (Tools + STDIO + OS-Level Security)

**Goal:** Universal MCP client compatibility with safe read/write operations

**Architecture Components:**

- **Transport:** STDIO only (stdin/stdout for protocol, stderr for logs)
- **MCP Primitives:** Tools only (40 tools across fundamental/advanced/professional tiers)
- **Security:** OS-level isolation (process sandboxing, file permissions)
- **Deployment:** Single Linux process, systemd service or container
- **Database:** Postgres for devices, plans, audit logs
- **Background Jobs:** APScheduler for health checks and metrics collection

**What's Included:**

- Device registration and lifecycle management
- Read-only fundamental tools (inventory, health, diagnostics)
- Advanced tools for low-risk single-device writes (DNS/NTP, identity, comments)
- Professional tools for multi-device plan/apply workflows
- Phase-1 fallback tools for resource data (device health, configs)
- Audit logging for all writes and sensitive reads

**What's NOT Included:**

- Resources and Prompts (deferred to Phase 2)
- HTTP/SSE transport for MCP (deferred to Phase 2)
- OAuth flows (OIDC token validation only, no OAuth Authorization Code flow)

**Client Compatibility:** 100% of MCP clients (tools-only and full MCP clients)

---

### Phase 2: Enhanced Workflows (Resources + Prompts + HTTP/SSE Transport)

**Goal:** Richer user experience and remote access for capable MCP clients

**Architecture Additions:**

- **MCP Primitives:**
  - **Resources:** 12 resource URIs (device health, configs, fleet summaries)
  - **Prompts:** 8 workflow templates (dns_ntp_rollout, troubleshoot_dns_ntp, etc.)
- **Transport:**
  - **HTTP/SSE:** MCP protocol over HTTP (in addition to STDIO)
  - **OIDC Middleware:** Bearer token validation for HTTP endpoints
- **Infrastructure:**
  - **Resource Cache:** In-memory cache with TTL for device health/config
  - **Background Refresh:** Periodic job to update resource cache (every 60s)
  - **Prompt Loader:** YAML parser + Jinja2 template renderer
- **API Layer:**
  - `resources/list` handler (discovery)
  - `resources/read` handler (read from cache)
  - `prompts/list` handler (enumerate available prompts)
  - `prompts/get` handler (render template with arguments)

**What's Included:**

- Efficient resource access for capable clients (Claude, VS Code)
- Workflow guidance via prompts (DNS/NTP rollout, troubleshooting)
- HTTP/SSE transport for remote MCP clients
- Single-user OIDC bearer token authentication
- Backward compatibility: STDIO transport and Phase-1 fallback tools still available

**What's NOT Included:**

- Multi-user OAuth Authorization Code flow (deferred to Phase 5)
- Resource subscriptions and CAPsMAN tools (moved to Phase 2.1)
- Advanced writes for firewall filter rules, static routes, wireless RF (deferred to Phase 4+)

**Client Compatibility:**

- **Full MCP clients** (40%): Get resources + prompts + tools
- **Tools-only clients** (60%): Get tools only (including fallbacks)

---

### Phase 2.1: Resource Management & Real-Time Updates (Extending Phase 2)

**Goal:** Extend Phase 2 capabilities with resource snapshots, real-time subscriptions, and wireless visibility enhancements

**Architecture Additions:**

- **MCP Features:**
  - **Resource Subscriptions:** SSE subscriptions for real-time device health updates
  - **Configuration Snapshots:** Read-only snapshot creation/retrieval for backup and audit
  - **CAPsMAN Visibility:** Read-only tools for CAPsMAN controller-managed wireless
  - **User Guidance:** Contextual hints in wireless outputs for CAPsMAN deployments
- **Infrastructure:**
  - **Snapshot Storage:** Database table for configuration snapshots
  - **Scheduled Jobs:** APScheduler for automatic snapshot creation
  - **Subscription Manager:** Track active SSE subscriptions per device
  - **CAPsMAN Queries:** SSH fallback queries for `/caps-man` endpoints
- **Response Enhancements:**
  - Automatic CAPsMAN detection in wireless tools
  - Conditional guidance text added to responses

**What's Included:**

- Resource subscriptions via SSE (real-time health monitoring)
- Configuration snapshots (read-only, scheduled or on-demand)
- CAPsMAN controller visibility (read-only tools)
- User guidance in wireless outputs (informational only)
- All operations remain read-only; no configuration changes
- Backward compatibility: all Phase 2 features still available

**What's NOT Included:**

- Write operations (Phase 3 COMPLETED: single-device writes with plan/apply framework)
- Multi-user support (deferred to Phase 5)
- CAPsMAN controller configuration changes (write operations)
- Persistent subscription state across restarts
- Advanced filtering or transformation of subscribed data

**Client Compatibility:**

- Full MCP clients benefit most (40%): SSE subscriptions available
- Tools-only clients (60%): Snapshot tools and CAPsMAN tools still available as regular tool calls

---

### Phase 3: Admin Interface & Single-Device Writes (Plan/Apply) ✅ COMPLETED

**Goal:** Enable single-device advanced writes with mandatory plan/apply guardrails and admin tooling for lab/staging environments

**Architecture Additions:**

- **MCP Tools:**
  - **System:** System identity/comments
  - **Interface:** Interface comments and descriptions
  - **DNS/NTP:** DNS/NTP server configuration (lab/staging only)
  - **IP:** Secondary IP addresses on non-management interfaces
  - **Firewall (limited):** MCP-owned address-lists (create/update/delete)
  - **DHCP (limited):** DHCP server enable/disable and basic pool config (lab/staging only)
  - **Bridge (limited):** Bridge port membership on non-critical ports (lab/staging only)
- **Safety Mechanisms:**
  - Pre-checks for environment tags (lab/staging enforcement)
  - Device capability flags (`allow_professional_workflows`, topic-specific flags)
  - Risk classification per topic
  - Approval token generation and validation
  - Audit logs for all plan/apply operations
- **Admin UI/CLI:**
  - Device onboarding CLI
  - Plan review and approval UI (browser-based or CLI)
  - Audit log viewer

**What's Included:**

- Single-device write operations with plan/apply framework
- System identity, interface descriptions, DNS/NTP configuration
- Secondary IPs on non-management interfaces
- MCP-owned address-lists (limited firewall operations)
- Optional lab-only DHCP and bridge configuration
- Mandatory approvals for all write operations
- Lab/staging environment enforcement
- Admin UI/CLI for device and plan management

**What's NOT Included:**

- Firewall filter rule writes (deferred to Phase 4)
- Static route management (deferred to Phase 4)
- Wireless RF/SSID writes (deferred to Phase 4)
- Multi-device coordinated workflows (deferred to Phase 4)
- Diagnostics tools (ping/traceroute/bandwidth-test; deferred to Phase 4)
- SSH key authentication and client compatibility modes (deferred to Phase 4)
- CAPsMAN controller writes (out of scope)

**Client Compatibility:** 100% (STDIO or HTTP/SSE, client choice)

---

### Phase 4: Multi-Device Coordination & Diagnostics

**Goal:** Support coordinated multi-device workflows, diagnostics, and SSH key authentication

**Architecture Additions:**

- **Multi-Device Workflows:**
  - Batch plan/apply across multiple devices
  - Staged rollout with health checks between batches
  - Halt on failure with automatic rollback support
- **Diagnostics Tools:**
  - `tool/ping` (ICMP ping with streaming results)
  - `tool/traceroute` (network traceroute with streaming results)
  - `tool/bandwidth-test` (speed test with streaming results)
- **SSH Enhancements:**
  - SSH key-based authentication (in addition to password)
  - Client compatibility modes for legacy RouterOS versions
- **Automation:**
  - Automated approval tokens for trusted environments
  - Workflow orchestration for complex multi-device operations

**What's Included:**

- Coordinated multi-device plan/apply
- Long-running diagnostics with JSON-RPC streaming
- SSH key auth and client compatibility
- Automated approvals for trusted workflows

**What's NOT Included:**

- Multi-user RBAC (deferred to Phase 5)
- Approval workflow engine with separate approver roles (deferred to Phase 5)

**Client Compatibility:** 100% (STDIO or HTTP/SSE, client choice)

---

### Phase 5: Multi-User RBAC & Governance

### Phase 5: Multi-User RBAC & Governance

**Goal:** Support multi-user access with role-based permissions, approval workflows, and enterprise governance

**Architecture Additions:**

- **Security:**
  - **OAuth Authorization Code + PKCE:** Full OAuth flow for browser-based clients
  - **Multi-user RBAC:** Role-based access control for users and devices
  - **Per-user device scopes:** Users can only access devices they own or are granted access to
- **Approval Workflow Engine:**
  - Separate approver roles (initiator vs. approver)
  - Approval queue UI
  - Approval notifications (email, Slack, etc.)
  - Approval delegation and escalation
- **Governance & Observability:**
  - Per-user audit trails
  - Compliance reporting
  - Policy enforcement (e.g., require approval for production devices)
  - Resource quotas and rate limiting per user
- **Deployment:**
  - Token endpoint for OAuth access tokens
  - Load balancer for distributed HTTP/SSE instances
  - Shared session store (Redis) for multi-instance deployments

**What's Included:**

- Multi-user OAuth login flow
- Role-based access control
- Per-user device scopes
- Approval workflow engine with separate approver roles
- Enterprise governance and compliance features

**What's Unchanged:**

- STDIO and HTTP/SSE transports still supported
- Single-user mode still available (backward compatibility)
- All Phase 1-4 features remain

**Client Compatibility:** 100% (STDIO or HTTP/SSE, client choice)

---

### Architectural Invariants (Across All Phases)

These principles remain constant regardless of phase:

1. **3-Layer Architecture:** API → Domain → Infrastructure separation never violated
2. **Zero Trust for Clients:** All safety controls enforced server-side, never client-side
3. **Single Responsibility:** MCP server manages RouterOS only (no scope creep)
4. **Stateless API Layer:** Horizontal scaling always possible (state in DB/cache)
5. **Audit Everything:** All writes and sensitive reads logged with correlation ID
6. **Environment/Capability Flags:** Always enforced, even for admin users
7. **Per-Device Rate Limiting:** RouterOS clients never overload devices

---

## Component overview (API/MCP layer, domain/services, infrastructure)

At a high level, the system is split into three layers:

```
┌─────────────────────────────────────────────────────────────────┐
│                      EXTERNAL SYSTEMS                            │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│ MCP Clients  │ RouterOS     │ OIDC Provider│ Cloudflare Tunnel  │
│ (ChatGPT,    │ Devices      │ (Azure AD,   │                    │
│  Claude,     │ (v7 REST API)│  Okta)       │                    │
│  VS Code)    │              │              │                    │
└──────┬───────┴──────────────┴──────┬───────┴─────────┬──────────┘
       │ STDIO (Phase 1-5)           │ HTTPS           │ HTTPS
       │ HTTP/SSE (Phase 2-5)        │                 │
       ▼                              ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MCP SERVER (Linux Host/Container)             │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │                     API & MCP LAYER                         │ │
│ │  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐       │ │
│ │  │ MCP Protocol │  │  HTTP API   │  │ Auth Handler │       │ │
│ │  │ (STDIO/HTTP) │  │ (Admin/UI)  │  │ (OIDC Token) │       │ │
│ │  │              │  │             │  │              │       │ │
│ │  │ - Tools      │  │ - Devices   │  │ - Validate   │       │ │
│ │  │ - Resources  │  │ - Plans     │  │ - Map roles  │       │ │
│ │  │ - Prompts    │  │ - Approvals │  │ - Scope      │       │ │
│ │  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘       │ │
│ │         │                 │                 │               │ │
│ │         └─────────────────┼─────────────────┘               │ │
│ └───────────────────────────┼─────────────────────────────────┘ │
│                             ▼                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │                   DOMAIN & SERVICE LAYER                    │ │
│ │  ┌──────────────┐ ┌─────────────┐ ┌──────────────┐         │ │
│ │  │   Device     │ │  RouterOS   │ │  Plan/Job    │         │ │
│ │  │   Registry   │ │  Operations │ │ Orchestration│         │ │
│ │  │              │ │             │ │              │         │ │
│ │  │ - Manage     │ │ - DNS/NTP   │ │ - Plan gen   │         │ │
│ │  │   devices    │ │ - System    │ │ - Multi-dev  │         │ │
│ │  │ - Env/caps   │ │ - Interface │ │ - Rollback   │         │ │
│ │  │ - Credentials│ │ - Firewall  │ │              │         │ │
│ │  └──────┬───────┘ └──────┬──────┘ └──────┬───────┘         │ │
│ │         │                │                │                 │ │
│ │  ┌──────┴────────────────┴────────────────┴──────┐          │ │
│ │  │          Audit & Policy Service               │          │ │
│ │  │  - Environment/capability checks              │          │ │
│ │  │  - Audit event logging                        │          │ │
│ │  └───────────────────────┬───────────────────────┘          │ │
│ └──────────────────────────┼──────────────────────────────────┘ │
│                            ▼                                    │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │                   INFRASTRUCTURE LAYER                      │ │
│ │  ┌──────────────┐ ┌─────────────┐ ┌──────────────┐         │ │
│ │  │  RouterOS    │ │ Persistence │ │ Background   │         │ │
│ │  │  REST/SSH    │ │  (Database) │ │  Jobs        │         │ │
│ │  │   Clients    │ │             │ │              │         │ │
│ │  │              │ │ - Devices   │ │ - Health     │         │ │
│ │  │ - Connection │ │ - Plans     │ │   checks     │         │ │
│ │  │   pooling    │ │ - Audit log │ │ - Metrics    │         │ │
│ │  │ - Retries    │ │ - Snapshots │ │ - Cache      │         │ │
│ │  │ - Rate limit │ │ - Encrypted │ │   refresh    │         │ │
│ │  │              │ │   credentials│ │              │         │ │
│ │  └──────────────┘ └─────────────┘ └──────────────┘         │ │
│ │                                                              │ │
│ │  ┌──────────────────────────────────────────────┐           │ │
│ │  │        Observability Stack                   │           │ │
│ │  │  - Prometheus metrics                        │           │ │
│ │  │  - Structured logging (stderr)               │           │ │
│ │  │  - OpenTelemetry traces                      │           │ │
│ │  └──────────────────────────────────────────────┘           │ │
│ └─────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────── ┘
        │                            │                     │
        ▼                            ▼                     ▼
  ┌──────────┐               ┌──────────┐         ┌──────────────┐
  │ Postgres │               │Prometheus│         │ Log Collector│
  │ Database │               │  Metrics │         │   (stderr)   │
  └──────────┘               └──────────┘         └──────────────┘

Legend:
  ──────▶  Data flow
  ───────  Layer boundary
  ┌─────┐  Component
```

**Request Flow Example (numbered steps):**

1. **MCP Client** sends `tools/call` request with `tool="dns/get-status"` via STDIO
2. **API Layer** receives request, validates OIDC token, checks user role
3. **API Layer** dispatches to **Domain Layer** `dns_service.get_status(device_id)`
4. **Domain Layer** checks **Audit Service** for environment/capability flags
5. **Domain Layer** calls **Infrastructure Layer** RouterOS REST client
6. **RouterOS Client** makes HTTP GET to `https://router-01/rest/ip/dns`
7. **RouterOS** returns DNS configuration JSON
8. **Infrastructure Layer** maps RouterOS response to domain model
9. **Domain Layer** writes audit event via **Audit Service**
10. **API Layer** sends JSON-RPC response via stdout to **MCP Client**

---

1. **API & MCP layer**

   - **MCP server / HTTP API**:
     - Exposes MCP tools and possibly a REST/JSON HTTP API for human-oriented UIs.
     - Handles request authentication (OIDC tokens) and maps identities to internal user roles and device scopes.
     - Implements request validation, rate limiting, and basic per-tool authorization before invoking domain services.
     - **MCP Protocol Lifecycle**:
       1. **Initialize**: Client sends `initialize` request with client info and capabilities
          - Server responds with server info, protocol version, MCP primitives supported
          - Example response:
            ```json
            {
              "protocolVersion": "2024-11-05",
              "serverInfo": {
                "name": "RouterOS-MCP",
                "version": "1.0.0"
              },
              "capabilities": {
                "tools": { "listChanged": true },
                "resources": { "subscribe": true, "listChanged": true },
                "prompts": { "listChanged": true }
              }
            }
            ```
       2. **Capability Negotiation**: Server adapts based on client capabilities
          - **Tools-only clients** (ChatGPT, Mistral): Server exposes all 40 tools (including fallbacks)
          - **Full MCP clients** (Claude, VS Code): Server exposes tools + resources + prompts
       3. **Operation**: Client makes `tools/call`, `resources/read`, `prompts/get` requests
       4. **Shutdown**: Client sends `shutdown` notification, server closes STDIO streams cleanly
   - **Admin/UI endpoints (optional)**:
     - Web console or HTTP endpoints for human operators to manage devices, review plans, approve changes, and inspect audit logs.

2. **Domain & service layer**

   - **Device registry service**:
     - Manages devices, environments (`lab`/`staging`/`prod`), capability flags, and associated credentials.
     - Implements security checks around device scope and environment-based gating.
   - **RouterOS operation services** (per topic or group of topics):
     - System, interface, IP, DNS, NTP, DHCP, routing, logs, diagnostics, etc.
     - Encapsulate validation, idempotency, and mapping between domain objects and RouterOS API calls.
   - **Plan & job orchestration service**:
     - Implements plan/apply, multi-device workflows, and long-running tasks (Phase 3-5).
     - Coordinates pre-checks, validations, rollouts with backoff, and rollbacks.
   - **Audit & policy service**:
     - Applies cross-cutting policies (e.g., environment/capability constraints).
     - Writes structured audit events for sensitive reads and all writes.

3. **Infrastructure layer**
   - **RouterOS REST clients** (and limited SSH client):
     - Performs actual HTTP/REST calls (and, where required, whitelisted SSH commands) to RouterOS devices.
     - Handles connection pooling, timeouts, retries, and error mapping.
   - **Persistence**:
     - Relational or document database for devices, credentials (encrypted), plans, jobs, audit logs, configuration snapshots.
     - Optional time-series or metrics store for counters and performance data.
   - **Messaging / background processing**:
     - Job queue or task runner for scheduled health checks, metrics collection, and long-running workflows.
     - **Background Job Scheduler Architecture:**
       - **Technology:** APScheduler (Advanced Python Scheduler) for Phase 1
         - Lightweight, no external dependencies (in-process scheduling)
         - Cron-like and interval-based job triggers
         - Job persistence via DB (resume jobs after restart)
       - **Job Types:**
         1. **Health Checks:** Per-device health polling (every 60s with jitter)
         2. **Metrics Collection:** System resource metrics (every 30s)
         3. **Resource Cache Refresh:** Update device health/config cache (every 60s)
         4. **Plan Execution:** Long-running multi-device apply workflows (async jobs)
       - **Concurrency:** asyncio-based (non-blocking I/O for RouterOS calls)
       - **Persistence:** Job state and schedule stored in Postgres (survive restarts)
       - **Scaling:** Each MCP instance runs its own scheduler; DB-based locking prevents duplicate execution
       - **Alternative (Phase 4+):** Celery with Redis/RabbitMQ for distributed task queue (if needed for > 100 devices)
   - **Observability stack**:
     - Logging, metrics, and tracing sinks (e.g., OpenTelemetry exporters, log collectors, dashboards).

### MCP Transport Layer Architecture

The MCP service uses different transports across phases, balancing universal client compatibility with deployment flexibility:

**Phase 1-2: STDIO Transport (Universal Client Compatibility)**

- **Primary transport**: STDIO (stdin/stdout) for MCP JSON-RPC protocol
- **Why STDIO**: Ensures compatibility with 100% of MCP clients:
  - Tools-only clients: ChatGPT, Mistral, Zed, Continue.dev
  - Full MCP clients: Claude Desktop, VS Code Copilot
- **Transport isolation**:
  - `stdin`: Receive MCP JSON-RPC requests from client
  - `stdout`: Send MCP JSON-RPC responses (tools, resources, prompts)
  - `stderr`: Application logs, errors, diagnostics (NEVER protocol messages)
- **Logging discipline**: All application logs, debug output, and error messages MUST go to stderr to avoid corrupting stdout protocol stream
- **Process model**: Single process handling both MCP protocol (STDIO) and optional HTTP admin API (separate port)

**Admin/UI HTTP API (Coexists with STDIO)**

- **Separate concern**: HTTP API for human operators to manage devices, review plans, generate approval tokens
- **Port binding**: Listens on a different port (e.g., :8080) than any MCP transport
- **Not MCP protocol**: This is standard REST/JSON for UIs, not MCP JSON-RPC
- **Security**: Protected by OIDC, typically behind Cloudflare Tunnel

**Phase 2-5: HTTP Transport for MCP Protocol (Remote/Enterprise)**

- **Evolution**: MCP protocol over HTTP/SSE (in addition to STDIO)
- **When used**: Remote clients, cloud deployments, OAuth flows
- **Phase 1 compatibility**: STDIO remains supported even after HTTP is added
- **Implementation note**: FastMCP supports both STDIO and HTTP transports; Phase 1 uses STDIO exclusively, Phase 2+ adds HTTP/SSE

**Transport Selection Logic**

```
Phase 1 deployment:
  MCP protocol: STDIO (universal client support)
  Admin API: HTTP on :8080 (human operators)
  Logging: stderr only

Phase 2+ deployment:
  MCP protocol: STDIO OR HTTP/SSE (client choice)
  Admin API: HTTP on :8080
  Logging: stderr (STDIO mode) or structured JSON logs (HTTP mode)
```

**Critical STDIO best practices:**

- Never use `print()` for debugging (use `logging.error()` to stderr)
- Never write to stdout except via MCP protocol handler
- Test STDIO transport by piping sample requests: `echo '{"jsonrpc":"2.0",...}' | ./mcp-server`
- Monitor stderr separately from stdout in production

---

### MCP Primitive Architectural Placement

MCP exposes three primitives (Tools, Resources, Prompts), each with different architectural placement and lifecycle:

**1. Tools (Model-Controlled, Request-Driven Operations)**

- **Placement**: API layer (MCP server) dispatches to Domain layer (services)
- **Lifecycle**: Invoked on-demand by LLM client via `tools/call` JSON-RPC request
- **Flow**:
  1. Client sends `tools/call` request via STDIO
  2. API layer validates OIDC token, authorization, tool parameters
  3. API layer dispatches to domain service (e.g., `dns_service.get_status()`)
  4. Domain service calls Infrastructure layer (RouterOS REST client)
  5. Domain service returns result to API layer
  6. API layer sends JSON-RPC response via stdout
- **State**: Stateless; each tool invocation is independent
- **Examples**: `dns/get-status`, `config/plan-dns-ntp-rollout`, `tool/ping`

**2. Resources (Application-Controlled, Read-Only Context)**

- **Placement**: Infrastructure layer (cached data) + API layer (resource handler)
- **Lifecycle**:
  - **Discovery**: Client lists available resources via `resources/list`
  - **Access**: Client reads resource content via `resources/read` with URI
  - **Refresh**: MCP server updates resource cache periodically (background job)
- **Flow**:
  1. Background job periodically fetches device health via RouterOS REST
  2. Infrastructure layer caches result with TTL (e.g., 60 seconds)
  3. Client sends `resources/read` with URI `device://router-01/health`
  4. API layer reads from cache, returns resource content
  5. No RouterOS call needed (cache hit)
- **Caching strategy**:
  - Device health: 60-second TTL (refreshed by background job)
  - Device config snapshots: 5-minute TTL (expensive to fetch)
  - Fleet summaries: 2-minute TTL (aggregated data)
- **Token budget**: Resources include `metadata.estimated_tokens` to help LLM manage context
- **Examples**: `device://{id}/health`, `fleet://{env}/summary`, `plan://{id}`

**3. Prompts (User-Controlled, Workflow Templates)**

- **Placement**: API layer (YAML files loaded at startup, rendered on-demand)
- **Lifecycle**:
  1. Server startup: Load all YAML files from `prompts/` directory
  2. Client requests `prompts/list` → Server returns available prompts
  3. Client invokes `prompts/get` with prompt name and arguments
  4. API layer renders Jinja2 template with arguments
  5. API layer returns rendered prompt text to client
- **Flow**:
  1. User selects `dns_ntp_rollout` prompt in Claude Desktop
  2. Client sends `prompts/get` with `name=dns_ntp_rollout, args={environment: "prod"}`
  3. API layer loads `prompts/dns_ntp_rollout.yaml`
  4. API layer renders template with environment-specific content
  5. Client receives multi-step workflow guide
- **State**: Immutable templates; only arguments vary per invocation
- **Examples**: `dns_ntp_rollout`, `troubleshoot_dns_ntp`, `device_onboarding`

**Architectural Separation Benefits**

- **Tools**: Dynamic, request-driven, full CRUD capabilities
- **Resources**: Cached, efficient, read-only, optimized for LLM context windows
- **Prompts**: Static templates, user-controlled, provide consistency across workflows

**Phase-1 Fallback Pattern**

For clients that don't support Resources (ChatGPT, tools-only clients), Phase-1 fallback tools provide equivalent functionality:

- `device/get-health-data` tool → `device://{id}/health` resource
- `fleet/get-summary` tool → `fleet://{env}/summary` resource
- Each fallback tool includes `resource_uri` hint for migration to Phase 2

---

## Host platform assumptions (Linux, systemd, container vs bare metal)

- The service targets **Linux** as the primary host OS.
- Two primary deployment modes are supported:
  - As a **systemd-managed service** on a VM or bare-metal host.
  - As a **containerized service** (Docker, Kubernetes, etc.).
- In both cases:
  - Configuration is primarily via environment variables and optional config files.
  - A single binary/process may serve both MCP and HTTP endpoints; horizontal scaling is achieved by running multiple instances.
  - Secrets (master key, DB passwords, OIDC client secrets) are injected via environment or external secret managers, not stored in plain text on disk.

Operationally:

- There should be a clear **service unit** definition (for systemd) or a deployment manifest (for k8s) that configures ports, logging, and resource limits.
- The service must not assume local state other than configuration and transient caches; persistent state should be in external storage (DB, metrics store).

---

## Deployment topology (single region, HA, network layout)

### Single-region baseline

- Deploy at least one application instance in the management region (e.g., a data center or cloud region).
- RouterOS devices may be distributed across sites, as long as the management server can reach their management IPs over TCP (REST, optionally SSH).
- A **single-region, multi-instance** pattern is recommended for availability:
  - 2–3 stateless app instances behind a load balancer / reverse proxy (or behind Cloudflare Tunnel).

### Network layout

- MCP instances run in a **management network** with outbound access to:
  - RouterOS device REST/SSH ports.
  - The OIDC provider.
  - The database and observability backends.
  - Cloudflare Tunnel connector (if used).
- Inbound access from the public Internet is **not** direct:
  - Public-facing clients (ChatGPT / browsers) connect via Cloudflare Tunnel to the MCP service.
  - The origin (MCP) listens on a private interface/port accessible only to the Tunnel connector or internal load balancer.

### High availability

- Stateless app instances can be scaled horizontally; database and storage must provide at least basic HA (e.g., managed DB with replicas).
- Health checks and readiness probes are used so the orchestrator/systemd can restart unhealthy instances.
- In case of partial outages (e.g., DB read-only mode), the service should degrade gracefully (e.g., allow reads, deny writes).

---

## External integrations (RouterOS, OAuth/OIDC, Cloudflare Tunnel, logging/metrics backends)

### RouterOS

- The service connects to RouterOS devices via:
  - **REST API** endpoints (`/rest/...`) over HTTP(S).
  - Optional **SSH** for whitelisted commands on devices where REST is insufficient.
- Connectivity assumptions:
  - Management IP addresses or hostnames are reachable from the MCP network.
  - Network ACLs permit the relevant ports (e.g., 80/443/8728/8729 or custom REST/SSH ports).

### OAuth/OIDC

- The MCP service acts as an **OIDC client**:
  - Uses Authorization Code + PKCE flow for browser-based admin/UI.
  - Accepts bearer tokens (access tokens or ID tokens) for MCP/HTTP API calls.
- The service:
  - Validates tokens (signature, issuer, audience, expiry).
  - Extracts `sub`, `email`, and `groups`/`roles` claims.
  - Maps these claims to internal `user_role` and `device_scope` using a static configuration mapping.

### Cloudflare Tunnel

- Cloudflare Tunnel terminates TLS on the edge and forwards traffic to the MCP origin.
- The integration points:
  - Tunnel runs on the same host or same network as the MCP instances.
  - Origin is locked down so only the Tunnel (and internal admin access) can reach it.
- Cloudflare Access (or equivalent) can front the MCP UI, acting as an OIDC provider or SSO gate.

### Logging & metrics backends

- The MCP service emits:
  - Structured logs (JSON) to stdout or a log collector.
  - Metrics via an HTTP endpoint (e.g., Prometheus) or push-based exporter.
  - Traces via OpenTelemetry exporters.
- Backends may be:
  - Self-hosted (ELK/EFK, Prometheus/Grafana, Jaeger/Tempo).
  - Managed cloud services.

---

## Cloudflare Tunnel and OAuth/OIDC integration points in the request path

The typical request path from a user or AI client:

1. User/AI interacts with a client (ChatGPT UI or custom UI) that uses MCP.
2. MCP client connects to a public URL fronted by **Cloudflare Tunnel**.
3. Cloudflare forwards the request to the MCP origin (load balancer or service instance).
4. The MCP service:
   - Validates the attached OAuth/OIDC token (if present) or initiates an OIDC flow (for browser-based UI).
   - Maps identity to `user_role` and `device_scope`.
   - Applies environment and capability checks, then dispatches to the appropriate domain service.
5. Domain service calls RouterOS via REST (or SSH where needed) and returns structured results, which are sent back through the same path.

In this pipeline:

- Cloudflare Tunnel primarily handles secure connectivity and optional access policies.
- OAuth/OIDC handles identity; internal authorization logic enforces roles/scopes/tier/environment.

### Security Zones & Trust Boundaries

The architecture enforces multiple security zones with explicit trust boundaries:

```
┌───────────────────────────────────────────────────────────────────┐
│                      UNTRUSTED ZONE                                │
│  - Public Internet                                                 │
│  - MCP Clients (AI assistants, browsers)                           │
│  - Assumption: Potentially malicious, can generate arbitrary       │
│    tool calls, ignore system prompts                               │
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            │ HTTPS (TLS-encrypted)
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│                       EDGE ZONE                                    │
│  Cloudflare Tunnel                                                 │
│  - TLS termination                                                 │
│  - DDoS protection                                                 │
│  - Optional Cloudflare Access (additional OIDC gate)               │
│  - Trust: Cloudflare-managed, no application logic                 │
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            │ Forwarded to private origin
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│                    MANAGEMENT ZONE                                 │
│  MCP Server (API Layer)                                            │
│  - OIDC token validation (signature, issuer, expiry)               │
│  - Role mapping (groups → read_only / ops_rw / admin)              │
│  - Device scope enforcement                                        │
│  - Environment/capability checks                                   │
│  - Approval token validation (for professional tools)              │
│  - ALL SAFETY CONTROLS ENFORCED HERE (zero trust for clients)      │
│  Trust: Application-enforced, cryptographic validation             │
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            │ Internal API calls (authenticated)
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│                     INTERNAL ZONE                                  │
│  - Database (Postgres)                                             │
│  - Job queue (background tasks)                                    │
│  - Secrets store (encrypted RouterOS credentials)                  │
│  - Metrics/logging backends                                        │
│  Trust: Fully trusted, no external access, credentials encrypted   │
│         at rest                                                    │
└───────────────────────────┬───────────────────────────────────────┘
                            │
                            │ RouterOS REST API calls (HTTPS)
                            │ with per-device credentials
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│                      DEVICE ZONE                                   │
│  RouterOS Devices (v7)                                             │
│  - REST API endpoints (HTTPS on device-specific ports)             │
│  - SSH endpoints (fallback, whitelisted commands only)             │
│  - Per-device credentials (NOT shared across devices)              │
│  Trust: Managed devices, authenticated with credentials, network-  │
│         isolated from untrusted zone                               │
└───────────────────────────────────────────────────────────────────┘
```

**Trust Boundary Enforcement:**

1. **Untrusted → Edge**: TLS encryption, DDoS mitigation, no application trust
2. **Edge → Management**: Cloudflare forwards to private origin, MCP validates OIDC token
3. **Management → Internal**: Authenticated API calls, audit logging, no user-controlled input to DB
4. **Internal → Device**: Per-device credentials, rate-limited API calls, retries/backoff
5. **Cross-zone breaches**: If edge or management zones compromised:
   - Internal zone: Database credentials separate, master encryption key in secret manager
   - Device zone: Per-device credentials limit blast radius (compromise of MCP doesn't auto-compromise all devices)

**Security Principle:** Each zone trusts the previous zone only after explicit validation. **No security decisions are delegated to clients** (MCP clients are always untrusted, even with valid OIDC tokens).

---

## Scaling, multi-device and multi-tenant considerations

### Scaling

- Horizontal scaling by running multiple stateless app instances sharing:
  - A database.
  - A secrets store.
  - Metrics/logging backends.
- RouterOS calls are rate-limited **per device**; the RouterOS client library centralizes per-device concurrency and QPS limits.
- Background jobs (health checks, collectors, rollouts) are distributed via a job queue or database-backed scheduler to avoid duplication.

### Multi-device workflows

- Multi-device workflows (Phase 3-5) are implemented via plan/apply:
  - Plan generation computes changes across many devices and writes a `Plan` entity to the DB.
  - Apply executes the plan in stages (e.g., batches) with health checks and potential rollback.
- The orchestration service must consider:
  - Device environments (`lab`/`staging`/`prod`).
  - Capability flags per device.
  - Backoff and partial failure handling.

### Multi-tenant

- v1 is explicitly **single-tenant** per deployment.
- Multi-tenant support is out of scope for the entire 1.x series. If needed in the future, v2 will require additional isolation mechanisms (namespace, tenant IDs, per-tenant config).

---

## Failure modes, resilience, and backoff strategies

**Key failure modes**

- RouterOS device is unreachable (network issues, device down).
- RouterOS REST or SSH returns errors (auth failure, timeouts, rate limiting).
- Database or metrics storage is unavailable or degraded.
- OIDC provider or Cloudflare Tunnel is unavailable or misconfigured.
- Internal bugs or overload in the MCP service.

**Resilience strategies**

- Per-device retry and backoff policies for RouterOS calls, with circuit breakers/default cool-down when devices misbehave.
- Separation of read and write paths:
  - On partial outages, keep read-only operations working whenever possible; fail closed on writes.
- Robust error mapping:
  - Clear, structured error codes for MCP clients (including AI), so they can react appropriately.
- Timeouts and cancellation:
  - All outbound calls have conservative timeouts; long-running workflows use async jobs with progress tracking.

**Backoff strategies**

- Health checks and metrics collection:
  - When a device repeatedly fails, increase the interval between attempts, up to a configurable maximum.
- Multi-device apply:
  - Use staged rollout; pause further batches if error rates exceed thresholds.
  - Optionally auto-rollback for affected devices when post-change checks fail.
