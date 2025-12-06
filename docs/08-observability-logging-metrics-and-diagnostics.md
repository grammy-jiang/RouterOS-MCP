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
    - `tool_name`, `tool_tier`  
    - `user_sub`, `user_email`, `user_role` (where applicable)  
    - `device_id`, `device_environment` (if device-specific)  
    - `error_code`, `error_message` (for failures)

- **Correlation IDs**:
  - Every MCP request gets a `correlation_id` (propagated to internal logs and traces).  
  - RouterOS calls made during the request log the same `correlation_id` for end-to-end attribution.

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

- **MCP-level**:
  - Request counts and latencies per tool, tier, and user role.  
  - Success vs various failure codes.

- **RouterOS-level**:
  - REST call counts and latencies per device and topic.  
  - SSH usage metrics:
    - `ssh_commands_total{device_id, command_id, status}`.  
    - Useful for ensuring SSH is rarely used and monitored.

- **Job/system-level**:
  - Jobs queued, running, succeeded, failed (by type).  
  - Health check results per device.

These metrics should be exported via a standard scraping endpoint or push mechanism.

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
  - MCP overview:
    - Tool request rates, error rates, and latencies.  
    - Top failing tools and reasons.  
  - RouterOS fleet:
    - Device health distribution.  
    - REST error rates and latencies per device.  
  - Jobs:
    - Job queue depth, success/failure rates by type.

- **Alerts**:
  - High error rate for critical tools.  
  - Surge in `AUTHZ_DENIED` events (possible misuse).  
  - Many devices becoming `unreachable` or `degraded`.  
  - Abnormal SSH usage (e.g., more than expected in production).

