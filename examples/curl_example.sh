#!/bin/bash
# curl examples for RouterOS MCP HTTP transport
#
# This script demonstrates:
# 1. Obtaining OAuth access token
# 2. Testing MCP health endpoint
# 3. Initializing MCP session
# 4. Calling MCP tools
# 5. Reading MCP resources
#
# Usage:
#   # Configure environment
#   export MCP_BASE_URL=https://mcp.example.com
#   export OIDC_PROVIDER_URL=https://your-oidc-provider.com
#   export OIDC_CLIENT_ID=your-client-id
#   export OIDC_CLIENT_SECRET=your-client-secret
#
#   # Run script
#   bash examples/curl_example.sh
#
#   # Or run specific test
#   bash examples/curl_example.sh health
#   bash examples/curl_example.sh initialize
#   bash examples/curl_example.sh list_tools

set -e  # Exit on error

# ==========================================
# Configuration
# ==========================================

MCP_BASE_URL="${MCP_BASE_URL:-http://localhost:8080}"
OIDC_PROVIDER_URL="${OIDC_PROVIDER_URL:-}"
OIDC_CLIENT_ID="${OIDC_CLIENT_ID:-}"
OIDC_CLIENT_SECRET="${OIDC_CLIENT_SECRET:-}"
OIDC_AUDIENCE="${OIDC_AUDIENCE:-$MCP_BASE_URL}"
DEVICE_ID="${DEVICE_ID:-dev-001}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ==========================================
# Helper Functions
# ==========================================

print_header() {
    echo ""
    echo -e "${BLUE}======================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

check_dependencies() {
    if ! command -v curl &> /dev/null; then
        print_error "curl is not installed"
        exit 1
    fi
    
    if ! command -v jq &> /dev/null; then
        print_info "jq is not installed (optional, for pretty JSON output)"
    fi
}

validate_config() {
    if [ -z "$OIDC_PROVIDER_URL" ] || [ -z "$OIDC_CLIENT_ID" ] || [ -z "$OIDC_CLIENT_SECRET" ]; then
        print_error "Missing OAuth configuration"
        echo ""
        echo "Set environment variables:"
        echo "  export MCP_BASE_URL=https://mcp.example.com"
        echo "  export OIDC_PROVIDER_URL=https://your-provider.com"
        echo "  export OIDC_CLIENT_ID=your-client-id"
        echo "  export OIDC_CLIENT_SECRET=your-client-secret"
        echo ""
        exit 1
    fi
}

# ==========================================
# OAuth Token Functions
# ==========================================

get_token_auth0() {
    print_info "Requesting token from Auth0..."
    
    response=$(curl -s -X POST "${OIDC_PROVIDER_URL}/oauth/token" \
        -H "Content-Type: application/json" \
        -d "{
            \"client_id\": \"${OIDC_CLIENT_ID}\",
            \"client_secret\": \"${OIDC_CLIENT_SECRET}\",
            \"audience\": \"${OIDC_AUDIENCE}\",
            \"grant_type\": \"client_credentials\"
        }")
    
    access_token=$(echo "$response" | jq -r '.access_token // empty')
    
    if [ -z "$access_token" ]; then
        print_error "Failed to obtain access token"
        echo "$response" | jq . 2>/dev/null || echo "$response"
        exit 1
    fi
    
    echo "$access_token"
}

get_token_okta() {
    print_info "Requesting token from Okta..."
    
    response=$(curl -s -X POST "${OIDC_PROVIDER_URL}/v1/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "client_id=${OIDC_CLIENT_ID}" \
        -d "client_secret=${OIDC_CLIENT_SECRET}" \
        -d "grant_type=client_credentials" \
        -d "scope=mcp:access")
    
    access_token=$(echo "$response" | jq -r '.access_token // empty')
    
    if [ -z "$access_token" ]; then
        print_error "Failed to obtain access token"
        echo "$response" | jq . 2>/dev/null || echo "$response"
        exit 1
    fi
    
    echo "$access_token"
}

get_token_azure() {
    print_info "Requesting token from Azure AD..."
    
    response=$(curl -s -X POST "${OIDC_PROVIDER_URL}/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "client_id=${OIDC_CLIENT_ID}" \
        -d "client_secret=${OIDC_CLIENT_SECRET}" \
        -d "grant_type=client_credentials" \
        -d "scope=${OIDC_AUDIENCE}/.default")
    
    access_token=$(echo "$response" | jq -r '.access_token // empty')
    
    if [ -z "$access_token" ]; then
        print_error "Failed to obtain access token"
        echo "$response" | jq . 2>/dev/null || echo "$response"
        exit 1
    fi
    
    echo "$access_token"
}

get_access_token() {
    # Auto-detect provider and get token
    if [[ "$OIDC_PROVIDER_URL" == *"auth0.com"* ]]; then
        get_token_auth0
    elif [[ "$OIDC_PROVIDER_URL" == *"okta.com"* ]]; then
        get_token_okta
    elif [[ "$OIDC_PROVIDER_URL" == *"microsoftonline.com"* ]]; then
        get_token_azure
    else
        print_info "Unknown provider, trying generic OIDC..."
        get_token_azure  # Use Azure format as fallback
    fi
}

# ==========================================
# MCP API Functions
# ==========================================

test_health() {
    print_header "Testing Health Endpoint"
    
    print_info "GET ${MCP_BASE_URL}/health"
    
    response=$(curl -s -w "\nHTTP_CODE:%{http_code}" "${MCP_BASE_URL}/health")
    http_code=$(echo "$response" | grep "HTTP_CODE:" | cut -d: -f2)
    body=$(echo "$response" | sed '/HTTP_CODE:/d')
    
    echo "$body" | jq . 2>/dev/null || echo "$body"
    
    if [ "$http_code" = "200" ]; then
        print_success "Health check passed (HTTP $http_code)"
    else
        print_error "Health check failed (HTTP $http_code)"
        return 1
    fi
}

initialize_session() {
    print_header "Initializing MCP Session"
    
    TOKEN="${1:-$(get_access_token)}"
    
    print_info "POST ${MCP_BASE_URL}/mcp (method: initialize)"
    
    response=$(curl -s -X POST "${MCP_BASE_URL}/mcp" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${TOKEN}" \
        -d '{
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {"subscribe": true},
                    "prompts": {}
                },
                "clientInfo": {
                    "name": "curl-example",
                    "version": "1.0.0"
                }
            }
        }')
    
    echo "$response" | jq . 2>/dev/null || echo "$response"
    
    # Check for error
    error=$(echo "$response" | jq -r '.error // empty')
    if [ -n "$error" ]; then
        print_error "Initialization failed"
        return 1
    fi
    
    print_success "Session initialized"
}

list_tools() {
    print_header "Listing Available Tools"
    
    TOKEN="${1:-$(get_access_token)}"
    
    print_info "POST ${MCP_BASE_URL}/mcp (method: tools/list)"
    
    response=$(curl -s -X POST "${MCP_BASE_URL}/mcp" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${TOKEN}" \
        -d '{
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }')
    
    echo "$response" | jq . 2>/dev/null || echo "$response"
    
    # Count tools
    tool_count=$(echo "$response" | jq -r '.result.tools | length // 0')
    print_success "Found $tool_count tools"
}

call_system_overview() {
    print_header "Calling Tool: system/get-overview"
    
    TOKEN="${1:-$(get_access_token)}"
    
    print_info "POST ${MCP_BASE_URL}/mcp (method: tools/call)"
    print_info "Device ID: $DEVICE_ID"
    
    response=$(curl -s -X POST "${MCP_BASE_URL}/mcp" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${TOKEN}" \
        -d "{
            \"jsonrpc\": \"2.0\",
            \"id\": 3,
            \"method\": \"tools/call\",
            \"params\": {
                \"name\": \"system/get-overview\",
                \"arguments\": {
                    \"device_id\": \"${DEVICE_ID}\"
                }
            }
        }")
    
    echo "$response" | jq . 2>/dev/null || echo "$response"
    
    # Check for error
    error=$(echo "$response" | jq -r '.error // empty')
    if [ -n "$error" ]; then
        print_error "Tool call failed"
        return 1
    fi
    
    print_success "Tool executed successfully"
}

read_device_resource() {
    print_header "Reading Resource: device://${DEVICE_ID}/overview"
    
    TOKEN="${1:-$(get_access_token)}"
    
    print_info "POST ${MCP_BASE_URL}/mcp (method: resources/read)"
    
    response=$(curl -s -X POST "${MCP_BASE_URL}/mcp" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${TOKEN}" \
        -d "{
            \"jsonrpc\": \"2.0\",
            \"id\": 4,
            \"method\": \"resources/read\",
            \"params\": {
                \"uri\": \"device://${DEVICE_ID}/overview\"
            }
        }")
    
    echo "$response" | jq . 2>/dev/null || echo "$response"
    
    # Check for error
    error=$(echo "$response" | jq -r '.error // empty')
    if [ -n "$error" ]; then
        print_error "Resource read failed"
        return 1
    fi
    
    print_success "Resource retrieved successfully"
}

# ==========================================
# Main Execution
# ==========================================

main() {
    check_dependencies
    
    print_header "RouterOS MCP curl Examples"
    echo "MCP URL: $MCP_BASE_URL"
    echo "OIDC Provider: ${OIDC_PROVIDER_URL:-Not configured}"
    
    # Parse command-line argument for specific test
    test_name="${1:-all}"
    
    if [ "$test_name" = "health" ]; then
        test_health
        exit 0
    fi
    
    # All other tests require OAuth
    validate_config
    
    # Get access token once for all tests
    print_header "Obtaining Access Token"
    ACCESS_TOKEN=$(get_access_token)
    
    if [ -z "$ACCESS_TOKEN" ]; then
        print_error "Failed to obtain access token"
        exit 1
    fi
    
    print_success "Access token obtained"
    print_info "Token preview: ${ACCESS_TOKEN:0:50}..."
    
    # Run tests
    case "$test_name" in
        initialize)
            initialize_session "$ACCESS_TOKEN"
            ;;
        list_tools)
            list_tools "$ACCESS_TOKEN"
            ;;
        system_overview)
            call_system_overview "$ACCESS_TOKEN"
            ;;
        read_resource)
            read_device_resource "$ACCESS_TOKEN"
            ;;
        all)
            initialize_session "$ACCESS_TOKEN"
            list_tools "$ACCESS_TOKEN"
            call_system_overview "$ACCESS_TOKEN"
            read_device_resource "$ACCESS_TOKEN"
            ;;
        *)
            print_error "Unknown test: $test_name"
            echo ""
            echo "Available tests:"
            echo "  health           - Test health endpoint (no auth)"
            echo "  initialize       - Initialize MCP session"
            echo "  list_tools       - List available tools"
            echo "  system_overview  - Call system/get-overview tool"
            echo "  read_resource    - Read device resource"
            echo "  all              - Run all tests (default)"
            exit 1
            ;;
    esac
    
    print_header "All Tests Completed"
    print_success "Examples completed successfully"
}

# Run main function
main "$@"
