"""MCP prompts registration and management."""

import logging
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.mcp_prompts.loader import PromptLoader, PromptTemplate
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
        handler = _create_prompt_handler(template, renderer, settings)

        try:
            mcp.prompt(name=template.name, description=template.description)(handler)
            logger.info(f"Registered prompt: {template.name}")
        except Exception as e:
            logger.error(f"Failed to register prompt '{template.name}': {e}")

    logger.info(f"Registered {len(templates)} prompts with MCP server")


__all__ = ["register_prompts"]


def _create_prompt_handler(
    template: PromptTemplate,
    renderer: "PromptRenderer",
    settings: Settings,
) -> Callable[..., Any]:
    """Create a FastMCP-compatible prompt handler with a concrete signature.

    FastMCP does not allow prompt handlers with ``**kwargs``; it builds the
    schema from the function signature. We therefore emit a bespoke async
    function whose parameters mirror the YAML-defined arguments, including
    types and defaults, and delegate to the renderer.
    """

    # Map YAML arg types to Python hints
    type_map: dict[str, str] = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
    }

    # Build function parameter list (as code) and argument collection lines.
    param_defs: list[str] = []
    argument_lines: list[str] = []

    for arg in template.arguments:
        py_type = type_map.get(arg.type.lower(), "str")
        # Decide default expression
        if arg.default is not None:
            default_expr = repr(arg.default)
        elif arg.required:
            default_expr = None  # required, no default
        else:
            default_expr = "None"

        param_def = f"{arg.name}: {py_type}"
        if default_expr is not None:
            param_def = f"{param_def} = {default_expr}"

        param_defs.append(param_def)
        argument_lines.append(f"    arguments['{arg.name}'] = {arg.name}")

    # Enforce keyword-only parameters for clarity
    params_sig = ", ".join(param_defs)
    if params_sig:
        params_sig = "*, " + params_sig

    # Build the function body dynamically to avoid **kwargs in the signature
    function_source = [
        f"async def prompt_handler({params_sig}):",
        "    arguments = {}",
    ]
    function_source.extend(argument_lines)
    function_source.extend(
        [
            "    try:",
            "        context = {'environment': settings.environment}",
            "        rendered = renderer.render(template, arguments, context)",
            "        logger.info(",
            "            'Prompt invoked: %s', template.name, extra={'prompt': template.name, 'arguments': arguments}",
            "        )",
            "        return rendered",
            "    except Exception as e:",
            "        logger.error(f\"Error rendering prompt '{template.name}': {e}\", exc_info=True)",
            "        return f\"Error rendering prompt: {e}\"",
        ]
    )

    namespace: dict[str, Any] = {
        "renderer": renderer,
        "template": template,
        "settings": settings,
        "logger": logger,
    }

    exec(dedent("\n".join(function_source)), namespace)  # noqa: S102 (exec)

    prompt_handler = namespace["prompt_handler"]
    prompt_handler.__name__ = template.name.replace("-", "_")
    prompt_handler.__doc__ = template.description

    return prompt_handler
