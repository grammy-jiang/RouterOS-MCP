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
- ✅ **39 Tools Implemented** – Fundamental, advanced, and professional tiers
- ✅ **12+ Resources** – Device, fleet, plan, and audit resources
- ✅ **8 Prompts** – Guided workflows for common operations
- ✅ **Role-Based Authorization** – Three tiers (fundamental/advanced/professional)
- ✅ **Environment Separation** – Lab, staging, production with capability flags
- ✅ **Plan/Apply Workflows** – Safe multi-device operations with approvals
- ✅ **Comprehensive Observability** – Structured logging, metrics, tracing
- ✅ **Test-Driven Development** – 85%+ coverage for non-core, 95%+ for core modules

### Phase 2 (CURRENT - In Progress)

- ⚠️ **HTTP/SSE Transport** – Scaffold exists, needs completion
  - Add `sse-starlette` dependency
  - Integrate with FastMCP request handling
  - OAuth/OIDC middleware implementation
  - Resource subscription via SSE
- 🔜 **Read-Only Expansion** – Wireless, DHCP, bridge visibility
  - 6 new read-only tools for network topology
  - Additional troubleshooting prompts
- 🔜 **Resource Optimization** – Caching and performance
  - TTL-based resource cache
  - Cache invalidation on state changes
  - Subscription support

### Phase 3+ (Future)

- 🔮 Network diagnostics (ping/traceroute/bandwidth-test)
- 🔮 SSH key authentication
- 🔮 Advanced firewall write operations
- 🔮 Client compatibility modes

## Current Implementation Status

### Phase 1 (COMPLETED)

**MCP Surface:**

- **39 Tools (registered):** Platform helpers (echo, service health), device management, system, interface, IP, DNS/NTP, routing, firewall/logs, firewall write, and professional DNS/NTP rollout workflows
- **12+ Resources (templates + 1 concrete):** Concrete resource `fleet://health-summary` plus templated URIs for device/fleet/plan/audit (e.g., `device://{device_id}/overview`, `plan://{plan_id}/details`)
- **8 Prompts:** address-list-sync, comprehensive-device-review, device-onboarding, dns-ntp-rollout, fleet-health-review, security-audit, troubleshoot-device, troubleshoot-dns-ntp
- **Transport:** STDIO fully functional (HTTP/SSE scaffold exists but not wired)

**SSH Fallbacks:**

- Read-only CLI commands (e.g., `/ip/route/print`, `/interface/print`, `/system/package/print`) used when REST data is incomplete
- Details in [docs/15](docs/15-mcp-resources-and-prompts-design.md#ssh-commands-used-by-phase-1-resourcestools-reference)

### Phase 2 (IN PROGRESS)

**HTTP/SSE Transport Completion:**

- [ ] Add `sse-starlette` dependency
- [ ] Complete `_process_mcp_request()` integration with FastMCP
- [ ] Wire HTTP mode in `mcp/server.py`
- [ ] OAuth/OIDC middleware
- [ ] Resource subscription via SSE
- [ ] E2E testing

**Read-Only Expansion:**

- [ ] `wireless/get-interfaces` + `wireless/get-clients`
- [ ] `dhcp/get-server-status` + `dhcp/get-leases`
- [ ] `bridge/list-bridges` + `bridge/list-ports`
- [ ] Wireless/DHCP troubleshooting prompts

**Resource Optimization:**

- [ ] Resource cache with TTL
- [ ] Cache invalidation
- [ ] Performance benchmarking

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
- Routing summaries, logs (bounded), diagnostics (ping/traceroute)

**Advanced Tier** (single-device, low-risk writes):

- System identity, interface comments, DNS/NTP (lab/staging)
- Secondary IPs, MCP-owned address lists

**Professional Tier** (multi-device, high-risk):

- Multi-device DNS/NTP rollouts with plan/apply
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
| [04](docs/04-mcp-tools-interface-and-json-schema-specification.md)          | MCP Tools Interface        | 46 tools (40 core + 6 fallback), JSON-RPC schemas, intent-based descriptions |
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
- [GITHUB-COPILOT-AGENT-INSTRUCTIONS.md](GITHUB-COPILOT-AGENT-INSTRUCTIONS.md) – Copilot Coding Agent onboarding for this repo
- [GITHUB-COPILOT-TASKS.md](GITHUB-COPILOT-TASKS.md) – Structured task list mapped to phases

### 📊 Key Design Enhancements

All design documents have been enhanced with MCP best practices:

- **Intent-Based Tool Descriptions**: All 46 tools include "Use when" guidance for optimal LLM tool selection
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

### Phase 2 – Low-Risk Single-Device Writes

- System identity/comments, interface descriptions (production-safe)
- DNS/NTP changes (lab/staging only by default)
- Strong audit logging
- CLI wrappers and simple admin web console

### Phase 3 – Controlled Network Config Writes

- Secondary IPs on non-management interfaces
- MCP-owned address-lists (lab/staging)
- Optional lab-only DHCP/bridge changes
- Management path protection
- Optional automated device onboarding

### Phase 4 – Multi-Device & Cross-Topic Workflows

- Professional-tier tools for multi-device DNS/NTP rollouts
- Shared address-list sync
- Fleet-level health/drift reporting
- Mandatory plan/apply with human approval tokens
- Staged rollout and potential rollback

### Phase 5 – High-Risk Areas & Expert Workflows (Optional)

- Optional expert-only workflows (firewall templates, selected static routes)
- Interface admin on non-critical ports
- Limited wireless RF changes
- Always professional tier with plan/apply + approvals
- **Typically disabled by default in production**

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
- Study [docs/04](docs/04-mcp-tools-interface-and-json-schema-specification.md) (46 tools with intent-based descriptions)
- Review [docs/15](docs/15-mcp-resources-and-prompts-design.md) (resources & prompts)

### 2. Use GitHub Copilot Agent for Implementation

**📋 See [GITHUB-COPILOT-TASKS.md](GITHUB-COPILOT-TASKS.md) for structured implementation tasks.**

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

- Use tasks from [GITHUB-COPILOT-TASKS.md](GITHUB-COPILOT-TASKS.md)
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
- **Intent-Based Descriptions**: All 46 tools include "Use when" guidance for optimal LLM selection
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

Phase 1 Complete, Phase 2 In Progress\*\* - This repository contains a production-ready design specification with 20 comprehensive documents. Phase 1 implementation is complete with 39 tools, 12+ resources, 8 prompts, and full STDIO transport. Phase 2 focuses on HTTP/SSE transport completion and read-only feature expansion.

**Key Metrics (Phase 1)**:

- **39 MCP tools** (14 fundamental, 10 advanced, 8 professional, 6 fallbacks, 1 admin)
- **12+ resource URIs** (device, fleet, plan, audit)
- **8 prompts** for guided workflows
- **STDIO transport** fully functional
- **HTTP/SSE transport** scaffold exists (Phase 2 completion)
- **20 design documents** (~50,000 lines) with comprehensive specifications
- **3 security tiers** with OS-level auth (Phase 1) + OAuth 2.1/OIDC (Phase 2)
- **Test coverage**: 80%+ overall (Phase 1), targeting 85% non-core / 95%+ core
- **Test coverage targets**: at least 85% for non-core modules and at least 95% (ideally 100%) for core modules

For questions or contributions, please open an issue or discussion on GitHub.
