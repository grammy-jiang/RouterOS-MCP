"""Tests for Prometheus metrics utilities."""

from prometheus_client.parser import text_string_to_metric_families

from routeros_mcp.infra.observability import metrics


def _metric_value(sample_name: str) -> float:
    data = metrics.get_metrics_text()
    total = 0.0
    for family in text_string_to_metric_families(data):
        for sample in family.samples:
            if sample.name == sample_name:
                total += sample.value
    return total


def test_tool_and_routeros_metrics_recording() -> None:
    metrics.record_tool_call("tool/one", "fundamental", duration=0.2, success=True)
    metrics.record_tool_call("tool/one", "fundamental", duration=0.1, success=False)

    metrics.record_routeros_request("dev-1", "lab", "GET", duration=0.05, success=True)
    metrics.record_routeros_request("dev-1", "lab", "GET", duration=0.15, success=False)

    assert _metric_value("routeros_mcp_tool_calls_total") >= 2
    assert _metric_value("routeros_mcp_routeros_requests_total") >= 2


def test_health_and_plan_job_metrics() -> None:
    metrics.record_health_check(
        device_id="dev-2",
        environment="lab",
        status="healthy",
        cpu_percent=10.0,
        memory_percent=20.0,
        uptime_seconds=30,
    )

    metrics.record_plan_event("created", tool_name="tool/plan", risk_level="low")
    metrics.record_plan_event("approved", tool_name="tool/plan")
    metrics.record_plan_event("applied", tool_name="tool/plan")
    metrics.record_plan_event("failed", tool_name="tool/plan")

    metrics.record_job_event(
        event_type="created",
        job_type="sync",
        job_id="job-1",
        device_count=3,
    )
    metrics.record_job_event(
        event_type="executed",
        job_type="sync",
        duration=1.5,
        success=True,
    )

    assert _metric_value("routeros_mcp_health_checks_total") >= 1
    assert _metric_value("routeros_mcp_plans_created_total") >= 1
    assert _metric_value("routeros_mcp_plans_applied_total") >= 2  # applied + failed
    assert _metric_value("routeros_mcp_jobs_created_total") >= 1
    assert _metric_value("routeros_mcp_jobs_executed_total") >= 1


def test_resource_and_auth_metrics() -> None:
    metrics.record_resource_read("device", success=True)
    metrics.record_auth_check(success=True)
    metrics.record_authz_check(tool_tier="fundamental", success=False)

    assert _metric_value("routeros_mcp_resource_reads_total") >= 1
    assert _metric_value("routeros_mcp_auth_checks_total") >= 1
    assert _metric_value("routeros_mcp_authz_checks_total") >= 1
