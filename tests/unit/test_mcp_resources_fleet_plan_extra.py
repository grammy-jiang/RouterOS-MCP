import json

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp_resources import fleet as fleet_module
from routeros_mcp.mcp_resources import plan as plan_module


class FakeMCP:
    def __init__(self):
        self.resources = {}

    def resource(self, uri):  # noqa: D401
        def decorator(fn):
            self.resources[uri] = fn
            return fn

        return decorator


def _session_factory():
    class _Ctx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Factory:
        def session(self):
            return _Ctx()

    return _Factory()


class _Device:
    def __init__(self, id_: str, name: str, env: str, flags=None):
        self.id = id_
        self.name = name
        self.environment = env
        self.management_address = "10.0.0.1"
        self.tags = ["edge"]
        self.capability_flags = flags or {
            "allow_advanced_writes": True,
            "allow_professional_workflows": True,
        }


class FakeDeviceService:
    def __init__(self, session, settings):
        self.session = session
        self.settings = settings

    async def list_devices(self):
        return [
            _Device("d1", "dev1", "lab"),
            _Device("d2", "dev2", "prod"),
        ]


class FakeHealth:
    def __init__(self, status: str, metrics=None):
        self.status = status
        self.metrics = metrics or {"cpu_usage": 10, "memory_usage_percent": 20}


class FakeHealthService:
    def __init__(self, session, settings):
        self.session = session
        self.settings = settings
        self.calls = 0

    async def get_current_health(self, device_id):
        self.calls += 1
        if device_id == "d2":
            raise RuntimeError("unreachable")
        return FakeHealth("warning" if device_id == "d1" else "healthy")


class FakePlanService:
    def __init__(self, session):
        self.session = session

    async def get_plan(self, plan_id):
        return {
            "plan_id": plan_id,
            "tool_name": "config/apply",
            "status": "pending",
            "created_by": "user",
            "approved_by": None,
            "device_ids": ["d1"],
            "summary": "do things",
            "changes": {"dns": ["1.1.1.1"]},
            "created_at": "2024-01-01T00:00:00Z",
            "approved_at": None,
            "updated_at": "2024-01-02T00:00:00Z",
        }


class FakeJobService:
    def __init__(self, session):
        self.session = session

    async def list_jobs(self, plan_id: str, limit: int = 100):
        return [
            {"id": "j1", "status": "success"},
            {"id": "j2", "status": "failed"},
        ]


@pytest.fixture(autouse=True)
def patch_services(monkeypatch):
    monkeypatch.setattr(fleet_module, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(fleet_module, "HealthService", FakeHealthService)
    monkeypatch.setattr(plan_module, "PlanService", FakePlanService)
    monkeypatch.setattr(plan_module, "JobService", FakeJobService)


@pytest.fixture
def fleet_resources(monkeypatch):
    mcp = FakeMCP()
    settings = Settings()
    session_factory = _session_factory()
    fleet_module.register_fleet_resources(mcp, session_factory, settings)
    return mcp.resources


@pytest.fixture
def plan_resources(monkeypatch):
    mcp = FakeMCP()
    settings = Settings()
    session_factory = _session_factory()
    plan_module.register_plan_resources(mcp, session_factory, settings)
    return mcp.resources


@pytest.mark.asyncio
async def test_fleet_health_summary(fleet_resources):
    fn = fleet_resources["fleet://health-summary"]
    content = await fn()
    data = json.loads(content)
    assert data["summary"]["total_devices"] == 2
    assert data["health_distribution"]["unreachable"] == 1


@pytest.mark.asyncio
async def test_fleet_devices_filter(fleet_resources):
    fn = fleet_resources["fleet://devices"]
    content = await fn(environment="lab")
    data = json.loads(content)
    assert data["count"] == 1
    assert data["devices"][0]["environment"] == "lab"


@pytest.mark.asyncio
async def test_plan_resources_success(plan_resources):
    summary_fn = plan_resources["plan://{plan_id}/summary"]
    details_fn = plan_resources["plan://{plan_id}/details"]
    log_fn = plan_resources["plan://{plan_id}/execution-log"]

    summary = json.loads(await summary_fn("plan-1"))
    assert summary["plan_id"] == "plan-1"

    details = json.loads(await details_fn("plan-2"))
    assert details["plan_id"] == "plan-2"
    assert details["changes"]["dns"] == ["1.1.1.1"]

    log = json.loads(await log_fn("plan-3"))
    assert log["execution_summary"]["failed_jobs"] == 1


@pytest.mark.asyncio
async def test_plan_resources_error_path(monkeypatch, plan_resources):
    async def bad_get_plan(self, plan_id):
        raise RuntimeError("boom")

    # patch PlanService.get_plan to throw
    monkeypatch.setattr(FakePlanService, "get_plan", bad_get_plan)

    details_fn = plan_resources["plan://{plan_id}/details"]
    data = json.loads(await details_fn("plan-x"))
    assert data["error"] == "boom"
    assert data["plan_id"] == "plan-x"
