"""Structured logging with correlation IDs for observability.

Implements JSON-formatted logging with correlation ID propagation
using context variables for async-safe tracking.

See docs/08-observability-logging-metrics-and-diagnostics.md for
detailed requirements.
"""

import contextvars
import json
import logging
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

# Context variable for correlation ID (thread-safe, async-safe)
correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id",
    default=None,
)


def get_correlation_id() -> str:
    """Get current correlation ID or generate a new one.

    Returns:
        Correlation ID for current context
    """
    correlation_id = correlation_id_var.get()
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
        correlation_id_var.set(correlation_id)
    return correlation_id


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID for current context.

    Args:
        correlation_id: Correlation ID to set
    """
    correlation_id_var.set(correlation_id)


class CorrelationIDFilter(logging.Filter):
    """Logging filter to inject correlation ID into all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation_id to log record if available.

        Args:
            record: Log record to augment

        Returns:
            True to allow record to pass through
        """
        record.correlation_id = correlation_id_var.get() or "no-correlation-id"  # type: ignore
        return True


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    Formats log records as JSON with consistent fields for easy parsing
    and analysis in log aggregation systems.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log entry
        """
        # Base log entry
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat() + "Z",
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "no-correlation-id"),
        }

        # Add extra fields from record
        if hasattr(record, "device_id"):
            log_entry["device_id"] = record.device_id  # type: ignore

        if hasattr(record, "device_environment"):
            log_entry["device_environment"] = record.device_environment  # type: ignore

        if hasattr(record, "user_sub"):
            log_entry["user_sub"] = record.user_sub  # type: ignore

        if hasattr(record, "user_email"):
            log_entry["user_email"] = record.user_email  # type: ignore

        if hasattr(record, "user_role"):
            log_entry["user_role"] = record.user_role  # type: ignore

        if hasattr(record, "tool_name"):
            log_entry["tool_name"] = record.tool_name  # type: ignore

        if hasattr(record, "tool_tier"):
            log_entry["tool_tier"] = record.tool_tier  # type: ignore

        if hasattr(record, "mcp_method"):
            log_entry["mcp_method"] = record.mcp_method  # type: ignore

        if hasattr(record, "plan_id"):
            log_entry["plan_id"] = record.plan_id  # type: ignore

        if hasattr(record, "job_id"):
            log_entry["job_id"] = record.job_id  # type: ignore

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add stack info if present
        if record.stack_info:
            log_entry["stack_info"] = record.stack_info

        return json.dumps(log_entry)


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    log_file: str | None = None,
) -> None:
    """Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to use JSON formatting
        log_file: Optional file path for file logging
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Add correlation ID filter
    correlation_filter = CorrelationIDFilter()

    # Console handler (stderr to avoid corrupting stdio MCP transport)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.addFilter(correlation_filter)

    if json_format:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                fmt=(
                    "%(asctime)s - %(name)s - %(levelname)s - "
                    "%(correlation_id)s - %(message)s"
                ),
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(console_handler)

    # File handler if requested
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.addFilter(correlation_filter)
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    # Set specific loggers to appropriate levels
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncssh").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    root_logger.info(
        "Logging configured",
        extra={
            "level": level,
            "json_format": json_format,
            "log_file": log_file,
        },
    )


__all__ = [
    "correlation_id_var",
    "get_correlation_id",
    "set_correlation_id",
    "CorrelationIDFilter",
    "JSONFormatter",
    "setup_logging",
]
