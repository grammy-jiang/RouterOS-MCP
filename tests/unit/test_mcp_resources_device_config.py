"""Tests for device MCP resource helpers."""

import gzip
from types import SimpleNamespace

from routeros_mcp.mcp_resources.device import _decode_snapshot_data


def test_decode_snapshot_data_handles_gzip_compression() -> None:
    """Ensure snapshot data is decompressed based on metadata."""
    config_text = "# RouterOS config\n/system identity set name=test\n"
    compressed = gzip.compress(config_text.encode("utf-8"))
    snapshot = SimpleNamespace(
        id="snap-test",
        data=compressed,
        meta={"compression": "gzip"},
    )

    assert _decode_snapshot_data(snapshot) == config_text
