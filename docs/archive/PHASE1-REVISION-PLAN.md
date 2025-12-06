# Phase 1 Revision Plan: Single-User, Single MCP Server

## Date
2024-01-15

## Objective

Revise all documentation to focus on **Phase 1 implementation**:
- **Single user** (no multi-user OAuth/OIDC)
- **Single MCP server** (stdio transport only)
- **Multiple RouterOS devices** (up to 10 devices)
- **Local development focus** (no HTTP/SSE, no Cloudflare Tunnel)

---

## Scope Changes

### What to Simplify

1. **Authentication & Authorization**
   - Remove OAuth/OIDC requirements for Phase 1
   - Single implicit admin user (OS-level access control)
   - No role-based access control (RBAC) in Phase 1
   - Device access controlled by config file only

2. **Transport**
   - **Stdio only** for Phase 1
   - Remove HTTP/SSE transport implementation
   - Keep HTTP/SSE in design docs as "Future" sections

3. **Database**
   - Remove User table (no multi-user)
   - Remove authorization fields from audit events
   - Simplify to device management and health tracking only

4. **Configuration**
   - Remove OIDC settings for Phase 1
   - Simplify to local config file + environment variables
   - No need for complex role mapping

5. **Deployment**
   - Local process only (no Cloudflare Tunnel)
   - Single workstation/laptop deployment
   - No clustering or HA requirements

### What to Keep

1. **Core MCP Features**
   - FastMCP SDK integration
   - Tools, resources, prompts
   - MCP Inspector testing

2. **Device Management**
   - Multiple device support (up to 10)
   - Device registry with tags
   - Credential encryption
   - Health checks and metrics

3. **Safety Features**
   - Environment separation (lab/staging/prod)
   - Device capability flags
   - Audit logging (simplified, no user tracking)
   - Plan/approve workflows (self-approval)

4. **Database Foundation**
   - SQLite for Phase 1 (PostgreSQL remains optional)
   - Keep ORM models for future scalability
   - Migration strategy with Alembic

---

## Documents to Revise

### High Priority (Core Architecture Changes)

1. **Doc 02: Security, OAuth Integration, and Access Control**
   - Remove OAuth/OIDC sections for Phase 1
   - Simplify to OS-level access control
   - Keep device-level capability flags
   - Mark OAuth as "Phase 4: Multi-User Access"

2. **Doc 14: MCP Protocol Integration and Transport Design**
   - Make stdio the primary transport for Phase 1
   - Move HTTP/SSE to "Future Enhancements" section
   - Simplify configuration examples

3. **Doc 17: Configuration Specification**
   - Remove oidc_* settings for Phase 1
   - Simplify to essential settings only
   - Default to SQLite (not PostgreSQL)
   - Remove HTTP transport settings for Phase 1

4. **Doc 18: Database Schema and ORM Specification**
   - Remove User model
   - Simplify AuditEvent (no user_sub, user_email, user_role)
   - Keep Device, Credential, HealthCheck, Snapshot, Plan, Job
   - Note: Keep ORM flexible for future user model addition

5. **Doc 16: Detailed Module Specifications**
   - Remove security/auth.py (OIDC)
   - Simplify security/authz.py (no user roles)
   - Remove HTTP middleware
   - Focus on stdio MCP server

### Medium Priority (Operational Changes)

6. **Doc 01: Overall System Architecture and Deployment Topology**
   - Simplify deployment to single workstation
   - Remove Cloudflare Tunnel sections for Phase 1
   - Single-process architecture diagram

7. **Doc 09: Operations, Deployment, Self-Update, and Runbook**
   - Focus on local development setup
   - Remove production deployment sections for Phase 1
   - Simplify to "start server, connect Claude Desktop"

8. **Doc 11: Implementation Architecture and Module Layout**
   - Remove api/http.py for Phase 1
   - Remove security/auth.py
   - Simplify module tree

9. **Doc 12: Development Environment, Dependencies & Commands**
   - Remove authlib dependency for Phase 1
   - Remove uvicorn/FastAPI for Phase 1
   - Keep minimal dependencies

### Low Priority (Documentation Updates)

10. **README.md**
    - Update "Key Features" to reflect Phase 1 scope
    - Simplify "Quick Start" for single-user stdio mode
    - Mark multi-user features as "Future"

11. **Doc 00: Requirements and Scope Specification**
    - Add Phase 1 scope section
    - Mark multi-user as Phase 4
    - Update success criteria for Phase 1

12. **Doc 04: MCP Tools Interface and JSON Schema Specification**
    - Remove user_id from tool parameters
    - Simplify authorization checks (device-level only)

13. **Doc 15: MCP Resources and Prompts Design**
    - Remove user-specific resource URIs
    - Simplify audit resources (no user filtering)

---

## Architecture Changes

### Before (Multi-User)

```
┌─────────────────────────────────────────┐
│         MCP Host (Claude Desktop)       │
└────────────────┬────────────────────────┘
                 │ stdio or HTTP/SSE
                 ▼
┌─────────────────────────────────────────┐
│          MCP Server (FastAPI)           │
│  ┌───────────────────────────────────┐  │
│  │  OAuth/OIDC Authentication        │  │
│  │  User → Role → Device Scope       │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  Authorization Service             │  │
│  │  Check role, tier, device flags   │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  MCP Tools / Resources / Prompts  │  │
│  └───────────────────────────────────┘  │
└────────────┬───────────┬────────────────┘
             │           │
    ┌────────▼──────┐   │
    │  PostgreSQL   │   │
    │  (Multi-user) │   │
    └───────────────┘   │
                        ▼
              ┌──────────────────┐
              │ RouterOS Devices │
              │  (REST/SSH API)  │
              └──────────────────┘
```

### After (Phase 1: Single-User)

```
┌─────────────────────────────────────────┐
│         MCP Host (Claude Desktop)       │
└────────────────┬────────────────────────┘
                 │ stdio only
                 ▼
┌─────────────────────────────────────────┐
│     MCP Server (FastMCP + stdio)        │
│  ┌───────────────────────────────────┐  │
│  │  No Authentication (OS-level)     │  │
│  │  Single implicit admin user       │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  Device Capability Checks Only    │  │
│  │  (environment, flags)              │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  MCP Tools / Resources / Prompts  │  │
│  └───────────────────────────────────┘  │
└────────────┬───────────────────────────┘
             │
    ┌────────▼──────┐
    │  SQLite       │
    │  (Local file) │
    └───────────────┘
             │
             ▼
   ┌──────────────────┐
   │ RouterOS Devices │
   │   (up to 10)     │
   │  (REST/SSH API)  │
   └──────────────────┘
```

---

## Configuration Changes

### Before (Multi-User Config)

```yaml
# config/prod.yaml
environment: prod
mcp_transport: http
mcp_http_host: 0.0.0.0
mcp_http_port: 8080

database_url: postgresql+asyncpg://user:pass@postgres:5432/routeros_mcp

oidc_enabled: true
oidc_issuer: https://idp.example.com
oidc_client_id: routeros-mcp-prod
oidc_client_secret: ${OIDC_CLIENT_SECRET}

encryption_key: ${ENCRYPTION_KEY}
```

### After (Phase 1 Config)

```yaml
# config/lab.yaml (Phase 1)
environment: lab
mcp_transport: stdio  # Only stdio in Phase 1

database_url: sqlite:///./data/routeros_mcp.db  # Local SQLite

encryption_key: ${ENCRYPTION_KEY}  # For device credentials only

# Device management
routeros_rest_timeout_seconds: 5.0
health_check_interval_seconds: 60

# No OIDC settings needed for Phase 1
```

---

## Database Schema Changes

### Tables to Remove for Phase 1
- `users` - No multi-user support

### Tables to Simplify

**AuditEvent** (before):
```python
class AuditEvent(Base):
    user_sub: Mapped[str]           # Remove
    user_email: Mapped[Optional[str]]  # Remove
    user_role: Mapped[str]          # Remove
    device_id: Mapped[Optional[str]]
    action: Mapped[str]
    tool_name: Mapped[str]
    # ...
```

**AuditEvent** (after - Phase 1):
```python
class AuditEvent(Base):
    # No user tracking in Phase 1
    device_id: Mapped[Optional[str]]
    action: Mapped[str]
    tool_name: Mapped[str]
    tool_tier: Mapped[str]  # Keep for reference
    # ...
```

### Tables to Keep
- `devices` - Core device registry
- `credentials` - Encrypted device credentials
- `health_checks` - Device health history
- `snapshots` - Configuration backups
- `plans` - Change plans (self-approved)
- `jobs` - Background jobs

---

## Module Changes

### Modules to Remove for Phase 1
- `api/http.py` - No HTTP API needed
- `api/middleware.py` - No HTTP middleware
- `security/auth.py` - No OIDC authentication
- Remove most of `security/authz.py` - Keep only device capability checks

### Modules to Keep
- `config.py` - Simplified configuration
- `cli.py` - Command-line interface
- `mcp_server.py` - FastMCP stdio server
- `mcp_tools/` - All MCP tools
- `mcp_resources/` - All MCP resources
- `mcp_prompts/` - All MCP prompts
- `domain/` - Domain services
- `infra/routeros/` - RouterOS clients
- `infra/db/` - Database layer (simplified)
- `infra/jobs/` - Background jobs
- `infra/observability/` - Logging, metrics

### Simplified Module Tree (Phase 1)

```
routeros_mcp/
├── config.py                 # Simplified settings
├── cli.py                    # CLI arguments
├── mcp_server.py             # FastMCP stdio server
├── mcp_tools/                # MCP tool implementations
│   ├── system.py
│   ├── interface.py
│   └── ...
├── mcp_resources/            # MCP resources
│   ├── device.py
│   └── fleet.py
├── mcp_prompts/              # MCP prompts
│   └── workflows.py
├── security/
│   ├── crypto.py             # Credential encryption only
│   └── authz.py              # Device capability checks only
├── domain/                   # Domain services
│   ├── models.py             # No User model
│   ├── devices.py
│   ├── health.py
│   └── ...
├── infra/
│   ├── routeros/             # RouterOS clients
│   ├── db/                   # Database (SQLite focus)
│   ├── jobs/                 # Background jobs
│   └── observability/        # Logging, metrics
└── tests/
```

---

## Dependencies to Remove for Phase 1

- ❌ `authlib` - No OAuth/OIDC
- ❌ `fastapi` - No HTTP API (Phase 1)
- ❌ `uvicorn` - No ASGI server (Phase 1)
- ⚠️ `asyncpg` - Optional (SQLite default)

## Dependencies to Keep

- ✅ `fastmcp` - MCP SDK (stdio)
- ✅ `pydantic` - Data validation
- ✅ `pydantic-settings` - Configuration
- ✅ `sqlalchemy` - ORM
- ✅ `aiosqlite` - SQLite async driver
- ✅ `alembic` - Migrations
- ✅ `httpx` - RouterOS REST client
- ✅ `asyncssh` - RouterOS SSH client
- ✅ `cryptography` - Credential encryption
- ✅ `structlog` - Logging
- ✅ `prometheus-client` - Metrics

---

## Implementation Priority for Phase 1

### Phase 1.0: Minimal Viable MCP Server
1. Configuration system (stdio, SQLite)
2. Database setup (simplified schema)
3. MCP server with FastMCP (stdio only)
4. Device registry (CRUD operations)
5. Credential encryption

### Phase 1.1: Device Communication
1. RouterOS REST client
2. Basic system info tool
3. Interface listing tool
4. Test with MCP Inspector

### Phase 1.2: Read-Only Operations
1. All fundamental-tier tools (read-only)
2. Health check service
3. MCP resources for device data
4. Background health checks

### Phase 1.3: Safe Writes
1. Advanced-tier tools (low-risk writes)
2. Audit logging (simplified)
3. Configuration snapshots

### Phase 1.4: Plan/Apply
1. Plan creation for multi-device operations
2. Self-approval workflow (single user)
3. Job execution

---

## Future Phases (Beyond Phase 1)

### Phase 2: Enhanced Single-User
- HTTP API for admin UI (optional)
- Web-based device management
- Advanced monitoring dashboards

### Phase 3: Local Multi-User
- Multiple local users (Unix accounts)
- Basic role separation
- Shared device pool

### Phase 4: Enterprise Multi-User
- OAuth/OIDC integration
- HTTP/SSE transport
- Cloudflare Tunnel
- Full RBAC with device scoping

---

## Success Criteria for Phase 1

✅ Single user can manage up to 10 RouterOS devices via Claude Desktop
✅ Stdio transport with MCP protocol
✅ SQLite database for local storage
✅ All fundamental-tier tools working (read-only)
✅ Advanced-tier tools for safe writes
✅ Health monitoring and metrics collection
✅ Audit trail for all operations
✅ MCP Inspector testing support
✅ Simple configuration (YAML file + env vars)
✅ No external dependencies (no OAuth IdP, no PostgreSQL)

---

## Documentation Revision Checklist

- [ ] Doc 00: Add Phase 1 scope section
- [ ] Doc 01: Simplify to single-user deployment
- [ ] Doc 02: Remove OAuth, simplify to OS-level auth
- [ ] Doc 04: Remove user parameters from tools
- [ ] Doc 09: Focus on local development
- [ ] Doc 11: Simplify module layout
- [ ] Doc 12: Remove multi-user dependencies
- [ ] Doc 14: Make stdio primary transport
- [ ] Doc 15: Remove user-specific resources
- [ ] Doc 16: Remove auth/HTTP modules
- [ ] Doc 17: Simplify configuration
- [ ] Doc 18: Remove User table, simplify audit
- [ ] README: Update for Phase 1 focus

---

## Next Steps

1. Create Phase 1 revisions for all high-priority docs (02, 14, 16, 17, 18)
2. Update database schema and migration for simplified model
3. Update README with Phase 1 focus and roadmap
4. Create Phase 1 quick start guide
5. Mark multi-user features as "Phase 4" throughout docs

---

**This revision will make the implementation more achievable for Phase 1 while preserving the design foundation for future multi-user capabilities.**
