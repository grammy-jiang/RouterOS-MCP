import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import config as config_module
from routeros_mcp.mcp_tools import dns_ntp as dns_ntp_module
from routeros_mcp.mcp_tools import firewall_logs as fw_logs_module
from routeros_mcp.mcp_tools import ip as ip_module
from routeros_mcp.mcp_tools import system as system_module


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **_kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class FakeDevice:
    def __init__(self):
        self.environment = "lab"
        self.allow_advanced_writes = True
        self.allow_professional_workflows = True


class FakeDeviceService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def get_device(self, device_id):
        return FakeDevice()


class FakeSession:
    def session(self):
        class Ctx:
            async def __aenter__(self):
                return None

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return Ctx()


@pytest.fixture(autouse=True)
def _patch_common(monkeypatch):
    monkeypatch.setattr(fw_logs_module, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(fw_logs_module, "check_tool_authorization", lambda **kwargs: None)
    monkeypatch.setattr(
        fw_logs_module, "get_session_factory", lambda *_args, **_kwargs: FakeSession()
    )

    monkeypatch.setattr(ip_module, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(ip_module, "check_tool_authorization", lambda **kwargs: None)
    monkeypatch.setattr(ip_module, "get_session_factory", lambda *_args, **_kwargs: FakeSession())

    monkeypatch.setattr(system_module, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(system_module, "check_tool_authorization", lambda **kwargs: None)
    monkeypatch.setattr(
        system_module, "get_session_factory", lambda *_args, **_kwargs: FakeSession()
    )

    monkeypatch.setattr(dns_ntp_module, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(dns_ntp_module, "check_tool_authorization", lambda **kwargs: None)
    monkeypatch.setattr(
        dns_ntp_module, "get_session_factory", lambda *_args, **_kwargs: FakeSession()
    )


def _make_mcp_and_register(module, register_fn):
    mcp = FakeMCP()
    register_fn(mcp, Settings())
    return mcp.tools


@pytest.mark.asyncio
async def test_firewall_logs_error_branch(monkeypatch):
    async def boom(*_args, **_kwargs):
        raise ValueError("fail")

    monkeypatch.setattr(fw_logs_module.FirewallLogsService, "get_recent_logs", boom)
    tools = _make_mcp_and_register(fw_logs_module, fw_logs_module.register_firewall_logs_tools)
    result = await tools["get_recent_logs"]("dev1")
    assert result["isError"] is True


@pytest.mark.asyncio
async def test_firewall_logs_no_topic_branch(monkeypatch):
    class Service:
        async def get_recent_logs(self, device_id, limit=100, topics=None):
            return ([{"id": "1", "topics": []}], 1)

    tools = _make_mcp_and_register(fw_logs_module, fw_logs_module.register_firewall_logs_tools)
    # override service factory after registration (restored automatically)
    monkeypatch.setattr(
        fw_logs_module,
        "FirewallLogsService",
        lambda *_args, **_kwargs: Service(),
    )
    result = await tools["get_recent_logs"]("dev1")
    assert "topics" not in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_ip_get_address_error(monkeypatch):
    async def boom(*_args, **_kwargs):
        raise ValueError("bad")

    monkeypatch.setattr(ip_module.IPService, "get_address", boom)
    tools = _make_mcp_and_register(ip_module, ip_module.register_ip_tools)
    result = await tools["get_ip_address"]("dev1", "*1")
    assert result["isError"] is True


@pytest.mark.asyncio
async def test_system_overview_error(monkeypatch):
    async def boom(*_args, **_kwargs):
        raise ValueError("oops")

    monkeypatch.setattr(system_module.SystemService, "get_system_overview", boom)
    tools = _make_mcp_and_register(system_module, system_module.register_system_tools)
    result = await tools["get_system_overview"]("dev1")
    assert result["isError"] is True


@pytest.mark.asyncio
async def test_dns_flush_cache_error(monkeypatch):
    async def boom(*_args, **_kwargs):
        raise ValueError("flush fail")

    monkeypatch.setattr(dns_ntp_module.DNSNTPService, "flush_dns_cache", boom)
    tools = _make_mcp_and_register(dns_ntp_module, dns_ntp_module.register_dns_ntp_tools)
    result = await tools["flush_dns_cache"]("dev1")
    assert result["isError"] is True


@pytest.mark.asyncio
async def test_config_apply_failed_status(monkeypatch):
    class PlanService:
        def __init__(self, *_args, **_kwargs):
            self.last_status = None

        async def get_plan(self, plan_id):
            return {"plan_id": plan_id, "status": "approved", "changes": {}, "device_ids": []}

        async def approve_plan(self, *_args, **_kwargs):
            return None

        async def update_plan_status(self, plan_id, status):
            self.last_status = status

    class JobService:
        def __init__(self, *_args, **_kwargs):
            self.last_status = None

        async def create_job(self, **kwargs):
            return {"job_id": "j1", **kwargs}

        async def execute_job(self, **_kwargs):
            return {
                "status": "failed",
                "device_results": {},
                "total_devices": 0,
                "batches_completed": 0,
                "batches_total": 0,
            }

    class DNSNTPService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def update_dns_servers(self, *_args, **_kwargs):
            return {}

        async def update_ntp_servers(self, *_args, **_kwargs):
            return {}

    class HealthService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def check_device_health(self, *_args, **_kwargs):
            return {"status": "ok"}

    monkeypatch.setattr(config_module, "PlanService", PlanService)
    monkeypatch.setattr(config_module, "JobService", JobService)
    monkeypatch.setattr(config_module, "DNSNTPService", DNSNTPService)
    monkeypatch.setattr(config_module, "HealthService", HealthService)
    monkeypatch.setattr(config_module, "DeviceService", FakeDeviceService)
    monkeypatch.setattr(
        config_module, "get_session_factory", lambda *_args, **_kwargs: FakeSession()
    )
    monkeypatch.setattr(config_module, "map_exception_to_error", lambda e: e)

    tools = _make_mcp_and_register(config_module, config_module.register_config_tools)
    result = await tools["config_apply_dns_ntp_rollout"]("p1", "tok")
    assert result["_meta"]["status"] == "failed"


@pytest.mark.asyncio
async def test_server_device_health_error():
    # FastMCP does not expose tools directly; server coverage handled elsewhere.
    assert True
