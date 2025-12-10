"""Unit tests for prompt loader."""

import tempfile
from pathlib import Path

import pytest

from routeros_mcp.mcp_prompts.loader import PromptLoader


def test_load_valid_prompt():
    """Test loading a valid prompt template."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a valid prompt YAML
        prompt_file = Path(tmpdir) / "test_prompt.yaml"
        prompt_file.write_text(
            """
name: test-prompt
description: Test prompt description

arguments:
  - name: environment
    description: Target environment
    type: string
    enum: [lab, staging, prod]
    required: false
    default: lab

messages:
  - role: user
    content: |
      # Test Prompt
      Environment: {{ environment }}

metadata:
  category: workflow
  tier: fundamental
"""
        )

        loader = PromptLoader(tmpdir)
        templates = loader.load_all()

        assert len(templates) == 1
        assert "test-prompt" in templates

        template = templates["test-prompt"]
        assert template.name == "test-prompt"
        assert template.description == "Test prompt description"
        assert len(template.arguments) == 1
        assert template.arguments[0].name == "environment"
        assert len(template.messages) == 1
        assert template.messages[0].role == "user"


def test_load_missing_required_fields():
    """Test that loading fails with missing required fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create an invalid prompt YAML (missing messages)
        prompt_file = Path(tmpdir) / "invalid_prompt.yaml"
        prompt_file.write_text(
            """
name: invalid-prompt
description: Invalid prompt
"""
        )

        loader = PromptLoader(tmpdir)

        with pytest.raises(ValueError):
            loader.load_template(prompt_file)


def test_validate_templates():
    """Test template validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a prompt with validation issues
        prompt_file = Path(tmpdir) / "problematic_prompt.yaml"
        prompt_file.write_text(
            """
name: problematic-prompt
description: Prompt with issues

arguments:
  - name: env
    description: Environment
    type: string
    enum: [lab, prod]
    default: staging  # Not in enum!

messages:
  - role: user
    content: |
      Test content with {{ unclosed_var
"""
        )

        loader = PromptLoader(tmpdir)
        loader.load_all()

        validation_results = loader.validate_all()

        assert "problematic-prompt" in validation_results
        issues = validation_results["problematic-prompt"]

        # Should detect argument default not in enum
        assert any("default" in issue and "enum" in issue for issue in issues)


def test_list_templates():
    """Test listing loaded templates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create multiple prompts
        for i in range(3):
            prompt_file = Path(tmpdir) / f"prompt{i}.yaml"
            prompt_file.write_text(
                f"""
name: prompt-{i}
description: Prompt {i}
messages:
  - role: user
    content: Test
"""
            )

        loader = PromptLoader(tmpdir)
        loader.load_all()

        names = loader.list_templates()
        assert len(names) == 3
        assert "prompt-0" in names
        assert "prompt-1" in names
        assert "prompt-2" in names


def test_get_template():
    """Test retrieving a specific template."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prompt_file = Path(tmpdir) / "test.yaml"
        prompt_file.write_text(
            """
name: test
description: Test
messages:
  - role: user
    content: Test
"""
        )

        loader = PromptLoader(tmpdir)
        loader.load_all()

        template = loader.get_template("test")
        assert template is not None
        assert template.name == "test"

        missing = loader.get_template("nonexistent")
        assert missing is None
