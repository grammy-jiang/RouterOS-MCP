"""Unit tests for prompt renderer."""

import pytest

from routeros_mcp.mcp_prompts.loader import PromptArgument, PromptMessage, PromptTemplate
from routeros_mcp.mcp_prompts.renderer import PromptRenderer


def test_render_simple_template():
    """Test rendering a simple template without variables."""
    template = PromptTemplate(
        name="simple",
        description="Simple test",
        messages=[PromptMessage(role="user", content="Hello, world!")],
    )

    renderer = PromptRenderer()
    result = renderer.render(template)

    assert result == "Hello, world!"


def test_render_with_arguments():
    """Test rendering with argument substitution."""
    template = PromptTemplate(
        name="with-args",
        description="Test with arguments",
        arguments=[
            PromptArgument(
                name="name",
                description="User name",
                type="string",
                required=True,
            ),
            PromptArgument(
                name="greeting",
                description="Greeting",
                type="string",
                default="Hello",
            ),
        ],
        messages=[PromptMessage(role="user", content="{{ greeting }}, {{ name }}!")],
    )

    renderer = PromptRenderer()

    # With explicit arguments
    result = renderer.render(template, {"name": "Alice", "greeting": "Hi"})
    assert result == "Hi, Alice!"

    # Using default for greeting
    result = renderer.render(template, {"name": "Bob"})
    assert result == "Hello, Bob!"


def test_render_missing_required_argument():
    """Test that rendering fails with missing required argument."""
    template = PromptTemplate(
        name="required-arg",
        description="Test required argument",
        arguments=[
            PromptArgument(
                name="required_param",
                description="Required parameter",
                type="string",
                required=True,
            ),
        ],
        messages=[PromptMessage(role="user", content="{{ required_param }}")],
    )

    renderer = PromptRenderer()

    with pytest.raises(ValueError, match="Missing required arguments"):
        renderer.render(template, {})


def test_render_with_template_vars():
    """Test rendering with template variables."""
    template = PromptTemplate(
        name="with-vars",
        description="Test with template vars",
        messages=[PromptMessage(role="user", content="{{ title }}\n\n{{ content }}")],
        template_vars={
            "title": "Default Title",
            "content": "Default content",
        },
    )

    renderer = PromptRenderer()

    # Using defaults
    result = renderer.render(template)
    assert "Default Title" in result
    assert "Default content" in result

    # Overriding with context
    result = renderer.render(template, context={"title": "Custom Title"})
    assert "Custom Title" in result
    assert "Default content" in result


def test_render_with_conditionals():
    """Test rendering with Jinja2 conditionals."""
    template = PromptTemplate(
        name="conditional",
        description="Test conditionals",
        arguments=[
            PromptArgument(
                name="show_warning",
                description="Show warning",
                type="boolean",
                default=False,
            ),
        ],
        messages=[
            PromptMessage(
                role="user",
                content="""
# Test
{% if show_warning %}
⚠️ Warning message
{% endif %}
Normal content
""",
            )
        ],
    )

    renderer = PromptRenderer()

    # Without warning
    result = renderer.render(template, {"show_warning": False})
    assert "⚠️ Warning message" not in result
    assert "Normal content" in result

    # With warning
    result = renderer.render(template, {"show_warning": True})
    assert "⚠️ Warning message" in result
    assert "Normal content" in result


def test_render_with_loops():
    """Test rendering with Jinja2 loops."""
    template = PromptTemplate(
        name="loop",
        description="Test loops",
        messages=[
            PromptMessage(
                role="user",
                content="""
Items:
{% for item in items %}
- {{ item }}
{% endfor %}
""",
            )
        ],
    )

    renderer = PromptRenderer()

    result = renderer.render(template, context={"items": ["one", "two", "three"]})

    assert "- one" in result
    assert "- two" in result
    assert "- three" in result


def test_render_with_context():
    """Test render_with_context helper."""
    template = PromptTemplate(
        name="context-test",
        description="Test context",
        messages=[
            PromptMessage(
                role="user",
                content="Env: {{ environment }}, Devices: {{ device_count }}, Role: {{ user_role }}",
            )
        ],
    )

    renderer = PromptRenderer()

    result = renderer.render_with_context(
        template,
        device_count=5,
        user_role="admin",
        environment="prod",
    )

    assert "Env: prod" in result
    assert "Devices: 5" in result
    assert "Role: admin" in result


def test_render_multiple_messages():
    """Test rendering with multiple messages."""
    template = PromptTemplate(
        name="multi-message",
        description="Multiple messages",
        messages=[
            PromptMessage(role="user", content="First message"),
            PromptMessage(role="assistant", content="Second message"),
        ],
    )

    renderer = PromptRenderer()
    result = renderer.render(template)

    # Should combine with separators
    assert "First message" in result
    assert "Second message" in result
    assert "[user]" in result
    assert "[assistant]" in result
