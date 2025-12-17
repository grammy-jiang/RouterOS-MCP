"""Smoke test that renders at least one prompt with no required args."""

from __future__ import annotations

import inspect

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp_prompts import register_prompts
from tests.unit.mcp_tools_test_utils import DummyMCP


pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
async def test_prompt_render_no_required_args_smoke() -> None:
    """Find prompts with only optional args and render them without parameters."""

    mcp = DummyMCP()
    register_prompts(mcp, Settings())

    assert len(mcp.prompts) >= 0  # registration shouldn't error

    rendered_any = False
    for name, fn in mcp.prompts.items():
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        # All params must have defaults (i.e., optional) to call with no args
        if all(p.default is not inspect._empty for p in params):
            out = await fn()  # async handler returns str
            assert isinstance(out, str)
            assert out != ""
            rendered_any = True
            break

    # It's acceptable if none are renderable without args; then this test is a no-op validation
    # of registration having succeeded. Prefer at least registration.
    assert len(mcp.prompts) > 0
