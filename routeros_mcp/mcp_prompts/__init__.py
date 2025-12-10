"""MCP prompts engine for YAML-backed workflows and troubleshooting.

This package provides YAML-based prompt templates with Jinja2 rendering
for guided workflows and troubleshooting procedures.
"""

from routeros_mcp.mcp_prompts.loader import (
    PromptArgument,
    PromptLoader,
    PromptMessage,
    PromptMetadata,
    PromptTemplate,
)
from routeros_mcp.mcp_prompts.registry import register_prompts
from routeros_mcp.mcp_prompts.renderer import PromptRenderer

__all__ = [
    "PromptArgument",
    "PromptMessage",
    "PromptMetadata",
    "PromptTemplate",
    "PromptLoader",
    "PromptRenderer",
    "register_prompts",
]
