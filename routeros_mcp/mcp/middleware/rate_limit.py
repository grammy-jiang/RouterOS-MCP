"""Rate limiting middleware for MCP tool execution.

Enforces per-role rate limits on tool execution with X-RateLimit-* headers.
Integrates with authorization middleware to provide comprehensive access control.

Rate limit headers (added to responses):
- X-RateLimit-Limit: Maximum requests allowed
- X-RateLimit-Remaining: Requests remaining in window
- X-RateLimit-Reset: Unix timestamp when limit resets
- Retry-After: Seconds until next allowed request (on 429 only)

Example:
    middleware = RateLimitMiddleware(settings)
    await middleware.init()

    # Check rate limit before tool execution
    await middleware.check_rate_limit(user, tool_name)

See issue grammy-jiang/RouterOS-MCP#13 (Phase 5).
"""

import logging
import time

from routeros_mcp.config import Settings
from routeros_mcp.infra.rate_limit import (
    get_rate_limit_store,
    initialize_rate_limit_store,
)
from routeros_mcp.mcp.errors import RateLimitExceededError
from routeros_mcp.security.auth import User

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """Middleware for per-role rate limiting of MCP tool execution.

    Enforces configurable rate limits based on user role:
    - read_only: 10/min (default)
    - ops_rw: 5/min (default)
    - admin: unlimited (default)
    - approver: 5/min (default)

    Returns 429 Too Many Requests with X-RateLimit-* headers on exceed.

    Attributes:
        settings: Application settings
        store: Rate limit storage backend (Redis or in-memory)
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize rate limit middleware.

        Args:
            settings: Application settings with rate limit configuration
        """
        self.settings = settings
        self._initialized = False

    async def init(self) -> None:
        """Initialize rate limit store backend.

        Must be called before using the middleware.
        """
        if self._initialized:
            logger.warning("RateLimitMiddleware already initialized")
            return

        if not self.settings.rate_limit_enabled:
            logger.info("Rate limiting disabled by configuration")
            self._initialized = True
            return

        await initialize_rate_limit_store(
            use_redis=self.settings.rate_limit_use_redis,
            redis_url=self.settings.redis_url,
            pool_size=self.settings.redis_pool_size,
            timeout_seconds=self.settings.redis_timeout_seconds,
            window_seconds=self.settings.rate_limit_window_seconds,
        )

        self._initialized = True
        logger.info(
            "Rate limit middleware initialized",
            extra={
                "enabled": self.settings.rate_limit_enabled,
                "use_redis": self.settings.rate_limit_use_redis,
                "window_seconds": self.settings.rate_limit_window_seconds,
            },
        )

    async def close(self) -> None:
        """Close rate limit store backend."""
        from routeros_mcp.infra.rate_limit import close_rate_limit_store

        await close_rate_limit_store()
        self._initialized = False
        logger.info("Rate limit middleware closed")

    def _get_role_limit(self, role: str) -> int:
        """Get rate limit for user role.

        Args:
            role: User role (read_only, ops_rw, admin, approver)

        Returns:
            Maximum requests per window (0 = unlimited)
        """
        role_limits = {
            "read_only": self.settings.rate_limit_read_only_per_minute,
            "ops_rw": self.settings.rate_limit_ops_rw_per_minute,
            "admin": self.settings.rate_limit_admin_per_minute,
            "approver": self.settings.rate_limit_approver_per_minute,
        }

        return role_limits.get(role, 10)  # Default to 10/min if unknown role

    async def check_rate_limit(
        self,
        user: User,
        tool_name: str,
    ) -> dict[str, int | str]:
        """Check if user has quota for tool execution.

        Args:
            user: Authenticated user
            tool_name: Tool being executed

        Returns:
            Dictionary with rate limit headers:
            - limit: Maximum requests allowed
            - remaining: Requests remaining in window
            - reset: Unix timestamp when limit resets

        Raises:
            RateLimitExceededError: If rate limit exceeded (429)

        Example:
            try:
                headers = await middleware.check_rate_limit(user, "device/list")
                # Tool execution allowed, add headers to response
            except RateLimitExceededError as e:
                # Return 429 with Retry-After header
                return {
                    "error": e.to_jsonrpc_error(),
                    "headers": {
                        "Retry-After": str(e.data.get("retry_after_seconds", 60))
                    }
                }
        """
        if not self.settings.rate_limit_enabled:
            # Rate limiting disabled, allow all requests
            return {
                "limit": 999999,
                "remaining": 999999,
                "reset": int(time.time() + 3600),
            }

        if not self._initialized:
            raise RuntimeError("RateLimitMiddleware not initialized. Call init() first.")

        limit = self._get_role_limit(user.role)
        store = await get_rate_limit_store()

        # Log rate limit check attempt
        logger.debug(
            "Checking rate limit",
            extra={
                "user_sub": user.sub,
                "user_role": user.role,
                "tool_name": tool_name,
                "limit": limit,
            },
        )

        try:
            # Check and record request
            await store.check_and_record(
                user_id=user.sub,
                role=user.role,
                limit=limit,
            )

            # Get remaining quota
            remaining = await store.get_remaining(
                user_id=user.sub,
                role=user.role,
                limit=limit,
            )

            # Calculate reset timestamp
            reset_time = int(time.time() + self.settings.rate_limit_window_seconds)

            headers = {
                "limit": limit,
                "remaining": remaining,
                "reset": reset_time,
            }

            logger.debug(
                "Rate limit check passed",
                extra={
                    "user_sub": user.sub,
                    "user_role": user.role,
                    "tool_name": tool_name,
                    "limit": limit,
                    "remaining": remaining,
                },
            )

            return headers

        except RateLimitExceededError as e:
            # Log rate limit exceeded
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "user_sub": user.sub,
                    "user_role": user.role,
                    "user_email": user.email,
                    "tool_name": tool_name,
                    "limit": limit,
                    "current_count": e.data.get("current_count", 0),
                    "retry_after_seconds": e.data.get("retry_after_seconds", 0),
                },
            )
            # Re-raise to return 429 error
            raise

    async def get_rate_limit_headers(
        self,
        user: User,
    ) -> dict[str, str]:
        """Get current rate limit status headers for user.

        Useful for adding headers to successful responses.

        Args:
            user: Authenticated user

        Returns:
            Dictionary with X-RateLimit-* header values

        Example:
            headers = await middleware.get_rate_limit_headers(user)
            # Returns:
            # {
            #     "X-RateLimit-Limit": "10",
            #     "X-RateLimit-Remaining": "7",
            #     "X-RateLimit-Reset": "1704067200"
            # }
        """
        if not self.settings.rate_limit_enabled:
            return {}

        if not self._initialized:
            return {}

        limit = self._get_role_limit(user.role)
        store = await get_rate_limit_store()

        remaining = await store.get_remaining(
            user_id=user.sub,
            role=user.role,
            limit=limit,
        )

        reset_time = int(time.time() + self.settings.rate_limit_window_seconds)

        return {
            "X-RateLimit-Limit": str(limit if limit > 0 else "unlimited"),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time),
        }


def create_rate_limit_middleware(settings: Settings) -> RateLimitMiddleware:
    """Factory function to create rate limit middleware.

    Args:
        settings: Application settings

    Returns:
        Configured rate limit middleware instance

    Example:
        middleware = create_rate_limit_middleware(settings)
        await middleware.init()
    """
    return RateLimitMiddleware(settings)
