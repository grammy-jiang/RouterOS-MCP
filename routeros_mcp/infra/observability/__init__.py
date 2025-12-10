"""Observability infrastructure for RouterOS MCP.

Provides structured logging, metrics, and distributed tracing for
monitoring and debugging production deployments.

See docs/08-observability-logging-metrics-and-diagnostics.md for
detailed requirements.
"""

from routeros_mcp.infra.observability.logging import (
    CorrelationIDFilter,
    JSONFormatter,
    correlation_id_var,
    get_correlation_id,
    set_correlation_id,
    setup_logging,
)
from routeros_mcp.infra.observability.metrics import (
    get_metrics_text,
    get_registry,
    record_auth_check,
    record_authz_check,
    record_health_check,
    record_job_event,
    record_plan_event,
    record_resource_read,
    record_routeros_request,
    record_tool_call,
)
from routeros_mcp.infra.observability.tracing import (
    add_span_event,
    create_span,
    get_tracer,
    set_span_error,
    setup_tracing,
    trace_health_check,
    trace_job_execution,
    trace_mcp_tool_call,
    trace_plan_operation,
    trace_routeros_request,
)

__all__ = [
    # Logging
    "correlation_id_var",
    "get_correlation_id",
    "set_correlation_id",
    "CorrelationIDFilter",
    "JSONFormatter",
    "setup_logging",
    # Metrics
    "get_registry",
    "get_metrics_text",
    "record_tool_call",
    "record_routeros_request",
    "record_health_check",
    "record_plan_event",
    "record_job_event",
    "record_resource_read",
    "record_auth_check",
    "record_authz_check",
    # Tracing
    "setup_tracing",
    "get_tracer",
    "create_span",
    "trace_mcp_tool_call",
    "trace_routeros_request",
    "trace_health_check",
    "trace_plan_operation",
    "trace_job_execution",
    "add_span_event",
    "set_span_error",
]
