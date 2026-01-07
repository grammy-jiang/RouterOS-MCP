import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import config as config_module


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class FakeDevice:
    def __init__(self, env="lab", allow_prof=True):
        self.environment = env
        self.allow_professional_workflows = allow_prof
        self.allow_advanced_writes = True
        self.name = "dev"


class FakeDeviceService:
    def __init__(self, *_args, **_kwargs):
        self.env = "lab"
        self.allow_professional = True

    async def get_device(self, device_id):
        return FakeDevice(self.env, self.allow_professional)


class FakeDNSNTPService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def get_dns_status(self, device_id):
        return {"dns": []}

    async def get_ntp_status(self, device_id):
        return {"ntp": []}

    async def update_dns_servers(self, device_id, dns_servers, dry_run=False):
        return {"changed": True, "new_servers": dns_servers, "old_servers": []}

    async def update_ntp_servers(self, device_id, ntp_servers, enabled=True, dry_run=False):
        if dry_run:
            return {
                "changed": False,
                "planned_changes": {"new_servers": ntp_servers, "new_enabled": enabled},
                "dry_run": True,
                "new_servers": ntp_servers,
                "enabled": enabled,
            }
        return {"changed": True, "new_servers": ntp_servers, "enabled": enabled, "old_servers": []}

    async def flush_dns_cache(self, device_id):
        return {"changed": True, "entries_flushed": 1}


class FakePlanService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def create_plan(self, **kwargs):
        return {
            "plan_id": "p1",
            "approval_token": "tok",
            "approval_expires_at": "never",
            **kwargs,
        }

    async def create_multi_device_plan(self, **kwargs):
        device_ids = kwargs.get("device_ids", ["d1", "d2"])
        batch_size = kwargs.get("batch_size", 5)

        # Calculate batches
        batches = []
        for i in range(0, len(device_ids), batch_size):
            batch_devices = device_ids[i:i + batch_size]
            batches.append({
                "batch_number": len(batches) + 1,
                "device_ids": batch_devices,
                "device_count": len(batch_devices),
            })

        return {
            "plan_id": "p1",
            "approval_token": "tok",
            "approval_expires_at": "never",
            "batch_size": batch_size,
            "batch_count": len(batches),
            "batches": batches,
            "device_ids": device_ids,
            **kwargs,
        }

    async def get_plan(self, plan_id):
        return {
            "plan_id": plan_id,
            "status": "approved",
            "summary": "ok",
            "changes": {"dns_servers": ["1.1.1.1"], "ntp_servers": ["ntp"]},
            "device_ids": ["d1"],
            "tool_name": "config/apply",
            "created_by": "user",
            "approved_by": "user",
            "created_at": "now",
            "approved_at": "now",
            "approval_token": "tok",
            "approval_expires_at": "never",
        }

    async def approve_plan(self, plan_id, approval_token, approved_by):
        return None

    async def update_plan_status(self, plan_id, status):
        return None


class FakeJobService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def create_job(self, **kwargs):
        return {"job_id": "j1", **kwargs}

    async def execute_job(
        self, job_id, executor, executor_context, batch_size, batch_pause_seconds
    ):
        device_ids = executor_context.get("device_ids") or ["d1"]
        results = await executor(job_id, device_ids, executor_context)
        return {
            "status": results.get("status", "success"),
            "device_results": results.get("devices", {}),
            "total_devices": len(device_ids),
            "batches_completed": 1,
            "batches_total": 1,
        }


class FakeHealthService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def check_device_health(self, device_id):
        return {"status": "healthy"}


class FakeSession:
    def session(self):
        class Ctx:
            async def __aenter__(self):
                return None

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return Ctx()


@pytest.fixture(autouse=True)
def patch_services(monkeypatch):
    monkeypatch.setattr(config_module, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(config_module, "DNSNTPService", FakeDNSNTPService)
    monkeypatch.setattr(config_module, "PlanService", FakePlanService)
    monkeypatch.setattr(config_module, "JobService", FakeJobService)
    monkeypatch.setattr(config_module, "HealthService", FakeHealthService)
    monkeypatch.setattr(
        config_module, "get_session_factory", lambda *_args, **_kwargs: FakeSession()
    )
    monkeypatch.setattr(config_module, "map_exception_to_error", lambda e: e)


@pytest.fixture
def tools():
    mcp = FakeMCP()
    settings = Settings()
    config_module.register_config_tools(mcp, settings)
    return mcp.tools, settings


@pytest.mark.asyncio
async def test_config_apply_dns_ntp(tools, monkeypatch):
    tools_map, settings = tools
    apply_fn = tools_map["config_apply_dns_ntp_rollout"]
    result = await apply_fn(
        plan_id="p1", approval_token="tok", approved_by="user", batch_size=1, batch_pause_seconds=0
    )
    assert result["_meta"]["plan_id"] == "p1"


@pytest.mark.asyncio
async def test_config_validate_raises_for_prod(tools, monkeypatch):
    tools_map, settings = tools
    # force prod env
    settings.environment = "prod"
    config_module.DeviceService.env = "prod"
    config_module.DeviceService.allow_professional = True
    plan_fn = tools_map["config_plan_dns_ntp_rollout"]
    with pytest.raises(ValueError):
        await plan_fn(device_ids=["d1"], dns_servers=None, ntp_servers=None)


@pytest.mark.asyncio
async def test_config_plan_apply_flow(tools, monkeypatch):
    tools_map, _settings = tools
    plan_fn = tools_map["config_plan_dns_ntp_rollout"]
    apply_fn = tools_map["config_apply_dns_ntp_rollout"]

    plan = await plan_fn(
        device_ids=["d1", "d2"], dns_servers=["8.8.8.8"], ntp_servers=["ntp"], created_by="tester"
    )
    assert plan["_meta"]["plan_id"] == "p1"

    apply = await apply_fn(
        plan_id="p1", approval_token="tok", approved_by="user", batch_size=1, batch_pause_seconds=0
    )
    assert apply["_meta"]["plan_id"] == "p1"
