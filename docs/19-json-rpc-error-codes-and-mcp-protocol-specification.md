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

**Phase 1 Note:** In single-user stdio mode, this error is rare (OS-level auth). Appears in Phase 5 with OAuth/OIDC multi-user.

---

#### `FORBIDDEN` (-32002)

**When:** User/device lacks permission for operation

**Scenarios:**
1. Tool tier exceeds user role (Phase 5+)
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

### Plan/Apply Errors (Phase 3 - Implemented)

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
| `-32030` to `-32039` | Plan/Apply (Phase 3 Implemented) | Not approved, Expired |

### Phase 1 Most Common Errors

1. `-32003` `NOT_FOUND` - Device not in registry
2. `-32002` `FORBIDDEN` - Device capability flag disabled
3. `-32010` `DEVICE_UNREACHABLE` - Cannot connect to RouterOS
4. `-32011` `DEVICE_AUTH_FAILED` - Invalid device credentials
5. `-32005` `VALIDATION_ERROR` - Invalid input parameters

---

## MCP Best Practices Integration

### Intent-Based Error Messages (MCP Section A4.2)

Following MCP best practices, error messages must explain *what to do next*, not just *what went wrong*:

```python
# routeros_mcp/mcp/errors.py

from fastmcp.exceptions import McpError


def raise_device_not_found_intent_based(device_id: str, available_devices: list[str]) -> None:
    """Raise NOT_FOUND error with actionable guidance.

    Following MCP Section A4.2: Describe when to use, not just what failed.
    """
    # ❌ BAD: Functional description (what went wrong)
    # raise McpError(-32003, "Device not found")

    # ✅ GOOD: Intent-based description (what to do next)
    suggestion = (
        f"Device '{device_id}' not found in registry. "
        f"Available devices: {', '.join(available_devices[:5])}. "
        f"Use registry/list to see all devices, or registry/add to add a new device."
    )

    raise McpError(
        code=-32003,
        message="Device Not Found",
        data={
            "mcp_error_code": "NOT_FOUND",
            "details": suggestion,
            "device_id": device_id,
            "available_device_count": len(available_devices),
            "suggestions": [
                "Use registry/list to see all available devices",
                "Check device_id spelling and try again",
                f"Use registry/add to add '{device_id}' to the registry"
            ]
        }
    )
```

### Actionable Error Recovery Guidance (MCP Section B7)

Errors should classify themselves and provide recovery steps:

```python
# routeros_mcp/mcp/errors.py

from enum import Enum
from typing import Optional


class ErrorRecoveryStrategy(str, Enum):
    """Error recovery strategies for clients."""
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    USER_ACTION_REQUIRED = "user_action_required"
    FIX_AND_RETRY = "fix_and_retry"
    REPORT_AND_ABORT = "report_and_abort"


def create_actionable_error(
    code: int,
    mcp_error_code: str,
    details: str,
    recovery_strategy: ErrorRecoveryStrategy,
    **context
) -> McpError:
    """Create error with recovery guidance.

    Following MCP Section B7: Help the model recover from failures.

    Args:
        code: JSON-RPC error code
        mcp_error_code: MCP-specific error code
        details: Detailed error description
        recovery_strategy: How client should handle this error
        **context: Additional context fields

    Returns:
        McpError with recovery guidance

    Example:
        error = create_actionable_error(
            code=-32010,
            mcp_error_code="DEVICE_UNREACHABLE",
            details="Connection timeout after 5.0 seconds",
            recovery_strategy=ErrorRecoveryStrategy.RETRY_WITH_BACKOFF,
            device_id="dev-lab-01",
            retry_after=60
        )
    """
    error_data = {
        "mcp_error_code": mcp_error_code,
        "details": details,
        "recovery_strategy": recovery_strategy.value,
        **context
    }

    # Add strategy-specific guidance
    if recovery_strategy == ErrorRecoveryStrategy.RETRY_WITH_BACKOFF:
        error_data["suggestion"] = (
            f"Wait {context.get('retry_after', 60)} seconds and retry. "
            "This is likely a temporary issue."
        )

    elif recovery_strategy == ErrorRecoveryStrategy.USER_ACTION_REQUIRED:
        error_data["suggestion"] = (
            "User intervention required. "
            "Check permissions or configuration and try again."
        )

    elif recovery_strategy == ErrorRecoveryStrategy.FIX_AND_RETRY:
        error_data["suggestion"] = (
            "Fix the input parameters based on the validation errors below, "
            "then retry the request."
        )

    elif recovery_strategy == ErrorRecoveryStrategy.REPORT_AND_ABORT:
        error_data["suggestion"] = (
            "This error cannot be resolved automatically. "
            "Report to system administrator."
        )

    # Determine message based on code
    message_map = {
        -32003: "Not Found",
        -32002: "Forbidden",
        -32005: "Validation Error",
        -32006: "Rate Limited",
        -32007: "Timeout",
        -32010: "Device Unreachable",
        -32011: "Device Authentication Failed",
        -32012: "Device Error",
    }
    message = message_map.get(code, "Error")

    return McpError(code=code, message=message, data=error_data)


# Usage examples
def raise_device_unreachable(device_id: str, timeout: float) -> None:
    """Raise DEVICE_UNREACHABLE with retry guidance."""
    raise create_actionable_error(
        code=-32010,
        mcp_error_code="DEVICE_UNREACHABLE",
        details=f"Connection timeout after {timeout} seconds",
        recovery_strategy=ErrorRecoveryStrategy.RETRY_WITH_BACKOFF,
        device_id=device_id,
        timeout_seconds=timeout,
        retry_after=60
    )


def raise_validation_error(field: str, value: any, expected: str) -> None:
    """Raise VALIDATION_ERROR with fix-and-retry guidance."""
    raise create_actionable_error(
        code=-32005,
        mcp_error_code="VALIDATION_ERROR",
        details=f"Invalid value for field '{field}': {value}",
        recovery_strategy=ErrorRecoveryStrategy.FIX_AND_RETRY,
        field=field,
        value=str(value),
        expected=expected,
        suggestion=f"Provide a valid {expected} for field '{field}'"
    )


def raise_forbidden_tier(device_id: str, tier: str, required_flag: str) -> None:
    """Raise FORBIDDEN with user action required."""
    raise create_actionable_error(
        code=-32002,
        mcp_error_code="FORBIDDEN",
        details=f"Device '{device_id}' does not allow {tier} tier operations",
        recovery_strategy=ErrorRecoveryStrategy.USER_ACTION_REQUIRED,
        device_id=device_id,
        tool_tier=tier,
        required_flag=required_flag,
        suggestion=(
            f"Enable {tier} operations by setting device flag '{required_flag}=true', "
            "or use a different device."
        )
    )
```

### Token-Conscious Error Messages (MCP Section B8)

Keep error messages concise but helpful:

```python
# routeros_mcp/mcp/errors.py

def create_token_efficient_error(
    code: int,
    mcp_error_code: str,
    short_details: str,
    full_details: Optional[str] = None,
    **context
) -> McpError:
    """Create error optimized for token consumption.

    Following MCP Section B8: Token budget management.

    Provides short details for model consumption, with full details
    available in data object for debugging.

    Args:
        code: JSON-RPC error code
        mcp_error_code: MCP-specific error code
        short_details: Concise error description (for model)
        full_details: Detailed error description (for debugging)
        **context: Additional context fields

    Returns:
        McpError with token-optimized messaging
    """
    # Short details for model (token-efficient)
    error_data = {
        "mcp_error_code": mcp_error_code,
        "details": short_details,
        **context
    }

    # Full details in separate field (for logging/debugging)
    if full_details:
        error_data["_debug_details"] = full_details

    # Determine message
    message_map = {
        -32003: "Not Found",
        -32002: "Forbidden",
        -32005: "Validation Error",
        -32010: "Device Unreachable",
    }
    message = message_map.get(code, "Error")

    return McpError(code=code, message=message, data=error_data)


# Example: Concise vs Verbose
def raise_device_error_verbose(device_id: str, routeros_error: str) -> None:
    """❌ BAD: Verbose error that consumes too many tokens."""
    long_message = (
        f"The RouterOS device with identifier '{device_id}' has returned an error "
        f"response when attempting to execute the requested operation. The full error "
        f"message from the RouterOS API is as follows: {routeros_error}. This may "
        f"indicate a configuration issue, permission problem, or invalid parameters. "
        f"Please review the device configuration and ensure all parameters are correct "
        f"before retrying the operation."
    )
    raise McpError(-32012, "Device Error", {"details": long_message})


def raise_device_error_concise(device_id: str, routeros_error: str) -> None:
    """✅ GOOD: Concise error with essential information."""
    raise create_token_efficient_error(
        code=-32012,
        mcp_error_code="DEVICE_ERROR",
        short_details=f"RouterOS error: {routeros_error[:100]}",  # Truncate long errors
        full_details=routeros_error,  # Full error in debug field
        device_id=device_id,
        suggestion="Check device configuration or parameters"
    )
```

### Error Classification and Client Handling (MCP Section B7)

Provide clear error classification to guide client behavior:

```python
# routeros_mcp/mcp/error_handler.py

import logging
from typing import Callable, TypeVar, Any
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


def handle_tool_errors(tool_name: str, tier: str):
    """Decorator for consistent tool error handling.

    Following MCP Section B7: Classify errors and provide recovery guidance.

    Args:
        tool_name: Name of the tool
        tier: Tool tier (fundamental/advanced/professional)

    Returns:
        Decorated function with error handling
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await func(*args, **kwargs)

            # User errors (invalid parameters) - FIX_AND_RETRY
            except ValueError as e:
                logger.error(f"Validation error in {tool_name}: {e}")
                raise create_actionable_error(
                    code=-32005,
                    mcp_error_code="VALIDATION_ERROR",
                    details=str(e),
                    recovery_strategy=ErrorRecoveryStrategy.FIX_AND_RETRY,
                    tool_name=tool_name,
                    tool_tier=tier
                )

            # Permission errors - USER_ACTION_REQUIRED
            except PermissionError as e:
                logger.error(f"Permission denied in {tool_name}: {e}")
                raise create_actionable_error(
                    code=-32002,
                    mcp_error_code="FORBIDDEN",
                    details=str(e),
                    recovery_strategy=ErrorRecoveryStrategy.USER_ACTION_REQUIRED,
                    tool_name=tool_name,
                    tool_tier=tier
                )

            # Timeout errors - RETRY_WITH_BACKOFF
            except TimeoutError as e:
                logger.error(f"Timeout in {tool_name}: {e}")
                raise create_actionable_error(
                    code=-32007,
                    mcp_error_code="TIMEOUT",
                    details=str(e),
                    recovery_strategy=ErrorRecoveryStrategy.RETRY_WITH_BACKOFF,
                    tool_name=tool_name,
                    retry_after=60
                )

            # System errors - REPORT_AND_ABORT
            except Exception as e:
                logger.exception(f"Unexpected error in {tool_name}: {e}")
                raise create_actionable_error(
                    code=-32000,
                    mcp_error_code="INTERNAL_ERROR",
                    details=f"Unexpected error: {type(e).__name__}",
                    recovery_strategy=ErrorRecoveryStrategy.REPORT_AND_ABORT,
                    tool_name=tool_name,
                    error_type=type(e).__name__
                )

        return wrapper
    return decorator


# Usage in MCP tools
@mcp.tool()
@handle_tool_errors(tool_name="system/get-overview", tier="fundamental")
async def system_get_overview(device_id: str) -> dict:
    """Get system overview with automatic error handling."""
    # Tool implementation
    pass
```

### Structured Error Responses with Next-Step Guidance

Following MCP best practices, errors should guide the next action:

```python
# Example: Complete error response structure

{
  "jsonrpc": "2.0",
  "id": "req-001",
  "error": {
    "code": -32002,
    "message": "Forbidden",
    "data": {
      "mcp_error_code": "FORBIDDEN",
      "details": "Device 'dev-lab-01' does not allow advanced tier operations",
      "device_id": "dev-lab-01",
      "tool_tier": "advanced",
      "required_flag": "allow_advanced_writes",

      // Recovery guidance
      "recovery_strategy": "user_action_required",
      "suggestion": "Enable advanced operations by setting device flag 'allow_advanced_writes=true', or use a different device.",

      // Next steps (intent-based guidance)
      "next_steps": [
        "Use registry/update to enable allow_advanced_writes flag",
        "Use registry/list with environment filter to find devices with advanced tier enabled",
        "Contact administrator to enable advanced tier for this device"
      ],

      // Alternative actions
      "alternatives": [
        {
          "tool": "registry/list",
          "description": "List devices with advanced tier enabled",
          "arguments": {
            "environment": "lab",
            "filter": "allow_advanced_writes=true"
          }
        }
      ]
    }
  }
}
```

### Error Message Templates

**Device Errors:**

```python
DEVICE_ERROR_TEMPLATES = {
    "DEVICE_UNREACHABLE": {
        "code": -32010,
        "message_template": "Cannot connect to device '{device_id}' at {management_address}",
        "recovery": ErrorRecoveryStrategy.RETRY_WITH_BACKOFF,
        "suggestions": [
            "Wait {retry_after} seconds and retry",
            "Check device is powered on and network is accessible",
            "Use registry/update to update management address if changed"
        ]
    },
    "DEVICE_AUTH_FAILED": {
        "code": -32011,
        "message_template": "Authentication failed for device '{device_id}'",
        "recovery": ErrorRecoveryStrategy.USER_ACTION_REQUIRED,
        "suggestions": [
            "Check device credentials are correct",
            "Use registry/rotate-credentials to update credentials",
            "Verify user has access to device in RouterOS"
        ]
    },
    "DEVICE_ERROR": {
        "code": -32012,
        "message_template": "RouterOS error on device '{device_id}': {error_summary}",
        "recovery": ErrorRecoveryStrategy.FIX_AND_RETRY,
        "suggestions": [
            "Check RouterOS error message for details",
            "Verify operation is valid for this RouterOS version",
            "Use system/get-overview to check device state"
        ]
    }
}
```

**Validation Errors:**

```python
VALIDATION_ERROR_TEMPLATES = {
    "INVALID_IP_ADDRESS": {
        "code": -32005,
        "message_template": "Invalid IP address: {value}",
        "recovery": ErrorRecoveryStrategy.FIX_AND_RETRY,
        "expected": "Valid IPv4 or IPv6 address (e.g., 192.168.1.1 or 2001:db8::1)"
    },
    "INVALID_DEVICE_ID": {
        "code": -32005,
        "message_template": "Device '{value}' not found",
        "recovery": ErrorRecoveryStrategy.FIX_AND_RETRY,
        "expected": "Valid device ID from registry (use registry/list to see options)"
    },
    "REQUIRED_FIELD_MISSING": {
        "code": -32005,
        "message_template": "Required field '{field}' is missing",
        "recovery": ErrorRecoveryStrategy.FIX_AND_RETRY,
        "expected": "{field} must be provided"
    }
}
```

### Error Logging with Correlation (MCP Section A9)

Log errors with JSON-RPC request ID for traceability:

```python
# routeros_mcp/mcp/logging.py

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def log_error_with_correlation(
    request_id: str,
    tool_name: str,
    error_code: int,
    mcp_error_code: str,
    details: str,
    **context
) -> None:
    """Log error with correlation ID.

    Following MCP Section A9: Emit structured logs with correlation IDs.

    Args:
        request_id: JSON-RPC request ID
        tool_name: Tool that generated error
        error_code: JSON-RPC error code
        mcp_error_code: MCP-specific error code
        details: Error details
        **context: Additional context
    """
    logger.error(
        "tool_error",
        extra={
            "request_id": request_id,
            "tool_name": tool_name,
            "error_code": error_code,
            "mcp_error_code": mcp_error_code,
            "details": details,
            **context
        }
    )


# Enhanced error creation with logging
def create_logged_error(
    request_id: str,
    tool_name: str,
    code: int,
    mcp_error_code: str,
    details: str,
    **context
) -> McpError:
    """Create error and log with correlation ID."""
    # Log error
    log_error_with_correlation(
        request_id=request_id,
        tool_name=tool_name,
        error_code=code,
        mcp_error_code=mcp_error_code,
        details=details,
        **context
    )

    # Create error response
    return create_actionable_error(
        code=code,
        mcp_error_code=mcp_error_code,
        details=details,
        recovery_strategy=ErrorRecoveryStrategy.FIX_AND_RETRY,
        **context
    )
```

---

## Error Handling Best Practices Checklist

### Error Message Design

- [ ] Errors explain *what to do next*, not just *what went wrong* (A4.2)
- [ ] Each error includes recovery strategy
- [ ] Suggestions provided for user action
- [ ] Error messages are token-conscious (B8)
- [ ] Alternative actions listed when applicable

### Error Classification

- [ ] Errors classified by recovery strategy
- [ ] User errors (validation) separate from system errors
- [ ] Permission errors provide clear guidance
- [ ] Timeout errors include retry_after hint
- [ ] Device errors categorized correctly

### Observability

- [ ] All errors logged with correlation ID (A9)
- [ ] Error rates tracked per tool
- [ ] Error types monitored
- [ ] Full error details in logs (not in response for token efficiency)

### Client Experience

- [ ] Error codes consistent with JSON-RPC 2.0
- [ ] MCP error codes provided in data object
- [ ] Structured error data includes context
- [ ] Suggestions actionable by model
- [ ] No sensitive data in error messages

---

**This error taxonomy provides comprehensive coverage for all MCP tool operations while maintaining JSON-RPC 2.0 compliance and following MCP best practices for actionable, intent-based error handling.**
