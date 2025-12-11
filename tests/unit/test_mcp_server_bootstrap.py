
import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp import server as server_module


class FakeSessionManager:
    def __init__(self):
        self.initialized = True
        self.session_called = 0

    def session(self):
        self.session_called += 1
        return self

    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeMCP:
    def __init__(self):
        self.run_called = False

    async def run(self):
        self.run_called = True


@pytest.mark.asyncio
async def test_create_server_and_start(monkeypatch):
    settings = Settings()

    # stub FastMCP creation inside RouterOSMCPServer by replacing class with FakeMCP
    monkeypatch.setattr(server_module, "FastMCP", lambda **_: FakeMCP())

    # short-circuit registration helpers
    monkeypatch.setattr(server_module.RouterOSMCPServer, "_register_tools", lambda self: None)
    monkeypatch.setattr(server_module.RouterOSMCPServer, "_register_prompts", lambda self: None)

    fake_manager = FakeSessionManager()
    fake_mcp = FakeMCP()

    async def fake_initialize(settings_arg):
        assert settings_arg is settings
        return fake_manager

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

    # intercept RouterOSMCPServer.mcp assignment
    orig_init = server_module.RouterOSMCPServer.__init__

    def wrapped_init(self, settings):
        orig_init(self, settings)
        self.mcp = fake_mcp

    monkeypatch.setattr(server_module.RouterOSMCPServer, "__init__", wrapped_init)

    server = await server_module.create_mcp_server(settings)

    # avoid logging handler manipulation by setting transport to http to trigger NotImplemented
    settings.mcp_transport = "stdio"

    # run start, which should call mcp.run()
    await server.start()

    assert fake_mcp.run_called
    assert server.session_factory is fake_manager
