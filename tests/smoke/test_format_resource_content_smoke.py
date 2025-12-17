"""Smoke tests for resource content formatting helpers."""

from __future__ import annotations

import json

import pytest

from routeros_mcp.mcp_resources.utils import format_resource_content


pytestmark = pytest.mark.smoke


def test_format_resource_content_json_smoke() -> None:
    data = {"device_id": "dev-1", "ok": True}
    content = format_resource_content(data, mime_type="application/json")
    obj = json.loads(content)
    assert obj["device_id"] == "dev-1"
    assert obj["ok"] is True
