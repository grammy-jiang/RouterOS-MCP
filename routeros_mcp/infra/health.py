"""Health check infrastructure for distributed HA deployments.

Provides health checking for:
- Database connectivity
- Redis connectivity
- OIDC provider reachability
- Service readiness state

Health states:
- ready: All critical components operational
- degraded: Some non-critical components failing (e.g., Redis cache)
- shutdown: Service is shutting down, rejecting new requests
"""

import asyncio
import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from routeros_mcp.config import Settings

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status enumeration."""

    READY = "ready"
    DEGRADED = "degraded"
    SHUTDOWN = "shutdown"


class ComponentHealth:
    """Health status for a single component."""

    def __init__(
        self,
        name: str,
        healthy: bool,
        message: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        """Initialize component health.

        Args:
            name: Component name
            healthy: Whether component is healthy
            message: Status message or error details
            duration_ms: Check duration in milliseconds
        """
        self.name = name
        self.healthy = healthy
        self.message = message
        self.duration_ms = duration_ms

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "name": self.name,
            "healthy": self.healthy,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
        }


class HealthCheckResult:
    """Result of a complete health check."""

    def __init__(
        self,
        status: HealthStatus,
        components: list[ComponentHealth],
        timestamp: datetime | None = None,
    ) -> None:
        """Initialize health check result.

        Args:
            status: Overall health status
            components: List of component health checks
            timestamp: Check timestamp (defaults to now)
        """
        self.status = status
        self.components = components
        self.timestamp = timestamp or datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "components": {comp.name: comp.to_dict() for comp in self.components},
        }


class HealthChecker:
    """Health checker for distributed HA deployments.

    Performs health checks on critical service dependencies and
    tracks service readiness state for load balancer integration.
    """

    def __init__(
        self,
        settings: Settings,
        db_engine: AsyncEngine | None = None,
    ) -> None:
        """Initialize health checker.

        Args:
            settings: Application settings
            db_engine: Optional database engine (will be fetched if not provided)
        """
        self.settings = settings
        self._db_engine = db_engine
        self._is_shutting_down = False

    def set_shutdown(self) -> None:
        """Mark service as shutting down."""
        self._is_shutting_down = True
        logger.info("Health checker marked as shutting down")

    async def check_health(self) -> HealthCheckResult:
        """Perform comprehensive health check.

        Checks:
        - Database connectivity (critical)
        - Redis connectivity (non-critical, only if enabled)
        - OIDC provider reachability (non-critical, only if enabled)

        Returns:
            HealthCheckResult with overall status and component details
        """
        # If shutting down, return immediately
        if self._is_shutting_down:
            return HealthCheckResult(
                status=HealthStatus.SHUTDOWN,
                components=[
                    ComponentHealth(
                        name="service",
                        healthy=False,
                        message="Service is shutting down",
                    )
                ],
            )

        components: list[ComponentHealth] = []

        # Check database (critical)
        db_health = await self._check_database()
        components.append(db_health)

        # Check Redis (non-critical, only if enabled)
        if self.settings.redis_cache_enabled:
            redis_health = await self._check_redis()
            components.append(redis_health)

        # Check OIDC provider (non-critical, only if enabled)
        if self.settings.oidc_enabled:
            oidc_health = await self._check_oidc()
            components.append(oidc_health)

        # Determine overall status
        status = self._determine_status(components)

        return HealthCheckResult(status=status, components=components)

    def _determine_status(self, components: list[ComponentHealth]) -> HealthStatus:
        """Determine overall health status from component checks.

        Args:
            components: List of component health checks

        Returns:
            Overall health status
        """
        # Database is critical - if it's down, we're degraded
        db_component = next((c for c in components if c.name == "database"), None)
        if db_component and not db_component.healthy:
            return HealthStatus.DEGRADED

        # Check if any non-database components are unhealthy
        any_unhealthy = any(not c.healthy for c in components if c.name != "database")

        # If non-critical components are down, we're degraded but still usable
        if any_unhealthy:
            return HealthStatus.DEGRADED

        return HealthStatus.READY

    async def _check_database(self) -> ComponentHealth:
        """Check database connectivity.

        Returns:
            ComponentHealth for database
        """
        start = asyncio.get_event_loop().time()
        try:
            # Get engine if not provided
            if self._db_engine is None:
                from routeros_mcp.infra.db.session import get_session_manager

                manager = get_session_manager(self.settings)
                self._db_engine = manager.engine

            # Execute simple query
            async with self._db_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

            duration_ms = (asyncio.get_event_loop().time() - start) * 1000
            return ComponentHealth(
                name="database",
                healthy=True,
                message="Connected",
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (asyncio.get_event_loop().time() - start) * 1000
            logger.error(
                "Database health check failed",
                exc_info=True,
                extra={"error": str(e)},
            )
            return ComponentHealth(
                name="database",
                healthy=False,
                message=f"Connection failed: {str(e)}",
                duration_ms=duration_ms,
            )

    async def _check_redis(self) -> ComponentHealth:
        """Check Redis connectivity.

        Returns:
            ComponentHealth for Redis
        """
        start = asyncio.get_event_loop().time()
        redis_client = None
        try:
            # Create temporary Redis client
            redis_client = Redis.from_url(
                self.settings.redis_url,
                decode_responses=True,
                socket_timeout=self.settings.redis_timeout_seconds,
                socket_connect_timeout=self.settings.redis_timeout_seconds,
            )

            # Execute ping
            await redis_client.ping()

            duration_ms = (asyncio.get_event_loop().time() - start) * 1000
            return ComponentHealth(
                name="redis",
                healthy=True,
                message="Connected",
                duration_ms=duration_ms,
            )

        except (RedisError, ConnectionError, TimeoutError) as e:
            duration_ms = (asyncio.get_event_loop().time() - start) * 1000
            logger.warning(
                "Redis health check failed",
                extra={"error": str(e)},
            )
            return ComponentHealth(
                name="redis",
                healthy=False,
                message=f"Connection failed: {str(e)}",
                duration_ms=duration_ms,
            )
        finally:
            if redis_client:
                await redis_client.aclose()

    async def _check_oidc(self) -> ComponentHealth:
        """Check OIDC provider reachability.

        Returns:
            ComponentHealth for OIDC provider
        """
        start = asyncio.get_event_loop().time()

        # Determine issuer URL
        issuer = self.settings.oidc_issuer or self.settings.oidc_provider_url
        if not issuer:
            return ComponentHealth(
                name="oidc",
                healthy=False,
                message="OIDC issuer not configured",
                duration_ms=0.0,
            )

        discovery_url = f"{issuer}/.well-known/openid-configuration"

        try:
            # Try to fetch OIDC discovery document
            async with httpx.AsyncClient(
                timeout=self.settings.redis_timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.get(discovery_url)
                response.raise_for_status()

            duration_ms = (asyncio.get_event_loop().time() - start) * 1000
            return ComponentHealth(
                name="oidc",
                healthy=True,
                message="Reachable",
                duration_ms=duration_ms,
            )

        except (httpx.HTTPError, TimeoutError) as e:
            duration_ms = (asyncio.get_event_loop().time() - start) * 1000
            logger.warning(
                "OIDC health check failed",
                extra={"error": str(e), "discovery_url": discovery_url},
            )
            return ComponentHealth(
                name="oidc",
                healthy=False,
                message=f"Unreachable: {str(e)}",
                duration_ms=duration_ms,
            )


__all__ = [
    "HealthStatus",
    "ComponentHealth",
    "HealthCheckResult",
    "HealthChecker",
]
