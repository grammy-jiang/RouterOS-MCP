# RouterOS MCP Service

A **Model Context Protocol (MCP)** service for managing multiple MikroTik RouterOS v7 devices via their REST API (and tightly-scoped SSH/CLI where necessary). This service exposes safe, well-typed, auditable operations to AI tools (e.g., ChatGPT via Claude Desktop) and human operators, with strong security and operational guardrails.

## Overview

The implementation follows **MCP best practices** and is structured around clean separation of concerns:

- **API & MCP layer** – MCP protocol integration using FastMCP SDK
- **Domain & service layer** – Business logic and orchestration
- **Infrastructure layer** – RouterOS REST/SSH clients, persistence, observability

All design decisions for the 1.x line are captured in the [`docs/`](docs/) directory. The 1.x line is intentionally **single-tenant per deployment**, with environments (`lab`/`staging`/`prod`) and per-device capability flags controlling which tools and workflows are allowed where.

## Key Features

- ✅ **MCP Protocol Compliant** – Full support for tools, resources, and prompts
- ✅ **Dual Transport** – Stdio (local development) and HTTP/SSE (production)
- ✅ **OAuth/OIDC Authentication** – Enterprise-ready security via external IdP
- ✅ **Role-Based Authorization** – Three tiers (fundamental/advanced/professional)
- ✅ **Environment Separation** – Lab, staging, production with capability flags
- ✅ **Plan/Apply Workflows** – Safe multi-device operations with approvals
- ✅ **Comprehensive Observability** – Structured logging, metrics, tracing
- ✅ **Test-Driven Development** – 85% overall coverage, 100% core modules

## Architecture Highlights

### MCP Integration

Built on the official **FastMCP SDK** for Python:

- Zero-boilerplate tool registration via decorators
- Automatic schema generation from type hints
- Support for stdio (development) and HTTP/SSE (production) transports
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

| Doc | Title | Description |
|-----|-------|-------------|
| [00](docs/00-requirements-and-scope-specification.md) | Requirements & Scope | Problem statement, use cases, success criteria |
| [01](docs/01-overall-system-architecture-and-deployment-topology.md) | Architecture & Deployment | High-level architecture, Cloudflare Tunnel integration |
| [02](docs/02-security-oauth-integration-and-access-control.md) | Security & Access Control | Threat model, OAuth/OIDC, RBAC, device scopes |
| [03](docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md) | RouterOS Integration | REST client, SSH whitelisting, idempotency |
| [04](docs/04-mcp-tools-interface-and-json-schema-specification.md) | MCP Tools Interface | 40 tool specifications, JSON-RPC schemas, authorization |
| [05](docs/05-domain-model-persistence-and-task-job-model.md) | Domain Model & Persistence | Business logic, workflows, retention policies |
| [06](docs/06-system-information-and-metrics-collection-module-design.md) | Metrics Collection | Endpoint mappings, health thresholds, collection intervals |
| [07](docs/07-device-control-and-high-risk-operations-safeguards.md) | High-Risk Operations | Risk catalog, safeguards, governance |
| [08](docs/08-observability-logging-metrics-and-diagnostics.md) | Observability | Structured logging, metrics, tracing |
| [09](docs/09-operations-deployment-self-update-and-runbook.md) | Operations & Deployment | Runbooks, deployment modes, operational procedures |

### 🔧 Implementation Specifications (10-19)

Detailed implementation guidelines:

| Doc | Title | Description |
|-----|-------|-------------|
| [10](docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md) | Testing & Validation | TDD methodology, test layers, coverage targets (85% overall, 100% core) |
| [11](docs/11-implementation-architecture-and-module-layout.md) | Implementation Architecture | Runtime stack, module layout, key classes |
| [12](docs/12-development-environment-dependencies-and-commands.md) | Dev Environment & Dependencies | Python 3.11+, dependencies, common commands |
| [13](docs/13-python-coding-standards-and-conventions.md) | Python Coding Standards | Type hints, async, testing conventions, style guide |
| [14](docs/14-mcp-protocol-integration-and-transport-design.md) | **MCP Protocol Integration** | FastMCP SDK, stdio/HTTP transports, best practices |
| [15](docs/15-mcp-resources-and-prompts-design.md) | **MCP Resources & Prompts** | Resource URIs, prompt templates, workflows |
| [16](docs/16-detailed-module-specifications.md) | **Detailed Module Specifications** | Class/method signatures, implementation patterns |
| [17](docs/17-configuration-specification.md) | **Configuration Specification** | Settings class, CLI args, env vars, config files |
| [18](docs/18-database-schema-and-orm-specification.md) | **Database Schema & ORM** | SQLAlchemy models, migrations, session management |
| [19](docs/19-json-rpc-error-codes-and-mcp-protocol-specification.md) | **JSON-RPC Error Codes** | Complete error taxonomy, protocol compliance |

### 📊 Meta & Reference Documents

| Doc | Title | Description |
|-----|-------|-------------|
| [ANALYSIS](docs/ANALYSIS.md) | **Design Analysis** | MCP compliance analysis, gaps, recommendations |
| [ENDPOINT-TOOL-MAPPING](docs/ENDPOINT-TOOL-MAPPING.md) | **Endpoint-Tool Mapping** | Cross-reference: RouterOS endpoints ↔ MCP tools |
| [DOCUMENTATION-AUDIT](docs/DOCUMENTATION-AUDIT.md) | **Documentation Audit** | Comprehensive audit, consolidation analysis |

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
- PostgreSQL 14+
- RouterOS v7.10+ devices
- OIDC provider (for production HTTP mode)
- Optional: Claude Desktop or compatible MCP host

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/routeros-mcp.git
cd routeros-mcp

# Create virtual environment (using uv recommended)
uv venv .venv
source .venv/bin/activate  # Unix
# or .venv\Scripts\activate  # Windows

# Install dependencies
uv pip install -e .[dev]
```

### Configuration

Create `config/lab.yaml`:

```yaml
# MCP transport
mcp_transport: stdio  # or "http"

# Environment
environment: lab
log_level: DEBUG

# Database
database_url: postgresql+asyncpg://user:pass@localhost/routeros_mcp_lab

# RouterOS
routeros_rest_timeout_seconds: 5.0
routeros_max_concurrent_requests_per_device: 3

# Encryption (generate secure key)
encryption_key: ${ENCRYPTION_KEY}

# OIDC (for HTTP transport)
oidc_enabled: false  # true for production HTTP
```

### Database Setup

```bash
# Run migrations
uv run alembic upgrade head
```

### Run MCP Server (Stdio Mode)

```bash
# Start server
uv run python -m routeros_mcp.mcp_server --config config/lab.yaml
```

### Configure Claude Desktop

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "routeros-mcp": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "routeros_mcp.mcp_server",
        "--config",
        "/absolute/path/to/config/lab.yaml"
      ],
      "env": {
        "ROUTEROS_MCP_LOG_LEVEL": "INFO",
        "ENCRYPTION_KEY": "your-secure-key"
      }
    }
  }
}
```

### Test with MCP Inspector

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Launch inspector
npx @modelcontextprotocol/inspector uv run python -m routeros_mcp.mcp_server \
    --config config/lab.yaml
```

Navigate to `http://localhost:5173` to interactively test tools, resources, and prompts.

## Development

### Run Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=routeros_mcp --cov-report=html

# Using tox (recommended)
uv run tox
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

```bash
uv run python -m routeros_mcp.mcp_server --config config/prod.yaml
```

Server listens on configured port (default 8080) with SSE endpoint at `/mcp/sse`.

### Container Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install uv && uv pip install -e .

CMD ["python", "-m", "routeros_mcp.mcp_server", "--config", "config/prod.yaml"]
```

## Getting Started (For Implementers)

If you are implementing this service:

1. **Read Core Design Docs**:
   - Start with [docs/00](docs/00-requirements-and-scope-specification.md) (requirements)
   - Then [docs/01](docs/01-overall-system-architecture-and-deployment-topology.md) (architecture)
   - Review [docs/14](docs/14-mcp-protocol-integration-and-transport-design.md) (MCP integration)

2. **Understand Security & MCP Tools**:
   - Read [docs/02](docs/02-security-oauth-integration-and-access-control.md) (security)
   - Review [docs/04](docs/04-mcp-tools-interface-and-json-schema-specification.md) (tools)
   - Study [docs/15](docs/15-mcp-resources-and-prompts-design.md) (resources & prompts)

3. **Set Up Development Environment**:
   - Follow [docs/12](docs/12-development-environment-dependencies-and-commands.md)
   - Review [docs/13](docs/13-python-coding-standards-and-conventions.md)

4. **Implement Phase 0 and Phase 1**:
   - Use RouterOS integration guidelines from [docs/03](docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md)
   - Follow domain model from [docs/05](docs/05-domain-model-persistence-and-task-job-model.md)
   - Reference module layout from [docs/11](docs/11-implementation-architecture-and-module-layout.md)
   - Use detailed specs from [docs/16](docs/16-detailed-module-specifications.md)

5. **Test Thoroughly**:
   - Follow [docs/10](docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md)
   - Test against lab RouterOS devices
   - Use MCP Inspector for tool testing
   - Achieve 85%+ coverage before Phase 2

## Key Design Principles

### Security First

- All clients (including AI) are untrusted
- Server-side enforcement of all safety rules
- OAuth 2.1 authorization for HTTP transport
- Encrypted credential storage
- Comprehensive audit logging

### MCP Best Practices

- Official FastMCP SDK usage
- Stdio safety (stderr only for logs)
- HTTP/SSE for production with OAuth
- JSON-RPC 2.0 error handling
- Resources for contextual data
- Prompts for workflow guidance
- MCP Inspector for testing

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
- 85% overall coverage, 100% core modules
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

**Status**: This is a comprehensive design specification and architectural blueprint. Implementation is organized in phases (0-5) as described in the roadmap above. The design follows MCP best practices and industry standards for Python development.

For questions or contributions, please open an issue or discussion on GitHub.
