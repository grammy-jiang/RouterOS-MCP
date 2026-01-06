"""Rate limiting for diagnostic tools.

Implements simple in-memory rate limiting for diagnostic operations
(ping, traceroute, bandwidth-test) to prevent overwhelming devices.
"""

import asyncio
import logging
import time
from collections import defaultdict

from routeros_mcp.mcp.errors import RateLimitExceededError

logger = logging.getLogger(__name__)


class RateLimiter:
    """In-memory rate limiter for diagnostic tools.

    Implements sliding window rate limiting per device.
    Thread-safe for async operations within single process via asyncio.Lock.

    Example:
        limiter = RateLimiter()
        await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)
    """

    def __init__(self) -> None:
        """Initialize rate limiter with empty tracking."""
        # Structure: {(device_id, operation): [(timestamp, ...), ...]}
        self._records: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check_and_record(
        self,
        device_id: str,
        operation: str,
        limit: int,
        window_seconds: int = 60,
    ) -> None:
        """Check rate limit and record operation if allowed.

        Args:
            device_id: Device identifier
            operation: Operation name (e.g., "ping", "traceroute")
            limit: Maximum operations allowed in window
            window_seconds: Time window in seconds (default: 60)

        Raises:
            RateLimitExceededError: If rate limit exceeded
        """
        async with self._lock:
            key = (device_id, operation)
            now = time.time()
            cutoff = now - window_seconds

            # Remove old records outside window
            self._records[key] = [ts for ts in self._records[key] if ts > cutoff]

            # Check limit
            if len(self._records[key]) >= limit:
                raise RateLimitExceededError(
                    f"Rate limit exceeded for {operation} on device {device_id}: "
                    f"{limit} operations per {window_seconds} seconds",
                    data={
                        "device_id": device_id,
                        "operation": operation,
                        "limit": limit,
                        "window_seconds": window_seconds,
                        "current_count": len(self._records[key]),
                    },
                )

            # Record this operation
            self._records[key].append(now)
            logger.debug(
                f"Rate limit check passed: {operation} on {device_id} "
                f"({len(self._records[key])}/{limit} in {window_seconds}s window)"
            )

    def reset(self, device_id: str | None = None, operation: str | None = None) -> None:
        """Reset rate limit records.

        Args:
            device_id: If provided, reset only this device
            operation: If provided, reset only this operation
        """
        if device_id is None and operation is None:
            # Reset all
            self._records.clear()
        elif device_id and operation:
            # Reset specific device+operation
            key = (device_id, operation)
            if key in self._records:
                del self._records[key]
        elif device_id:
            # Reset all operations for device
            keys_to_delete = [k for k in self._records if k[0] == device_id]
            for key in keys_to_delete:
                del self._records[key]
        elif operation:
            # Reset operation across all devices
            keys_to_delete = [k for k in self._records if k[1] == operation]
            for key in keys_to_delete:
                del self._records[key]

    async def get_remaining(
        self,
        device_id: str,
        operation: str,
        limit: int,
        window_seconds: int = 60,
    ) -> int:
        """Get remaining operations allowed in current window.

        Args:
            device_id: Device identifier
            operation: Operation name
            limit: Maximum operations allowed
            window_seconds: Time window in seconds

        Returns:
            Number of operations remaining in window
        """
        async with self._lock:
            key = (device_id, operation)
            now = time.time()
            cutoff = now - window_seconds

            # Remove old records
            self._records[key] = [ts for ts in self._records[key] if ts > cutoff]

            return max(0, limit - len(self._records[key]))


# Global rate limiter instance
_global_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance.

    Returns:
        Global RateLimiter instance (singleton)
    """
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter


def reset_rate_limiter() -> None:
    """Reset global rate limiter (primarily for testing)."""
    global _global_rate_limiter
    if _global_rate_limiter is not None:
        _global_rate_limiter.reset()
