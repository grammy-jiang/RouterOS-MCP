# Observability, Logging, Metrics & Diagnostics

## Purpose

Define how the system is observed in production, including structured logs, metrics, traces, and diagnostics flows, and how these tie back to RouterOS operations and MCP tool invocations. This document also distinguishes operational logging from security/audit logging.

---

## Observability goals and SLIs/SLOs (latency, error rate, availability)

**Goals**

- Quickly detect and diagnose:
  - MCP service outages or performance degradation.  
  - RouterOS connectivity or behavior issues.  
  - Misbehaving or misused tools (especially writes).

**Representative SLIs**

- Request latency:
  - 95th percentile latency for MCP tool invocations by type (read vs write).  
  - Distinguish between internal (MCP) and external (RouterOS) latency contributions.

- Error rate:
  - Proportion of failed MCP tool calls, categorized by error code (e.g., `DEVICE_UNREACHABLE`, `UNAUTHORIZED`, `RATE_LIMITED`).  
  - RouterOS-specific error rate (REST failures).

- Availability:
  - MCP API uptime (e.g., 99.x%).  
  - Per-device health (percentage of devices classified as healthy).

These SLIs can be rolled into SLOs appropriate for the environment (lab vs production).

---

## Structured logging design (correlation IDs, device IDs, user IDs, tool names)

- **Log format**:
  - All logs are structured (JSON) with consistent fields.
  - Example core fields:
    - `timestamp`
    - `level` (`INFO`, `WARN`, `ERROR`, etc.)
    - `component` (e.g., `mcp-api`, `routeros-client`, `job-runner`)
    - `correlation_id` (unique per request/operation)
    - `mcp_method` (e.g., `tools/call`, `resources/read`, `prompts/get`)
    - `tool_name`, `tool_tier`
    - `user_sub`, `user_email`, `user_role` (where applicable)
    - `device_id`, `device_environment` (if device-specific)
    - `error_code`, `error_message` (for failures)
    - `estimated_tokens` (for large responses that may exceed LLM context)
    - `client_info` (MCP client name/version from initialize)

- **Correlation IDs**:
  - Every MCP request gets a `correlation_id` (propagated to internal logs and traces).
  - RouterOS calls made during the request log the same `correlation_id` for end-to-end attribution.

### Correlation ID Implementation (Context Variable Propagation)

**Using Python context variables for correlation ID propagation:**

```python
import contextvars
import uuid
import logging
from typing import Any

# Context variable for correlation ID (thread-safe, async-safe)
correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id",
    default=None
)

class CorrelationIDFilter(logging.Filter):
    """Logging filter to inject correlation ID into all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation_id to log record if available."""
        record.correlation_id = correlation_id_var.get() or "no-correlation-id"
        return True

# Configure logging with correlation ID filter
logging.basicConfig(
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","component":"%(name)s","correlation_id":"%(correlation_id)s","message":"%(message)s"}',
    level=logging.INFO
)
logging.root.addFilter(CorrelationIDFilter())

async def handle_mcp_request(request: dict) -> dict:
    """Handle MCP JSON-RPC request with correlation ID propagation.

    Correlation ID flows through all layers:
    1. API layer (MCP handler)
    2. Domain layer (services)
    3. Infrastructure layer (RouterOS client, database)
    4. Audit logging
    """
    # Generate correlation ID for this request
    correlation_id = str(uuid.uuid4())
    correlation_id_var.set(correlation_id)

    logger = logging.getLogger("mcp-api")
    logger.info(
        "MCP request received",
        extra={
            "mcp_method": request.get("method"),
            "mcp_request_id": request.get("id"),
            "params": request.get("params", {})
        }
    )

    try:
        # Dispatch to appropriate handler
        result = await dispatch_mcp_method(request)

        logger.info(
            "MCP request completed",
            extra={
                "mcp_method": request.get("method"),
                "status": "success",
                "duration_ms": calculate_duration()
            }
        )

        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": result
        }

    except Exception as e:
        logger.error(
            "MCP request failed",
            extra={
                "mcp_method": request.get("method"),
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )

        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "error": format_mcp_error(e)
        }

async def dispatch_mcp_method(request: dict) -> Any:
    """Dispatch MCP request to appropriate handler.

    Correlation ID automatically available via correlation_id_var.get()
    """
    method = request.get("method")

    if method == "tools/call":
        return await handle_tool_call(request["params"])
    elif method == "resources/read":
        return await handle_resource_read(request["params"])
    elif method == "prompts/get":
        return await handle_prompt_get(request["params"])
    else:
        raise ValueError(f"Unknown MCP method: {method}")

# Example: Domain service automatically has correlation ID
async def dns_get_status(device_id: str) -> dict:
    """Get DNS status (domain layer).

    Correlation ID propagated automatically via context variable.
    """
    logger = logging.getLogger("dns-service")

    # Correlation ID injected by filter
    logger.info(
        "Fetching DNS status",
        extra={
            "device_id": device_id,
            "operation": "dns_get_status"
        }
    )

    # Call infrastructure layer (RouterOS client)
    dns_config = await routeros_client.get("/rest/ip/dns", device_id)

    # Correlation ID still available in all logs
    logger.info(
        "DNS status fetched",
        extra={
            "device_id": device_id,
            "dns_servers": dns_config.get("servers")
        }
    )

    return dns_config

# Example: Infrastructure layer (RouterOS client)
async def routeros_rest_call(
    device_id: str,
    method: str,
    endpoint: str
) -> dict:
    """Make RouterOS REST call with correlation tracking."""
    logger = logging.getLogger("routeros-client")

    # Correlation ID available here too
    logger.debug(
        "RouterOS REST call starting",
        extra={
            "device_id": device_id,
            "method": method,
            "endpoint": endpoint
        }
    )

    try:
        response = await httpx_client.request(method, endpoint)
        response.raise_for_status()

        logger.info(
            "RouterOS REST call succeeded",
            extra={
                "device_id": device_id,
                "endpoint": endpoint,
                "status_code": response.status_code,
                "response_time_ms": response.elapsed.total_seconds() * 1000
            }
        )

        return response.json()

    except Exception as e:
        logger.error(
            "RouterOS REST call failed",
            extra={
                "device_id": device_id,
                "endpoint": endpoint,
                "error": str(e)
            }
        )
        raise
```

**Correlation ID Flow Example:**

```
User calls dns/get-status tool
├─ API Layer: correlation_id=abc-123 set, logs "MCP request received"
│  ├─ Domain Layer: dns_service.get_status() logs "Fetching DNS status" (correlation_id=abc-123)
│  │  ├─ Infrastructure: routeros_client.get() logs "RouterOS REST call starting" (correlation_id=abc-123)
│  │  │  └─ RouterOS: HTTP GET /rest/ip/dns
│  │  ├─ Infrastructure: logs "RouterOS REST call succeeded" (correlation_id=abc-123)
│  │  └─ Domain: logs "DNS status fetched" (correlation_id=abc-123)
│  ├─ Audit Service: writes AuditEvent with correlation_id=abc-123
│  └─ API Layer: logs "MCP request completed" (correlation_id=abc-123)
└─ Response sent to client
```

**Benefits:**
- **End-to-end tracing**: Search logs for `correlation_id=abc-123` to see entire request lifecycle
- **Performance analysis**: Measure time spent in each layer for single request
- **Error debugging**: Find all related logs when request fails
- **Multi-device operations**: All devices in plan share same correlation_id

---

## Standardized log and metric fields that tie MCP tool invocations to RouterOS operations

To connect MCP activity with RouterOS operations:

- **Logs**:
  - When MCP calls RouterOS:
    - Log an event including `correlation_id`, `device_id`, REST endpoint, HTTP method.  
    - On failure, include RouterOS error payload (sanitized) in `details`.

- **Metrics**:
  - Per-tool metrics:
    - `mcp_tool_requests_total{tool_name, tool_tier, status}`.  
    - `mcp_tool_latency_seconds_bucket{tool_name, tool_tier}`.
  - Per-device metrics:
    - `mcp_routeros_requests_total{device_id, topic, method, status}`.  
    - `mcp_routeros_latency_seconds_bucket{device_id, topic}`.

This standardization supports queries like:

- “Show error rate for `dns` advanced writes on `prod` devices in the last 1h.”  
- “Which devices have the highest RouterOS REST latency?”

---

## Metrics and counters (per-tool, per-device, per-topic, REST vs SSH usage)

Key metric families:

- **MCP Protocol-Level** (Phase 1):
  - `mcp_requests_total{method, status}` - Total MCP JSON-RPC requests by method (`tools/call`, `tools/list`, `initialize`, etc.)
  - `mcp_request_duration_seconds{method}` - MCP request duration histogram
  - `mcp_initialize_total{client_name, client_version}` - Client type distribution (tracks tools-only vs full MCP clients)
  - `mcp_tools_list_calls_total` - How often clients discover tools
  - `mcp_error_total{error_code}` - MCP protocol errors by JSON-RPC error code

- **MCP Tool-Level** (Phase 1):
  - `mcp_tool_requests_total{tool_name, tool_tier, status}` - Per-tool request counts
  - `mcp_tool_latency_seconds{tool_name, tool_tier}` - Per-tool latency histogram
  - `mcp_tool_response_size_bytes{tool_name}` - Response payload size (for token budget monitoring)
  - `mcp_tool_estimated_tokens{tool_name}` - Estimated token count in responses (for LLM context management)
  - `mcp_tool_token_budget_warnings_total{tool_name}` - Count of responses >5000 tokens

- **MCP Resources-Level** (Phase 2):
  - `mcp_resources_list_calls_total` - Resource discovery calls
  - `mcp_resources_read_total{resource_uri_pattern, status}` - Resource reads by URI pattern (`device://*/health`, etc.)
  - `mcp_resource_cache_hits_total{resource_type}` - Cache hit rate for resources
  - `mcp_resource_cache_misses_total{resource_type}` - Cache misses (triggers fresh fetch)
  - `mcp_resource_cache_ttl_expirations_total{resource_type}` - TTL expirations (requires refresh)
  - `mcp_resource_size_bytes{resource_uri_pattern}` - Resource payload size distribution

- **MCP Prompts-Level** (Phase 2):
  - `mcp_prompts_list_calls_total` - Prompt discovery calls
  - `mcp_prompts_get_total{prompt_name, status}` - Prompt invocations by name
  - `mcp_prompt_render_duration_seconds{prompt_name}` - Template rendering time

- **RouterOS-level**:
  - REST call counts and latencies per device and topic.
  - SSH usage metrics:
    - `ssh_commands_total{device_id, command_id, status}`.
    - Useful for ensuring SSH is rarely used and monitored.

- **Job/system-level**:
  - Jobs queued, running, succeeded, failed (by type).
  - Health check results per device.

- **Plan/Apply Workflow Metrics** (Professional Tools):
  - `mcp_plans_created_total{tool_name, risk_level}` - Plans created by tool and risk level
  - `mcp_plans_applied_total{risk_level, status}` - Plan executions by status (success, partial_failure, failed)
  - `mcp_approval_tokens_generated_total` - Approval token generation rate
  - `mcp_approval_tokens_expired_total` - Expired tokens (not used within TTL)
  - `mcp_approval_tokens_validated_total{status}` - Token validation attempts (success/failure)
  - `mcp_rollbacks_triggered_total{reason}` - Automatic rollbacks by reason (health_check_failed, verification_failed)
  - `mcp_rollbacks_succeeded_total` - Successful automatic rollbacks
  - `mcp_rollbacks_failed_total` - Failed rollbacks (manual intervention required)

These metrics should be exported via a standard scraping endpoint or push mechanism.

### Example Prometheus Metrics Implementation

```python
from prometheus_client import Counter, Histogram, Gauge, Info

# MCP Protocol Metrics
mcp_requests_total = Counter(
    "mcp_requests_total",
    "Total MCP JSON-RPC requests",
    ["method", "status"]
)

mcp_request_duration_seconds = Histogram(
    "mcp_request_duration_seconds",
    "MCP request duration",
    ["method"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

mcp_initialize_total = Counter(
    "mcp_initialize_total",
    "MCP client initializations",
    ["client_name", "client_version", "capabilities"]
)

# MCP Tool Metrics
mcp_tool_requests_total = Counter(
    "mcp_tool_requests_total",
    "Total tool invocations",
    ["tool_name", "tool_tier", "status"]
)

mcp_tool_latency_seconds = Histogram(
    "mcp_tool_latency_seconds",
    "Tool execution duration",
    ["tool_name", "tool_tier"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

mcp_tool_response_size_bytes = Histogram(
    "mcp_tool_response_size_bytes",
    "Tool response payload size",
    ["tool_name"],
    buckets=[100, 1000, 10000, 100000, 1000000]
)

mcp_tool_estimated_tokens = Histogram(
    "mcp_tool_estimated_tokens",
    "Estimated token count in tool responses",
    ["tool_name"],
    buckets=[100, 500, 1000, 5000, 10000, 50000, 100000]
)

mcp_tool_token_budget_warnings_total = Counter(
    "mcp_tool_token_budget_warnings_total",
    "Responses exceeding token budget warning threshold",
    ["tool_name"]
)

# MCP Resource Metrics (Phase 2)
mcp_resource_cache_hits_total = Counter(
    "mcp_resource_cache_hits_total",
    "Resource cache hits",
    ["resource_type"]
)

mcp_resource_cache_misses_total = Counter(
    "mcp_resource_cache_misses_total",
    "Resource cache misses",
    ["resource_type"]
)

# Plan/Apply Workflow Metrics
mcp_plans_created_total = Counter(
    "mcp_plans_created_total",
    "Plans created",
    ["tool_name", "risk_level"]
)

mcp_plans_applied_total = Counter(
    "mcp_plans_applied_total",
    "Plan executions",
    ["risk_level", "status"]
)

mcp_rollbacks_triggered_total = Counter(
    "mcp_rollbacks_triggered_total",
    "Automatic rollbacks triggered",
    ["reason"]
)

# Example usage in MCP handler
async def handle_tool_call(params: dict) -> dict:
    """Handle tools/call with metrics."""
    tool_name = params["name"]
    tool_tier = get_tool_tier(tool_name)

    start_time = time.time()

    try:
        result = await execute_tool(tool_name, params.get("arguments", {}))

        # Record success metrics
        mcp_tool_requests_total.labels(
            tool_name=tool_name,
            tool_tier=tool_tier,
            status="success"
        ).inc()

        # Record response size
        response_json = json.dumps(result)
        response_size = len(response_json.encode())
        mcp_tool_response_size_bytes.labels(tool_name=tool_name).observe(response_size)

        # Record estimated tokens
        estimated_tokens = result.get("_meta", {}).get("estimated_tokens", 0)
        if estimated_tokens:
            mcp_tool_estimated_tokens.labels(tool_name=tool_name).observe(estimated_tokens)

        # Check token budget warning threshold
        if estimated_tokens > 5000:
            mcp_tool_token_budget_warnings_total.labels(tool_name=tool_name).inc()

        return result

    except Exception as e:
        # Record failure metrics
        mcp_tool_requests_total.labels(
            tool_name=tool_name,
            tool_tier=tool_tier,
            status="error"
        ).inc()
        raise

    finally:
        # Record latency
        duration = time.time() - start_time
        mcp_tool_latency_seconds.labels(
            tool_name=tool_name,
            tool_tier=tool_tier
        ).observe(duration)
```

---

## Tracing model across MCP tools, service layers, and RouterOS calls

- **Tracing framework**:
  - Use OpenTelemetry or similar to generate spans for:
    - MCP request handling (tool invocation).  
    - Domain service operations.  
    - RouterOS REST/SSH calls.

- **Span structure**:
  - Root span: MCP request (per tool call).  
  - Child spans:
    - Authorization checks.  
    - Domain service logic.  
    - Each RouterOS call (REST/SSH).

- **Trace attributes**:
  - `tool_name`, `tool_tier`, `user_role`, `device_id`, `topic`, `routeros_endpoint`.  
  - Error flags and RouterOS error details (sanitized) on failing spans.

Traces help answer questions like:

- “Is latency dominated by MCP or RouterOS?”  
- “Where in the pipeline do failures occur?”

---

## Diagnostics flows for RouterOS call failures (request IDs, device ID, RouterOS error payloads, retry behavior)

When RouterOS calls fail, diagnostics should be consistent and rich:

- **Failure logging**:
  - Log entries include:
    - `correlation_id`, `device_id`, `routeros_endpoint`, HTTP status.  
    - RouterOS error body (where safe and useful).  
    - Retry behavior: attempted retries, backoff, final outcome.

- **Error surfacing to clients**:
  - MCP error responses map RouterOS errors to standardized error codes and messages.  
  - Include `device_id` and a hint (e.g., “device unreachable”, “auth failure”, “validation error”).

- **Diagnostic tools**:
  - Provide tools (read-only) to:
    - Fetch recent RouterOS error history for a device.  
    - Inspect health and metrics around the time of failures.

Runbooks (in the operations doc) can rely on these diagnostics for triage.

---

## Audit vs operational logging (separation and storage)

- **Audit logs**:
  - Focus on:
    - Who did what, when, where, and what changed.  
    - All writes and sensitive reads.  
  - Immutable, append-only; may be stored in a separate audit store.  
  - Longer retention than operational logs.

- **Operational logs**:
  - Focus on:
    - Service health, errors, performance, diagnostics.  
  - Rotated more aggressively; primarily used for debugging and monitoring.

- **Separation**:
  - Even if audit and operational logs end up in the same backend, they should be distinguishable via fields (e.g., `log_type = "audit" | "operational"`).

---

## Integration with log/metrics backends and dashboards/alerts

- **Backends**:
  - Logging: ELK/EFK stack, cloud logging services, or similar.
  - Metrics: Prometheus + Grafana or managed metrics service.
  - Tracing: Jaeger, Tempo, or managed tracing service.

- **Dashboards**:
  - **MCP Protocol Overview**:
    - MCP client distribution (tools-only vs full MCP clients)
    - Request rate by MCP method (`tools/call`, `resources/read`, `prompts/get`)
    - MCP protocol error rate by error code
    - Initialize requests over time (client adoption tracking)

  - **MCP Tools Dashboard**:
    - Tool request rates by tier (fundamental, advanced, professional)
    - Tool latency distribution (p50, p95, p99)
    - Top 10 most-used tools
    - Top 10 slowest tools
    - Top failing tools and error reasons
    - Token budget warnings by tool (responses >5000 tokens)
    - Tool usage distribution (which tools are LLMs actually calling?)

  - **MCP Resources Dashboard** (Phase 2):
    - Resource cache hit/miss ratio by resource type
    - Resource access patterns (which URIs are most popular?)
    - Resource cache TTL expirations
    - Resource payload size distribution
    - Background refresh job success rate

  - **MCP Prompts Dashboard** (Phase 2):
    - Prompt usage frequency
    - Prompt rendering duration
    - Most popular workflow prompts

  - **Plan/Apply Workflows Dashboard** (Professional Tier):
    - Plans created per hour
    - Plan execution success rate
    - Approval token lifecycle metrics (generated, expired, validated)
    - Rollback rate and success rate
    - Per-device plan execution duration
    - Blast radius (devices affected per plan)

  - **RouterOS fleet**:
    - Device health distribution.
    - REST error rates and latencies per device.

  - **Jobs**:
    - Job queue depth, success/failure rates by type.

- **Alerts**:
  - **MCP Protocol Alerts**:
    - High MCP protocol error rate (>5% of requests failing with JSON-RPC errors)
    - MCP server unavailable (no initialize requests in 5 minutes)
    - Unknown MCP client detected (client_name not in allowlist)

  - **MCP Tool Alerts**:
    - High error rate for critical tools (>10% failure rate for fundamental tier)
    - Tool latency degradation (p95 latency >2x baseline for >5 minutes)
    - Token budget warnings spike (>50% of tool responses exceeding 5000 tokens)
    - Unauthorized tool access surge (>10 `AUTHZ_DENIED` events in 5 minutes)

  - **MCP Resource Alerts** (Phase 2):
    - Resource cache hit rate <80% (background refresh failing?)
    - Resource payload size exceeding 1MB (potential performance issue)

  - **Plan/Apply Workflow Alerts** (Professional Tier):
    - Rollback rate >10% (indicates unstable changes or bad health checks)
    - Approval token expiration rate >20% (tokens not being used within TTL)
    - Failed rollback detected (manual intervention required)
    - Plan affecting >50 devices (blast radius warning)

  - **RouterOS Fleet Alerts**:
    - Many devices becoming `unreachable` or `degraded`.
    - Abnormal SSH usage (e.g., more than expected in production).

  - **Security Alerts**:
    - Surge in `AUTHZ_DENIED` events (possible misuse or compromised credentials).
    - Professional tool executed without approval token (Phase 4)
    - Credential rotation failure (devices unreachable after rotation)

### Example Grafana Dashboard Queries

**MCP Tools Usage (Top 10)**

```promql
# Top 10 tools by request count (last 1 hour)
topk(10, sum by(tool_name) (
  increase(mcp_tool_requests_total[1h])
))
```

**Tool Latency Heatmap**

```promql
# p95 latency by tool (last 24 hours)
histogram_quantile(0.95, sum by(tool_name, le) (
  rate(mcp_tool_latency_seconds_bucket[24h])
))
```

**Token Budget Warnings**

```promql
# Tools exceeding token budget (>5000 tokens)
sum by(tool_name) (
  increase(mcp_tool_token_budget_warnings_total[1h])
) > 0
```

**Resource Cache Efficiency**

```promql
# Cache hit rate by resource type
sum by(resource_type) (rate(mcp_resource_cache_hits_total[5m]))
/
(
  sum by(resource_type) (rate(mcp_resource_cache_hits_total[5m])) +
  sum by(resource_type) (rate(mcp_resource_cache_misses_total[5m]))
)
```

**Plan Execution Success Rate**

```promql
# Success rate for plan executions (last 24 hours)
sum(increase(mcp_plans_applied_total{status="completed"}[24h]))
/
sum(increase(mcp_plans_applied_total[24h]))
```

**Rollback Rate**

```promql
# Percentage of plans requiring rollback
sum(increase(mcp_rollbacks_triggered_total[24h]))
/
sum(increase(mcp_plans_applied_total[24h]))
```

### MCP Server Health Check Endpoint

**Endpoint:** `GET /health` (HTTP API, not MCP protocol)

**Purpose:** Load balancer health checks, readiness probes

**Response Format:**

```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T14:30:00Z",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5.2,
      "last_check": "2025-01-15T14:29:55Z"
    },
    "routeros_devices": {
      "status": "healthy",
      "reachable_count": 8,
      "unreachable_count": 2,
      "total_count": 10,
      "last_check": "2025-01-15T14:29:50Z"
    },
    "job_scheduler": {
      "status": "healthy",
      "jobs_running": 3,
      "jobs_queued": 0,
      "last_check": "2025-01-15T14:29:58Z"
    },
    "resource_cache": {
      "status": "healthy",
      "cached_devices": 8,
      "cache_hit_rate": 0.92,
      "last_refresh": "2025-01-15T14:29:00Z"
    }
  },
  "version": "1.0.0",
  "uptime_seconds": 86400
}
```

**Health Status Values:**
- `healthy`: All systems operational
- `degraded`: Some non-critical issues (e.g., some devices unreachable)
- `unhealthy`: Critical issues (e.g., database down, cannot serve requests)

**HTTP Status Codes:**
- `200 OK`: status = healthy or degraded
- `503 Service Unavailable`: status = unhealthy

**Load Balancer Configuration:**
- Check interval: 10 seconds
- Timeout: 5 seconds
- Unhealthy threshold: 3 consecutive failures
- Healthy threshold: 2 consecutive successes

---

## MCP Observability Best Practices

### Request Correlation with JSON-RPC IDs

Following MCP best practices (Section A9), use JSON-RPC request IDs for correlation:

```python
# Every log includes the JSON-RPC request ID for tracing

@mcp.tool()
async def system_get_overview(device_id: str, _context: McpContext) -> dict:
    """System overview with request correlation."""
    request_id = _context.request_id  # JSON-RPC request ID

    logger.info(
        "tool_call_start",
        extra={
            "request_id": request_id,
            "tool": "system/get-overview",
            "device_id": device_id
        }
    )

    try:
        result = await system_service.get_overview(device_id, correlation_id=request_id)

        logger.info(
            "tool_call_success",
            extra={
                "request_id": request_id,
                "tool": "system/get-overview",
                "device_id": device_id,
                "duration_ms": 123
            }
        )

        return result

    except Exception as e:
        logger.error(
            "tool_call_error",
            extra={
                "request_id": request_id,
                "tool": "system/get-overview",
                "device_id": device_id,
                "error": str(e)
            }
        )
        raise
```

### Tool Call Latency Percentiles

Track P50/P95/P99 latencies per tool:

```python
# routeros_mcp/observability/metrics.py

from prometheus_client import Histogram

mcp_tool_duration_seconds = Histogram(
    "mcp_tool_duration_seconds",
    "Tool call duration distribution",
    ["tool_name", "tier"],
    buckets=(
        0.01, 0.05, 0.1, 0.25, 0.5,  # Fast tools (< 500ms)
        1.0, 2.5, 5.0,                # Moderate tools (< 5s)
        10.0, 30.0, 60.0              # Slow tools (< 60s)
    )
)

# Usage
with mcp_tool_duration_seconds.labels(tool_name="system/get-overview", tier="fundamental").time():
    result = await system_service.get_overview(device_id)
```

**Query for P95 latency:**
```promql
histogram_quantile(
  0.95,
  sum by (tool_name, le) (
    rate(mcp_tool_duration_seconds_bucket[5m])
  )
)
```

### Error Rate by Tool and Error Code

Track errors with MCP error code taxonomy:

```python
mcp_tool_errors_total = Counter(
    "mcp_tool_errors_total",
    "Tool call errors by type",
    ["tool_name", "error_code", "mcp_error_code"]
)

# Usage
try:
    result = await tool_function(device_id)
except McpError as e:
    mcp_tool_errors_total.labels(
        tool_name="system/get-overview",
        error_code=str(e.code),           # JSON-RPC error code
        mcp_error_code=e.data.get("mcp_error_code", "UNKNOWN")
    ).inc()
    raise
```

**Alert on high error rate:**
```yaml
- alert: HighToolErrorRate
  expr: |
    sum by (tool_name) (
      rate(mcp_tool_errors_total[5m])
    ) / sum by (tool_name) (
      rate(mcp_tool_calls_total[5m])
    ) > 0.05
  annotations:
    summary: "{{ $labels.tool_name }} error rate > 5%"
```

### Token Budget Tracking and Warnings

Monitor token consumption and warnings:

```python
mcp_tool_response_tokens = Histogram(
    "mcp_tool_response_tokens",
    "Estimated token count in tool responses",
    ["tool_name"],
    buckets=(10, 50, 100, 500, 1000, 5000, 10000, 50000, 100000)
)

mcp_token_budget_warnings_total = Counter(
    "mcp_token_budget_warnings_total",
    "Tools that exceeded token budget thresholds",
    ["tool_name", "threshold"]
)

# Usage
response_text = json.dumps(result)
estimated_tokens = len(response_text) // 4  # ~4 chars/token

mcp_tool_response_tokens.labels(tool_name="system/get-overview").observe(estimated_tokens)

if estimated_tokens > 10000:
    mcp_token_budget_warnings_total.labels(
        tool_name="system/get-overview",
        threshold="10k"
    ).inc()
    logger.warning(
        "token_budget_warning",
        extra={
            "tool": "system/get-overview",
            "estimated_tokens": estimated_tokens,
            "threshold": 10000
        }
    )
```

### MCP Client Tracking

Track which MCP clients are connecting:

```python
mcp_initialize_total = Counter(
    "mcp_initialize_total",
    "MCP initialize calls by client",
    ["client_name", "client_version", "capabilities"]
)

# Usage in initialize handler
async def handle_initialize(request: InitializeRequest):
    client_info = request.client_info
    caps = ",".join([
        k for k, v in request.capabilities.items()
        if v.get("supported", False)
    ])

    mcp_initialize_total.labels(
        client_name=client_info.get("name", "unknown"),
        client_version=client_info.get("version", "unknown"),
        capabilities=caps
    ).inc()

    return InitializeResponse(...)
```

**Query client distribution:**
```promql
sum by (client_name) (mcp_initialize_total)
```

### Connection Pool Metrics

Track database and RouterOS connection health:

```python
# Database connection pool
db_pool_connections = Gauge(
    "db_pool_connections",
    "Database connection pool status",
    ["state"]  # active, idle, waiting
)

# RouterOS connection pool
routeros_pool_connections = Gauge(
    "routeros_pool_connections",
    "RouterOS connection pool per device",
    ["device_id", "state"]
)

# Update periodically
async def update_pool_metrics():
    while True:
        # Database pool
        pool_status = await db_manager.get_pool_status()
        db_pool_connections.labels(state="active").set(pool_status.active)
        db_pool_connections.labels(state="idle").set(pool_status.idle)
        db_pool_connections.labels(state="waiting").set(pool_status.waiting)

        # RouterOS pools
        for device_id, pool in routeros_pools.items():
            routeros_pool_connections.labels(
                device_id=device_id,
                state="active"
            ).set(pool.active_count)

        await asyncio.sleep(15)  # Update every 15s
```

### Structured Logging with JSON

Use structured JSON logging for easy parsing:

```python
import structlog

logger = structlog.get_logger()

# Configure JSON logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

# Usage
logger.info(
    "tool_call",
    request_id="req-123",
    tool="system/get-overview",
    device_id="dev-lab-01",
    duration_ms=123,
    status="success"
)

# Output:
# {"event": "tool_call", "request_id": "req-123", "tool": "system/get-overview", ...}
```

### Observability Checklist

- [ ] All tool calls logged with request_id (JSON-RPC ID)
- [ ] Latency tracked with P50/P95/P99 percentiles
- [ ] Error rates monitored per tool and error code
- [ ] Token budget tracked and warnings emitted
- [ ] Client types and versions tracked
- [ ] Connection pools monitored (DB + RouterOS)
- [ ] Structured JSON logging configured
- [ ] Correlation IDs propagate through all layers
- [ ] Dashboards created for key metrics
- [ ] Alerts configured for SLO violations
- [ ] Health check endpoint exposes component status
- [ ] Metrics exported to Prometheus/OpenTelemetry

---

## Summary

This observability design provides comprehensive monitoring for MCP-based RouterOS management:

**Core Capabilities:**

✅ **Correlation ID propagation** - End-to-end tracing from MCP request through all system layers to RouterOS calls
✅ **MCP protocol metrics** - Track client types, method distribution, protocol errors
✅ **Tool-level observability** - Per-tool latency, error rates, token budget warnings
✅ **Resource cache monitoring** - Phase 2 cache hit/miss rates, TTL expirations
✅ **Plan/apply workflow tracking** - Approval tokens, rollbacks, blast radius
✅ **Token budget management** - Automatic warnings for large responses exceeding LLM context limits
✅ **MCP-specific dashboards** - Ready-to-use Grafana queries for tools, resources, prompts
✅ **MCP-specific alerts** - Protocol errors, token budget warnings, rollback rates
✅ **Health check endpoint** - Load balancer integration with detailed component status

**MCP Integration Highlights:**

- **Client compatibility tracking**: Distinguish tools-only vs full MCP clients via `mcp_initialize_total{client_name, capabilities}`
- **Token budget observability**: `mcp_tool_estimated_tokens` and `mcp_tool_token_budget_warnings_total` prevent LLM context overflow
- **Resource efficiency**: `mcp_resource_cache_hits_total` tracks Phase 2 resource cache performance
- **Workflow observability**: `mcp_plans_applied_total`, `mcp_rollbacks_triggered_total` for professional tier safety
- **Context variable pattern**: Correlation IDs propagate automatically through all layers without explicit parameter passing

**Operational Benefits:**

- **Fast incident response**: Search logs by `correlation_id` to trace entire request lifecycle
- **Performance optimization**: Identify slow tools, high-latency devices, inefficient cache patterns
- **Security monitoring**: Detect unauthorized access, approval token abuse, credential failures
- **Capacity planning**: Track tool usage distribution, resource cache size, device fleet growth
- **Compliance**: Audit logs separate from operational logs, long retention for sensitive operations

**This observability design is production-ready for Phase 1 with clear extension paths for Phase 2 (resources/prompts), Phase 4 (multi-device workflows), and Phase 5 (multi-user RBAC).**

---

**Cross-References:**
- **[Doc 02: Security & Access Control](02-security-oauth-integration-and-access-control.md)** - Audit logging requirements
- **[Doc 04: MCP Tools Interface](04-mcp-tools-interface-and-json-schema-specification.md)** - Tool metadata for observability
- **[Doc 05: Domain Model & Persistence](05-domain-model-persistence-and-task-job-model.md)** - Correlation ID in entities
- **[Doc 06: Metrics Collection](06-system-information-and-metrics-collection-module-design.md)** - Health check metrics
- **[Doc 07: High-Risk Operations](07-device-control-and-high-risk-operations-safeguards.md)** - Plan/apply workflow observability
- **[Doc 19: Error Codes](19-json-rpc-error-codes-and-mcp-protocol-specification.md)** - Error code tracking in metrics

