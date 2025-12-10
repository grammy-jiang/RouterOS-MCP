"""OpenTelemetry distributed tracing for observability.

Provides tracing across HTTP, MCP, and RouterOS clients with correlation
ID propagation.

See docs/08-observability-logging-metrics-and-diagnostics.md for
detailed requirements.
"""

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from routeros_mcp.infra.observability.logging import correlation_id_var, get_correlation_id

logger = logging.getLogger(__name__)

# Global tracer provider
_tracer_provider: TracerProvider | None = None
_tracer: trace.Tracer | None = None


def setup_tracing(
    service_name: str = "routeros-mcp",
    environment: str = "lab",
    console_export: bool = False,
) -> None:
    """Configure OpenTelemetry tracing.

    Args:
        service_name: Service name for traces
        environment: Environment (lab/staging/prod)
        console_export: Whether to export traces to console (for debugging)
    """
    global _tracer_provider, _tracer

    # Create resource
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "0.1.0",
            "deployment.environment": environment,
        }
    )

    # Create tracer provider
    _tracer_provider = TracerProvider(resource=resource)

    # Add console exporter for debugging
    if console_export:
        console_exporter = ConsoleSpanExporter()
        console_processor = BatchSpanProcessor(console_exporter)
        _tracer_provider.add_span_processor(console_processor)

    # Set as global tracer provider
    trace.set_tracer_provider(_tracer_provider)

    # Get tracer
    _tracer = trace.get_tracer(__name__)

    logger.info(
        "Tracing configured",
        extra={
            "service_name": service_name,
            "environment": environment,
            "console_export": console_export,
        },
    )


def get_tracer() -> trace.Tracer:
    """Get the global tracer.

    Returns:
        OpenTelemetry tracer

    Raises:
        RuntimeError: If tracing not configured
    """
    if _tracer is None:
        raise RuntimeError("Tracing not configured. Call setup_tracing() first.")
    return _tracer


def create_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
) -> trace.Span:
    """Create a new trace span with correlation ID.

    Args:
        name: Span name
        attributes: Span attributes
        kind: Span kind (INTERNAL/CLIENT/SERVER/etc)

    Returns:
        Trace span
    """
    tracer = get_tracer()

    # Add correlation ID to attributes
    attrs = attributes or {}
    attrs["correlation_id"] = get_correlation_id()

    span = tracer.start_span(name, attributes=attrs, kind=kind)
    return span


def trace_mcp_tool_call(tool_name: str, tool_tier: str) -> trace.Span:
    """Create a span for an MCP tool call.

    Args:
        tool_name: Tool name
        tool_tier: Tool tier

    Returns:
        Trace span
    """
    return create_span(
        f"mcp.tool.{tool_name}",
        attributes={
            "mcp.tool.name": tool_name,
            "mcp.tool.tier": tool_tier,
        },
        kind=trace.SpanKind.SERVER,
    )


def trace_routeros_request(
    device_id: str, method: str, endpoint: str
) -> trace.Span:
    """Create a span for a RouterOS API request.

    Args:
        device_id: Device identifier
        method: HTTP method
        endpoint: API endpoint

    Returns:
        Trace span
    """
    return create_span(
        f"routeros.{method}.{endpoint}",
        attributes={
            "routeros.device.id": device_id,
            "http.method": method,
            "http.url": endpoint,
        },
        kind=trace.SpanKind.CLIENT,
    )


def trace_health_check(device_id: str) -> trace.Span:
    """Create a span for a device health check.

    Args:
        device_id: Device identifier

    Returns:
        Trace span
    """
    return create_span(
        "health.check",
        attributes={
            "device.id": device_id,
        },
        kind=trace.SpanKind.INTERNAL,
    )


def trace_plan_operation(plan_id: str, operation: str) -> trace.Span:
    """Create a span for a plan operation.

    Args:
        plan_id: Plan identifier
        operation: Operation (create/approve/apply)

    Returns:
        Trace span
    """
    return create_span(
        f"plan.{operation}",
        attributes={
            "plan.id": plan_id,
            "plan.operation": operation,
        },
        kind=trace.SpanKind.INTERNAL,
    )


def trace_job_execution(job_id: str, job_type: str) -> trace.Span:
    """Create a span for job execution.

    Args:
        job_id: Job identifier
        job_type: Job type

    Returns:
        Trace span
    """
    return create_span(
        f"job.execute.{job_type}",
        attributes={
            "job.id": job_id,
            "job.type": job_type,
        },
        kind=trace.SpanKind.INTERNAL,
    )


def add_span_event(
    span: trace.Span, name: str, attributes: dict[str, Any] | None = None
) -> None:
    """Add an event to a span.

    Args:
        span: Span to add event to
        name: Event name
        attributes: Event attributes
    """
    span.add_event(name, attributes=attributes or {})


def set_span_error(span: trace.Span, error: Exception) -> None:
    """Mark span as error and record exception.

    Args:
        span: Span to mark as error
        error: Exception that occurred
    """
    span.set_status(trace.Status(trace.StatusCode.ERROR, str(error)))
    span.record_exception(error)


__all__ = [
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
