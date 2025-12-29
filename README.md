# RouterOS MCP Service

A **Model Context Protocol (MCP)** service for managing multiple MikroTik RouterOS v7 devices via their REST API (and tightly-scoped SSH/CLI where necessary). This service exposes safe, well-typed, auditable operations to AI tools (e.g., ChatGPT via Claude Desktop) and human operators, with strong security and operational guardrails.

## Overview

The implementation follows **MCP best practices** and is structured around clean separation of concerns:

- **API & MCP layer** – MCP protocol integration using FastMCP SDK
- **Domain & service layer** – Business logic and orchestration
- **Infrastructure layer** – RouterOS REST/SSH clients, persistence, observability

All design decisions for the 1.x line are captured in the [`docs/`](docs/) directory. The 1.x line is intentionally **single-tenant per deployment**, with environments (`lab`/`staging`/`prod`) and per-device capability flags controlling which tools and workflows are allowed where.

## Key Features

### Phase 1 (COMPLETED)

- ✅ **MCP Protocol Compliant** – Full support for tools, resources, and prompts
- ✅ **STDIO Transport** – Fully functional local development transport
- ✅ **Core Read-Only Tools** – System, interface, IP, routing, firewall logs
- ✅ **12+ Resources** – Device, fleet, plan, and audit resources
- ✅ **8 Prompts** – Guided workflows for common operations
- ✅ **Role-Based Authorization** – Three tiers (fundamental/advanced/professional)
- ✅ **Environment Separation** – Lab, staging, production with capability flags
- ✅ **Comprehensive Observability** – Structured logging, metrics, tracing
- ✅ **Test-Driven Development** – 85%+ coverage for non-core, 95%+ for core modules

### Phase 2 (COMPLETED)

- ✅ **HTTP/SSE Transport Documentation** – Production deployment guides complete
  - ✅ Deployment guide with system requirements, SSL/TLS, load balancing
  - ✅ OAuth setup guides for Azure AD, Okta, Auth0
  - ✅ Troubleshooting guide for common issues
  - ✅ Python and curl client examples
  - ⚠️ HTTP/SSE transport implementation needs completion (code exists, needs testing)
- ✅ **Read-Only Expansion** – Wireless, DHCP, bridge visibility
  - 9 wireless read-only tools (interfaces, clients, CAPsMAN)
  - 6 DHCP tools (server status, leases, pool management)
  - 6 bridge tools (topology, port management)
- ✅ **Resource Optimization** – Caching and performance
  - TTL-based resource cache
  - Cache invalidation on state changes
  - Subscription support

### Phase 3 (COMPLETED)

- ✅ **Admin CLI Tools** – Device management, plan approval, credential rotation
  - Device CRUD operations (add, list, update, remove)
  - Plan approval workflow with HMAC-signed tokens
  - Connectivity testing (REST + SSH)
- ✅ **Single-Device Writes (Lab/Staging)** – Safe configuration changes with plan/apply
  - Firewall management (5 tools: address lists, rules)
  - DHCP configuration (6 tools: pools, leases)
  - Bridge management (6 tools: topology, ports)
  - Wireless configuration (9 tools: SSID, RF settings, CAPsMAN)
  - System identity, DNS/NTP (10 tools)
  - IP address management (5 tools)
- ✅ **Plan/Apply Framework** – HMAC-signed approval tokens, automatic rollback
  - Token expiration (15 minutes)
  - State machine validation
  - Comprehensive audit logging
  - Health check verification
- ❌ Web-based admin UI deferred to Phase 4
- ❌ Diagnostics tools deferred to Phase 4+
- ❌ SSH key authentication deferred to Phase 4+

### Phase 4 (Planned)

## Current Implementation Status

### Phase 1-3 (COMPLETED)

**MCP Surface:**

- **62 Tools (registered):** 
  - Platform helpers (echo, service health)
  - Device management (2 tools)
  - System (4 tools)
  - Interface (3 tools)
  - IP (5 tools)
  - DNS/NTP (6 tools)
  - Routing (6 tools)
  - Firewall logs (5 tools)
  - Firewall write (5 tools)
  - DHCP (6 tools)
  - Bridge (6 tools)
  - Wireless (9 tools)
  - Config/Plan (3 tools)
- **Diagnostics tools (2 tools, ping + traceroute):** Implemented but intentionally not registered in Phase 1–3; planned for enablement in Phase 4+ per [docs/04-mcp-tools-interface](docs/04-mcp-tools-interface-and-json-schema-specification.md).
- **12+ Resources (templates + 1 concrete):** Concrete resource `fleet://health-summary` plus templated URIs for device/fleet/plan/audit (e.g., `device://{device_id}/overview`, `plan://{plan_id}/details`)
- **8 Prompts:** address-list-sync, comprehensive-device-review, device-onboarding, dns-ntp-rollout, fleet-health-review, security-audit, troubleshoot-device, troubleshoot-dns-ntp
- **Transport:** STDIO fully functional (HTTP/SSE scaffold exists but not wired)

**SSH Fallbacks:**

- Read-only CLI commands (e.g., `/ip/route/print`, `/interface/print`, `/system/package/print`) used when REST data is incomplete
- Details in [docs/15](docs/15-mcp-resources-and-prompts-design.md#ssh-commands-used-by-phase-1-resourcestools-reference)

### Phase 2 Remaining Tasks (HTTP/SSE Transport Completion)

- [ ] Add `sse-starlette` dependency
- [ ] Complete `_process_mcp_request()` integration with FastMCP
- [ ] Wire HTTP mode in `mcp/server.py`
- [ ] OAuth/OIDC middleware
- [ ] Resource subscription via SSE
- [ ] E2E testing

See [docs/04](docs/04-mcp-tools-interface-and-json-schema-specification.md#phase-1-current-implementation-tool-snapshot) for detailed tool list.

## Architecture Highlights

### MCP Integration

Built on the official **FastMCP SDK** for Python:

- Zero-boilerplate tool registration via decorators
- Automatic schema generation from type hints
- STDIO transport fully implemented (Phase 1)
- HTTP/SSE transport in progress (Phase 2)
- MCP Inspector compatible for interactive testing

### Security Model

- **Authentication**: OAuth 2.1 / OIDC integration
- **Authorization**: Per-user, per-device, per-tool enforcement
- **Three User Roles**:
  - `read_only` – Fundamental tools only (read-only, diagnostics)
  - `ops_rw` – Advanced tools (low-risk writes)
  - `admin` – Professional tools (high-risk, multi-device)
- **Device Capability Flags**: Control which tools are allowed per device
- **Audit Logging**: All writes and sensitive reads logged for compliance

### Tool Taxonomy

**Fundamental Tier** (read-only):

- System overview, interfaces, IP addresses, DNS/NTP status
- Routing summaries, logs (bounded)
- Wireless interfaces, clients, CAPsMAN status
- DHCP server status, leases
- Bridge topology, port listings
- Diagnostics (ping/traceroute) - Phase 4

**Advanced Tier** (single-device, low-risk writes):

- System identity, interface comments, DNS/NTP (lab/staging)
- Secondary IPs, MCP-owned address lists
- DHCP pool management (lab/staging)
- Bridge port adjustments (lab/staging)
- Wireless SSID management, RF settings (lab/staging)

**Professional Tier** (multi-device, high-risk):

- Multi-device DNS/NTP rollouts with plan/apply (Phase 4)
- Fleet-level health and drift reporting
- Requires human approval tokens and immutable plans

### MCP Resources

Provide read-only contextual data:

- `device://{device_id}/overview` – System metrics
- `device://{device_id}/config` – Configuration snapshot
- `device://{device_id}/health` – Real-time health (subscribable)
- `fleet://health-summary` – Fleet-wide aggregation
- `plan://{plan_id}/details` – Change plan details
- `audit://events/recent` – Audit trail

### MCP Prompts

Guided workflows:

- `dns-ntp-rollout` – Step-by-step DNS/NTP change guide
- `troubleshoot-device` – Device diagnostics workflow
- `device-onboarding` – New device registration guide

## Documentation

All design decisions are captured in the `docs/` directory, organized into logical groups:

### 📋 Core Design Documents (00-09)

Foundation and high-level design:

| Doc                                                                         | Title                      | Description                                                                  |
| --------------------------------------------------------------------------- | -------------------------- | ---------------------------------------------------------------------------- |
| [00](docs/00-requirements-and-scope-specification.md)                       | Requirements & Scope       | Problem statement, use cases, success criteria                               |
| [01](docs/01-overall-system-architecture-and-deployment-topology.md)        | Architecture & Deployment  | High-level architecture, Cloudflare Tunnel integration                       |
| [02](docs/02-security-oauth-integration-and-access-control.md)              | Security & Access Control  | Threat model, OAuth/OIDC, RBAC, device scopes                                |
| [03](docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md) | RouterOS Integration       | 41 REST API endpoints, SSH whitelisting, idempotency                         |
| [04](docs/04-mcp-tools-interface-and-json-schema-specification.md)          | MCP Tools Interface        | 62 tools across 13 categories, JSON-RPC schemas, intent-based descriptions |
| [05](docs/05-domain-model-persistence-and-task-job-model.md)                | Domain Model & Persistence | Business logic, workflows, retention policies                                |
| [06](docs/06-system-information-and-metrics-collection-module-design.md)    | Metrics Collection         | Endpoint mappings, health thresholds, collection intervals                   |
| [07](docs/07-device-control-and-high-risk-operations-safeguards.md)         | High-Risk Operations       | Risk catalog, safeguards, governance                                         |
| [08](docs/08-observability-logging-metrics-and-diagnostics.md)              | Observability              | Structured logging, metrics, tracing                                         |
| [09](docs/09-operations-deployment-self-update-and-runbook.md)              | Operations & Deployment    | Runbooks, deployment modes, operational procedures                           |

### 🔧 Implementation Specifications (10-19)

Detailed implementation guidelines:

| Doc                                                                      | Title                              | Description                                                                                |
| ------------------------------------------------------------------------ | ---------------------------------- | ------------------------------------------------------------------------------------------ |
| [10](docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md) | Testing & Validation               | TDD methodology, test layers, coverage targets (≥85% non-core, ≥95% core, aiming for 100%) |
| [11](docs/11-implementation-architecture-and-module-layout.md)           | Implementation Architecture        | Runtime stack, module layout, key classes                                                  |
| [12](docs/12-development-environment-dependencies-and-commands.md)       | Dev Environment & Dependencies     | Python 3.11+, dependencies, common commands                                                |
| [13](docs/13-python-coding-standards-and-conventions.md)                 | Python Coding Standards            | Type hints, async, testing conventions, style guide                                        |
| [14](docs/14-mcp-protocol-integration-and-transport-design.md)           | **MCP Protocol Integration**       | FastMCP SDK, stdio/HTTP transports, best practices                                         |
| [15](docs/15-mcp-resources-and-prompts-design.md)                        | **MCP Resources & Prompts**        | Resource URIs, prompt templates, workflows                                                 |
| [16](docs/16-detailed-module-specifications.md)                          | **Detailed Module Specifications** | Class/method signatures, implementation patterns                                           |
| [17](docs/17-configuration-specification.md)                             | **Configuration Specification**    | Settings class, CLI args, env vars, config files                                           |
| [18](docs/18-database-schema-and-orm-specification.md)                   | **Database Schema & ORM**          | SQLAlchemy models, migrations, session management                                          |
| [19](docs/19-json-rpc-error-codes-and-mcp-protocol-specification.md)     | **JSON-RPC Error Codes**           | Complete error taxonomy, protocol compliance                                               |

### 📈 Planning & Best Practices

- [docs/PHASE-2-PLAN.md](docs/PHASE-2-PLAN.md) – Phase 2 implementation plan and checklist
- [docs/best_practice/vscode-copilot-custom-agents-best-practices.md](docs/best_practice/vscode-copilot-custom-agents-best-practices.md) – VS Code Copilot custom agents best practices
- _Removed legacy Copilot agent instruction/task files_

### 📊 Key Design Enhancements

All design documents have been enhanced with MCP best practices:

- **Intent-Based Tool Descriptions**: All 62 tools include "Use when" guidance for optimal LLM tool selection
- **Resource Metadata**: Comprehensive metadata with token estimation, size hints, and context safety flags
- **Versioning & Capability Negotiation**: Semantic versioning with backward compatibility rules
- **LLM-in-the-Loop Testing**: Testing strategy for tool selection accuracy (target: 90%+) and parameter inference (target: 85%+)
- **MCP Observability**: Request correlation, token budget tracking, and tool-level metrics

## Implementation Roadmap (Phases)

Implementation is organized into phases that reflect increasing capability and risk:

### Phase 0 – Service Skeleton & Security Baseline

- ✅ Core config, logging, HTTP/MCP plumbing
- ✅ OAuth/OIDC + Cloudflare Tunnel integration
- ✅ Device registry and secure credential storage
- ✅ MCP server with FastMCP SDK
- ⚠️ No RouterOS writes, minimal reads

### Phase 1 – Read-Only Inventory & Health MVP

- Safe read-only tools: system overview, interfaces, IP addresses
- DNS/NTP status, routing summary
- Bounded diagnostics (ping/traceroute)
- Limited log viewing
- Metrics & health check collection
- Secured admin HTTP API for device onboarding

### Phase 2 – Read-Only Expansion & HTTP/SSE Transport

- HTTP/SSE transport for remote MCP clients
- OAuth/OIDC integration for authentication
- Resource URIs and Prompts (guided workflows)
- Additional read-only tools (wireless, DHCP, bridge)
- Resource caching and performance optimization

### Phase 2.1 – Resource Management & Real-Time Updates (Extending Phase 2)

- Resource subscriptions (SSE for real-time health monitoring)
- Configuration snapshots (read-only backup/audit)
- CAPsMAN visibility (read-only controller tools for managed APs)
- User guidance in responses (contextual hints for wireless/CAPsMAN)
- All features remain read-only; no write operations

### Phase 3 – Admin Interface & Single-Device Writes ✅

- System identity/comments, interface descriptions (production-safe)
- DNS/NTP changes (lab/staging only by default)
- Secondary IPs on non-management interfaces
- Firewall management (address lists, rules)
- DHCP configuration (pools, leases)
- Bridge management (topology, ports)
- Wireless configuration (SSID, RF settings, CAPsMAN)
- Admin CLI for device management and plan approval
- Management path protection
- Plan/apply framework with HMAC-signed tokens

### Phase 4 – Multi-Device Coordination & Diagnostics (Planned)

- Coordinated multi-device plan/apply with staged rollout
- Web-based admin UI for device and plan management
- Diagnostics tools (ping/traceroute/bandwidth-test)
- SSH key-based authentication
- Client compatibility modes for legacy RouterOS
- Automated approval tokens for trusted environments
- Long-running operations with JSON-RPC streaming

### Phase 5 – Multi-User RBAC & Governance (Optional)

- Multi-user role-based access control (RBAC)
- OAuth Authorization Code flow with PKCE
- Per-user device scopes and approval workflows
- Separate approver roles and approval queue
- Compliance reporting and policy enforcement
- Multi-instance deployments with shared session store

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Optional: PostgreSQL 14+ (SQLite works for development)
- Optional: RouterOS v7.10+ devices (for full functionality)
- Optional: OIDC provider (for production HTTP mode)
- Optional: Claude Desktop or compatible MCP host

### Installation

```bash
# Clone repository
git clone https://github.com/grammy-jiang/RouterOS-MCP.git
cd RouterOS-MCP

# Create virtual environment (using uv recommended)
uv venv .venv
source .venv/bin/activate  # Unix
# or .venv\Scripts\activate  # Windows

# Install dependencies
uv pip install -e .[dev]
```

### Test the CLI

Run the CLI with the example lab configuration:

```bash
routeros-mcp --config config/lab.yaml
```

Or test with command-line overrides:

```bash
routeros-mcp --debug --log-level DEBUG
```

### Configuration

The service supports multiple configuration methods (in priority order):

1. **Built-in defaults** - Sensible defaults for development
2. **Configuration file** - YAML or TOML via `--config`
3. **Environment variables** - `ROUTEROS_MCP_*` prefix
4. **Command-line arguments** - Highest priority

Example `config/lab.yaml` (included):

```yaml
# Application
environment: lab
debug: true
log_level: DEBUG
log_format: text

# MCP (stdio for local development with Claude Desktop)
mcp_transport: stdio

# Database (SQLite for easy development)
database_url: sqlite:///./data/routeros_mcp_lab.db
database_echo: true

# RouterOS (permissive for lab)
routeros_rest_timeout_seconds: 10.0
routeros_retry_attempts: 2

# Health checks (more frequent for testing)
health_check_interval_seconds: 30
health_check_jitter_seconds: 5
```

### HTTP Transport Quickstart (Phase 2)

For production deployments with multi-user access and OAuth authentication:

#### Prerequisites

- Valid SSL/TLS certificate (Let's Encrypt or commercial CA)
- OAuth/OIDC provider configured (Azure AD, Okta, or Auth0)
- PostgreSQL database (recommended for production)

#### Configuration

Create `config/prod.yaml`:

```yaml
# Production configuration
environment: prod
debug: false
log_level: INFO
log_format: json

# HTTP Transport
mcp_transport: http
mcp_http_host: 0.0.0.0
mcp_http_port: 8080
mcp_http_base_path: /mcp

# Database
database_url: postgresql+asyncpg://user:password@localhost:5432/routeros_mcp
database_pool_size: 20

# OAuth/OIDC (REQUIRED for HTTP mode in production)
oidc_enabled: true
oidc_provider_url: https://your-provider.com
oidc_client_id: your-client-id
oidc_audience: https://mcp.example.com
oidc_skip_verification: false # NEVER true in production
```

#### Set Encryption Key

```bash
# Generate strong encryption key (32 bytes, base64-encoded)
export ROUTEROS_MCP_ENCRYPTION_KEY=$(python3 -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())")

# Store securely (use secrets manager in production)
```

#### Run HTTP Server

```bash
# Start server
routeros-mcp --config config/prod.yaml

# Or with systemd (see deployment guide)
sudo systemctl start routeros-mcp
```

#### Test with Example Clients

**Using curl:**

```bash
# Set environment
export MCP_BASE_URL=https://mcp.example.com
export OIDC_PROVIDER_URL=https://your-provider.com
export OIDC_CLIENT_ID=your-client-id
export OIDC_CLIENT_SECRET=your-client-secret

# Run examples
bash examples/curl_example.sh
```

**Using Python client:**

```bash
# Install dependencies
pip install httpx authlib

# Run client
python examples/http_client.py --mcp-url https://mcp.example.com --device-id dev-001
```

#### Documentation

For comprehensive deployment and OAuth setup guides:

- **[HTTP/SSE Transport Deployment Guide](docs/20-http-sse-transport-deployment-guide.md)** - System requirements, SSL/TLS setup, load balancing, horizontal scaling
- **[OAuth Setup: Azure AD](docs/21-oauth-setup-azure-ad.md)** - Step-by-step Azure AD integration
- **[OAuth Setup: Okta](docs/22-oauth-setup-okta.md)** - Okta configuration and testing
- **[OAuth Setup: Auth0](docs/23-oauth-setup-auth0.md)** - Auth0 application setup and claims
- **[HTTP Transport Troubleshooting](docs/24-http-transport-troubleshooting.md)** - Common issues, debug logging, performance tuning

### Next Steps

- Explore the design documents in `docs/`, especially:
  - `docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md` for testing and coverage expectations.
  - `docs/11-implementation-architecture-and-module-layout.md` and `PHASE1_IMPLEMENTATION_OVERVIEW.md` for how the current implementation maps to the design.
- Run the automated test suite with coverage to validate changes:

  ```bash
  uv run pytest --cov=routeros_mcp
  ```

Future capabilities (implementation pending):

- Database migrations
- MCP server with stdio/HTTP transports
- RouterOS device management
- MCP tools, resources, and prompts
- Claude Desktop integration

## Development

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=routeros_mcp --cov-report=html

# Specific test file
pytest tests/unit/test_config.py

# Type checking
mypy routeros_mcp

# Linting
ruff check routeros_mcp

# Code formatting
black routeros_mcp
```

#### Smoke tests (fast, offline)

The repository includes a lightweight smoke suite designed to validate core wiring quickly without touching live devices or a real database.

- Location: `tests/smoke/`
- Marker: `@pytest.mark.smoke` (registered in `pyproject.toml`)
- Covers:
  - MCP server startup and basic tool invocation (echo, service_health)
  - JSON-RPC helpers and response formatting
  - Resource cache behavior and content formatting
  - Settings validators and common warnings
  - Prompt registration and simple render
  - Tool registrar coverage: device, system, interface, IP, routing, diagnostics, firewall/logs, DNS/NTP
  - Registrar tests patch the session factory to a fake to remain offline

Run the smoke suite locally:

```bash
pytest tests/smoke -q --maxfail=1
```

Or by marker:

```bash
pytest -m smoke -q --maxfail=1
```

Generate smoke-only coverage:

```bash
pytest tests/smoke --cov=routeros_mcp --cov-report=term-missing:skip-covered -q
```

CI note: the reusable workflow `.github/workflows/copilot-setup-steps.yml` runs the smoke suite and a smoke coverage snapshot as part of environment validation.

### Performance Testing

Phase 2 introduces performance benchmarks and load tests to validate caching improvements:

#### Run Load Tests

Simulate 100 devices and 10 concurrent clients:

```bash
# Full 5-minute load test
python tests/e2e/load_test.py

# Or run via pytest
pytest tests/e2e/load_test.py::test_load_test_5_minutes -v

# Quick 30-second test for development
pytest tests/e2e/load_test.py::test_load_test_quick -v
```

**Acceptance Criteria:**

- Load test runs 5 minutes without errors
- Cache hit rate >70%
- Resource fetch latency <1s (95th percentile)
- No memory leaks detected

#### Run Benchmarks

Single-device baseline performance tests:

```bash
# Run all benchmarks
python tests/e2e/benchmark_test.py

# Or run via pytest
pytest tests/e2e/benchmark_test.py -v

# Run specific benchmark
pytest tests/e2e/benchmark_test.py::test_benchmark_resource_fetch_latency -v
```

**Benchmarks include:**

- Resource fetch latency (with/without cache)
- Cache hit rate validation
- Memory leak detection

#### Generate Performance Report

Generate comprehensive report with graphs:

```bash
# Generate report from benchmark results
python scripts/benchmark_report.py \
    --benchmark reports/benchmark_results.json \
    --load-test reports/load_test_results.json \
    --output reports/phase2_benchmark.md

# Compare against baseline (Phase 1)
python scripts/benchmark_report.py \
    --benchmark reports/benchmark_results.json \
    --baseline reports/phase1_baseline.json \
    --output reports/comparison_report.md

# Generate JSON report
python scripts/benchmark_report.py \
    --benchmark reports/benchmark_results.json \
    --output reports/phase2_benchmark.json \
    --format json
```

**Report includes:**

- Latency graphs (p50, p95, p99)
- Cache hit rate visualization
- Memory usage tracking
- Comparison with Phase 1 baseline (if available)
- Phase 2 acceptance criteria validation

#### Performance Targets (Phase 2)

- **Resource fetch latency:** <1s (95th percentile)
- **Cache hit rate:** >70%
- **Throughput:** >100 requests/second (10 concurrent clients)
- **Memory:** No leaks, <50MB increase per 1000 requests
- **Error rate:** <5%

### E2E Testing with HTTP Transport

End-to-end tests for HTTP/SSE transport use Docker Compose to orchestrate a complete test environment including:

- RouterOS-MCP HTTP server
- Mock OIDC provider for authentication testing
- PostgreSQL database (optional, can use SQLite)

**Prerequisites:**

- Docker and Docker Compose installed
- Python dependencies installed (`pip install -e .[dev]`)

**Run E2E tests locally:**

```bash
# Start Docker Compose services
docker-compose -f tests/e2e/docker-compose.yml up -d

# Wait for services to be healthy (about 10-15 seconds)
sleep 15

# Run E2E tests
pytest tests/e2e/test_http_transport_clients.py -v

# Stop services when done
docker-compose -f tests/e2e/docker-compose.yml down
```

**Run E2E tests with one command:**

```bash
# Start services, run tests, and clean up
docker-compose -f tests/e2e/docker-compose.yml up -d && \
  sleep 15 && \
  (pytest tests/e2e/test_http_transport_clients.py -v; EXIT_CODE=$?; docker-compose -f tests/e2e/docker-compose.yml down; exit $EXIT_CODE)
```

**Debug service logs:**

```bash
# View all service logs
docker-compose -f tests/e2e/docker-compose.yml logs

# View specific service logs
docker-compose -f tests/e2e/docker-compose.yml logs routeros-mcp
docker-compose -f tests/e2e/docker-compose.yml logs mock-oidc
```

**Test coverage:**

The E2E test suite covers:

- ✅ Direct HTTP JSON-RPC request handling
- ✅ Connection timeout handling
- ✅ Correlation ID propagation
- ✅ Concurrent request handling
- ✅ Malformed JSON error handling
- ⏭️ MCP client tool invocation (Phase 3: `device_list`)
- ⏭️ MCP client tool with parameters (Phase 3: `device_get`)
- ⏭️ MCP client resource fetching (Phase 3: `device://` URIs)
- ⏭️ MCP client error handling (Phase 3: invalid device IDs)
- ⏭️ OIDC authentication with valid tokens (Phase 3)
- ⏭️ OIDC authentication with invalid tokens (Phase 3)

**CI Integration:**

E2E tests run automatically in GitHub Actions on:

- Push to `main` or `develop` branches
- Pull requests that modify transport or E2E test files
- Manual workflow dispatch

See `.github/workflows/e2e-http-transport.yml` for CI configuration.

### Linting and Formatting

```bash
# Lint
uv run ruff check routeros_mcp

# Format
uv run black routeros_mcp

# Type check
uv run mypy routeros_mcp
```

### Database Migrations

```bash
# Create new migration
uv run alembic revision --autogenerate -m "Description"

# Apply migrations
uv run alembic upgrade head

# Rollback
uv run alembic downgrade -1
```

Note: For greenfield setups without legacy data, you can generate the initial migration on demand and keep `alembic/versions/` untracked until the schema stabilizes.

## Production Deployment

### HTTP/SSE Transport Mode

1. **Configure OAuth/OIDC**:

```yaml
# config/prod.yaml
mcp_transport: http
oidc_enabled: true
oidc_issuer: https://idp.example.com
oidc_client_id: routeros-mcp-prod
oidc_client_secret: ${OIDC_CLIENT_SECRET}
oidc_audience: routeros-mcp
```

2. **Deploy with Cloudflare Tunnel**:

See [docs/01](docs/01-overall-system-architecture-and-deployment-topology.md) for full deployment guide.

3. **Run Server**:

For stdio MCP (local tools in editors/hosts):

```bash
uv run python -m routeros_mcp.main -- --config config/prod.yaml
```

For HTTP/SSE MCP (remote/production deployment, once HTTP transport is enabled):

```bash
uv run python -m routeros_mcp.main -- --config config/prod.yaml
```

Using `mcp_transport: http` in the config will start the HTTP/SSE transport instead of stdio.

### Container Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install uv && uv pip install -e .

CMD ["python", "-m", "routeros_mcp.main", "--config", "config/prod.yaml"]
```

## Getting Started (For Implementers)

If you are implementing this service:

### 1. Review Design Documentation

**Core Design Documents:**

- Start with [docs/00](docs/00-requirements-and-scope-specification.md) (requirements & scope)
- Then [docs/01](docs/01-overall-system-architecture-and-deployment-topology.md) (architecture & deployment)
- Review [docs/14](docs/14-mcp-protocol-integration-and-transport-design.md) (MCP protocol & transport)

**Security, Tools & Endpoints:**

- Read [docs/02](docs/02-security-oauth-integration-and-access-control.md) (OAuth, RBAC, threat model)
- Review [docs/03](docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md) (41 REST endpoints)
- Study [docs/04](docs/04-mcp-tools-interface-and-json-schema-specification.md) (62 tools with intent-based descriptions)
- Review [docs/15](docs/15-mcp-resources-and-prompts-design.md) (resources & prompts)

### 2. Use GitHub Copilot Agent for Implementation

**📋 Structured implementation tasks live in the design docs and issue tracker (legacy Copilot task file removed).**

This file contains **13 tasks (Phase 0-2)** organized into 6-hour blocks for GitHub Copilot Agent:

- **Phase 0 (4 tasks, ~24h):** Project setup, database, security, MCP server skeleton
- **Phase 1 (6 tasks, ~36h):** Read-only tools, health checks, admin API (23 fundamental tools)
- **Phase 2 (3 tasks, ~18h):** Advanced write tools with safety guardrails (9 advanced tools)

Each task includes:

- Clear title, description, and acceptance criteria
- **Custom prompt tailored for GitHub Copilot Agent**
- References to relevant design documents
- Code examples and testing requirements

### 3. Set Up Development Environment

- Follow [docs/12](docs/12-development-environment-dependencies-and-commands.md)
- Review [docs/13](docs/13-python-coding-standards-and-conventions.md)
- Set up Python 3.11+, PostgreSQL, and RouterOS lab device

### 4. Implement Using Structured Tasks

- Use the design docs and current issue tracker for task breakdown (legacy Copilot task file removed)
- Create GitHub issues for each task
- Assign to GitHub Copilot Agent with custom prompts
- Review output against design specifications
- Test against lab RouterOS device after each task

### 5. Testing Strategy

- Follow [docs/10](docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md)
- Achieve 85%+ coverage for non-core modules and 95%+ coverage for core modules (aim for 100% where practical)
- Use MCP Inspector for tool validation
- Test against real RouterOS lab devices
- Validate LLM tool selection accuracy (90%+ target)

## Key Design Principles

### Security First

- All clients (including AI) are untrusted
- Server-side enforcement of all safety rules
- OAuth 2.1 / OIDC authorization for HTTP transport
- Fernet-encrypted credential storage (AES-128-CBC)
- Comprehensive audit logging with immutable event records
- Three-tier authorization: fundamental (read-only), advanced (single-device writes), professional (multi-device workflows)

### MCP Best Practices Integration

This design follows official MCP best practices from Anthropic:

- **FastMCP SDK**: Zero-boilerplate tool registration with automatic schema generation
- **Transport Safety**: Stdio (stderr only for logs) and HTTP/SSE with OAuth
- **Intent-Based Descriptions**: All 62 tools include "Use when" guidance for optimal LLM selection
- **Resource Metadata**: Token estimation, size hints, safe_for_context flags
- **Error Recovery**: Actionable error messages with recovery strategies
- **Versioning**: Semantic versioning with capability negotiation
- **Observability**: Request correlation, token budget tracking, tool-level metrics
- **LLM Testing**: Automated testing for tool selection accuracy (90%+) and parameter inference (85%+)

### Operational Excellence

- Structured logging with correlation IDs
- Prometheus metrics and OpenTelemetry tracing
- Health checks and alerting
- Deployment automation
- Runbooks for common incidents

### Code Quality

- Python 3.11+ with full type hints
- Async/await throughout
- Test-driven development
- 85%+ coverage for non-core modules, 95%+ (targeting 100%) for core modules, and tests that cover all return and exception branches
- Ruff + Black + mypy enforcement

## Community and Contrib

- **Issues**: Report bugs or request features via GitHub Issues
- **Discussions**: Design discussions welcome in GitHub Discussions
- **PRs**: Follow coding standards in [docs/13](docs/13-python-coding-standards-and-conventions.md)
- **Documentation**: Improvements to docs always welcome

## License

[MIT License](LICENSE) (or your chosen license)

## Acknowledgments

- **MikroTik** for RouterOS v7 and REST API
- **Anthropic** for Model Context Protocol specification
- **FastAPI** team for excellent async web framework
- **SQLAlchemy** team for powerful ORM

---

**Phase 1-3 Complete, Phase 4 Planned** - This repository contains a production-ready design specification with 24+ comprehensive documents. Phase 1-3 implementation is complete with 62 tools, 12+ resources, 8 prompts, and full STDIO transport. Phase 4 will focus on HTTP/SSE transport completion, web admin UI, and multi-device coordination.

**Key Metrics (Phase 1-3)**:

- **62 MCP tools** registered across 13 categories (Platform 2 + Device 2 + System 4 + Interface 3 + IP 5 + DNS/NTP 6 + Routing 6 + Firewall logs 5 + Firewall write 5 + DHCP 6 + Bridge 6 + Wireless 9 + Config 3)
- **12+ resource URIs** (device, fleet, plan, audit)
- **8 prompts** for guided workflows
- **STDIO transport** fully functional
- **HTTP/SSE transport** scaffold exists (Phase 4 completion)
- **Admin CLI** complete with device management and plan approval
- **Plan/Apply framework** with HMAC-signed tokens and automatic rollback
- **24+ design documents** (~40,000 lines) with comprehensive specifications
- **3 security tiers** with OS-level auth (Phase 1) + OAuth 2.1/OIDC (Phase 4)
- **Test coverage**: 80%+ overall (Phase 1-3), targeting 85% non-core / 95%+ core
- **Test coverage targets**: at least 85% for non-core modules and at least 95% (ideally 100%) for core modules

For questions or contributions, please open an issue or discussion on GitHub.
