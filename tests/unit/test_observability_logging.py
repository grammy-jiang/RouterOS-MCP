"""Tests for structured logging utilities."""

import io
import json
import logging
import sys
from pathlib import Path

import pytest

from routeros_mcp.infra.observability.logging import (
    CorrelationIDFilter,
    JSONFormatter,
    get_correlation_id,
    set_correlation_id,
    setup_logging,
)


def test_correlation_id_generation_and_override() -> None:
    """Correlation IDs should be generated and overridable."""
    cid1 = get_correlation_id()
    assert cid1

    set_correlation_id("fixed-id")
    cid2 = get_correlation_id()
    assert cid2 == "fixed-id"


def test_json_formatter_includes_extra_fields() -> None:
    """JSON formatter should inject correlation ID and extras."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test.component",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.device_id = "dev-1"
    record.tool_name = "tool/test"
    record.correlation_id = "cid-123"

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "hello"
    assert payload["component"] == "test.component"
    assert payload["correlation_id"] == "cid-123"
    assert payload["device_id"] == "dev-1"
    assert payload["tool_name"] == "tool/test"


def test_correlation_filter_injects_default_id() -> None:
    """CorrelationIDFilter should attach a placeholder when none is set."""
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", args=(), exc_info=None)
    filt = CorrelationIDFilter()

    assert filt.filter(record) is True
    assert hasattr(record, "correlation_id")
    assert record.correlation_id  # either generated or placeholder


def test_setup_logging_configures_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    """setup_logging should configure a JSON console handler with correlation IDs."""
    stream = io.StringIO()
    monkeypatch.setattr("sys.stderr", stream)

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level

    try:
        setup_logging(level="INFO", json_format=True, log_file=None)
        logging.getLogger("test_setup_logging").info("test message", extra={"device_id": "devX"})
    finally:
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_level)

    log_output = stream.getvalue().strip().splitlines()[-1]
    payload = json.loads(log_output)

    assert payload["message"] == "test message"
    assert payload["device_id"] == "devX"
    assert "correlation_id" in payload


def test_json_formatter_handles_user_and_exception_fields() -> None:
    """Formatter should include user metadata and exception details when provided."""
    formatter = JSONFormatter()

    try:
        raise ValueError("boom")
    except ValueError:
        exc = sys.exc_info()

    record = logging.LogRecord(
        name="audit",
        level=logging.ERROR,
        pathname=__file__,
        lineno=99,
        msg="failed",
        args=(),
        exc_info=exc,
    )
    record.user_sub = "user-123"
    record.user_email = "user@example.com"
    record.user_role = "admin"
    record.tool_tier = "fundamental"
    record.mcp_method = "mcp.call"
    record.plan_id = "plan-1"
    record.job_id = "job-1"
    record.device_environment = "lab"
    record.stack_info = "stack info"

    payload = json.loads(formatter.format(record))

    assert payload["user_sub"] == "user-123"
    assert payload["user_email"] == "user@example.com"
    assert payload["user_role"] == "admin"
    assert payload["tool_tier"] == "fundamental"
    assert payload["mcp_method"] == "mcp.call"
    assert payload["plan_id"] == "plan-1"
    assert payload["job_id"] == "job-1"
    assert payload["device_environment"] == "lab"
    assert payload["stack_info"] == "stack info"
    assert "exception" in payload


def test_setup_logging_plain_text_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-JSON mode should still include correlation ID in output."""
    stream = io.StringIO()
    monkeypatch.setattr("sys.stderr", stream)

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level

    try:
        setup_logging(level="DEBUG", json_format=False)
        logging.getLogger("plain").debug("plain message")
    finally:
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_level)

    output_lines = stream.getvalue().strip().splitlines()
    last_line = output_lines[-1]
    assert "plain message" in last_line
    parts = last_line.split(" - ")
    assert len(parts) >= 5
    assert parts[3]


def test_setup_logging_file_handler(tmp_path: Path) -> None:
    """File handler should emit JSON formatted entries."""
    log_file = tmp_path / "log.json"
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level

    try:
        setup_logging(level="INFO", json_format=True, log_file=str(log_file))
        logging.getLogger("filetest").info("file message", extra={"tool_name": "tool/file"})
    finally:
        for handler in list(root_logger.handlers):
            try:
                handler.flush()
            finally:
                handler.close()
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_level)

    contents = log_file.read_text().strip().splitlines()
    assert contents, "log file should contain entries"
    payload = json.loads(contents[-1])
    assert payload["message"] == "file message"
    assert payload["tool_name"] == "tool/file"
    assert payload.get("correlation_id")
