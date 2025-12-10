"""MCP prompts registration and management."""

import logging
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.mcp_prompts.loader import PromptLoader
from routeros_mcp.mcp_prompts.renderer import PromptRenderer

logger = logging.getLogger(__name__)


def register_prompts(
    mcp: FastMCP,
    settings: Settings,
    prompts_dir: Path | str | None = None,
) -> None:
    """Register YAML-backed prompts with MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
        prompts_dir: Directory containing prompt YAML files (optional,
                     defaults to ./prompts relative to repository root)
    """
    # Determine prompts directory
    if prompts_dir is None:
        # Default to ./prompts in repository root
        # Assuming this module is at routeros_mcp/mcp_prompts/registry.py
        repo_root = Path(__file__).parent.parent.parent
        prompts_dir = repo_root / "prompts"

    prompts_dir = Path(prompts_dir)

    if not prompts_dir.exists():
        logger.warning(
            f"Prompts directory not found: {prompts_dir}. No prompts will be loaded."
        )
        return

    # Load all templates
    loader = PromptLoader(prompts_dir)
    try:
        templates = loader.load_all()
    except Exception as e:
        logger.error(f"Failed to load prompt templates: {e}")
        return

    if not templates:
        logger.warning("No prompt templates found")
        return

    # Validate templates
    validation_results = loader.validate_all()
    for name, issues in validation_results.items():
        if issues:
            logger.warning(f"Prompt template '{name}' has issues: {', '.join(issues)}")

    # Create renderer
    renderer = PromptRenderer()

    # Register each template as an MCP prompt
    for name, template in templates.items():
        # Create prompt handler function
        def create_prompt_handler(tmpl):
            """Create a prompt handler for the given template."""

            async def prompt_handler(**kwargs: Any) -> str:
                """Handle prompt invocation.

                Renders the template with provided arguments.
                """
                try:
                    # Extract arguments
                    arguments = {
                        arg.name: kwargs.get(arg.name, arg.default)
                        for arg in tmpl.arguments
                    }

                    # TODO: Fetch context from services (device count, user role, etc.)
                    # For now, use basic context
                    context = {
                        "environment": settings.environment,
                    }

                    # Render prompt
                    rendered = renderer.render(tmpl, arguments, context)

                    logger.info(
                        f"Prompt invoked: {tmpl.name}",
                        extra={"prompt": tmpl.name, "arguments": arguments},
                    )

                    return rendered

                except Exception as e:
                    logger.error(f"Error rendering prompt '{tmpl.name}': {e}")
                    return f"Error rendering prompt: {e}"

            # Set function name and docstring
            prompt_handler.__name__ = tmpl.name.replace("-", "_")
            prompt_handler.__doc__ = tmpl.description

            return prompt_handler

        # Register prompt with FastMCP
        handler = create_prompt_handler(template)

        # Build argument schema for MCP
        # FastMCP expects function with typed parameters
        # For dynamic prompts from YAML, we use **kwargs approach

        try:
            mcp.prompt(name=template.name, description=template.description)(handler)
            logger.info(f"Registered prompt: {template.name}")
        except Exception as e:
            logger.error(f"Failed to register prompt '{template.name}': {e}")

    logger.info(f"Registered {len(templates)} prompts with MCP server")


__all__ = ["register_prompts"]
