import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp import server as server_module
from routeros_mcp.mcp.errors import MCPError
from routeros_mcp.mcp.server import RouterOSMCPServer, create_mcp_server


class FakeSessionContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakeSessionFactory:
    def session(self):  # pragma: no cover - used in async context
        return FakeSessionContext()


class FakeMCP:
    def __init__(self, *args, **kwargs):
        self.tools = {}
        self.resources = {}
        self.prompts = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator

    def resource(self, uri: str):
        def decorator(fn):
            self.resources[uri] = fn
            return fn

        return decorator

    def prompt(self, *args, **kwargs):
        def decorator(fn):
            name = kwargs.get("name") or fn.__name__
            self.prompts[name] = fn
            return fn

        return decorator

    async def run(self):  # pragma: no cover - not invoked in tests
        return None


@pytest.fixture(autouse=True)
def patch_fastmcp(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server_module, "FastMCP", FakeMCP)
    yield


@pytest.mark.asyncio
async def test_device_health_mcp_error(monkeypatch: pytest.MonkeyPatch):
    server = RouterOSMCPServer(Settings())
    server.session_factory = FakeSessionFactory()

    class BoomHealthService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def run_health_check(self, *_args, **_kwargs):
            raise MCPError("no health", data={"device": "dev1"})

    monkeypatch.setattr(server_module, "HealthService", BoomHealthService)

    tool = server.mcp.tools["device_health"]
    result = await tool("dev1")
    assert result["isError"] is True
    assert result["_meta"]["device"] == "dev1"


@pytest.mark.asyncio
async def test_device_health_generic_error(monkeypatch: pytest.MonkeyPatch):
    server = RouterOSMCPServer(Settings())
    server.session_factory = FakeSessionFactory()

    class BoomHealthService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def run_health_check(self, *_args, **_kwargs):
            raise RuntimeError("explode")

    class DummyError(MCPError):
        def __init__(self):
            super().__init__("mapped", data={"mapped": True})

    async def map_exc(exc):  # pragma: no cover - replaced below
        return DummyError()

    monkeypatch.setattr(server_module, "HealthService", BoomHealthService)
    monkeypatch.setattr(server_module, "map_exception_to_error", lambda exc: DummyError())

    tool = server.mcp.tools["device_health"]
    result = await tool("dev1")
    assert result["isError"] is True
    assert result["_meta"]["mapped"] is True


@pytest.mark.asyncio
async def test_service_health_tool():
    server = RouterOSMCPServer(Settings())
    tool = server.mcp.tools["service_health"]
    result = await tool()
    assert result["content"][0]["text"].startswith("Service is running")
    assert result["_meta"]["environment"] == server.settings.environment


@pytest.mark.asyncio
async def test_start_not_implemented_transport(monkeypatch: pytest.MonkeyPatch):
    """Test that HTTP transport raises RuntimeError when MCP doesn't support it."""
    settings = Settings()
    settings.mcp_transport = "http"

    server = RouterOSMCPServer(settings)

    async def fake_initialize(_settings):
        return FakeSessionFactory()

    monkeypatch.setattr(server_module, "initialize_session_manager", fake_initialize, raising=False)
    monkeypatch.setattr(
        server_module, "register_device_resources", lambda *args, **kwargs: None, raising=False
    )
    monkeypatch.setattr(
        server_module, "register_fleet_resources", lambda *args, **kwargs: None, raising=False
    )
    monkeypatch.setattr(
        server_module, "register_plan_resources", lambda *args, **kwargs: None, raising=False
    )
    monkeypatch.setattr(
        server_module, "register_audit_resources", lambda *args, **kwargs: None, raising=False
    )

    # HTTP transport now implemented, but FakeMCP doesn't have run_http_async
    with pytest.raises(RuntimeError, match="does not support HTTP transport"):
        await server.start()


@pytest.mark.asyncio
async def test_create_mcp_server_default_settings(monkeypatch: pytest.MonkeyPatch):
    called = {}

    def fake_get_settings():
        called["used"] = True
        return Settings()

    monkeypatch.setattr("routeros_mcp.config.get_settings", fake_get_settings, raising=False)

    server = await create_mcp_server()
    assert isinstance(server, RouterOSMCPServer)
    assert called["used"] is True
