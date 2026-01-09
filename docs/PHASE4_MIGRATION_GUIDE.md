# Phase 4 Migration Guide

## Overview

This guide provides step-by-step instructions for upgrading from Phase 3 to Phase 4 of the RouterOS MCP service. Phase 4 introduces significant enhancements including diagnostics tools, multi-device coordination, HTTP/SSE transport, and real-time subscriptions.

**Target Audience**: System administrators, DevOps engineers, and operators managing RouterOS MCP deployments.

---

## What's New in Phase 4

### Key Features

1. **Diagnostics Tools Enabled (3 tools)**
   - `ping` - Network connectivity testing with real-time progress
   - `traceroute` - Path discovery and latency analysis
   - `bandwidth_test` - Throughput and performance measurement
   - All tools include rate limiting and safety guardrails

2. **Multi-Device Coordination**
   - Batch operations across multiple devices
   - Staged rollout support with health checks between stages
   - Multi-device plan/apply framework with rollback capabilities
   - Device group management and selective targeting

3. **HTTP/SSE Transport (Production-Ready)**
   - Full HTTP/SSE transport implementation
   - Real-time resource subscriptions via Server-Sent Events
   - OAuth 2.1/OIDC authentication and authorization
   - Load balancing and horizontal scaling support

4. **Long-Running Operations with Streaming**
   - JSON-RPC progress notifications
   - SSE-based real-time updates for long-running tasks
   - Comprehensive metrics and audit logging
   - Client-side progress tracking

5. **Enhanced Testing**
   - 19 comprehensive E2E tests covering Phase 4 features
   - Total test count: 583 tests (564 unit + 19 e2e)
   - 80%+ code coverage overall

### Tool Count Update

- **Phase 3**: 63 tools registered
- **Phase 4**: 66 tools registered (+3 diagnostics tools)

---

## Prerequisites

Before upgrading to Phase 4, ensure you have:

- [ ] **Phase 3 Complete**: All Phase 3 features operational
- [ ] **Database Backup**: Current backup of SQLite/PostgreSQL database
- [ ] **Python 3.11+**: Python 3.11 or higher installed
- [ ] **Dependencies Updated**: All Python dependencies up to date
- [ ] **Configuration Files**: Current config files backed up
- [ ] **Downtime Window**: Planned maintenance window (5-15 minutes)
- [ ] **OAuth Provider** (optional): OIDC provider configured if using HTTP transport

---

## Migration Steps

### Step 1: Backup Current Installation

```bash
# Backup database (SQLite example)
cp data/routeros_mcp.db data/routeros_mcp.db.backup.$(date +%Y%m%d_%H%M%S)

# Backup configuration
cp config/lab.yaml config/lab.yaml.backup
cp .env .env.backup 2>/dev/null || true

# Note current version
routeros-mcp --version > version_before_upgrade.txt
```

### Step 2: Update Code

```bash
# Pull latest changes
git pull origin master

# Or if using a release tag
git checkout v1.4.0  # Replace with actual Phase 4 version tag
```

### Step 3: Update Dependencies

```bash
# Activate virtual environment
source .venv/bin/activate

# Update dependencies
pip install -e .[dev] --upgrade

# Verify installation
routeros-mcp --version
```

### Step 4: Database Migration

Phase 4 does not introduce new database schema changes, but it's recommended to ensure migrations are current:

```bash
# Check current migration status
alembic current

# Apply any pending migrations
alembic upgrade head

# Verify migration succeeded
alembic current
```

**Expected Output**: Should show latest migration ID (same as Phase 3 if no schema changes).

### Step 5: Configuration Updates

#### For STDIO Transport (No Changes Required)

If you're using STDIO transport (default for local/Claude Desktop integration), no configuration changes are needed. The diagnostics tools are automatically available.

#### For HTTP/SSE Transport (Optional)

If you want to enable HTTP/SSE transport for remote clients or web UI integration, add the following to your configuration:

**config/production.yaml** (example):

```yaml
environment: prod
debug: false

# Enable HTTP/SSE transport
mcp_transport: http
mcp_http_host: "0.0.0.0"
mcp_http_port: 8080
mcp_http_base_path: "/mcp"

# Database (PostgreSQL recommended for production)
database_url: "postgresql+asyncpg://user:password@localhost:5432/routeros_mcp"

# OIDC Authentication (required for HTTP transport in production)
oidc_enabled: true
oidc_provider_url: "https://your-idp.example.com"
oidc_client_id: "your-client-id"
oidc_audience: "api://routeros-mcp"
oidc_skip_verification: false  # MUST be false in production

# Encryption key (REQUIRED)
# Generate with: python3 -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
# encryption_key: "your-base64-encoded-key"  # Set via environment variable instead
```

**Environment Variables** (recommended for secrets):

```bash
# Add to .env or secrets manager
export ROUTEROS_MCP_ENCRYPTION_KEY="your-base64-key-here"
export ROUTEROS_MCP_DATABASE_URL="postgresql+asyncpg://..."
export ROUTEROS_MCP_OIDC_CLIENT_ID="your-client-id"
```

See [docs/20-http-sse-transport-deployment-guide.md](20-http-sse-transport-deployment-guide.md) for detailed HTTP/SSE configuration.

### Step 6: Verify Diagnostics Tools

After restarting the service, verify diagnostics tools are available:

```bash
# Start service (STDIO mode)
routeros-mcp --config config/lab.yaml

# In another terminal, use MCP Inspector or client to list tools
# You should see: ping, traceroute, bandwidth_test
```

**Expected Tools Count**: 66 total tools (was 63 in Phase 3).

### Step 7: Test Multi-Device Features (Optional)

If you have multiple devices and want to test multi-device coordination:

```python
# Example: Multi-device health check using MCP client
# (This is illustrative - actual implementation depends on your client)

# Check health across all devices
for device in devices:
    result = await mcp_client.call_tool("device_health", device_id=device.id)
    print(f"{device.name}: {result['status']}")

# Use multi-device plan (if implemented in your workflow)
plan = await mcp_client.call_tool(
    "config_plan_dns_ntp_rollout",
    device_ids=["dev-lab-01", "dev-lab-02"],
    dns_servers=["8.8.8.8", "8.8.4.4"]
)
```

### Step 8: Update Monitoring and Alerts

If you have monitoring dashboards or alerts configured:

1. **Update Tool Count Alerts**: Change expected tool count from 63 → 66
2. **Add Diagnostics Metrics**: Monitor ping/traceroute/bandwidth_test usage
3. **SSE Connection Monitoring**: If using HTTP/SSE, monitor active SSE connections

---

## New Features Guide

### Using Diagnostics Tools

#### Ping

```python
# Example MCP tool call
result = await mcp_client.call_tool(
    "ping",
    device_id="dev-lab-01",
    target="8.8.8.8",
    count=4,
    packet_size=64
)

# With streaming progress (HTTP transport only)
result = await mcp_client.call_tool(
    "ping",
    device_id="dev-lab-01",
    target="8.8.8.8",
    count=10,
    stream_progress=True  # Get per-packet updates
)
```

**Rate Limits**: 10 pings per device per minute (configurable)

#### Traceroute

```python
result = await mcp_client.call_tool(
    "traceroute",
    device_id="dev-lab-01",
    target="1.1.1.1",
    max_hops=20
)
```

#### Bandwidth Test

```python
result = await mcp_client.call_tool(
    "bandwidth_test",
    device_id="dev-lab-01",
    target="192.168.1.100",
    duration_seconds=10,
    direction="both",  # upload, download, or both
    protocol="tcp"
)
```

### Multi-Device Coordination

Phase 4 introduces enhanced multi-device coordination through the existing plan/apply framework:

```python
# Create multi-device plan
plan = await mcp_client.call_tool(
    "config_plan_dns_ntp_rollout",
    device_ids=["dev-lab-01", "dev-lab-02", "dev-lab-03"],
    dns_servers=["8.8.8.8", "8.8.4.4"],
    ntp_servers=["time.cloudflare.com"]
)

# Review plan details
plan_details = await mcp_client.get_resource(f"plan://{plan['plan_id']}/details")

# Approve plan (generates HMAC token)
approval = await mcp_client.call_tool(
    "approve_plan",  # Admin CLI or API endpoint
    plan_id=plan["plan_id"]
)

# Apply with staged rollout
result = await mcp_client.call_tool(
    "config_apply_dns_ntp_rollout",
    plan_id=plan["plan_id"],
    approval_token=approval["token"],
    staged=True,  # Apply to devices sequentially with health checks
    batch_size=1  # Number of devices per stage
)
```

### HTTP/SSE Subscriptions

If using HTTP/SSE transport, subscribe to real-time updates:

```javascript
// JavaScript example (browser or Node.js)
const eventSource = new EventSource('/mcp/subscribe?resource=fleet://health-summary');

eventSource.onmessage = (event) => {
  const healthData = JSON.parse(event.data);
  console.log('Fleet health update:', healthData);
};

eventSource.onerror = (error) => {
  console.error('SSE connection error:', error);
};
```

---

## Breaking Changes

**Good News**: Phase 4 has **NO breaking changes** to the MCP protocol or existing tool signatures.

### What Remains Compatible

- ✅ All Phase 1-3 tools work unchanged
- ✅ Existing configuration files compatible (no required changes)
- ✅ Database schema unchanged (no data migration needed)
- ✅ STDIO transport fully backward compatible
- ✅ Plan/apply workflow unchanged
- ✅ Resource URIs and prompts unchanged

### What's Additive

- ✅ 3 new diagnostics tools (opt-in usage)
- ✅ HTTP/SSE transport (opt-in, STDIO remains default)
- ✅ Enhanced multi-device coordination (backward compatible with single-device workflows)
- ✅ Streaming progress (optional parameter, defaults to off)

---

## Rollback Instructions

If you encounter issues and need to rollback:

### Rollback Code

```bash
# Stop the service
pkill -f routeros-mcp || systemctl stop routeros-mcp

# Restore previous version
git checkout <previous-commit-or-tag>

# Restore dependencies
pip install -e .[dev]

# Restore configuration (if modified)
cp config/lab.yaml.backup config/lab.yaml
cp .env.backup .env 2>/dev/null || true
```

### Rollback Database (if needed)

```bash
# Restore database backup
cp data/routeros_mcp.db.backup.* data/routeros_mcp.db

# Or for PostgreSQL
# pg_restore -d routeros_mcp backup_file.sql
```

### Restart Service

```bash
# STDIO mode
routeros-mcp --config config/lab.yaml

# Or systemd
systemctl start routeros-mcp
```

---

## Validation Checklist

After migration, verify:

- [ ] Service starts without errors
- [ ] Tool count shows 66 (was 63 in Phase 3)
- [ ] All existing tools work as before
- [ ] New diagnostics tools are available
  - [ ] `ping` responds correctly
  - [ ] `traceroute` returns path data
  - [ ] `bandwidth_test` completes successfully
- [ ] Database queries work normally
- [ ] Existing plans and audit logs are accessible
- [ ] Health checks pass for all devices
- [ ] If using HTTP/SSE:
  - [ ] OAuth authentication works
  - [ ] SSE subscriptions connect
  - [ ] Real-time updates arrive

---

## Troubleshooting

### Issue: Diagnostics Tools Not Available

**Symptoms**: Tool count still shows 63 instead of 66.

**Solution**:
```bash
# Verify code is up to date
git log --oneline -5

# Check server.py has diagnostics registration
grep "register_diagnostics_tools" routeros_mcp/mcp/server.py

# Restart service
pkill -f routeros-mcp
routeros-mcp --config config/lab.yaml
```

### Issue: HTTP/SSE Transport Not Working

**Symptoms**: Connection refused or 401 Unauthorized when accessing HTTP endpoint.

**Solution**:
```bash
# Verify transport setting
grep "mcp_transport" config/production.yaml

# Check OIDC configuration
env | grep ROUTEROS_MCP_OIDC

# Review logs for authentication errors
journalctl -u routeros-mcp -n 50

# Test without authentication (lab only!)
curl http://localhost:8080/health
```

See [docs/20-http-sse-transport-deployment-guide.md](20-http-sse-transport-deployment-guide.md#troubleshooting) for detailed HTTP/SSE troubleshooting.

### Issue: Database Migration Fails

**Symptoms**: `alembic upgrade head` returns errors.

**Solution**:
```bash
# Check current migration state
alembic current

# Show migration history
alembic history

# If stuck, restore backup and retry
cp data/routeros_mcp.db.backup.* data/routeros_mcp.db
alembic upgrade head
```

### Issue: Performance Degradation

**Symptoms**: Slower response times after upgrade.

**Solution**:
```bash
# Check database connection pool
# Increase pool size in config if needed
database_pool_size: 20  # Default 5
database_max_overflow: 10

# Monitor active connections
# For PostgreSQL: SELECT count(*) FROM pg_stat_activity WHERE datname = 'routeros_mcp';

# Check for rate limiting on diagnostics
# Review rate limiter settings in config
```

---

## Support and Resources

### Documentation

- **Main README**: [README.md](../README.md)
- **HTTP/SSE Deployment**: [docs/20-http-sse-transport-deployment-guide.md](20-http-sse-transport-deployment-guide.md)
- **MCP Tools Specification**: [docs/04-mcp-tools-interface-and-json-schema-specification.md](04-mcp-tools-interface-and-json-schema-specification.md)
- **Testing Guide**: [docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md](10-testing-validation-and-sandbox-strategy-and-safety-nets.md)

### Getting Help

- **GitHub Issues**: Report bugs or issues at https://github.com/grammy-jiang/RouterOS-MCP/issues
- **Discussions**: Ask questions in GitHub Discussions
- **Pull Requests**: Contribute improvements following [CONTRIBUTING.md](../CONTRIBUTING.md)

### Community

- Review test cases in `tests/e2e/test_phase4_comprehensive.py` for usage examples
- Check example configurations in `config/` directory
- See `PHASE_FEATURES_SUMMARY.md` for detailed Phase 4 feature breakdown

---

## Conclusion

Phase 4 brings significant enhancements to the RouterOS MCP service while maintaining full backward compatibility. The migration process is straightforward with no breaking changes. Take advantage of new diagnostics tools, multi-device coordination, and HTTP/SSE transport to improve your network management workflows.

**Next Steps**:
1. Complete the migration checklist
2. Test diagnostics tools in your lab environment
3. Consider enabling HTTP/SSE transport for web UI integration
4. Review Phase 5 roadmap for upcoming multi-user RBAC features

For questions or issues during migration, please open a GitHub issue with:
- Migration step where issue occurred
- Error messages or logs
- Environment details (OS, Python version, database type)
- Configuration (sanitized, no secrets)

---

**Last Updated**: January 9, 2026  
**Version**: Phase 4 (1.4.0)  
**Status**: Production Ready ✅
