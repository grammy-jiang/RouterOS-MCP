"""Shared helpers for MCP unit tests.

These utilities provide small stubs for the MCP server object used by tool/resource
registration functions.
"""

from __future__ import annotations

from typing import Any, Callable


class DummyMCP:
    """Minimal MCP stub capturing registered tools/resources/prompts."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        # Store callables as Any to avoid static type-checker false-positives in tests.
        self.tools: dict[str, Any] = {}
        self.resources: dict[str, Any] = {}
        self.prompts: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for registering a tool.

        Supports FastMCP-like usage:
        - @mcp.tool()
        - @mcp.tool(name="...")
        """

        name = kwargs.get("name") if kwargs else None

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            tool_name = name or func.__name__
            self.tools[tool_name] = func
            return func

        return decorator

    def resource(self, uri: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for registering a resource by URI."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.resources[uri] = func
            return func

        return decorator

    def prompt(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for registering a prompt.

        Supports FastMCP-like usage:
        - @mcp.prompt()
        - @mcp.prompt(name="...")
        """

        name = kwargs.get("name") if kwargs else None

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            prompt_name = name or func.__name__
            self.prompts[prompt_name] = func
            return func

        return decorator

    async def run(self) -> None:  # pragma: no cover - not invoked in tests
        return None


class FakeSessionFactory:
    """Async context manager that mimics DatabaseSessionManager.session()."""

    def session(self) -> FakeSessionFactory:  # pragma: no cover - used via async with
        return self

    async def __aenter__(self) -> FakeSessionFactory:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None
