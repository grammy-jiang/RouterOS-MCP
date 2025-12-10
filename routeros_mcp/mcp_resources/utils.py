"""Utilities for MCP resources."""

import json
from datetime import UTC, datetime
from typing import Any


def estimate_tokens(text: str) -> int:
    """Estimate token count for text content.

    Uses a simple heuristic: ~4 characters per token for English text.
    For more accuracy, integrate with tiktoken library for specific models.

    Args:
        text: Content to estimate tokens for

    Returns:
        Estimated token count
    """
    # Simple estimation (4 chars/token average for English)
    return len(text) // 4


def is_safe_for_context(size_bytes: int, threshold_bytes: int = 50000) -> bool:
    """Determine if resource is safe to load into typical context windows.

    Args:
        size_bytes: Size of resource in bytes
        threshold_bytes: Threshold for safe size (default 50KB)

    Returns:
        True if resource is safe for context
    """
    return size_bytes < threshold_bytes


def create_resource_metadata(
    content: str,
    device_id: str | None = None,
    device_name: str | None = None,
    environment: str | None = None,
    additional_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create standardized resource metadata.

    Args:
        content: Resource content
        device_id: Device identifier (optional)
        device_name: Device name (optional)
        environment: Environment name (optional)
        additional_metadata: Additional metadata fields (optional)

    Returns:
        Metadata dictionary with size, token estimates, and safety flags
    """
    size_bytes = len(content.encode("utf-8"))
    estimated_tokens = estimate_tokens(content)
    safe_for_context = is_safe_for_context(size_bytes)

    metadata: dict[str, Any] = {
        "size_bytes": size_bytes,
        "size_hint_kb": round(size_bytes / 1024, 2),
        "estimated_tokens": estimated_tokens,
        "safe_for_context": safe_for_context,
        "snapshot_timestamp": datetime.now(UTC).isoformat(),
    }

    if device_id:
        metadata["device_id"] = device_id
    if device_name:
        metadata["device_name"] = device_name
    if environment:
        metadata["environment"] = environment

    if additional_metadata:
        metadata.update(additional_metadata)

    return metadata


def format_resource_content(
    data: Any,
    mime_type: str = "application/json",
    indent: int = 2,
) -> str:
    """Format resource data as string content.

    Args:
        data: Data to format
        mime_type: MIME type of content
        indent: JSON indent level (if applicable)

    Returns:
        Formatted string content
    """
    if mime_type == "application/json":
        if isinstance(data, str):
            # Already JSON string
            return data
        return json.dumps(data, indent=indent, default=str)
    elif mime_type in ["text/plain", "text/x-routeros-script"]:
        return str(data)
    else:
        # Default to string representation
        return str(data)
