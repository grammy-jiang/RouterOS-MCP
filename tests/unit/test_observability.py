"""Tests for observability logging."""

import json
import logging

import pytest

from routeros_mcp.infra.observability.logging import (
    CorrelationIDFilter,
    JSONFormatter,
    get_correlation_id,
    set_correlation_id,
)


class TestCorrelationID:
    """Tests for correlation ID context variable."""

    def test_get_correlation_id_generates_new(self) -> None:
        """Test get_correlation_id generates new ID if not set."""
        correlation_id = get_correlation_id()
        assert correlation_id is not None
        assert len(correlation_id) > 0

    def test_set_and_get_correlation_id(self) -> None:
        """Test setting and getting correlation ID."""
        test_id = "test-correlation-id-123"
        set_correlation_id(test_id)

        retrieved_id = get_correlation_id()
        assert retrieved_id == test_id


class TestCorrelationIDFilter:
    """Tests for CorrelationIDFilter."""

    def test_filter_adds_correlation_id(self) -> None:
        """Test filter adds correlation ID to log record."""
        test_id = "test-filter-id"
        set_correlation_id(test_id)

        log_filter = CorrelationIDFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )

        result = log_filter.filter(record)

        assert result is True
        assert hasattr(record, "correlation_id")
        assert record.correlation_id == test_id  # type: ignore

    def test_filter_uses_default_if_no_correlation_id(self) -> None:
        """Test filter uses default if no correlation ID set."""
        # Clear any existing correlation ID by setting to None
        import routeros_mcp.infra.observability.logging as logging_module

        logging_module.correlation_id_var.set(None)

        log_filter = CorrelationIDFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )

        result = log_filter.filter(record)

        assert result is True
        assert hasattr(record, "correlation_id")
        assert record.correlation_id == "no-correlation-id"  # type: ignore


class TestJSONFormatter:
    """Tests for JSONFormatter."""

    def test_json_formatter_basic(self) -> None:
        """Test JSON formatter creates valid JSON."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "test-id-456"  # type: ignore

        formatted = formatter.format(record)

        # Should be valid JSON
        log_entry = json.loads(formatted)

        assert log_entry["level"] == "INFO"
        assert log_entry["component"] == "test.module"
        assert log_entry["message"] == "test message"
        assert log_entry["correlation_id"] == "test-id-456"
        assert "timestamp" in log_entry

    def test_json_formatter_with_extra_fields(self) -> None:
        """Test JSON formatter includes extra fields."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test.module",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="warning message",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "test-id"  # type: ignore
        record.device_id = "dev-001"  # type: ignore
        record.user_sub = "user-123"  # type: ignore
        record.tool_name = "test-tool"  # type: ignore

        formatted = formatter.format(record)
        log_entry = json.loads(formatted)

        assert log_entry["device_id"] == "dev-001"
        assert log_entry["user_sub"] == "user-123"
        assert log_entry["tool_name"] == "test-tool"

    def test_json_formatter_with_exception(self) -> None:
        """Test JSON formatter handles exceptions."""
        formatter = JSONFormatter()

        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.module",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error occurred",
            args=(),
            exc_info=exc_info,
        )
        record.correlation_id = "test-id"  # type: ignore

        formatted = formatter.format(record)
        log_entry = json.loads(formatted)

        assert log_entry["level"] == "ERROR"
        assert "exception" in log_entry
        assert "ValueError: test error" in log_entry["exception"]
