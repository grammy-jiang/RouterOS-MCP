"""Prometheus metrics for observability.

Provides metrics collection for MCP operations, RouterOS requests,
health checks, and plan/job execution.

See docs/08-observability-logging-metrics-and-diagnostics.md for
detailed requirements.
"""

import logging

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)

# Global registry for metrics
_registry = CollectorRegistry()


# MCP Tool Metrics
mcp_tool_calls_total = Counter(
    "routeros_mcp_tool_calls_total",
    "Total number of MCP tool calls",
    ["tool_name", "tool_tier", "status"],
    registry=_registry,
)

mcp_tool_duration_seconds = Histogram(
    "routeros_mcp_tool_duration_seconds",
    "Duration of MCP tool calls in seconds",
    ["tool_name", "tool_tier"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=_registry,
)

# RouterOS Client Metrics
routeros_requests_total = Counter(
    "routeros_mcp_routeros_requests_total",
    "Total number of RouterOS API requests",
    ["device_id", "environment", "method", "status"],
    registry=_registry,
)

routeros_request_duration_seconds = Histogram(
    "routeros_mcp_routeros_request_duration_seconds",
    "Duration of RouterOS API requests in seconds",
    ["device_id", "method"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=_registry,
)

# Health Check Metrics
health_checks_total = Counter(
    "routeros_mcp_health_checks_total",
    "Total number of health checks performed",
    ["device_id", "status"],
    registry=_registry,
)

device_health_status = Gauge(
    "routeros_mcp_device_health_status",
    "Device health status (1=healthy, 0.5=degraded, 0=unreachable)",
    ["device_id", "environment"],
    registry=_registry,
)

device_cpu_usage_percent = Gauge(
    "routeros_mcp_device_cpu_usage_percent",
    "Device CPU usage percentage",
    ["device_id", "environment"],
    registry=_registry,
)

device_memory_usage_percent = Gauge(
    "routeros_mcp_device_memory_usage_percent",
    "Device memory usage percentage",
    ["device_id", "environment"],
    registry=_registry,
)

device_uptime_seconds = Gauge(
    "routeros_mcp_device_uptime_seconds",
    "Device uptime in seconds",
    ["device_id", "environment"],
    registry=_registry,
)

# Plan/Job Metrics
plans_created_total = Counter(
    "routeros_mcp_plans_created_total",
    "Total number of plans created",
    ["tool_name", "risk_level"],
    registry=_registry,
)

plans_approved_total = Counter(
    "routeros_mcp_plans_approved_total",
    "Total number of plans approved",
    ["tool_name"],
    registry=_registry,
)

plans_applied_total = Counter(
    "routeros_mcp_plans_applied_total",
    "Total number of plans applied",
    ["tool_name", "status"],
    registry=_registry,
)

jobs_created_total = Counter(
    "routeros_mcp_jobs_created_total",
    "Total number of jobs created",
    ["job_type"],
    registry=_registry,
)

jobs_executed_total = Counter(
    "routeros_mcp_jobs_executed_total",
    "Total number of jobs executed",
    ["job_type", "status"],
    registry=_registry,
)

job_execution_duration_seconds = Histogram(
    "routeros_mcp_job_execution_duration_seconds",
    "Duration of job execution in seconds",
    ["job_type"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
    registry=_registry,
)

job_device_count = Gauge(
    "routeros_mcp_job_device_count",
    "Number of devices in job",
    ["job_id", "job_type"],
    registry=_registry,
)

# MCP Resource Metrics
mcp_resource_reads_total = Counter(
    "routeros_mcp_resource_reads_total",
    "Total number of MCP resource reads",
    ["resource_type", "status"],
    registry=_registry,
)

# Authentication/Authorization Metrics
auth_checks_total = Counter(
    "routeros_mcp_auth_checks_total",
    "Total number of authentication checks",
    ["status"],
    registry=_registry,
)

authz_checks_total = Counter(
    "routeros_mcp_authz_checks_total",
    "Total number of authorization checks",
    ["tool_tier", "status"],
    registry=_registry,
)


def get_registry() -> CollectorRegistry:
    """Get the metrics registry.

    Returns:
        Prometheus collector registry
    """
    return _registry


def get_metrics_text() -> str:
    """Get metrics in Prometheus text format.

    Returns:
        Metrics in Prometheus exposition format
    """
    return generate_latest(_registry).decode("utf-8")


def record_tool_call(
    tool_name: str, tool_tier: str, duration: float, success: bool
) -> None:
    """Record metrics for an MCP tool call.

    Args:
        tool_name: Name of the tool
        tool_tier: Tool tier (fundamental/advanced/professional)
        duration: Execution duration in seconds
        success: Whether the call succeeded
    """
    status = "success" if success else "error"
    mcp_tool_calls_total.labels(
        tool_name=tool_name, tool_tier=tool_tier, status=status
    ).inc()
    mcp_tool_duration_seconds.labels(tool_name=tool_name, tool_tier=tool_tier).observe(
        duration
    )


def record_routeros_request(
    device_id: str,
    environment: str,
    method: str,
    duration: float,
    success: bool,
) -> None:
    """Record metrics for a RouterOS API request.

    Args:
        device_id: Device identifier
        environment: Device environment
        method: HTTP method or endpoint
        duration: Request duration in seconds
        success: Whether the request succeeded
    """
    status = "success" if success else "error"
    routeros_requests_total.labels(
        device_id=device_id, environment=environment, method=method, status=status
    ).inc()
    routeros_request_duration_seconds.labels(device_id=device_id, method=method).observe(
        duration
    )


def record_health_check(
    device_id: str,
    environment: str,
    status: str,
    cpu_percent: float | None = None,
    memory_percent: float | None = None,
    uptime_seconds: int | None = None,
) -> None:
    """Record metrics for a device health check.

    Args:
        device_id: Device identifier
        environment: Device environment
        status: Health status (healthy/degraded/unreachable)
        cpu_percent: CPU usage percentage
        memory_percent: Memory usage percentage
        uptime_seconds: Device uptime in seconds
    """
    health_checks_total.labels(device_id=device_id, status=status).inc()

    # Convert status to numeric
    status_value = {"healthy": 1.0, "degraded": 0.5, "unreachable": 0.0}.get(
        status, 0.0
    )
    device_health_status.labels(device_id=device_id, environment=environment).set(
        status_value
    )

    if cpu_percent is not None:
        device_cpu_usage_percent.labels(device_id=device_id, environment=environment).set(
            cpu_percent
        )

    if memory_percent is not None:
        device_memory_usage_percent.labels(
            device_id=device_id, environment=environment
        ).set(memory_percent)

    if uptime_seconds is not None:
        device_uptime_seconds.labels(device_id=device_id, environment=environment).set(
            uptime_seconds
        )


def record_plan_event(
    event_type: str, tool_name: str, risk_level: str | None = None
) -> None:
    """Record metrics for a plan event.

    Args:
        event_type: Event type (created/approved/applied)
        tool_name: Tool that created the plan
        risk_level: Plan risk level (low/medium/high)
    """
    if event_type == "created" and risk_level:
        plans_created_total.labels(tool_name=tool_name, risk_level=risk_level).inc()
    elif event_type == "approved":
        plans_approved_total.labels(tool_name=tool_name).inc()
    elif event_type == "applied":
        plans_applied_total.labels(tool_name=tool_name, status="success").inc()
    elif event_type == "failed":
        plans_applied_total.labels(tool_name=tool_name, status="failed").inc()


def record_job_event(
    event_type: str,
    job_type: str,
    job_id: str | None = None,
    device_count: int | None = None,
    duration: float | None = None,
    success: bool | None = None,
) -> None:
    """Record metrics for a job event.

    Args:
        event_type: Event type (created/executed)
        job_type: Job type
        job_id: Job identifier
        device_count: Number of devices in job
        duration: Execution duration in seconds
        success: Whether execution succeeded
    """
    if event_type == "created":
        jobs_created_total.labels(job_type=job_type).inc()
        if job_id and device_count is not None:
            job_device_count.labels(job_id=job_id, job_type=job_type).set(device_count)
    elif event_type == "executed":
        status = "success" if success else "failed"
        jobs_executed_total.labels(job_type=job_type, status=status).inc()
        if duration is not None:
            job_execution_duration_seconds.labels(job_type=job_type).observe(duration)


def record_resource_read(resource_type: str, success: bool) -> None:
    """Record metrics for an MCP resource read.

    Args:
        resource_type: Resource type (device/plan/fleet)
        success: Whether the read succeeded
    """
    status = "success" if success else "error"
    mcp_resource_reads_total.labels(resource_type=resource_type, status=status).inc()


def record_auth_check(success: bool) -> None:
    """Record metrics for an authentication check.

    Args:
        success: Whether authentication succeeded
    """
    status = "success" if success else "failed"
    auth_checks_total.labels(status=status).inc()


def record_authz_check(tool_tier: str, success: bool) -> None:
    """Record metrics for an authorization check.

    Args:
        tool_tier: Tool tier being checked
        success: Whether authorization succeeded
    """
    status = "allowed" if success else "denied"
    authz_checks_total.labels(tool_tier=tool_tier, status=status).inc()


__all__ = [
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
]
