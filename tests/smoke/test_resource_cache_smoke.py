"""Smoke tests for resource cache decorator."""

from __future__ import annotations

import pytest

from routeros_mcp.infra.observability.resource_cache import initialize_cache, with_cache


pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
async def test_with_cache_caches_result_smoke() -> None:
    # Initialize cache (enabled)
    initialize_cache(ttl_seconds=60, max_entries=100, enabled=True)

    state = {"count": 0}

    @with_cache("test://{name}")
    async def greet(name: str) -> str:
        state["count"] += 1
        return f"hello {name}"

    # First call computes
    a = await greet("alice")
    # Second call should be cached
    b = await greet("alice")

    assert a == "hello alice"
    assert b == "hello alice"
    assert state["count"] == 1
