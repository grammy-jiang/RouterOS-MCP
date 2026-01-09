# RouterOS MCP Service

> **Model Context Protocol (MCP) service for managing multiple MikroTik RouterOS v7 devices.** Expose safe, auditable network operations to ChatGPT, Claude Desktop, and other AI tools with strong security guardrails, role-based authorization, and built-in approval workflows.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Tests](https://img.shields.io/badge/tests-583%20passing-brightgreen.svg)](tests/) [![Coverage](https://img.shields.io/badge/coverage-80%25-brightgreen.svg)](htmlcov/)

## Features

- **66 Production-Ready Tools** – System status, interfaces, IP, routing, firewall, wireless, DHCP, bridge, and diagnostics
- **Multi-Device Fleet Management** – Manage multiple RouterOS v7 devices from a single service instance
- **Three-Tier Security Model** – Role-based access control, per-device capability flags, OAuth 2.1/OIDC authentication
- **Safe Configuration Changes** – Plan/apply workflow with HMAC-signed approval tokens, automatic rollback, and health checks
- **Environment Separation** – Lab, staging, production modes with tool restrictions and safety guardrails
- **Full Observability** – Structured logging, Prometheus metrics, OpenTelemetry tracing, 80%+ test coverage

## Quick Start

### Prerequisites

- Python 3.11 or later
- MikroTik RouterOS v7 device(s) with REST API enabled
- (Optional) Claude Desktop or MCP-compatible client

### Installation

```bash
git clone https://github.com/grammy-jiang/RouterOS-MCP.git
cd RouterOS-MCP
uv sync
```

Or with dev dependencies for testing:

```bash
uv sync --all-extras
```

### Run STDIO Server

For local development with Claude Desktop:

```bash
routeros-mcp --config config/lab.yaml
```

The server uses JSON-RPC over stdin/stdout. Configure your MCP client to connect.

### Register a Device

```bash
routeros-mcp device add \
  --name lab-router \
  --hostname 192.168.88.1 \
  --rest-user admin \
  --rest-password secret
```

### Run Tests

```bash
# Quick smoke test (6 seconds)
uv run pytest tests/unit -q

# Full suite with coverage (21 seconds)
uv run pytest
```

## Documentation

Comprehensive design documentation in [`docs/`](docs/):

| Topic | Document |
|-------|----------|
| **Getting Started** | [Development Setup](docs/12-development-environment-dependencies-and-commands.md), [Requirements](docs/00-requirements-and-scope-specification.md) |
| **Architecture** | [System Design & Architecture](ARCHITECTURE.md), [Implementation Layout](docs/11-implementation-architecture-and-module-layout.md) |
| **Security & Auth** | [Security Model](docs/02-security-oauth-integration-and-access-control.md), [OAuth Setup (Azure/Okta/Auth0)](docs/21-oauth-setup-azure-ad.md) |
| **MCP Integration** | [MCP Protocol](docs/14-mcp-protocol-integration-and-transport-design.md), [Tools Catalog](docs/04-mcp-tools-interface-and-json-schema-specification.md), [Resources & Prompts](docs/15-mcp-resources-and-prompts-design.md) |
| **Operations** | [Admin CLI](docs/ADMIN_CLI.md), [HTTP/SSE Deployment](docs/20-http-sse-transport-deployment-guide.md), [Production Runbook](docs/09-operations-deployment-self-update-and-runbook.md) |
| **Testing** | [Testing Strategy](docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md), [Performance Testing](docs/PERFORMANCE_TESTING.md) |
| **Contributing** | [Contribution Guidelines](CONTRIBUTING.md) |
| **Implementation** | [All 20 Design Docs](docs/) – Phase planning, database schema, error codes, module specifications |

## Project Status

**Phase 4 Complete (January 2026):**

- ✅ 66 MCP tools (read + write + diagnostics) with role-based authorization
- ✅ STDIO and HTTP/SSE transports fully functional
- ✅ Multi-device coordination with staged rollouts
- ✅ Plan/apply framework with HMAC-signed approval tokens
- ✅ 12+ MCP resources and 8 guided workflow prompts
- ✅ Admin CLI for device and plan management
- ✅ Full observability (structured logging, metrics, tracing)
- ✅ 583 tests (564 unit + 19 e2e), 80%+ coverage

**Planned (Phase 5):**
- Multi-user role-based access control (RBAC)
- OAuth Authorization Code flow with PKCE
- Per-user device scopes and approval workflows
- Compliance reporting and policy enforcement

## Support & Community

- **Issues** – [GitHub Issues](https://github.com/grammy-jiang/RouterOS-MCP/issues) for bug reports and feature requests
- **Discussions** – [GitHub Discussions](https://github.com/grammy-jiang/RouterOS-MCP/discussions) for questions and ideas
- **Contributing** – See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and setup instructions

## License

MIT License – see [LICENSE](LICENSE) for details.
