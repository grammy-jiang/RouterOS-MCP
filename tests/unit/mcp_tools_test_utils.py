"""Shared helpers for MCP tools unit tests."""

from __future__ import annotations

from typing import Any


class DummyMCP:
    """Minimal MCP stub capturing registered tools."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):  # type: ignore[override]
        def decorator(func: Any) -> Any:
            self.tools[func.__name__] = func
            return func

        return decorator


class FakeSessionFactory:
    """Async context manager that mimics DatabaseSessionManager.session()."""

    def session(self) -> FakeSessionFactory:  # pragma: no cover - used via async with
        return self

    async def __aenter__(self) -> FakeSessionFactory:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None
