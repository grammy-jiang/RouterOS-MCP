"""Unit tests for resource utilities."""

import json

from routeros_mcp.mcp_resources.utils import (
    create_resource_metadata,
    estimate_tokens,
    format_resource_content,
    is_safe_for_context,
)


def test_estimate_tokens():
    """Test token estimation."""
    # Simple heuristic: ~4 characters per token
    text = "Hello world"  # 11 chars
    tokens = estimate_tokens(text)
    assert tokens == 2  # 11 // 4 = 2

    text = "A" * 400  # 400 chars
    tokens = estimate_tokens(text)
    assert tokens == 100  # 400 // 4 = 100


def test_is_safe_for_context():
    """Test safe for context check."""
    # Under threshold
    assert is_safe_for_context(1000) is True
    assert is_safe_for_context(49999) is True

    # At/over threshold
    assert is_safe_for_context(50000) is False
    assert is_safe_for_context(100000) is False

    # Custom threshold
    assert is_safe_for_context(1000, threshold_bytes=500) is False
    assert is_safe_for_context(100, threshold_bytes=500) is True


def test_create_resource_metadata():
    """Test creating resource metadata."""
    content = "Test content"
    metadata = create_resource_metadata(
        content,
        device_id="dev-001",
        device_name="test-device",
        environment="lab",
    )

    assert "size_bytes" in metadata
    assert "size_hint_kb" in metadata
    assert "estimated_tokens" in metadata
    assert "safe_for_context" in metadata
    assert "snapshot_timestamp" in metadata
    assert metadata["device_id"] == "dev-001"
    assert metadata["device_name"] == "test-device"
    assert metadata["environment"] == "lab"

    # Check calculated fields
    assert metadata["size_bytes"] == len(content.encode("utf-8"))
    assert metadata["estimated_tokens"] == len(content) // 4
    assert metadata["safe_for_context"] is True  # Small content


def test_create_resource_metadata_large_content():
    """Test metadata for large content."""
    large_content = "X" * 60000  # 60KB
    metadata = create_resource_metadata(large_content)

    assert metadata["size_bytes"] == 60000
    assert metadata["size_hint_kb"] == 58.59  # 60000 / 1024 rounded
    assert metadata["safe_for_context"] is False  # Over 50KB threshold


def test_create_resource_metadata_additional():
    """Test adding additional metadata fields."""
    content = "Test"
    additional = {
        "custom_field": "custom_value",
        "another_field": 123,
    }

    metadata = create_resource_metadata(content, additional_metadata=additional)

    assert metadata["custom_field"] == "custom_value"
    assert metadata["another_field"] == 123
    # Standard fields still present
    assert "size_bytes" in metadata
    assert "estimated_tokens" in metadata


def test_format_resource_content_json():
    """Test formatting JSON content."""
    data = {"key": "value", "number": 42}

    # Dict to JSON
    result = format_resource_content(data, "application/json")
    parsed = json.loads(result)
    assert parsed["key"] == "value"
    assert parsed["number"] == 42

    # Already JSON string
    json_str = '{"key": "value"}'
    result = format_resource_content(json_str, "application/json")
    assert result == json_str


def test_format_resource_content_text():
    """Test formatting text content."""
    data = "Simple text content"

    result = format_resource_content(data, "text/plain")
    assert result == "Simple text content"

    # RouterOS script
    script = "/system identity set name=test"
    result = format_resource_content(script, "text/x-routeros-script")
    assert result == script


def test_format_resource_content_default():
    """Test default formatting for unknown MIME types."""
    data = {"key": "value"}

    result = format_resource_content(data, "application/octet-stream")
    # Should use str() as fallback
    assert isinstance(result, str)
    assert "key" in result
