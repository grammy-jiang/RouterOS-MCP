"""Tests for prompt registry behaviour."""

from pathlib import Path

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp_prompts import registry
from routeros_mcp.mcp_prompts.loader import (
    PromptArgument,
    PromptMessage,
    PromptMetadata,
    PromptTemplate,
)


class FakeMCP:
    """Minimal FastMCP stub capturing prompt registrations."""

    def __init__(self) -> None:
        self.registered: dict[str, dict[str, object]] = {}

    def prompt(self, name: str, description: str):  # noqa: D401
        def decorator(fn):
            self.registered[name] = {"description": description, "fn": fn}
            return fn

        return decorator


def make_template() -> PromptTemplate:
    return PromptTemplate(
        name="sample",
        description="Sample prompt",
        arguments=[PromptArgument(name="arg1", description="arg", required=False, default="d")],
        messages=[PromptMessage(role="user", content="Hello {{ arg1 }}")],
        metadata=PromptMetadata(),
    )


def test_register_prompts_missing_directory(tmp_path: Path) -> None:
    mcp = FakeMCP()
    missing_dir = tmp_path / "missing"

    settings = Settings()
    registry.register_prompts(mcp, settings, prompts_dir=missing_dir)

    assert not mcp.registered


@pytest.mark.asyncio
async def test_register_prompts_registers_and_renders(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[PromptTemplate, dict, dict]] = []

    class FakeLoader:
        def __init__(self, prompts_dir: Path) -> None:  # noqa: D401
            self.prompts_dir = prompts_dir

        def load_all(self):
            return {"sample": make_template()}

        def validate_all(self):
            return {"sample": ["minor"]}

    class FakeRenderer:
        def render(self, template, arguments, context):  # noqa: ANN001, D401
            calls.append((template, arguments, context))
            return "rendered"

    monkeypatch.setattr(registry, "PromptLoader", FakeLoader)
    monkeypatch.setattr(registry, "PromptRenderer", FakeRenderer)

    mcp = FakeMCP()
    settings = Settings()

    registry.register_prompts(mcp, settings, prompts_dir=tmp_path)

    assert "sample" in mcp.registered
    handler = mcp.registered["sample"]["fn"]

    result = await handler(arg1="value")

    assert result == "rendered"
    assert calls
    template, arguments, context = calls[-1]
    assert template.name == "sample"
    assert arguments["arg1"] == "value"
    assert context["environment"] == settings.environment


@pytest.mark.asyncio
async def test_register_prompts_handles_render_error(monkeypatch, tmp_path: Path) -> None:
    class FakeLoader:
        def __init__(self, prompts_dir: Path) -> None:  # noqa: D401
            self.prompts_dir = prompts_dir

        def load_all(self):
            return {"sample": make_template()}

        def validate_all(self):
            return {}

    class FailingRenderer:
        def render(self, template, arguments, context):  # noqa: ANN001, D401
            raise ValueError("boom")

    monkeypatch.setattr(registry, "PromptLoader", FakeLoader)
    monkeypatch.setattr(registry, "PromptRenderer", FailingRenderer)

    mcp = FakeMCP()
    settings = Settings()

    registry.register_prompts(mcp, settings, prompts_dir=tmp_path)

    handler = mcp.registered["sample"]["fn"]
    assert await handler() == "Error rendering prompt: boom"
