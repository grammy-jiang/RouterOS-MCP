from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

import routeros_mcp.mcp_prompts as mcp_prompts
import routeros_mcp.mcp_resources as mcp_resources
import routeros_mcp.mcp_tools as mcp_tools
from routeros_mcp.config import Settings
from routeros_mcp.mcp import server as mcp_server
from routeros_mcp.mcp.transport.http import MCPHTTPTransport


class _DummyFastMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}
        self.resources: dict[str, object] = {}
        self.prompts_registered = False
        self.run_called = False

    def tool(self):  # type: ignore[override]
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator

    def resource(self, uri: str):  # pragma: no cover - not used here
        def decorator(func):
            self.resources[uri] = func
            return func

        return decorator

    def prompt(self):  # pragma: no cover - not used here
        def decorator(func):
            self.prompts_registered = True
            return func

        return decorator

    async def run(self):  # pragma: no cover - invoked in test
        self.run_called = True


class _FakeSessionFactory:
    def __init__(self) -> None:
        self.entered = False

    def session(self):  # pragma: no cover - used via async with
        return self

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_mcp_server_start_stdio(monkeypatch: pytest.MonkeyPatch):
    settings = Settings(mcp_transport="stdio")

    dummy_mcp = _DummyFastMCP()
    fake_session_factory = _FakeSessionFactory()

    # Patch FastMCP and registration functions to no-op
    monkeypatch.setattr(mcp_server, "FastMCP", lambda *args, **kwargs: dummy_mcp)

    async def _fake_init_session(_settings):
        return fake_session_factory

    monkeypatch.setattr(mcp_server, "initialize_session_manager", _fake_init_session, raising=False)
    monkeypatch.setattr(mcp_prompts, "register_prompts", lambda *args, **kwargs: None)

    for name in [
        "register_config_tools",
        "register_device_tools",
        "register_dns_ntp_tools",
        "register_firewall_logs_tools",
        "register_firewall_write_tools",
        "register_interface_tools",
        "register_ip_tools",
        "register_routing_tools",
        "register_system_tools",
    ]:
        monkeypatch.setattr(mcp_tools, name, lambda *args, **kwargs: None)

    # Patch resource registration to capture calls
    registered_resources: list[str] = []

    def _make_register(name: str):
        def _register(mcp, session_factory, _settings):
            registered_resources.append(name)

        return _register

    monkeypatch.setattr(mcp_resources, "register_device_resources", _make_register("device"))
    monkeypatch.setattr(mcp_resources, "register_fleet_resources", _make_register("fleet"))
    monkeypatch.setattr(mcp_resources, "register_plan_resources", _make_register("plan"))
    monkeypatch.setattr(mcp_resources, "register_audit_resources", _make_register("audit"))

    server = mcp_server.RouterOSMCPServer(settings)
    # Override session_factory before device_health usage
    server.session_factory = fake_session_factory

    # Device health tool should use fake HealthService
    class _FakeHealthResult:
        status = "healthy"
        cpu_usage_percent = 5.0
        memory_usage_percent = 10.0
        uptime_seconds = 7200
        issues: list[str] = []
        warnings: list[str] = []
        timestamp = datetime.now(UTC)

    class _FakeHealthService:
        def __init__(self, *_args, **_kwargs) -> None:
            self.called_with: str | None = None

        async def run_health_check(self, device_id: str):
            self.called_with = device_id
            return _FakeHealthResult()

    monkeypatch.setattr(mcp_server, "HealthService", lambda *args, **kwargs: _FakeHealthService())

    # Start server (stdio path) should call mcp.run and register resources
    await server.start()

    assert dummy_mcp.run_called is True
    assert set(registered_resources) == {"device", "fleet", "plan", "audit"}

    # Invoke echo tool to ensure tool registration occurred
    result = await dummy_mcp.tools["echo"]("hello")
    assert result["_meta"]["original_message"] == "hello"

    # Device health tool should work using fake health service
    health = await dummy_mcp.tools["device_health"]("dev-1")
    assert health["_meta"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_mcp_server_start_http_not_implemented(monkeypatch: pytest.MonkeyPatch):
    """Test that HTTP transport raises RuntimeError when MCP doesn't support it."""
    settings = Settings(mcp_transport="http")
    dummy_mcp = _DummyFastMCP()

    monkeypatch.setattr(mcp_server, "FastMCP", lambda *args, **kwargs: dummy_mcp)

    async def _fake_init_session_http(_settings):
        return _FakeSessionFactory()

    monkeypatch.setattr(
        mcp_server, "initialize_session_manager", _fake_init_session_http, raising=False
    )
    monkeypatch.setattr(mcp_prompts, "register_prompts", lambda *args, **kwargs: None)

    for name in [
        "register_config_tools",
        "register_device_tools",
        "register_dns_ntp_tools",
        "register_firewall_logs_tools",
        "register_firewall_write_tools",
        "register_interface_tools",
        "register_ip_tools",
        "register_routing_tools",
        "register_system_tools",
    ]:
        monkeypatch.setattr(mcp_tools, name, lambda *args, **kwargs: None)

    monkeypatch.setattr(mcp_resources, "register_device_resources", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp_resources, "register_fleet_resources", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp_resources, "register_plan_resources", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp_resources, "register_audit_resources", lambda *args, **kwargs: None)

    server = mcp_server.RouterOSMCPServer(settings)

    # HTTP transport now implemented, but _DummyFastMCP doesn't have run_http_async
    with pytest.raises(RuntimeError, match="does not support HTTP transport"):
        await server.start()


@pytest.mark.asyncio
async def test_mcp_server_start_http_success(monkeypatch: pytest.MonkeyPatch):
    """Test that HTTP transport starts successfully when MCP supports it."""
    settings = Settings(
        mcp_transport="http",
        mcp_http_host="0.0.0.0",
        mcp_http_port=9090,
        mcp_http_base_path="/api/mcp",
    )

    # Track what was called
    transport_started = {"called": False, "settings": None, "mcp_instance": None}

    class _FakeMCPWithHTTP(_DummyFastMCP):
        async def run_http_async(self, **kwargs):
            # Just mark that it was called
            pass

    dummy_mcp = _FakeMCPWithHTTP()

    monkeypatch.setattr(mcp_server, "FastMCP", lambda *args, **kwargs: dummy_mcp)

    async def _fake_init_session_http(_settings):
        return _FakeSessionFactory()

    monkeypatch.setattr(
        mcp_server, "initialize_session_manager", _fake_init_session_http, raising=False
    )
    monkeypatch.setattr(mcp_prompts, "register_prompts", lambda *args, **kwargs: None)

    for name in [
        "register_config_tools",
        "register_device_tools",
        "register_dns_ntp_tools",
        "register_firewall_logs_tools",
        "register_firewall_write_tools",
        "register_interface_tools",
        "register_ip_tools",
        "register_routing_tools",
        "register_system_tools",
        "register_bridge_tools",
        "register_dhcp_tools",
        "register_wireless_tools",
    ]:
        monkeypatch.setattr(mcp_tools, name, lambda *args, **kwargs: None)

    for resource_name in [
        "register_device_resources",
        "register_bridge_resources",
        "register_dhcp_resources",
        "register_fleet_resources",
        "register_plan_resources",
        "register_audit_resources",
        "register_wireless_resources",
    ]:
        monkeypatch.setattr(mcp_resources, resource_name, lambda *args, **kwargs: None)

    # Patch cache initialization
    from routeros_mcp.infra.observability import resource_cache
    monkeypatch.setattr(resource_cache, "initialize_cache", lambda **kwargs: None)

    # Create a fake HTTPSSETransport that tracks initialization
    class _FakeHTTPSSETransport:
        def __init__(self, settings_arg, mcp_instance):
            transport_started["called"] = True
            transport_started["settings"] = settings_arg
            transport_started["mcp_instance"] = mcp_instance

        async def run(self):
            # Simulate running the transport
            pass

    from routeros_mcp.mcp.transport import http_sse
    monkeypatch.setattr(http_sse, "HTTPSSETransport", _FakeHTTPSSETransport)

    server = mcp_server.RouterOSMCPServer(settings)

    # Start server - should use HTTP transport
    await server.start()

    # Verify HTTP transport was initialized with correct settings
    assert transport_started["called"] is True
    assert transport_started["settings"] == settings
    assert transport_started["mcp_instance"] == dummy_mcp
    assert transport_started["settings"].mcp_http_host == "0.0.0.0"
    assert transport_started["settings"].mcp_http_port == 9090
    assert transport_started["settings"].mcp_http_base_path == "/api/mcp"


@pytest.mark.asyncio
async def test_http_transport_jsonrpc_and_health(monkeypatch: pytest.MonkeyPatch):
    settings = Settings()
    transport = MCPHTTPTransport(settings, mcp_handler=None)

    class _FakeRequest:
        def __init__(self, body: str, headers: dict[str, str] | None = None):
            self._body = body
            self.headers = headers or {}
            self.method = "POST"
            self.url = type("obj", (), {"path": "/rpc"})
            self.state = type("obj", (), {})()

        async def json(self):
            return json.loads(self._body)

    # Patch internal MCP processing to echo back method
    async def _fake_process(body):
        return {"jsonrpc": "2.0", "id": body.get("id"), "result": {"ok": True}}

    monkeypatch.setattr(transport, "_process_mcp_request", _fake_process)

    request = _FakeRequest(
        json.dumps({"id": 1, "method": "ping", "params": {}}), {"X-Correlation-ID": "abc"}
    )
    response = await transport.handle_jsonrpc(request)
    assert response.status_code == 200
    assert response.body is not None

    # SSE health endpoint
    health_req = type("obj", (), {"headers": {}, "url": type("obj", (), {"path": "/health"})})
    health_resp = await transport.handle_health(health_req)
    assert health_resp.status_code == 200
