"""Tests for tracing utilities."""

import pytest
from opentelemetry import trace

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


def test_setup_and_get_tracer() -> None:
    setup_tracing(service_name="test-service", environment="lab", console_export=False)
    tracer = get_tracer()
    assert tracer is not None


def test_create_span_and_events() -> None:
    setup_tracing(service_name="test-service", environment="lab", console_export=False)
    span = create_span("test-span", attributes={"key": "value"})
    add_span_event(span, "event", {"foo": "bar"})
    set_span_error(span, RuntimeError("boom"))
    span.end()

    # Ensure status has been set to error
    assert span.status.status_code == trace.StatusCode.ERROR


def test_specialized_span_builders() -> None:
    setup_tracing(service_name="test-service", environment="lab", console_export=False)

    spans = [
        trace_mcp_tool_call("tool/one", "fundamental"),
        trace_routeros_request("dev-1", "GET", "/rest/endpoint"),
        trace_health_check("dev-2"),
        trace_plan_operation("plan-1", "apply"),
        trace_job_execution("job-1", "sync"),
    ]

    for span in spans:
        assert span is not None
        span.end()


def test_get_tracer_without_setup_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("routeros_mcp.infra.observability.tracing._tracer", None)
    monkeypatch.setattr("routeros_mcp.infra.observability.tracing._tracer_provider", None)

    with pytest.raises(RuntimeError, match="Tracing not configured"):
        get_tracer()
