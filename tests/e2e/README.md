# E2E Tests for HTTP Transport

This directory contains end-to-end (E2E) tests for the RouterOS-MCP HTTP/SSE transport, validating integration with real MCP clients like Claude Desktop and VS Code.

## Overview

The E2E test suite tests the complete HTTP/SSE transport stack:
- MCP JSON-RPC protocol over HTTP
- Server-Sent Events (SSE) for streaming
- OIDC authentication and authorization
- Tool invocation and resource fetching
- Error handling and edge cases

## Test Environment

The E2E tests use Docker Compose to orchestrate a complete test environment:

### Services

1. **routeros-mcp** - RouterOS-MCP HTTP server
   - Runs on port 18765
   - Uses SQLite database (in-memory or file-based)
   - Exposes MCP protocol over HTTP/SSE

2. **mock-oidc** - Mock OAuth2/OIDC provider
   - Runs on port 18080
   - Provides OpenID Connect discovery and token validation
   - Based on [navikt/mock-oauth2-server](https://github.com/navikt/mock-oauth2-server)

3. **postgres** (optional) - PostgreSQL database
   - Runs on port 15432
   - Used for testing with real database
   - Can be disabled in favor of SQLite

## Running Tests

### Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ with project dependencies (`pip install -e .[dev]`)
- Free ports: 18765 (HTTP), 18080 (OIDC), 15432 (PostgreSQL)

### Quick Start

**Option 1: Using the helper script (recommended)**

```bash
# Run from project root
./tests/e2e/run_e2e_tests.sh

# Clean up previous containers first
./tests/e2e/run_e2e_tests.sh --clean
```

**Option 2: Manual Docker Compose workflow**

```bash
# Start services
docker-compose -f tests/e2e/docker-compose.yml up -d

# Wait for services to be ready (10-15 seconds)
sleep 15

# Run tests
pytest tests/e2e/test_http_transport_clients.py -v

# Stop services
docker-compose -f tests/e2e/docker-compose.yml down
```

**Option 3: One-liner for CI/scripts**

```bash
docker-compose -f tests/e2e/docker-compose.yml up -d && \
  sleep 15 && \
  (pytest tests/e2e/test_http_transport_clients.py -v; EXIT_CODE=$?; docker-compose -f tests/e2e/docker-compose.yml down; exit $EXIT_CODE)
```

## Test Coverage

### Current Tests (Phase 2)

✅ **Passing Tests** (5 tests)
- Direct HTTP JSON-RPC request handling
- Connection timeout handling
- Correlation ID propagation
- Concurrent request handling
- Malformed JSON error handling

⏭️ **Skipped Tests** (6 tests - awaiting Phase 3)
- MCP client tool invocation (`device_list`)
- Tool with parameters (`device_get`)
- Resource fetching (`device://` URIs)
- Error handling for invalid devices
- OIDC authentication (valid tokens)
- OIDC authentication (invalid tokens)

### Test Scenarios

1. **Tool Invocation**
   - Simple tools without parameters
   - Tools with required parameters
   - Tools with optional parameters

2. **Resource Fetching**
   - Device resources (`device://...`)
   - Fleet resources (`fleet://...`)
   - Plan resources (`plan://...`)

3. **Error Handling**
   - Invalid device IDs
   - Malformed JSON requests
   - Invalid JSON-RPC structure
   - Connection timeouts
   - Server unavailable

4. **Authentication** (Phase 3)
   - Valid OIDC tokens
   - Invalid/expired tokens
   - Missing authorization headers
   - Token validation errors

5. **Concurrency**
   - Multiple simultaneous requests
   - Correlation ID isolation
   - No data corruption

## Debugging

### View Service Logs

```bash
# All services
docker-compose -f tests/e2e/docker-compose.yml logs

# Specific service
docker-compose -f tests/e2e/docker-compose.yml logs routeros-mcp
docker-compose -f tests/e2e/docker-compose.yml logs mock-oidc
docker-compose -f tests/e2e/docker-compose.yml logs postgres

# Follow logs in real-time
docker-compose -f tests/e2e/docker-compose.yml logs -f routeros-mcp
```

### Check Service Health

```bash
# Mock OIDC discovery endpoint
curl http://localhost:18080/default/.well-known/openid-configuration

# PostgreSQL (requires psql client)
psql -h localhost -p 15432 -U mcp_test -d routeros_mcp_test

# RouterOS-MCP server (port check)
nc -zv localhost 18765
```

### Interactive Container Access

```bash
# Access RouterOS-MCP container
docker exec -it routeros-mcp-http-server /bin/bash

# Access PostgreSQL container
docker exec -it routeros-mcp-postgres-test /bin/bash
```

## CI Integration

The E2E tests run automatically in GitHub Actions:

**Triggers:**
- Push to `main` or `develop` branches
- Pull requests modifying transport or E2E test files
- Manual workflow dispatch

**Workflow:** `.github/workflows/e2e-http-transport.yml`

**Timeout:** 15 minutes total, 5 minutes per test

**Artifacts:** Test results and logs uploaded on failure

## Common Issues

### Port Already in Use

If you get "port already allocated" errors:

```bash
# Check what's using the port
lsof -i :18765
lsof -i :18080

# Stop existing containers
docker-compose -f tests/e2e/docker-compose.yml down
```

### Services Not Starting

Check Docker logs:

```bash
docker-compose -f tests/e2e/docker-compose.yml logs
```

Common issues:
- Database migration failures (check `routeros-mcp` logs)
- OIDC provider misconfiguration (check `mock-oidc` logs)
- Insufficient Docker resources (increase Docker Desktop limits)

### Tests Timing Out

If tests timeout waiting for services:

1. Increase wait time in script: `sleep 20` instead of `sleep 15`
2. Check service logs for startup errors
3. Verify all containers are running: `docker-compose -f tests/e2e/docker-compose.yml ps`

### Database Issues

If using PostgreSQL and encountering errors:

```bash
# Reset database
docker-compose -f tests/e2e/docker-compose.yml down -v
docker-compose -f tests/e2e/docker-compose.yml up -d postgres

# Or switch to SQLite (edit docker-compose.yml)
ROUTEROS_MCP_DATABASE_URL: sqlite+aiosqlite:////tmp/routeros_mcp_test.db
```

## Development

### Adding New Tests

1. Add test function to `test_http_transport_clients.py`
2. Use `@pytest.mark.asyncio` for async tests
3. Use `@pytest.mark.skip()` if feature not yet implemented
4. Follow naming convention: `test_<what>_<scenario>_<expected>`
5. Include docstring explaining what the test validates

Example:

```python
@pytest.mark.asyncio
@pytest.mark.skip(reason="Feature not yet implemented")
async def test_resource_subscription_sse() -> None:
    """Test SSE subscription to resource updates.
    
    Verifies that clients can subscribe to device resources
    and receive real-time updates via Server-Sent Events.
    """
    # Test implementation
    pass
```

### Modifying Docker Environment

Edit `docker-compose.yml` to:
- Change port mappings
- Add new services
- Modify environment variables
- Adjust health check intervals

After changes, rebuild:

```bash
docker-compose -f tests/e2e/docker-compose.yml build
```

## References

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Design Doc: Testing Strategy](../../docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md)
- [Design Doc: Transport Design](../../docs/14-mcp-protocol-integration-and-transport-design.md)
