# Architecture Overview

## System Design

Built on **[FastMCP SDK](https://github.com/modelcontextprotocol/python-sdk)** with clean separation of concerns:

- **MCP Layer** – Protocol integration (STDIO, HTTP/SSE transports), tool/resource/prompt registration via FastMCP decorators
- **Domain Layer** – Business logic organized by capability area (device, system, interface, IP, DNS/NTP, firewall, DHCP, bridge, wireless, routing, diagnostics)
- **Infrastructure Layer** – RouterOS REST client (httpx) and SSH fallback (asyncssh), SQLAlchemy 2.x ORM, observability stack (structlog, Prometheus, OpenTelemetry)

### Key Design Principles

- **Server-side safety first** – All authorization logic, tool restrictions, and approval workflows enforced server-side. Clients (including AI) are untrusted.
- **Single-tenant per deployment** – Multi-device management within one admin context; Phase 5 adds OAuth/OIDC for multi-user RBAC
- **Environment-aware** – Lab/staging/production modes with per-environment tool restrictions and safety guardrails
- **Test-driven development** – 85%+ overall coverage, 95%+ for core domain services; comprehensive E2E testing for tool workflows
- **Domain-driven architecture** – Tools → domain services → infrastructure clients; never call RouterOS directly from MCP tools
- **Plan/apply approval framework** – All writes use immutable change plans with HMAC-signed approval tokens and automatic rollback

### Module Organization

```
routeros_mcp/
├── config.py              # Pydantic Settings with priority: defaults → YAML/env → CLI
├── cli.py                 # Argument parsing and config file loading
├── main.py                # Application startup, logging setup, server initialization
├── domain/                # Business logic layer
│   ├── models.py          # SQLAlchemy ORM models (Device, Job, Plan, AuditEvent, etc.)
│   └── services/          # Core services (device, dns_ntp, firewall, health, interface, ip, routing, system, diagnostics, job, plan)
├── infra/                 # Infrastructure layer
│   ├── db/                # SQLAlchemy session management
│   ├── observability/     # Logging (structlog), metrics (Prometheus), tracing (OpenTelemetry)
│   └── routeros/          # REST client (httpx) and SSH client (asyncssh) for RouterOS devices
├── mcp/                   # MCP protocol implementation
│   ├── server.py          # FastMCP server, tool/resource/prompt registration
│   ├── protocol/          # JSON-RPC protocol handling
│   └── transport/         # stdio and HTTP/SSE transports
├── mcp_tools/             # MCP tool implementations (34 tools across categories)
├── mcp_resources/         # MCP resource providers (device, fleet, plan, audit)
└── mcp_prompts/           # Jinja2 prompt templates (8 prompts)
```

### Tool Organization

**66 Tools** organized by risk tier and capability area:

**Fundamental (Read-Only, Safe)**
- **Platform** (3) – echo, service/device health checks
- **Device** (2) – list devices, check connectivity  
- **System** (3) – info, packages, clock (read-only)
- **Interface** (3) – list, status, statistics
- **IP** (3) – addresses, ARP table, secondary IPs (read-only)
- **DNS/NTP** (4) – status, cache, configuration (read-only)
- **Routing** (4) – routes, summaries, protocol status
- **DHCP** (3) – server status, lease tracking
- **Bridge** (3) – topology, ports, VLANs
- **Wireless** (4) – interfaces, clients, CAPsMAN status
- **Firewall & Logs** (5) – filter rules, NAT, address-lists, logs (read-only)
- **Diagnostics** (3) – ping, traceroute, bandwidth test

**Advanced (Single-Device Writes, Lab/Staging Only)**
- System identity, DNS/NTP servers, secondary IPs, firewall address-lists, DHCP pools, bridge ports, wireless SSIDs/RF (write operations on individual devices)

**Professional (Multi-Device Orchestration, Approval Required)**
- Fleet-wide DNS/NTP rollouts, coordinated address-list sync, staged multi-device changes (require plan/apply + HMAC-signed approval)

See [**MCP Tools Catalog**](docs/04-mcp-tools-interface-and-json-schema-specification.md) for complete tool list, schemas, and endpoint mappings.

### Security Model

#### Current Security Model

- **STDIO Transport** (Claude Desktop) – OS-enforced process isolation; no network exposure; user's filesystem ACLs control database access
- **Implicit Admin Role** – Single OS user with full tool access; multi-user RBAC planned for Phase 5
- **Encrypted Credentials** – RouterOS device credentials encrypted at rest using Fernet; encryption key managed via environment variables
- **Audit Logging** – All tool calls logged with timestamp and device context

#### Phase 5: OAuth 2.1 / OIDC Multi-User RBAC (Planned)

- **HTTP/SSE Transport** – OAuth 2.1/OIDC required (Azure AD, Okta, Auth0)
- **Per-user device scopes** – Users can be restricted to specific devices and tool tiers
- **RBAC tiers** – Read-only users, ops_rw users (advanced writes), admin users (professional workflows)
- **Approval workflows** – Mandatory approval tokens for professional tier operations

#### Safety Framework for Configuration Changes

All write operations (Advanced/Professional tier) follow a 7-step plan/apply pattern:

1. **Plan Creation** – Tool generates immutable plan document with pre/post state, change summary, and blast radius
2. **Plan Persistence** – Plan stored in database for audit trail and later approval
3. **Plan Review** – Human reviews plan via MCP resource (`plan://{id}`) or admin CLI (`routeros-mcp plan show`)
4. **Approval Token** – CLI generates HMAC-SHA256 signed token (15-minute expiry) with plan ID and user
5. **Plan Execution** – Tool verifies token signature and applies plan atomically
6. **Health Validation** – Automatic post-apply device health check (connectivity, DNS, NTP status)
7. **Automatic Rollback** – If health checks fail, reverts device configuration to pre-plan state

See [**Security & Access Control**](docs/02-security-oauth-integration-and-access-control.md) for threat model, credential management, and OAuth setup guides ([Azure AD](docs/21-oauth-setup-azure-ad.md), [Okta](docs/22-oauth-setup-okta.md), [Auth0](docs/23-oauth-setup-auth0.md)).

### MCP Interface

#### 66 Tools

All tools expose RouterOS capabilities as first-class MCP operations. See [**Tool Tiers**](#tool-organization) above for risk classification. Complete schemas and endpoint mappings in [**Tools Interface Specification**](docs/04-mcp-tools-interface-and-json-schema-specification.md).

#### 12+ Resources

Read-only contextual data providers (MCP resource URIs):
- **Device Resources** – `device://{device_id}/overview` (system metrics), `device://{device_id}/health` (real-time status, subscribable via SSE), `device://{device_id}/config` (current configuration)
- **Fleet Resources** – `fleet://health-summary` (aggregated health across all devices), `fleet://devices-by-environment` (devices grouped by lab/staging/prod)
- **Plan Resources** – `plan://{plan_id}/details` (change plan with pre/post state and approval status), `plan://{plan_id}/history` (execution history and rollback info)
- **Audit Resources** – `audit://events/recent` (timestamped operations log), `audit://events/by-device` (audit trail filtered by device)

See [**Resources & Prompts Design**](docs/15-mcp-resources-and-prompts-design.md) for full URIs and streaming/subscription details.

#### 8 Prompts

Jinja2-based workflow templates for common operational tasks:
- **Onboarding** – `device-onboarding` (new device registration, validation, credential verification)
- **Troubleshooting** – `troubleshoot-device` (multi-step diagnostics for connectivity/DNS/NTP), `troubleshoot-dns-ntp` (DNS/NTP-specific remediation)
- **Operational Workflows** – `dns-ntp-rollout` (step-by-step multi-device rollout), `fleet-health-review` (aggregated health analysis and alerting), `address-list-sync` (synchronized firewall address-list updates)
- **Security & Compliance** – `security-audit` (device security posture assessment), `comprehensive-device-review` (full config audit with recommendations)

### Database Schema

**SQLAlchemy ORM Models:**

- **Device** – RouterOS device metadata, credentials, capability flags
- **Job** – Long-running operation tracking (for async/streaming)
- **Plan** – Configuration change plans with state machine (draft → review → approved → executing → complete)
- **AuditEvent** – Immutable audit log with user context, timestamp, operation type
- **Lease** – DHCP lease tracking (optional, for DHCP server monitoring)

**Migrations:**
- Alembic for versioned database schema evolution
- Single initial migration (4f1013926767_initial_schema.py)
- SQLite for development, PostgreSQL recommended for production

### Observability

#### Structured Logging

- **structlog** for structured logging with context
- **JSON format** in production for log aggregation
- **Correlation IDs** for request tracing
- **Log levels** configurable per environment (DEBUG in lab, INFO in production)

#### Metrics

- **Prometheus** metrics exported on `/metrics` endpoint
- **Tool execution** metrics (count, duration, errors)
- **Device health** metrics (reachability, response time)
- **Request metrics** (JSON-RPC request count, latency)

#### Tracing

- **OpenTelemetry** integration for distributed tracing
- **Request correlation** across MCP and infrastructure calls
- **Tool selection metrics** for LLM accuracy monitoring
- **Token budget tracking** for context window optimization

### Transport Layers

#### STDIO Transport

- **Protocol** – JSON-RPC 2.0 over stdin/stdout
- **Client** – Claude Desktop, MCP Inspector, VS Code Copilot
- **Security Model** – OS-level process isolation; STDIO channel enforced by kernel
- **Logging** – Redirected to stderr (stdout reserved for MCP protocol)
- **Use case** – Local development and testing
- **Configuration** – Default mode; set via `--config` flag or env vars

#### HTTP/SSE Transport

- **Protocol** – HTTP/1.1 with Server-Sent Events for server-to-client streaming
- **Authentication** – OAuth 2.1/OIDC (Azure AD, Okta, Auth0) for Phase 5 multi-user
- **TLS/HTTPS** – Required for production; supports wildcard certificates and Cloudflare Tunnel
- **Features** – Resource subscriptions (real-time health updates), long-running operation progress, streaming tool outputs
- **Use case** – Remote clients, multi-user deployments, enterprise integrations
- **Scaling** – Stateless service design; horizontal scaling with PostgreSQL session store

See [**HTTP/SSE Deployment Guide**](docs/20-http-sse-transport-deployment-guide.md) and [**Transport Troubleshooting**](docs/24-http-transport-troubleshooting.md).

## Deployment Architecture

### Development (STDIO)

```
Claude Desktop / MCP Inspector
        ↓ (JSON-RPC over stdio)
    RouterOS MCP Service
        ↓
    SQLite + RouterOS Devices (lab)
```

### Production (HTTP/SSE)

```
MCP Clients (remote, multi-user)
        ↓ (HTTPS + OAuth 2.1)
Load Balancer (nginx, CloudFlare)
        ↓
    RouterOS MCP Service (horizontal scaling)
        ↓
    PostgreSQL (shared session store)
        ↓
    RouterOS Devices (production)
```

### Cloudflare Tunnel Integration

- **Outbound-only connectivity** – RouterOS devices can be behind NAT/firewall
- **Zero-trust security** – OAuth/OIDC authentication
- **Scalability** – Multiple MCP instances load-balanced through tunnel
- **Reliability** – Automatic failover and connection management

## Configuration Precedence

1. **Built-in defaults** – Sensible development defaults
2. **Config file** – YAML/TOML via `--config` flag (highest precedence)
3. **Environment variables** – `ROUTEROS_MCP_*` prefix
4. **CLI arguments** – Override all other settings

**Example priority for encryption key:**
```
ROUTEROS_MCP_ENCRYPTION_KEY (env var)
  ↑ overrides ↑
encryptionKey in config file (YAML/TOML)
  ↑ overrides ↑
ROUTEROS_MCP_ENCRYPTION_KEY env var
  ↑ overrides ↑
encrypted_key default (insecure, lab only)
```

## Testing Strategy

**Test-Driven Development (TDD) is mandatory** for all features and bug fixes. Tests define correctness, enable safe refactoring, and document expected behavior.

### Test Organization & Coverage

- **tests/unit/** (564 tests) – Domain services, authorization logic, config validation, utility functions
- **tests/e2e/** (19 tests) – Full tool execution workflows, multi-device scenarios, plan/apply cycle
- **Execution** – `uv run pytest` runs full suite (~21 seconds); `uv run pytest tests/unit -q` for fast feedback (~6 seconds)

### Coverage Targets

- **Overall** – 85%+ (current: 80%+)
- **Core domain services** – 95%+ (device, system, firewall, dns/ntp, plan, audit)
- **Authorization logic** – 100% (single-line security bugs are catastrophic)
- **Non-core utilities** – 85%+ (CLI, config, infra)

### Tool Testing Patterns

- **Mocked RouterOS** – Unit tests use in-memory mocks of REST/SSH responses; E2E tests use sandbox devices
- **State machines** – Plan/apply workflow tested in isolation and integration
- **Error handling** – Explicit tests for timeout, connectivity loss, malformed responses
- **Rollback scenarios** – Health check failures trigger rollback; rollback failures are logged/alertd

See [**Testing & Validation Strategy**](docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md) for TDD workflow, sandbox environment setup, and safety net details.

## Key Dependencies

### Core MCP & Runtime

- **fastmcp** (≥0.1.0) – Official Anthropic MCP SDK; automatic tool schema generation, transport abstraction
- **fastapi** (≥0.109.0) – Modern async web framework (HTTP/SSE transport, admin UI)
- **uvicorn** (≥0.27.0) – ASGI server with uvloop/httptools performance optimizations
- **pydantic** (≥2.5.0) – Type-based validation, JSON schema generation, settings management

### RouterOS Integration

- **httpx** (≥0.26.0) – Async HTTP client for RouterOS REST API with connection pooling
- **asyncssh** (≥2.14.0) – Async SSH client for CLI fallbacks and scripting

### Persistence & Background Tasks

- **sqlalchemy** (≥2.0.0) – ORM with async support, migrations via Alembic
- **apscheduler** (≥3.10.0) – Background task scheduling (health checks, metrics collection)
- **cryptography** (≥41.0.0) – Fernet symmetric encryption for stored credentials

### Observability

- **structlog** (≥23.2.0) – Structured logging with JSON output in production
- **prometheus_client** (≥0.19.0) – Metrics export on `/metrics` endpoint
- **opentelemetry** (≥1.21.0) – Distributed tracing with FastAPI/HTTPX instrumentation

### Development & Testing

- **pytest**, **pytest-asyncio**, **pytest-cov** – Test execution and coverage reporting
- **mypy**, **ruff**, **black** – Type checking, linting, code formatting
- **uv** – Fast Python environment and dependency management

See [**Development Environment & Dependencies**](docs/12-development-environment-dependencies-and-commands.md) for dependency selection philosophy and version pinning strategy.
