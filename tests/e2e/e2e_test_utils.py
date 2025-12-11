"""Shared helpers for e2e MCP tool tests."""

from __future__ import annotations

from dataclasses import dataclass
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

    def session(self) -> FakeSessionFactory:
        return self

    async def __aenter__(self) -> FakeSessionFactory:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None


@dataclass
class FakeDeviceBase:
    """Common attributes for fake devices used in e2e tests."""

    id: str = "dev-lab-01"
    name: str = "router-lab-01"
    environment: str = "lab"
    allow_advanced_writes: bool = True
    allow_professional_workflows: bool = False
