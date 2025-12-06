# JSON-RPC 2.0 Error Codes & MCP Protocol Specification

## Purpose

Define the complete JSON-RPC 2.0 error code taxonomy, MCP protocol message formats, and error handling semantics for the RouterOS MCP service. This document ensures consistent error reporting across all MCP tools and proper protocol compliance.

---

## JSON-RPC 2.0 Protocol Overview

The RouterOS MCP service uses **JSON-RPC 2.0** as its wire protocol, following the MCP (Model Context Protocol) specification.

### Protocol Version

- **JSON-RPC**: 2.0
- **MCP Protocol**: 2025-11-25 (latest stable)

### Message Types

1. **Request** (client → server)
2. **Response** (server → client)
3. **Notification** (server → client, no response expected)
4. **Error Response** (server → client, when request fails)

---

## JSON-RPC Request Format

### Standard Request

```json
{
  "jsonrpc": "2.0",
  "id": "req-12345",
  "method": "tools/call",
  "params": {
    "name": "system/get-overview",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `jsonrpc` | string | ✅ | Must be exactly `"2.0"` |
| `id` | string/number | ✅ | Client-provided request identifier (must be unique) |
| `method` | string | ✅ | MCP method name (`tools/call`, `resources/read`, `prompts/get`) |
| `params` | object | ✅ | Method-specific parameters |

### MCP Tool Call Request

For MCP tool invocations:

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "tools/call",
  "params": {
    "name": "system/get-overview",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Fields:**
- `params.name`: Tool name in format `topic/tool-name` (e.g., `system/get-overview`)
- `params.arguments`: Tool-specific arguments (defined per tool in Doc 04)

---

## JSON-RPC Success Response Format

### Standard Success Response

```json
{
  "jsonrpc": "2.0",
  "id": "req-12345",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "System overview retrieved successfully"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "routeros_version": "7.10.1",
      "uptime_seconds": 86400,
      "cpu_usage_percent": 5.2,
      "memory_total_bytes": 536870912,
      "memory_used_bytes": 134217728
    }
  }
}
```

### Response Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `jsonrpc` | string | ✅ | Must be exactly `"2.0"` |
| `id` | string/number | ✅ | Matches request `id` |
| `result` | object | ✅ | Tool execution result |
| `result.content` | array | ✅ | MCP content blocks (text, image, resource) |
| `result.isError` | boolean | ❌ | Optional error flag (default: false) |
| `result._meta` | object | ❌ | Optional structured metadata |

---

## JSON-RPC Error Response Format

### Standard Error Response

```json
{
  "jsonrpc": "2.0",
  "id": "req-12345",
  "error": {
    "code": -32602,
    "message": "Invalid params",
    "data": {
      "mcp_error_code": "INVALID_DEVICE_ID",
      "details": "Device 'dev-unknown' not found in registry",
      "device_id": "dev-unknown"
    }
  }
}
```

### Error Object Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | integer | ✅ | JSON-RPC error code (see taxonomy below) |
| `message` | string | ✅ | Human-readable error message |
| `data` | object | ❌ | Additional error information |

### Error Data Object

The `error.data` object contains MCP-specific error details:

```json
{
  "mcp_error_code": "DEVICE_UNREACHABLE",
  "details": "Connection timeout after 5.0 seconds",
  "device_id": "dev-lab-01",
  "routeros_error": "connect ETIMEDOUT 192.168.1.1:443",
  "retry_after": 60
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mcp_error_code` | string | ✅ | MCP-specific error code (see below) |
| `details` | string | ✅ | Detailed error description |
| `device_id` | string | ❌ | Related device ID (if applicable) |
| `routeros_error` | string | ❌ | Raw RouterOS error message |
| `retry_after` | integer | ❌ | Seconds to wait before retry (for rate limits) |

---

## JSON-RPC 2.0 Error Code Taxonomy

### Standard JSON-RPC Error Codes

These are defined by JSON-RPC 2.0 specification:

| Code | Name | Description | When to Use |
|------|------|-------------|-------------|
| `-32700` | Parse error | Invalid JSON was received | Malformed JSON in request body |
| `-32600` | Invalid Request | The JSON is not a valid Request object | Missing required fields (`jsonrpc`, `id`, `method`) |
| `-32601` | Method not found | The method does not exist or is not available | Unknown MCP method or tool name |
| `-32602` | Invalid params | Invalid method parameters | Missing required params, wrong types, validation errors |
| `-32603` | Internal error | Internal JSON-RPC error | Unexpected server errors, crashes |

### MCP-Specific Error Codes

These extend JSON-RPC for MCP tool operations:

| Code | Name | MCP Error Code | Description |
|------|------|----------------|-------------|
| `-32000` | Server error | `INTERNAL_ERROR` | Unexpected server error |
| `-32001` | Authorization error | `UNAUTHORIZED` | Missing or invalid authentication |
| `-32002` | Forbidden | `FORBIDDEN` | User lacks permission for operation |
| `-32003` | Not found | `NOT_FOUND` | Resource not found (device, plan, etc.) |
| `-32004` | Conflict | `CONFLICT` | Resource already exists or state conflict |
| `-32005` | Validation error | `VALIDATION_ERROR` | Input validation failed |
| `-32006` | Rate limited | `RATE_LIMITED` | Too many requests |
| `-32007` | Timeout | `TIMEOUT` | Operation timed out |
| `-32010` | Device error | `DEVICE_UNREACHABLE` | Cannot connect to device |
| `-32011` | Device error | `DEVICE_AUTH_FAILED` | Device authentication failed |
| `-32012` | Device error | `DEVICE_ERROR` | Device returned error |
| `-32013` | Device error | `DEVICE_UNSUPPORTED` | Operation not supported by device |
| `-32020` | Configuration error | `INVALID_CONFIGURATION` | Invalid configuration state |
| `-32021` | Configuration error | `UNSAFE_OPERATION` | Operation blocked by safety rules |
| `-32030` | Plan error | `PLAN_NOT_APPROVED` | Plan requires approval before apply |
| `-32031` | Plan error | `PLAN_EXPIRED` | Plan has expired and cannot be applied |

---

## MCP Error Code Details

### Authentication & Authorization Errors

#### `UNAUTHORIZED` (-32001)

**When:** Missing or invalid credentials/tokens

**Example:**
```json
{
  "code": -32001,
  "message": "Unauthorized",
  "data": {
    "mcp_error_code": "UNAUTHORIZED",
    "details": "No valid authentication found"
  }
}
```

**Phase 1 Note:** In single-user stdio mode, this error is rare (OS-level auth). Appears in Phase 4 with OAuth/OIDC.

---

#### `FORBIDDEN` (-32002)

**When:** User/device lacks permission for operation

**Scenarios:**
1. Tool tier exceeds user role (Phase 4+)
2. Device capability flag disabled
3. Environment mismatch
4. Operation not allowed on device

**Examples:**

**Device capability flag:**
```json
{
  "code": -32002,
  "message": "Forbidden: advanced tier requires allow_advanced_writes flag",
  "data": {
    "mcp_error_code": "FORBIDDEN",
    "details": "Device 'dev-lab-01' does not allow advanced writes",
    "device_id": "dev-lab-01",
    "required_flag": "allow_advanced_writes",
    "tool_tier": "advanced"
  }
}
```

**Environment mismatch:**
```json
{
  "code": -32002,
  "message": "Forbidden: environment mismatch",
  "data": {
    "mcp_error_code": "FORBIDDEN",
    "details": "Device environment 'prod' does not match service environment 'lab'",
    "device_id": "dev-prod-01",
    "device_environment": "prod",
    "service_environment": "lab"
  }
}
```

---

### Resource Errors

#### `NOT_FOUND` (-32003)

**When:** Requested resource does not exist

**Examples:**

**Device not found:**
```json
{
  "code": -32003,
  "message": "Not Found",
  "data": {
    "mcp_error_code": "NOT_FOUND",
    "details": "Device 'dev-unknown' not found in registry",
    "device_id": "dev-unknown",
    "resource_type": "device"
  }
}
```

**Plan not found:**
```json
{
  "code": -32003,
  "message": "Not Found",
  "data": {
    "mcp_error_code": "NOT_FOUND",
    "details": "Plan 'plan-abc123' not found",
    "plan_id": "plan-abc123",
    "resource_type": "plan"
  }
}
```

---

#### `CONFLICT` (-32004)

**When:** Resource already exists or state conflict

**Example:**
```json
{
  "code": -32004,
  "message": "Conflict",
  "data": {
    "mcp_error_code": "CONFLICT",
    "details": "Device with name 'lab-router-01' already exists",
    "device_name": "lab-router-01",
    "existing_device_id": "dev-lab-01"
  }
}
```

---

### Validation Errors

#### `VALIDATION_ERROR` (-32005)

**When:** Input validation failed

**Example:**
```json
{
  "code": -32005,
  "message": "Validation Error",
  "data": {
    "mcp_error_code": "VALIDATION_ERROR",
    "details": "Invalid IP address format",
    "field": "ip_address",
    "value": "192.168.1.999",
    "expected": "Valid IPv4 or IPv6 address"
  }
}
```

**Multiple validation errors:**
```json
{
  "code": -32005,
  "message": "Validation Error",
  "data": {
    "mcp_error_code": "VALIDATION_ERROR",
    "details": "Multiple validation errors",
    "errors": [
      {
        "field": "device_id",
        "message": "Required field missing"
      },
      {
        "field": "dns_servers",
        "message": "Must be array of strings"
      }
    ]
  }
}
```

---

### Rate Limiting & Timeouts

#### `RATE_LIMITED` (-32006)

**When:** Client exceeded rate limit

**Example:**
```json
{
  "code": -32006,
  "message": "Rate Limited",
  "data": {
    "mcp_error_code": "RATE_LIMITED",
    "details": "Too many requests to device 'dev-lab-01'",
    "device_id": "dev-lab-01",
    "retry_after": 60,
    "limit": "3 requests per device",
    "current_count": 5
  }
}
```

---

#### `TIMEOUT` (-32007)

**When:** Operation exceeded timeout

**Example:**
```json
{
  "code": -32007,
  "message": "Timeout",
  "data": {
    "mcp_error_code": "TIMEOUT",
    "details": "REST call to device timed out after 5.0 seconds",
    "device_id": "dev-lab-01",
    "timeout_seconds": 5.0,
    "operation": "GET /rest/system/resource"
  }
}
```

---

### Device Communication Errors

#### `DEVICE_UNREACHABLE` (-32010)

**When:** Cannot establish connection to RouterOS device

**Example:**
```json
{
  "code": -32010,
  "message": "Device Unreachable",
  "data": {
    "mcp_error_code": "DEVICE_UNREACHABLE",
    "details": "Connection refused to 192.168.1.1:443",
    "device_id": "dev-lab-01",
    "management_address": "192.168.1.1:443",
    "error_type": "ECONNREFUSED"
  }
}
```

---

#### `DEVICE_AUTH_FAILED` (-32011)

**When:** RouterOS device rejected credentials

**Example:**
```json
{
  "code": -32011,
  "message": "Device Authentication Failed",
  "data": {
    "mcp_error_code": "DEVICE_AUTH_FAILED",
    "details": "HTTP 401 Unauthorized from RouterOS",
    "device_id": "dev-lab-01",
    "credential_kind": "routeros_rest",
    "suggestion": "Check device credentials or rotate keys"
  }
}
```

---

#### `DEVICE_ERROR` (-32012)

**When:** RouterOS device returned an error

**Example:**
```json
{
  "code": -32012,
  "message": "Device Error",
  "data": {
    "mcp_error_code": "DEVICE_ERROR",
    "details": "RouterOS API error: invalid argument",
    "device_id": "dev-lab-01",
    "routeros_error": "failure: no such item (4)",
    "operation": "PATCH /rest/ip/address/*2"
  }
}
```

---

#### `DEVICE_UNSUPPORTED` (-32013)

**When:** Device does not support requested operation

**Example:**
```json
{
  "code": -32013,
  "message": "Device Unsupported",
  "data": {
    "mcp_error_code": "DEVICE_UNSUPPORTED",
    "details": "RouterOS version too old for this operation",
    "device_id": "dev-lab-01",
    "routeros_version": "7.8",
    "required_version": "7.10+",
    "tool": "system/get-ntp-status"
  }
}
```

---

### Configuration Errors

#### `INVALID_CONFIGURATION` (-32020)

**When:** Configuration state is invalid

**Example:**
```json
{
  "code": -32020,
  "message": "Invalid Configuration",
  "data": {
    "mcp_error_code": "INVALID_CONFIGURATION",
    "details": "Cannot add IP address: interface is disabled",
    "device_id": "dev-lab-01",
    "interface": "ether1",
    "interface_status": "disabled"
  }
}
```

---

#### `UNSAFE_OPERATION` (-32021)

**When:** Operation blocked by safety rules

**Example:**
```json
{
  "code": -32021,
  "message": "Unsafe Operation",
  "data": {
    "mcp_error_code": "UNSAFE_OPERATION",
    "details": "Cannot modify management interface IP address",
    "device_id": "dev-lab-01",
    "interface": "ether1",
    "reason": "Management interface protection",
    "safety_rule": "PROTECT_MANAGEMENT_PATH"
  }
}
```

---

### Plan/Apply Errors (Phase 4+)

#### `PLAN_NOT_APPROVED` (-32030)

**When:** Attempting to apply unapproved plan

**Example:**
```json
{
  "code": -32030,
  "message": "Plan Not Approved",
  "data": {
    "mcp_error_code": "PLAN_NOT_APPROVED",
    "details": "Plan requires approval before execution",
    "plan_id": "plan-abc123",
    "plan_status": "draft",
    "required_status": "approved"
  }
}
```

**Phase 1 Note:** Self-approval allowed in single-user mode.

---

#### `PLAN_EXPIRED` (-32031)

**When:** Plan has expired

**Example:**
```json
{
  "code": -32031,
  "message": "Plan Expired",
  "data": {
    "mcp_error_code": "PLAN_EXPIRED",
    "details": "Plan expired 2 hours ago",
    "plan_id": "plan-abc123",
    "created_at": "2024-01-15T10:00:00Z",
    "expires_at": "2024-01-15T12:00:00Z",
    "current_time": "2024-01-15T14:00:00Z"
  }
}
```

---

## Error Handling Best Practices

### Client-Side Error Handling

**Clients should handle errors by code:**

1. **Retry with backoff** (`-32006`, `-32007`, `-32010`):
   ```python
   if error.code in [-32006, -32007, -32010]:
       retry_after = error.data.get("retry_after", 60)
       await asyncio.sleep(retry_after)
       retry_request()
   ```

2. **User action required** (`-32002`, `-32030`, `-32031`):
   ```python
   if error.code == -32002:  # FORBIDDEN
       show_permission_error(error.data["details"])
   ```

3. **Fix and retry** (`-32005`, `-32602`):
   ```python
   if error.code in [-32005, -32602]:  # Validation
       fix_input_based_on(error.data["errors"])
       retry_request()
   ```

4. **Report and abort** (`-32012`, `-32020`, `-32021`):
   ```python
   if error.code in [-32012, -32020, -32021]:
       log_error(error)
       notify_user(error.message)
   ```

### Server-Side Error Generation

**Consistent error creation:**

```python
from fastmcp.exceptions import McpError

def raise_device_not_found(device_id: str) -> None:
    """Raise NOT_FOUND error for missing device."""
    raise McpError(
        code=-32003,
        message="Not Found",
        data={
            "mcp_error_code": "NOT_FOUND",
            "details": f"Device '{device_id}' not found in registry",
            "device_id": device_id,
            "resource_type": "device"
        }
    )

def raise_forbidden_tier(device: Device, tool_tier: str) -> None:
    """Raise FORBIDDEN error for insufficient device capabilities."""
    raise McpError(
        code=-32002,
        message=f"Forbidden: {tool_tier} tier requires device capability flag",
        data={
            "mcp_error_code": "FORBIDDEN",
            "details": f"Device '{device.id}' does not allow {tool_tier} tier operations",
            "device_id": device.id,
            "tool_tier": tool_tier,
            "required_flag": f"allow_{tool_tier}_operations"
        }
    )
```

---

## MCP Protocol Compliance Checklist

### Request Processing

- ✅ Validate `jsonrpc` field is exactly `"2.0"`
- ✅ Validate `id` is present and unique
- ✅ Validate `method` is a known MCP method
- ✅ Validate `params` structure matches method requirements
- ✅ Return error `-32600` for invalid request structure
- ✅ Return error `-32601` for unknown methods
- ✅ Return error `-32602` for invalid params

### Response Generation

- ✅ Always include `jsonrpc: "2.0"`
- ✅ Echo `id` from request
- ✅ Include `result` OR `error`, never both
- ✅ Format `result` with MCP content blocks
- ✅ Include `_meta` for structured data
- ✅ Use standard error codes from taxonomy

### Error Reporting

- ✅ Use JSON-RPC error codes (-32xxx)
- ✅ Include MCP error code in `error.data.mcp_error_code`
- ✅ Provide detailed error description
- ✅ Include relevant context (device_id, field names, etc.)
- ✅ Never expose sensitive data in errors (credentials, secrets)
- ✅ Mask RouterOS errors if they contain sensitive info

---

## Summary

### Error Code Quick Reference

| Code Range | Category | Examples |
|------------|----------|----------|
| `-32700` to `-32603` | JSON-RPC standard | Parse error, Invalid request, Method not found |
| `-32000` to `-32009` | General MCP | Internal, Unauthorized, Forbidden, Not found |
| `-32010` to `-32019` | Device communication | Unreachable, Auth failed, Device error |
| `-32020` to `-32029` | Configuration | Invalid config, Unsafe operation |
| `-32030` to `-32039` | Plan/Apply (Phase 4+) | Not approved, Expired |

### Phase 1 Most Common Errors

1. `-32003` `NOT_FOUND` - Device not in registry
2. `-32002` `FORBIDDEN` - Device capability flag disabled
3. `-32010` `DEVICE_UNREACHABLE` - Cannot connect to RouterOS
4. `-32011` `DEVICE_AUTH_FAILED` - Invalid device credentials
5. `-32005` `VALIDATION_ERROR` - Invalid input parameters

---

**This error taxonomy provides comprehensive coverage for all MCP tool operations while maintaining JSON-RPC 2.0 compliance.**
