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
- Providing a general “RouterOS-as-a-service” or full CLI abstraction layer; this is focused on carefully curated operations.

---

## Component overview (API/MCP layer, domain/services, infrastructure)

At a high level, the system is split into three layers:

1. **API & MCP layer**
   - **MCP server / HTTP API**:  
     - Exposes MCP tools and possibly a REST/JSON HTTP API for human-oriented UIs.  
     - Handles request authentication (OIDC tokens) and maps identities to internal user roles and device scopes.  
     - Implements request validation, rate limiting, and basic per-tool authorization before invoking domain services.
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
     - Implements plan/apply, multi-device workflows, and long-running tasks (Phase 4–5).  
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
   - **Observability stack**:  
     - Logging, metrics, and tracing sinks (e.g., OpenTelemetry exporters, log collectors, dashboards).

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

- Multi-device workflows (Phase 4–5) are implemented via plan/apply:  
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

