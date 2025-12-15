# Operations, Deployment, Self-Update & Rollback Runbook

## Purpose

Document how the service is operated over time: deployment workflows, configuration management, schema migrations, self-update and rollback strategies, and emergency procedures. This document is aimed at operators and SREs.

---

## Configuration model (env vars, config files, secrets, per-environment overrides)

- **Configuration sources**:

  - Environment variables (primary).
  - Optional configuration files (YAML/TOML/JSON) for structured settings.
  - Secret sources (environment, secret manager) for sensitive values.

- **Key configuration areas**:

  - Database connection (URLs, pools).
  - OIDC provider settings (issuer, client ID, client secret, redirect URIs).
  - Cloudflare Tunnel origin port and hostname.
  - RouterOS integration defaults (timeouts, retries, per-device limits).
  - Logging and metrics (exporter endpoints, log level).
  - Environment tag for the MCP deployment itself (e.g., `MCP_ENV=lab|staging|prod`).

- **MCP-specific configuration** (new):

  - **MCP server metadata**:

    - `MCP_SERVER_NAME` (e.g., "routeros-mcp")
    - `MCP_SERVER_VERSION` (semantic version, e.g., "1.2.3")
    - `MCP_SERVER_DESCRIPTION` (brief description for MCP clients)

  - **MCP transport configuration**:

    - `MCP_TRANSPORT` (stdio, http) - Phase 1: stdio only; Phase 2: both supported
    - `MCP_HTTP_PORT` (default: 8080) for HTTP/SSE transport (Phase 2)
    - `MCP_HTTP_BASE_PATH` (default: "/mcp") for reverse proxy integration (Phase 2)
    - `MCP_HTTP_HOST` (default: "127.0.0.1") for HTTP server binding (Phase 2)
    - Note: HTTP/SSE transport scaffold exists but not functional in Phase 1

  - **MCP protocol features**:

    - `MCP_ENABLE_TOOLS` (default: true)
    - `MCP_ENABLE_RESOURCES` (default: false, Phase 2)
    - `MCP_ENABLE_PROMPTS` (default: false, Phase 2)
    - `MCP_ENABLE_SAMPLING` (default: false, future)

  - **MCP tool configuration**:

    - `MCP_TOOL_TIERS` (comma-separated, e.g., "free,basic,professional")
    - `MCP_DEFAULT_TOOL_TIER` (default: "free")
    - `MCP_TOKEN_BUDGET_WARNING_THRESHOLD` (default: 5000)
    - `MCP_TOKEN_BUDGET_ERROR_THRESHOLD` (default: 50000)

  - **MCP resource configuration** (Phase 2):

    - `MCP_RESOURCE_CACHE_ENABLED` (default: false)
    - `MCP_RESOURCE_CACHE_TTL_SECONDS` (default: 300)
    - `MCP_RESOURCE_CACHE_MAX_ENTRIES` (default: 1000)

  - **MCP client compatibility**:
    - `MCP_CLIENT_COMPATIBILITY_MODE` (strict, permissive)
    - `MCP_LOG_UNKNOWN_CAPABILITIES` (default: true)

- **Per-environment overrides**:
  - Use separate configuration profiles for lab, staging, prod.
  - Avoid sharing secrets or DBs between environments.
  - Capability flags default more permissive in lab, restrictive in prod.
  - **MCP-specific overrides**:
    - Lab: `MCP_ENABLE_RESOURCES=true`, `MCP_CLIENT_COMPATIBILITY_MODE=permissive` for testing
    - Staging: All MCP features enabled for integration testing
    - Production: Conservative feature flags, `MCP_CLIENT_COMPATIBILITY_MODE=strict`

**Configuration validation on startup:**

The MCP server MUST validate all configuration on startup before accepting client connections:

1. **Database connectivity**: Verify database connection with timeout
2. **MCP schema validation**: Validate all tool JSON schemas are well-formed
3. **Transport availability**: Verify configured transports can bind (ports, stdio)
4. **RouterOS connectivity**: Test connection to at least one device for health check
5. **Secret availability**: Verify all required secrets are accessible
6. **Feature flag consistency**: Warn if conflicting feature flags detected

Example startup validation pseudocode:

```python
async def validate_startup_configuration():
    """Validate configuration before accepting MCP client connections."""
    errors = []
    warnings = []

    # Database connectivity
    try:
        await db.execute("SELECT 1")
    except Exception as e:
        errors.append(f"Database connection failed: {e}")

    # MCP tool schema validation
    for tool in load_all_tool_schemas():
        try:
            validate_json_schema(tool.input_schema)
        except Exception as e:
            errors.append(f"Invalid tool schema {tool.name}: {e}")

    # Transport binding
    if config.MCP_TRANSPORT_MODE in ("http", "both"):
        try:
            await bind_http_server(config.MCP_HTTP_PORT)
        except Exception as e:
            errors.append(f"Cannot bind HTTP transport on port {config.MCP_HTTP_PORT}: {e}")

    # RouterOS device connectivity (at least one reachable)
    devices = await db.get_active_devices()
    if not devices:
        warnings.append("No active RouterOS devices configured")
    else:
        reachable_count = 0
        for device in devices[:5]:  # Test first 5
            if await test_device_connectivity(device):
                reachable_count += 1
        if reachable_count == 0:
            errors.append("No RouterOS devices are reachable")

    # Feature flag validation
    if config.MCP_ENABLE_RESOURCES and not config.MCP_RESOURCE_CACHE_ENABLED:
        warnings.append("Resources enabled but cache disabled - may impact performance")

    if errors:
        raise StartupValidationError(f"Startup validation failed: {errors}")

    if warnings:
        logger.warning("Startup validation warnings", extra={"warnings": warnings})

    logger.info("Startup validation passed", extra={
        "mcp_server_name": config.MCP_SERVER_NAME,
        "mcp_server_version": config.MCP_SERVER_VERSION,
        "transport_mode": config.MCP_TRANSPORT_MODE,
        "features_enabled": {
            "tools": config.MCP_ENABLE_TOOLS,
            "resources": config.MCP_ENABLE_RESOURCES,
            "prompts": config.MCP_ENABLE_PROMPTS
        }
    })
```

---

## Deployment modes (systemd unit, container orchestrator, or both)

### MCP Transport Modes

The MCP server supports multiple transport modes that affect deployment architecture:

1. **Stdio transport** (default for MCP protocol):

   - MCP client launches the server as a subprocess
   - Communication via stdin/stdout using JSON-RPC over stdio
   - **Pros**: Simple, no network configuration, secure (local process isolation)
   - **Cons**: One client per server instance, no horizontal scaling, process lifecycle tied to client

2. **HTTP/SSE transport** (alternative):

   - MCP server runs as a persistent HTTP service
   - Communication via HTTP with Server-Sent Events for server-to-client messages
   - **Pros**: Multiple clients, horizontal scaling, independent lifecycle, load balancing
   - **Cons**: Requires network configuration, authentication/authorization complexity

3. **Both transports** (recommended for production):
   - Server supports both stdio and HTTP/SSE simultaneously
   - Stdio for local development/testing
   - HTTP/SSE for production multi-client deployments

**Transport mode selection guidance:**

| Environment       | Transport Mode | Rationale                                                |
| ----------------- | -------------- | -------------------------------------------------------- |
| Local development | stdio          | Simplest setup, matches MCP client expectations          |
| Lab               | stdio or http  | Test both modes, validate HTTP reverse proxy config      |
| Staging           | both           | Validate both transports work, test client compatibility |
| Production        | http (or both) | Multi-client support, horizontal scaling, load balancing |

### Systemd-based Deployment

**For stdio transport:**

```ini
# /etc/systemd/system/routeros-mcp-stdio@.service
[Unit]
Description=RouterOS MCP Server (stdio) for %i
After=network.target postgresql.service

[Service]
Type=exec
User=mcp
Group=mcp
Environment="MCP_TRANSPORT_MODE=stdio"
Environment="MCP_ENV=production"
EnvironmentFile=/etc/routeros-mcp/config.env
ExecStart=/usr/local/bin/routeros-mcp-server
StandardInput=socket
StandardOutput=socket
StandardError=journal
Restart=on-failure
RestartSec=5s

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/routeros-mcp

[Install]
WantedBy=multi-user.target
```

**For HTTP/SSE transport:**

```ini
# /etc/systemd/system/routeros-mcp-http.service
[Unit]
Description=RouterOS MCP Server (HTTP/SSE)
After=network.target postgresql.service

[Service]
Type=notify
User=mcp
Group=mcp
Environment="MCP_TRANSPORT_MODE=http"
Environment="MCP_HTTP_PORT=8080"
Environment="MCP_ENV=production"
EnvironmentFile=/etc/routeros-mcp/config.env
ExecStart=/usr/local/bin/routeros-mcp-server
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=10s
WatchdogSec=30s

# Health check endpoint for systemd
ExecStartPre=/usr/local/bin/routeros-mcp-preflight-check

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/routeros-mcp

[Install]
WantedBy=multi-user.target
```

**Systemd socket activation** (optional for stdio):

```ini
# /etc/systemd/system/routeros-mcp.socket
[Unit]
Description=RouterOS MCP Server Socket

[Socket]
ListenStream=0.0.0.0:8080
Accept=false

[Install]
WantedBy=sockets.target
```

**Cloudflare Tunnel integration:**

- Cloudflare Tunnel runs as a separate systemd service
- Tunnels HTTP/SSE transport to public URL for remote clients
- Example: `cloudflared tunnel --url http://localhost:8080 run routeros-mcp`

### Container-based Deployment

**Docker Compose example:**

```yaml
# docker-compose.yml
version: "3.8"

services:
  routeros-mcp:
    image: routeros-mcp:1.2.3
    environment:
      - MCP_TRANSPORT_MODE=http
      - MCP_HTTP_PORT=8080
      - MCP_SERVER_NAME=routeros-mcp
      - MCP_SERVER_VERSION=1.2.3
      - MCP_ENV=production
      - DATABASE_URL=postgresql://postgres:5432/routeros_mcp
      - OIDC_ISSUER=https://auth.example.com
    env_file:
      - .env.production
    ports:
      - "8080:8080"
    volumes:
      - mcp-data:/var/lib/routeros-mcp
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 30s
    restart: unless-stopped

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=routeros_mcp
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD_FILE=/run/secrets/db_password
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
    secrets:
      - db_password

  cloudflared:
    image: cloudflare/cloudflared:latest
    command: tunnel --url http://routeros-mcp:8080 run routeros-mcp
    depends_on:
      - routeros-mcp
    restart: unless-stopped

volumes:
  mcp-data:
  postgres-data:

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

**Kubernetes deployment example:**

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: routeros-mcp
  namespace: mcp-production
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: routeros-mcp
  template:
    metadata:
      labels:
        app: routeros-mcp
        version: "1.2.3"
    spec:
      containers:
        - name: mcp-server
          image: routeros-mcp:1.2.3
          ports:
            - containerPort: 8080
              name: http
              protocol: TCP
          env:
            - name: MCP_TRANSPORT_MODE
              value: "http"
            - name: MCP_HTTP_PORT
              value: "8080"
            - name: MCP_ENV
              value: "production"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: routeros-mcp-secrets
                  key: database-url
            - name: OIDC_CLIENT_SECRET
              valueFrom:
                secretKeyRef:
                  name: routeros-mcp-secrets
                  key: oidc-client-secret
          envFrom:
            - configMapRef:
                name: routeros-mcp-config
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 2
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2000m"
          volumeMounts:
            - name: data
              mountPath: /var/lib/routeros-mcp
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: routeros-mcp-data
---
apiVersion: v1
kind: Service
metadata:
  name: routeros-mcp
  namespace: mcp-production
spec:
  type: ClusterIP
  selector:
    app: routeros-mcp
  ports:
    - port: 8080
      targetPort: 8080
      protocol: TCP
      name: http
  sessionAffinity: ClientIP # For MCP client session consistency
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: routeros-mcp-config
  namespace: mcp-production
data:
  MCP_SERVER_NAME: "routeros-mcp"
  MCP_SERVER_VERSION: "1.2.3"
  MCP_ENABLE_TOOLS: "true"
  MCP_ENABLE_RESOURCES: "false"
  MCP_ENABLE_PROMPTS: "false"
  MCP_TOKEN_BUDGET_WARNING_THRESHOLD: "5000"
  MCP_CLIENT_COMPATIBILITY_MODE: "strict"
```

### Common Deployment Patterns

In both modes:

- **Health and readiness endpoints**: Used for orchestration (k8s probes or systemd watchdogs)

  - Health endpoint: `/health` (returns 200 OK or 503 Service Unavailable)
  - Readiness endpoint: Same as health, checks database connectivity and at least one RouterOS device reachable
  - Metrics endpoint: `/metrics` (Prometheus format)

- **Horizontal scaling** (HTTP/SSE transport only):

  - Multiple instances behind load balancer
  - Session affinity recommended (ClientIP or cookie-based) for MCP client session consistency
  - Database connection pooling with appropriate pool size per instance
  - Shared cache layer (Redis) for resource caching in Phase 2

- **Graceful shutdown**:

  - On SIGTERM, server stops accepting new MCP requests
  - In-flight tool calls are allowed to complete (with timeout, e.g., 30 seconds)
  - Database connections drained
  - Then exit with code 0

- **Zero-downtime deployments**:
  - Rolling update strategy (one instance at a time)
  - Health checks ensure new instances are ready before old ones terminate
  - Tool execution state is ephemeral (no long-running state), safe to restart

---

## Deployment pipelines (build, test, deploy, rollback)

- **Build stage**:
  - Linting, unit tests, and basic integration tests run in CI.
  - **MCP-specific validation**:
    - Validate all tool JSON schemas are well-formed
    - Check tool names follow naming conventions (e.g., `category.action` format)
    - Verify tool tier assignments are valid
    - Validate MCP server capabilities declaration
    - Ensure no duplicate tool names across tiers
  - Container image built and tagged (e.g., with git SHA or semantic version).
  - **Generate MCP tool catalog**: Export tool definitions to JSON for client documentation

Example CI validation script:

```bash
#!/bin/bash
# ci/validate-mcp-tools.sh

set -e

echo "Validating MCP tool schemas..."

# Load all tool schemas and validate JSON Schema format
python3 << 'EOF'
import json
import sys
from pathlib import Path
from jsonschema import Draft7Validator, ValidationError

tools_dir = Path("src/mcp/tools")
errors = []

for tool_file in tools_dir.glob("**/*.json"):
    with open(tool_file) as f:
        tool_schema = json.load(f)

    # Validate JSON Schema itself
    try:
        Draft7Validator.check_schema(tool_schema.get("inputSchema", {}))
    except ValidationError as e:
        errors.append(f"{tool_file}: Invalid JSON Schema - {e.message}")

    # Validate tool name format
    tool_name = tool_schema.get("name", "")
    if "." not in tool_name:
        errors.append(f"{tool_file}: Tool name '{tool_name}' must use 'category.action' format")

    # Validate tier assignment
    tier = tool_schema.get("tier", "")
    if tier not in ["free", "basic", "professional"]:
        errors.append(f"{tool_file}: Invalid tier '{tier}'")

if errors:
    print("MCP tool validation failed:")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)

print(f"✓ All {len(list(tools_dir.glob('**/*.json')))} tool schemas valid")
EOF

echo "Checking for duplicate tool names..."
python3 << 'EOF'
import json
from pathlib import Path
from collections import Counter

tools_dir = Path("src/mcp/tools")
tool_names = []

for tool_file in tools_dir.glob("**/*.json"):
    with open(tool_file) as f:
        tool_schema = json.load(f)
    tool_names.append(tool_schema.get("name"))

duplicates = [name for name, count in Counter(tool_names).items() if count > 1]
if duplicates:
    print(f"Duplicate tool names found: {duplicates}")
    exit(1)

print(f"✓ No duplicate tool names")
EOF

echo "Generating MCP tool catalog..."
python3 -m src.mcp.generate_catalog --output dist/mcp-tool-catalog.json

echo "✓ MCP tool validation complete"
```

- **Pre-deploy tests**:
  - Deploy to a lab environment and run end-to-end tests:
    - **MCP protocol tests**:
      - Test MCP initialization handshake (`initialize` method)
      - Verify server capabilities match configuration
      - Test `tools/list` returns all expected tools for each tier
      - Validate tool JSON schemas in `tools/list` response
    - **Tool execution tests**:
      - Execute each tool with valid inputs (smoke test)
      - Verify tool responses match expected schema
      - Test tool execution with invalid inputs (negative tests)
      - Verify estimated tokens are included in responses
    - **Integration tests**:
      - Test against one or more lab RouterOS devices
      - Validate device connectivity and credential storage
      - Test audit logging for tool executions
      - Verify RBAC enforcement (if applicable)
    - **Performance tests**:
      - Measure tool execution latency (p50, p95, p99)
      - Test concurrent tool executions
      - Validate token budget calculations

Example MCP protocol test:

```python
# tests/e2e/test_mcp_protocol.py
import pytest
from mcp_client import MCPClient

@pytest.mark.asyncio
async def test_mcp_initialization():
    """Test MCP initialize handshake."""
    client = MCPClient(transport="stdio", command=["./routeros-mcp-server"])

    # Send initialize request
    response = await client.initialize(
        protocol_version="2024-11-05",
        capabilities={"tools": {}},
        client_info={"name": "test-client", "version": "1.0.0"}
    )

    # Verify server capabilities
    assert response["protocolVersion"] == "2024-11-05"
    assert "tools" in response["capabilities"]
    assert response["serverInfo"]["name"] == "routeros-mcp"

    # Verify tools/list
    tools_response = await client.call_method("tools/list")
    tool_names = [tool["name"] for tool in tools_response["tools"]]

    # Expected free tier tools (Phase 0)
    assert "system.get_overview" in tool_names
    assert "system.get_health" in tool_names

    await client.close()

@pytest.mark.asyncio
async def test_tool_execution():
    """Test tools/call execution."""
    client = MCPClient(transport="stdio", command=["./routeros-mcp-server"])
    await client.initialize()

    # Execute a read-only tool
    response = await client.call_tool(
        name="system.get_overview",
        arguments={"device_id": "test-device-001"}
    )

    # Verify response structure
    assert "content" in response
    assert len(response["content"]) > 0
    assert response["content"][0]["type"] == "text"

    # Verify metadata
    assert "_meta" in response
    assert "estimated_tokens" in response["_meta"]
    assert response["_meta"]["estimated_tokens"] > 0

    await client.close()
```

- **Deploy stage**:

  - Staged rollout:
    - Lab → staging → production.
    - For production, introduce changes to a subset of instances first (canary deployment).
  - **MCP-specific deployment validation**:
    - After deployment, verify MCP protocol initialization succeeds
    - Test `tools/list` returns expected tools for the deployed version
    - Smoke test critical tools (e.g., `system.get_overview`)
    - Verify health endpoint returns 200 OK
    - Check metrics endpoint exports MCP-specific metrics

- **Rollback**:
  - CI/CD must support rapid rollback to a previous known-good version.
  - Rollback includes:
    - Application binaries/containers.
    - Configuration (versioned).
    - Database migrations (see next section).
  - **MCP-specific rollback considerations**:
    - **Tool schema compatibility**: New version may have added/removed tools
      - Document breaking changes in release notes
      - Clients may have cached tool list from `tools/list`
      - Consider deprecation period for tool removals
    - **Client compatibility**: Ensure rolled-back version still supports connected clients
      - If new protocol features were added, ensure graceful degradation
    - **In-flight tool executions**: Allow in-flight tool calls to complete before shutdown
      - Graceful shutdown period (30 seconds)
      - Log incomplete tool executions for investigation

---

## Database/schema and data migrations strategy

- **Schema migrations**:

  - Managed via a migration tool (e.g., Alembic, Flyway, Liquibase).
  - Migrations are versioned and applied in order as part of deployment.

- **Backward compatibility**:

  - Whenever possible, migrations are:
    - **Additive** (adding columns/tables) before removing old fields.
    - Carefully designed so that old application versions can still function during rollout.

- **Rollback of migrations**:
  - For high-risk schema changes, define reversible migrations or a data backup strategy.
  - For non-trivial migrations, deploy in two phases (add new schema, deploy code; only later remove old schema).

---

## Device lifecycle operations (register, update metadata, rotate credentials, decommission)

- **Register**:

  - Phase 0: define the Device and Credential model and enable secure storage (no user-facing input yet).
  - Phase 1: operator uses a secured **admin HTTP API** to:
    - Provide device management address, environment, tags.
    - Provide RouterOS credentials (or reference to a secret).
    - Confirm connectivity and basic health (using Phase 0–1 tools).
  - Phase 2: add convenience tooling on top of the admin API:
    - A CLI wrapper for registration flows.
    - A simple browser-based admin console for device onboarding and credential rotation.
  - Phase 3: optionally add automated onboarding:
    - A RouterOS-side bootstrap script or similar mechanism that creates MCP service accounts and reports credentials to the MCP registration API in a controlled way.

- **Update metadata**:

  - Change name, tags, environment, capability flags as needed.
  - Such changes may require explicit approval or admin-only rights.

- **Rotate credentials**:

  - Operator triggers rotation for a device:
    - MCP creates new secret on RouterOS (via appropriate method).
    - Updates stored credentials.
    - Validates that operations work with new credentials.
    - Disables old credential.

- **Decommission**:
  - MCP marks device as inactive.
  - Optionally triggers cleanup on RouterOS (e.g., removing service accounts), if policy allows.
  - Retains audit events and selected snapshots for historical reference.

---

## Self-update and versioning strategy for MCP tools and service

- **Service versioning**:

  - Semantic versioning (e.g., `1.2.3`).
  - Clearly indicate breaking changes in major versions.

- **Tool versioning**:

  - Tools may embed version identifiers (e.g., `system.get_overview.v1`).
  - New incompatible behavior introduces new tool versions; old ones are deprecated and eventually removed.

- **Self-update**:

  - Where supported, the service may:
    - Check for new versions (e.g., via a release endpoint).
    - Notify operators via logs or UI; it should not silently self-upgrade in production.
  - Actual upgrade is preferred via external CI/CD, not fully self-managed.

- **Rollout strategy**:
  - New versions:
    - First deployed and tested in lab.
    - Then in staging.
    - Lastly in production, possibly with canary instances.

---

## Rollback procedures (service binaries, configuration, database, and RouterOS-facing behavior)

- **Service & config rollback**:

  - Maintain previous app versions and configuration snapshots.
  - If a new version causes issues:
    - Roll back container image or binary.
    - Restore previous configuration (from version control or config store).

- **Database rollback**:

  - For additive migrations, rollback often not needed if old version can work with new schema.
  - For destructive changes:
    - Take DB backups before migration.
    - Roll back to a backup only in severe cases, accepting some downtime if necessary.

- **RouterOS-facing behavior**:
  - Rollbacks must ensure:
    - No half-applied plans are left in limbo.
    - High-risk tools can be disabled quickly (e.g., via config flag) if misbehavior is discovered.

---

## Backup/restore procedures and disaster recovery

- **Backups**:

  - Database backups on a regular schedule (e.g., daily full, incremental as supported).
  - Snapshot of configuration (app config, secrets references, not secrets themselves).
  - Optional snapshots of critical RouterOS configs (if policy allows).

- **Restore**:

  - Document steps to:
    - Restore DB to a new instance.
    - Redeploy MCP pointing at the restored DB.
    - Re-establish connections to RouterOS devices and IdP.

- **Disaster recovery**:
  - Define RPO (Recovery Point Objective) and RTO (Recovery Time Objective) for each environment.
  - Ensure backup and restore processes are periodically tested.

---

## Runbooks for common incidents (RouterOS API down, auth failures, misbehaving tools)

Example incident types and high-level runbook bullets:

### MCP Protocol-Level Incidents

- **MCP protocol errors (malformed JSON-RPC)**:

  - **Symptoms**: `mcp_requests_total{method="*",status="protocol_error"}` increasing
  - **Diagnosis**:
    - Check logs for JSON-RPC parsing errors: `grep "protocol_error" /var/log/routeros-mcp/mcp.log`
    - Identify problematic client from `client_info` in logs
    - Review correlation ID to trace full request/response
  - **Remediation**:
    - If client is using incompatible MCP protocol version, notify client to upgrade
    - If server is rejecting valid requests, check `MCP_CLIENT_COMPATIBILITY_MODE` setting
    - Review recent server changes for protocol compatibility issues
  - **Prevention**:
    - Add protocol version validation in pre-deploy tests
    - Document supported MCP protocol versions in API docs

- **MCP tool execution failures**:

  - **Symptoms**: `mcp_tool_requests_total{tool_name="*",status="error"}` spiking
  - **Diagnosis**:
    - Identify failing tool: `promql: topk(5, increase(mcp_tool_requests_total{status="error"}[5m]))`
    - Review tool execution logs: `grep "tool_name=system.get_overview" /var/log/routeros-mcp/mcp.log | grep ERROR`
    - Check for common error patterns: device unreachable, timeout, invalid arguments
  - **Remediation**:
    - If RouterOS device unreachable, follow "RouterOS REST/SSH unavailable" runbook
    - If tool arguments invalid, check for client-side validation issues
    - If tool implementation bug, disable tool via feature flag: `MCP_DISABLE_TOOLS=system.broken_tool`
    - Roll back to previous version if tool regression detected
  - **Prevention**:
    - Add negative test cases for tool execution in CI/CD
    - Monitor tool error rates and set up alerts for anomalies

- **Token budget violations**:

  - **Symptoms**: `mcp_tool_token_budget_warnings_total` or `mcp_tool_token_budget_errors_total` increasing
  - **Diagnosis**:
    - Identify tools returning large responses: `promql: topk(5, mcp_tool_estimated_tokens{tool_name="*"})`
    - Check if specific devices or queries triggering large responses
    - Review logs for specific tool invocations exceeding budget
  - **Remediation**:
    - Temporarily increase token budget thresholds: `MCP_TOKEN_BUDGET_WARNING_THRESHOLD=10000`
    - Implement pagination for large result sets (if applicable)
    - Add filtering options to tools to reduce response size
    - Notify clients to use more specific queries or filtering
  - **Prevention**:
    - Set reasonable token budget thresholds in production
    - Add response size limits in tool implementation
    - Document expected response sizes for each tool

- **MCP resource cache issues** (Phase 2):
  - **Symptoms**: `mcp_resource_cache_misses_total` high, performance degradation
  - **Diagnosis**:
    - Check cache hit ratio: `promql: mcp_resource_cache_hits / (mcp_resource_cache_hits + mcp_resource_cache_misses)`
    - Review cache size and eviction patterns
    - Check for cache TTL expiration patterns
  - **Remediation**:
    - Increase cache size: `MCP_RESOURCE_CACHE_MAX_ENTRIES=5000`
    - Increase cache TTL: `MCP_RESOURCE_CACHE_TTL_SECONDS=600`
    - Flush cache if stale data suspected: `curl -X POST http://localhost:8080/admin/cache/flush`
  - **Prevention**:
    - Monitor cache efficiency metrics
    - Tune cache settings based on usage patterns

### RouterOS Integration Incidents

- **RouterOS REST/SSH unavailable**:

  - **Symptoms**: `routeros_device_reachable{device_id="*"}` dropping, tool execution failures
  - **Diagnosis**:
    - Check network connectivity between MCP and device: `ping <device_ip>`
    - Verify RouterOS service availability: `curl http://<device_ip>/rest/system/resource`
    - Review MCP logs for error codes and diagnostics for the device
    - Check device-specific metrics: `promql: routeros_api_errors_total{device_id="device-001"}`
  - **Remediation**:
    - If network issue, investigate firewall rules, routing, VPN tunnels
    - If RouterOS service down, check device health, restart services on device
    - If credentials invalid, rotate credentials via device management API
    - If many devices affected, investigate upstream network or firewall changes
  - **Prevention**:
    - Set up proactive device health monitoring with alerts
    - Implement automated credential rotation
    - Document network topology and dependencies

- **Device credential rotation failures**:
  - **Symptoms**: Credential rotation job failing, manual credential updates rejected
  - **Diagnosis**:
    - Check credential rotation logs: `grep "credential_rotation" /var/log/routeros-mcp/jobs.log`
    - Verify current credentials still work: Test connection via admin API
    - Check RouterOS user permissions for credential management
  - **Remediation**:
    - Manually rotate credentials via RouterOS console if automated rotation fails
    - Update stored credentials in MCP database
    - Verify new credentials work before disabling old ones
  - **Prevention**:
    - Test credential rotation in lab environment regularly
    - Implement credential rotation dry-run mode

### Authentication and Authorization Incidents

- **Auth failures (IdP or token issues)**:

  - **Symptoms**: `auth_failures_total` spiking, users unable to connect
  - **Diagnosis**:
    - Check IdP health dashboards and status page
    - Validate configuration (issuer, client ID, secrets): `env | grep OIDC`
    - Check token expiration and refresh logic
    - Review logs for specific error codes: `grep "auth_error" /var/log/routeros-mcp/auth.log`
  - **Remediation**:
    - If IdP down, wait for recovery or activate break-glass access
    - If configuration issue, validate OIDC client secret: `curl https://<idp>/.well-known/openid-configuration`
    - If token refresh failing, check refresh token expiration policies
    - Consider activating break-glass access for essential operations (e.g., local admin accounts)
  - **Prevention**:
    - Set up IdP health monitoring and alerts
    - Implement break-glass access procedures
    - Document OIDC configuration and troubleshooting steps

- **RBAC permission errors**:
  - **Symptoms**: Users reporting access denied errors, `rbac_authorization_denied_total` increasing
  - **Diagnosis**:
    - Check user roles and permissions in database
    - Review audit logs for denied operations
    - Identify specific tool or operation being denied
  - **Remediation**:
    - If incorrect role assignment, update user roles via admin API
    - If legitimate access needed, update RBAC policies
    - If bug in RBAC logic, disable strict RBAC temporarily: `MCP_RBAC_MODE=permissive`
  - **Prevention**:
    - Document RBAC roles and permissions clearly
    - Implement RBAC policy testing in CI/CD

### Tool and Workflow Incidents

- **Misbehaving tools (unexpected changes or error spikes)**:

  - **Symptoms**: Unexpected configuration changes on devices, audit log anomalies, tool error spikes
  - **Diagnosis**:
    - Identify tool(s) and user(s) from logs and audit events: `grep "audit_event" /var/log/routeros-mcp/audit.log`
    - Review correlation IDs to trace full request flow
    - Check tool execution parameters and device state changes
    - Review metrics for tool usage patterns: `promql: increase(mcp_tool_requests_total{tool_name="*"}[1h])`
  - **Remediation**:
    - Temporarily disable affected tools via feature flag: `MCP_DISABLE_TOOLS=firewall.add_rule,firewall.delete_rule`
    - If high-risk operations involved, pause all plan/apply workflows: `MCP_ENABLE_PLAN_APPLY=false`
    - Roll back device configuration if safe to do so
    - Investigate root cause: tool bug, user error, compromised credentials
    - Notify affected users and document incident
  - **Prevention**:
    - Implement tool usage rate limiting
    - Add anomaly detection for unusual tool usage patterns
    - Require multi-step approval for high-risk tools

- **Plan/apply workflow failures** (Professional tier):
  - **Symptoms**: Plans failing to apply, rollbacks triggering automatically, approval timeouts
  - **Diagnosis**:
    - Check plan execution logs: `grep "plan_id=<plan_id>" /var/log/routeros-mcp/workflows.log`
    - Review rollback reasons: `promql: mcp_rollbacks_triggered_total{reason="*"}`
    - Check approval token usage and timeouts
  - **Remediation**:
    - If rollback triggered, review device state to confirm rollback success
    - If approval timeout, extend approval window: `MCP_PLAN_APPROVAL_TIMEOUT_SECONDS=1800`
    - If plan execution failed, review error details and retry manually
    - If automatic rollback failed, manual intervention required
  - **Prevention**:
    - Test plan/apply workflows in lab environment
    - Set appropriate approval timeouts based on operational needs
    - Document rollback procedures and test regularly

### Performance and Scaling Incidents

- **Performance degradation**:

  - **Symptoms**: Tool execution latency increasing, timeouts, slow responses
  - **Diagnosis**:
    - Inspect metrics: CPU/memory on MCP instances, DB load, RouterOS API latency
    - Check tool execution latency: `promql: histogram_quantile(0.95, mcp_tool_latency_seconds)`
    - Review database connection pool usage: `promql: database_connection_pool_active`
    - Check for slow queries: `grep "slow_query" /var/log/postgresql/postgres.log`
  - **Remediation**:
    - Scale out MCP instances if CPU/memory saturated
    - Increase database connection pool size: `DATABASE_POOL_SIZE=50`
    - Reduce health check and metrics collection frequency if necessary
    - Optimize slow database queries (add indexes, rewrite queries)
    - Enable resource caching (Phase 2): `MCP_RESOURCE_CACHE_ENABLED=true`
  - **Prevention**:
    - Set up performance monitoring and alerts
    - Load test before production deployments
    - Document scaling procedures and thresholds

- **Database connection pool exhaustion**:
  - **Symptoms**: `database_connection_pool_wait_time` increasing, tool execution failures
  - **Diagnosis**:
    - Check active connections: `promql: database_connection_pool_active`
    - Review long-running queries: `SELECT * FROM pg_stat_activity WHERE state = 'active' AND query_start < now() - interval '1 minute'`
    - Check for connection leaks in application code
  - **Remediation**:
    - Increase connection pool size: `DATABASE_POOL_SIZE=100`
    - Kill long-running queries if blocking others
    - Restart MCP instances to reset connection pool
  - **Prevention**:
    - Monitor connection pool metrics
    - Implement connection pool overflow handling
    - Test connection pool under load

---

### Incident Response Template

For each incident, follow this template:

1. **Detect**: Alert fires or user reports issue
2. **Triage**: Identify affected components, severity, impact scope
3. **Diagnose**: Review logs, metrics, traces using correlation IDs
4. **Remediate**: Apply immediate fix, restore service
5. **Document**: Record incident details, timeline, resolution in incident log
6. **Follow-up**: Root cause analysis, preventive actions, runbook updates

Each runbook should be expanded in the ops documentation with step-by-step commands and dashboards specific to the deployment.

---

## Summary

This document provides comprehensive operational guidance for deploying and maintaining the RouterOS MCP service with MCP protocol-specific considerations:

**Core Operations Capabilities:**

- **MCP-aware configuration**: Server metadata, transport modes, protocol features, tool tiers, token budgets
- **Startup validation**: Automated checks for database, tool schemas, transport binding, device connectivity
- **Multiple transport modes**: Stdio (simple), HTTP/SSE (scalable), or both (flexible)
- **Production-ready deployment**: Systemd units, Docker Compose, Kubernetes with health checks and graceful shutdown
- **CI/CD integration**: Automated tool schema validation, MCP protocol testing, canary deployments
- **Database migrations**: Backward-compatible, reversible, tested with rollback strategies
- **Comprehensive runbooks**: MCP protocol errors, tool failures, token violations, performance issues

**MCP Integration Highlights:**

- **Transport flexibility**: Support for both stdio (1:1 client-server) and HTTP/SSE (multi-client) transports
- **Tool lifecycle management**: Schema validation, versioning, deprecation, feature flags for disabling problematic tools
- **Protocol testing**: Automated tests for MCP initialization, tool listing, tool execution, client compatibility
- **Graceful operations**: In-flight tool call completion during shutdown, zero-downtime rolling updates
- **Incident response**: Specific runbooks for MCP protocol errors, token budget violations, resource cache issues

**Operational Benefits:**

- **Fast deployment**: Validated configurations, automated testing, staged rollouts reduce deployment risk
- **Easy troubleshooting**: Correlation IDs, structured logs, MCP-specific metrics enable rapid incident diagnosis
- **Scalable architecture**: HTTP/SSE transport with load balancing supports horizontal scaling
- **Safe rollbacks**: Tool schema compatibility, client compatibility, graceful degradation ensure safe rollbacks
- **Proactive monitoring**: Health checks, readiness probes, metrics, alerts catch issues before users affected

**Cross-references:**

- See [Doc 04 (MCP Tools Interface)](04-mcp-tools-interface-and-json-schema-specification.md) for tool JSON schema specifications
- See [Doc 08 (Observability)](08-observability-logging-metrics-and-diagnostics.md) for correlation IDs, metrics, and monitoring
- See [Doc 05 (Domain Model)](05-domain-model-persistence-and-task-job-model.md) for database schema and migrations
- See [Doc 07 (Device Control)](07-device-control-and-high-risk-operations-safeguards.md) for plan/apply workflows and rollback safeguards
- See [Doc 00 (Overview)](00-overview-and-objectives.md) for MCP protocol architecture and transport modes
