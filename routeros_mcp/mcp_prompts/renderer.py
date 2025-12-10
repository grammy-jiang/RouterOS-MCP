"""Jinja2-based prompt renderer."""

import logging
from typing import Any

from jinja2 import Environment, Template, TemplateSyntaxError

from routeros_mcp.mcp_prompts.loader import PromptTemplate

logger = logging.getLogger(__name__)


class PromptRenderer:
    """Renderer for prompt templates using Jinja2."""

    def __init__(self):
        """Initialize prompt renderer."""
        self.env = Environment(
            autoescape=False,  # Don't escape HTML/XML in prompts
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(
        self,
        template: PromptTemplate,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Render a prompt template with arguments and context.

        Args:
            template: PromptTemplate to render
            arguments: User-provided argument values
            context: Additional context variables (device counts, user role, etc.)

        Returns:
            Rendered prompt content

        Raises:
            ValueError: If required arguments are missing or rendering fails
        """
        arguments = arguments or {}
        context = context or {}

        # Validate required arguments
        missing_args = []
        for arg in template.arguments:
            if arg.required and arg.name not in arguments:
                if arg.default is None:
                    missing_args.append(arg.name)

        if missing_args:
            raise ValueError(
                f"Missing required arguments for prompt '{template.name}': {', '.join(missing_args)}"
            )

        # Build rendering context
        render_context = {}

        # Add template variables
        render_context.update(template.template_vars)

        # Add provided context
        render_context.update(context)

        # Add arguments with defaults
        for arg in template.arguments:
            if arg.name in arguments:
                render_context[arg.name] = arguments[arg.name]
            elif arg.default is not None:
                render_context[arg.name] = arg.default

        # Render each message
        rendered_messages = []
        for msg in template.messages:
            try:
                # Create Jinja2 template from message content
                jinja_template = self.env.from_string(msg.content)

                # Render with context
                rendered_content = jinja_template.render(**render_context)

                rendered_messages.append(
                    {"role": msg.role, "content": rendered_content}
                )
            except TemplateSyntaxError as e:
                logger.error(
                    f"Jinja2 syntax error in prompt '{template.name}': {e}"
                )
                raise ValueError(
                    f"Template syntax error in prompt '{template.name}': {e}"
                )
            except Exception as e:
                logger.error(
                    f"Error rendering prompt '{template.name}': {e}"
                )
                raise ValueError(
                    f"Failed to render prompt '{template.name}': {e}"
                )

        # Combine messages into single prompt
        # For MCP, typically we return the content of the first (and usually only) message
        if len(rendered_messages) == 1:
            return rendered_messages[0]["content"]
        else:
            # Multiple messages - concatenate with separators
            return "\n\n---\n\n".join(
                [f"[{msg['role']}]\n{msg['content']}" for msg in rendered_messages]
            )

    def render_with_context(
        self,
        template: PromptTemplate,
        arguments: dict[str, Any] | None = None,
        device_count: int | None = None,
        user_role: str | None = None,
        environment: str | None = None,
    ) -> str:
        """Render a prompt with common context variables.

        Args:
            template: PromptTemplate to render
            arguments: User-provided arguments
            device_count: Number of devices in scope
            user_role: Current user's role
            environment: Current environment

        Returns:
            Rendered prompt content
        """
        context = {}

        if device_count is not None:
            context["device_count"] = device_count
        if user_role is not None:
            context["user_role"] = user_role
        if environment is not None:
            context["environment"] = environment

        return self.render(template, arguments, context)


__all__ = ["PromptRenderer"]
