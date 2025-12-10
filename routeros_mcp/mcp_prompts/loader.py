"""YAML prompt loader and validator."""

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class PromptArgument(BaseModel):
    """Prompt argument definition."""

    name: str
    description: str
    type: str = "string"
    enum: list[str] | None = None
    required: bool = False
    default: Any = None


class PromptMessage(BaseModel):
    """Prompt message definition."""

    role: str
    content: str


class PromptMetadata(BaseModel):
    """Prompt metadata."""

    category: str = "workflow"
    tier: str = "fundamental"
    environments: list[str] = Field(default_factory=lambda: ["lab", "staging", "prod"])
    requires_approval: bool = False
    approvals_per_environment: dict[str, bool] | None = None


class PromptTemplate(BaseModel):
    """Complete prompt template definition."""

    name: str
    description: str
    arguments: list[PromptArgument] = Field(default_factory=list)
    messages: list[PromptMessage]
    template_vars: dict[str, Any] = Field(default_factory=dict)
    metadata: PromptMetadata = Field(default_factory=PromptMetadata)


class PromptLoader:
    """Loader for YAML prompt templates."""

    def __init__(self, prompts_dir: Path | str):
        """Initialize prompt loader.

        Args:
            prompts_dir: Directory containing YAML prompt templates
        """
        self.prompts_dir = Path(prompts_dir)
        self.templates: dict[str, PromptTemplate] = {}

    def load_all(self) -> dict[str, PromptTemplate]:
        """Load all YAML prompt templates from the prompts directory.

        Returns:
            Dictionary mapping prompt names to PromptTemplate objects

        Raises:
            ValueError: If prompt directory doesn't exist or validation fails
        """
        if not self.prompts_dir.exists():
            raise ValueError(f"Prompts directory does not exist: {self.prompts_dir}")

        templates = {}
        yaml_files = list(self.prompts_dir.glob("*.yaml")) + list(
            self.prompts_dir.glob("*.yml")
        )

        logger.info(
            f"Loading {len(yaml_files)} prompt templates from {self.prompts_dir}"
        )

        for yaml_file in yaml_files:
            try:
                template = self.load_template(yaml_file)
                templates[template.name] = template
                logger.info(f"Loaded prompt template: {template.name}")
            except Exception as e:
                logger.error(f"Failed to load prompt template {yaml_file}: {e}")
                # Continue loading other templates

        self.templates = templates
        logger.info(f"Successfully loaded {len(templates)} prompt templates")

        return templates

    def load_template(self, yaml_file: Path | str) -> PromptTemplate:
        """Load a single YAML prompt template.

        Args:
            yaml_file: Path to YAML file

        Returns:
            PromptTemplate object

        Raises:
            ValueError: If YAML is invalid or validation fails
        """
        yaml_path = Path(yaml_file)

        if not yaml_path.exists():
            raise ValueError(f"Prompt template file not found: {yaml_path}")

        with open(yaml_path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in {yaml_path}: {e}")

        if not data:
            raise ValueError(f"Empty YAML file: {yaml_path}")

        try:
            template = PromptTemplate(**data)
            return template
        except ValidationError as e:
            raise ValueError(f"Invalid prompt template structure in {yaml_path}: {e}")

    def get_template(self, name: str) -> PromptTemplate | None:
        """Get a loaded template by name.

        Args:
            name: Prompt name

        Returns:
            PromptTemplate if found, None otherwise
        """
        return self.templates.get(name)

    def list_templates(self) -> list[str]:
        """List all loaded template names.

        Returns:
            List of prompt names
        """
        return list(self.templates.keys())

    def validate_all(self) -> dict[str, list[str]]:
        """Validate all loaded templates.

        Returns:
            Dictionary mapping template names to list of warnings/issues
        """
        validation_results = {}

        for name, template in self.templates.items():
            issues = []

            # Check for empty messages
            if not template.messages:
                issues.append("No messages defined")

            # Check for Jinja2 syntax (basic check)
            for msg in template.messages:
                if "{{" in msg.content and "}}" not in msg.content:
                    issues.append("Possible unclosed Jinja2 variable in message")
                if "{%" in msg.content and "%}" not in msg.content:
                    issues.append("Possible unclosed Jinja2 block in message")

            # Check argument defaults match enum
            for arg in template.arguments:
                if arg.enum and arg.default and arg.default not in arg.enum:
                    issues.append(
                        f"Argument '{arg.name}' default '{arg.default}' not in enum"
                    )

            validation_results[name] = issues

        return validation_results


__all__ = [
    "PromptArgument",
    "PromptMessage",
    "PromptMetadata",
    "PromptTemplate",
    "PromptLoader",
]
