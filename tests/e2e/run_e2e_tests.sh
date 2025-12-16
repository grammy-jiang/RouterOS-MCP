#!/bin/bash
# Helper script to run E2E tests for HTTP transport
# Usage: ./tests/e2e/run_e2e_tests.sh [--clean]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Parse arguments
CLEAN=false
if [ "$1" = "--clean" ]; then
    CLEAN=true
fi

echo "=== RouterOS-MCP E2E Test Runner ==="
echo "Project root: $PROJECT_ROOT"
echo ""

# Navigate to project root
cd "$PROJECT_ROOT"

# Clean up previous containers if requested
if [ "$CLEAN" = true ]; then
    echo "Cleaning up previous containers..."
    docker-compose -f tests/e2e/docker-compose.yml down -v
fi

# Start Docker Compose services
echo "Starting Docker Compose services..."
docker-compose -f tests/e2e/docker-compose.yml up -d

# Wait for services to be healthy
echo "Waiting for services to be ready..."
sleep 5

# Check mock OIDC
echo -n "Waiting for mock OIDC provider..."
timeout 60 bash -c 'until curl -f http://localhost:18080/default/.well-known/openid-configuration 2>/dev/null >/dev/null; do echo -n "."; sleep 2; done' || {
    echo ""
    echo "ERROR: Mock OIDC provider failed to start"
    docker-compose -f tests/e2e/docker-compose.yml logs mock-oidc
    exit 1
}
echo " ready!"

# Check RouterOS-MCP HTTP server (port listening)
echo -n "Waiting for RouterOS-MCP HTTP server..."
timeout 60 bash -c 'until nc -z localhost 18765 2>/dev/null; do echo -n "."; sleep 2; done' || {
    echo ""
    echo "ERROR: RouterOS-MCP HTTP server failed to start"
    docker-compose -f tests/e2e/docker-compose.yml logs routeros-mcp
    exit 1
}
echo " ready!"

# Give it a bit more time to fully initialize
sleep 5

echo ""
echo "=== Running E2E Tests ==="
pytest tests/e2e/test_http_transport_clients.py -v --tb=short "$@"

TEST_EXIT_CODE=$?

# Display service logs if tests failed
if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo ""
    echo "=== Service Logs (for debugging) ==="
    echo ""
    echo "--- Mock OIDC Logs ---"
    docker-compose -f tests/e2e/docker-compose.yml logs --tail=50 mock-oidc
    echo ""
    echo "--- RouterOS-MCP Logs ---"
    docker-compose -f tests/e2e/docker-compose.yml logs --tail=50 routeros-mcp
fi

# Clean up
echo ""
read -p "Stop Docker Compose services? (y/N) " -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Stopping services..."
    docker-compose -f tests/e2e/docker-compose.yml down
else
    echo "Services left running. Stop with: docker-compose -f tests/e2e/docker-compose.yml down"
fi

exit $TEST_EXIT_CODE
