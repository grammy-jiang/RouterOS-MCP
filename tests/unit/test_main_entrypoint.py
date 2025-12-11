import asyncio
import logging

from routeros_mcp import main as main_module
from routeros_mcp.config import Settings


class DummyServer:
    def __init__(self):
        self.started = False

    async def start(self):
        self.started = True


def test_sanitize_database_url_redacts_password():
    url = "postgresql://user:secret@host:5432/db"
    sanitized = main_module.sanitize_database_url(url)
    assert "secret" not in sanitized
    assert "***" in sanitized


def test_setup_logging_selects_stream(monkeypatch):
    settings = Settings(mcp_transport="stdio", log_format="text", log_level="INFO")
    called = {}

    def fake_basicConfig(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(logging, "basicConfig", fake_basicConfig)
    main_module.setup_logging(settings)
    assert called.get("stream") is not None
    assert called["level"] == logging.INFO


def test_main_runs_stdio_server(monkeypatch):
    settings = Settings(mcp_transport="stdio")

    dummy_server = DummyServer()

    async def fake_create_server(passed_settings):
        assert passed_settings is settings
        return dummy_server

    # capture asyncio.run call
    async_calls = {}

    def fake_asyncio_run(coro):
        async_calls["called"] = True
        return asyncio.get_event_loop().run_until_complete(coro)

    monkeypatch.setattr(main_module, "load_config_from_cli", lambda: settings)
    monkeypatch.setattr(main_module, "set_settings", lambda s: None)
    monkeypatch.setattr("routeros_mcp.mcp.server.create_mcp_server", fake_create_server)
    monkeypatch.setattr(asyncio, "run", fake_asyncio_run)

    rc = main_module.main()

    assert rc == 0
    assert dummy_server.started
    assert async_calls["called"]
