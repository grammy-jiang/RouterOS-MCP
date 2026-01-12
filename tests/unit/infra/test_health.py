"""Unit tests for health check infrastructure."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncEngine

from routeros_mcp.config import Settings
from routeros_mcp.infra.health import (
    ComponentHealth,
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
)


class TestComponentHealth:
    """Tests for ComponentHealth class."""

    def test_init_creates_component_health(self) -> None:
        """__init__() should create ComponentHealth with provided values."""
        component = ComponentHealth(
            name="database",
            healthy=True,
            message="Connected",
            duration_ms=12.5,
        )

        assert component.name == "database"
        assert component.healthy is True
        assert component.message == "Connected"
        assert component.duration_ms == 12.5

    def test_to_dict_serializes_correctly(self) -> None:
        """to_dict() should serialize to dictionary."""
        component = ComponentHealth(
            name="redis",
            healthy=False,
            message="Connection timeout",
            duration_ms=5000.123,
        )

        result = component.to_dict()

        assert result == {
            "name": "redis",
            "healthy": False,
            "message": "Connection timeout",
            "duration_ms": 5000.12,  # Rounded to 2 decimals
        }


class TestHealthCheckResult:
    """Tests for HealthCheckResult class."""

    def test_init_creates_result_with_components(self) -> None:
        """__init__() should create result with status and components."""
        components = [
            ComponentHealth("database", True, "OK"),
            ComponentHealth("redis", False, "Failed"),
        ]
        result = HealthCheckResult(
            status=HealthStatus.DEGRADED,
            components=components,
        )

        assert result.status == HealthStatus.DEGRADED
        assert len(result.components) == 2
        assert result.timestamp is not None

    def test_to_dict_serializes_with_components(self) -> None:
        """to_dict() should serialize result with nested components."""
        components = [
            ComponentHealth("database", True, "OK", 10.0),
            ComponentHealth("redis", True, "OK", 5.0),
        ]
        result = HealthCheckResult(
            status=HealthStatus.READY,
            components=components,
        )

        data = result.to_dict()

        assert data["status"] == "ready"
        assert "timestamp" in data
        assert "components" in data
        assert "database" in data["components"]
        assert "redis" in data["components"]
        assert data["components"]["database"]["healthy"] is True


class TestHealthChecker:
    """Tests for HealthChecker class."""

    @pytest.fixture
    def settings(self) -> Settings:
        """Create test settings."""
        return Settings(
            environment="lab",
            database_url="sqlite+aiosqlite:///:memory:",
            redis_cache_enabled=True,
            redis_url="redis://localhost:6379/0",
            oidc_enabled=True,
            oidc_issuer="https://auth.example.com",
            oidc_client_id="test-client-id",
            oidc_client_secret="test-client-secret",
        )

    @pytest.fixture
    def mock_db_engine(self) -> AsyncMock:
        """Create mock database engine."""
        engine = AsyncMock(spec=AsyncEngine)
        conn = AsyncMock()
        conn.execute = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock()
        engine.connect = MagicMock(return_value=conn)
        return engine

    def test_init_creates_health_checker(self, settings: Settings) -> None:
        """__init__() should create HealthChecker with settings."""
        checker = HealthChecker(settings)

        assert checker.settings == settings
        assert checker._is_shutting_down is False

    def test_set_shutdown_marks_as_shutting_down(self, settings: Settings) -> None:
        """set_shutdown() should mark checker as shutting down."""
        checker = HealthChecker(settings)

        checker.set_shutdown()

        assert checker._is_shutting_down is True

    @pytest.mark.asyncio
    async def test_check_health_returns_shutdown_when_shutting_down(
        self, settings: Settings
    ) -> None:
        """check_health() should return SHUTDOWN status when shutting down."""
        checker = HealthChecker(settings)
        checker.set_shutdown()

        result = await checker.check_health()

        assert result.status == HealthStatus.SHUTDOWN
        assert len(result.components) == 1
        assert result.components[0].name == "service"
        assert result.components[0].healthy is False
        assert "shutting down" in result.components[0].message.lower()

    @pytest.mark.asyncio
    async def test_check_health_all_components_healthy(
        self, settings: Settings, mock_db_engine: AsyncMock
    ) -> None:
        """check_health() should return READY when all components healthy."""
        checker = HealthChecker(settings, db_engine=mock_db_engine)

        # Mock Redis ping
        with (
            patch.object(Redis, "from_url", return_value=AsyncMock(spec=Redis)) as mock_redis,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
            ) as mock_http_get,
        ):
            mock_redis_client = mock_redis.return_value
            mock_redis_client.ping = AsyncMock()
            mock_redis_client.aclose = AsyncMock()

            # Mock OIDC discovery
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_http_get.return_value = mock_response

            result = await checker.check_health()

        assert result.status == HealthStatus.READY
        assert len(result.components) == 3  # DB, Redis, OIDC
        assert all(c.healthy for c in result.components)

    @pytest.mark.asyncio
    async def test_check_health_database_failure_returns_degraded(
        self, settings: Settings, mock_db_engine: AsyncMock
    ) -> None:
        """check_health() should return DEGRADED when database fails."""
        # Make database fail
        mock_db_engine.connect.side_effect = Exception("Connection refused")

        checker = HealthChecker(settings, db_engine=mock_db_engine)

        with (
            patch.object(Redis, "from_url", return_value=AsyncMock(spec=Redis)) as mock_redis,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
            ),
        ):
            mock_redis_client = mock_redis.return_value
            mock_redis_client.ping = AsyncMock()
            mock_redis_client.aclose = AsyncMock()

            result = await checker.check_health()

        assert result.status == HealthStatus.DEGRADED
        db_component = next(c for c in result.components if c.name == "database")
        assert db_component.healthy is False
        assert "Connection refused" in db_component.message

    @pytest.mark.asyncio
    async def test_check_health_redis_failure_returns_degraded(
        self, settings: Settings, mock_db_engine: AsyncMock
    ) -> None:
        """check_health() should return DEGRADED when Redis fails."""
        checker = HealthChecker(settings, db_engine=mock_db_engine)

        # Mock Redis failure
        with (
            patch.object(Redis, "from_url", return_value=AsyncMock(spec=Redis)) as mock_redis,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
            ) as mock_http_get,
        ):
            mock_redis_client = mock_redis.return_value
            mock_redis_client.ping = AsyncMock(side_effect=RedisError("Connection timeout"))
            mock_redis_client.aclose = AsyncMock()

            # Mock OIDC success
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_http_get.return_value = mock_response

            result = await checker.check_health()

        assert result.status == HealthStatus.DEGRADED
        redis_component = next(c for c in result.components if c.name == "redis")
        assert redis_component.healthy is False
        assert "Connection timeout" in redis_component.message

    @pytest.mark.asyncio
    async def test_check_health_oidc_failure_returns_degraded(
        self, settings: Settings, mock_db_engine: AsyncMock
    ) -> None:
        """check_health() should return DEGRADED when OIDC fails."""
        checker = HealthChecker(settings, db_engine=mock_db_engine)

        # Mock OIDC failure
        with (
            patch.object(Redis, "from_url", return_value=AsyncMock(spec=Redis)) as mock_redis,
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
            ) as mock_http_get,
        ):
            mock_redis_client = mock_redis.return_value
            mock_redis_client.ping = AsyncMock()
            mock_redis_client.aclose = AsyncMock()

            # Mock OIDC failure
            mock_http_get.side_effect = httpx.HTTPError("Unreachable")

            result = await checker.check_health()

        assert result.status == HealthStatus.DEGRADED
        oidc_component = next(c for c in result.components if c.name == "oidc")
        assert oidc_component.healthy is False
        assert "Unreachable" in oidc_component.message

    @pytest.mark.asyncio
    async def test_check_health_skips_redis_when_disabled(
        self, settings: Settings, mock_db_engine: AsyncMock
    ) -> None:
        """check_health() should skip Redis check when disabled."""
        settings.redis_cache_enabled = False
        checker = HealthChecker(settings, db_engine=mock_db_engine)

        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
        ) as mock_http_get:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_http_get.return_value = mock_response

            result = await checker.check_health()

        # Should only have database and OIDC components
        assert len(result.components) == 2
        assert not any(c.name == "redis" for c in result.components)

    @pytest.mark.asyncio
    async def test_check_health_skips_oidc_when_disabled(
        self, settings: Settings, mock_db_engine: AsyncMock
    ) -> None:
        """check_health() should skip OIDC check when disabled."""
        settings.oidc_enabled = False
        checker = HealthChecker(settings, db_engine=mock_db_engine)

        with patch.object(Redis, "from_url", return_value=AsyncMock(spec=Redis)) as mock_redis:
            mock_redis_client = mock_redis.return_value
            mock_redis_client.ping = AsyncMock()
            mock_redis_client.aclose = AsyncMock()

            result = await checker.check_health()

        # Should only have database and Redis components
        assert len(result.components) == 2
        assert not any(c.name == "oidc" for c in result.components)

    @pytest.mark.asyncio
    async def test_check_database_success(
        self, settings: Settings, mock_db_engine: AsyncMock
    ) -> None:
        """_check_database() should return healthy component on success."""
        checker = HealthChecker(settings, db_engine=mock_db_engine)

        component = await checker._check_database()

        assert component.name == "database"
        assert component.healthy is True
        assert component.message == "Connected"
        assert component.duration_ms > 0

    @pytest.mark.asyncio
    async def test_check_database_failure(
        self, settings: Settings, mock_db_engine: AsyncMock
    ) -> None:
        """_check_database() should return unhealthy component on failure."""
        mock_db_engine.connect.side_effect = Exception("Database error")
        checker = HealthChecker(settings, db_engine=mock_db_engine)

        component = await checker._check_database()

        assert component.name == "database"
        assert component.healthy is False
        assert "Database error" in component.message
        assert component.duration_ms > 0

    @pytest.mark.asyncio
    async def test_check_redis_success(self, settings: Settings) -> None:
        """_check_redis() should return healthy component on success."""
        checker = HealthChecker(settings)

        with patch.object(Redis, "from_url", return_value=AsyncMock(spec=Redis)) as mock_redis:
            mock_redis_client = mock_redis.return_value
            mock_redis_client.ping = AsyncMock()
            mock_redis_client.aclose = AsyncMock()

            component = await checker._check_redis()

        assert component.name == "redis"
        assert component.healthy is True
        assert component.message == "Connected"
        assert component.duration_ms > 0

    @pytest.mark.asyncio
    async def test_check_redis_failure(self, settings: Settings) -> None:
        """_check_redis() should return unhealthy component on failure."""
        checker = HealthChecker(settings)

        with patch.object(Redis, "from_url", return_value=AsyncMock(spec=Redis)) as mock_redis:
            mock_redis_client = mock_redis.return_value
            mock_redis_client.ping = AsyncMock(side_effect=RedisError("Connection failed"))
            mock_redis_client.aclose = AsyncMock()

            component = await checker._check_redis()

        assert component.name == "redis"
        assert component.healthy is False
        assert "Connection failed" in component.message
        assert component.duration_ms > 0

    @pytest.mark.asyncio
    async def test_check_oidc_success(self, settings: Settings) -> None:
        """_check_oidc() should return healthy component on success."""
        checker = HealthChecker(settings)

        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
        ) as mock_http_get:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_http_get.return_value = mock_response

            component = await checker._check_oidc()

        assert component.name == "oidc"
        assert component.healthy is True
        assert component.message == "Reachable"
        assert component.duration_ms > 0

    @pytest.mark.asyncio
    async def test_check_oidc_failure(self, settings: Settings) -> None:
        """_check_oidc() should return unhealthy component on failure."""
        checker = HealthChecker(settings)

        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
        ) as mock_http_get:
            mock_http_get.side_effect = httpx.HTTPError("Timeout")

            component = await checker._check_oidc()

        assert component.name == "oidc"
        assert component.healthy is False
        assert "Timeout" in component.message
        assert component.duration_ms > 0

    @pytest.mark.asyncio
    async def test_check_oidc_no_issuer_configured(self, settings: Settings) -> None:
        """_check_oidc() should return unhealthy when issuer not configured."""
        settings.oidc_issuer = None
        settings.oidc_provider_url = None
        checker = HealthChecker(settings)

        component = await checker._check_oidc()

        assert component.name == "oidc"
        assert component.healthy is False
        assert "not configured" in component.message.lower()

    def test_determine_status_all_healthy(self, settings: Settings) -> None:
        """_determine_status() should return READY when all healthy."""
        checker = HealthChecker(settings)
        components = [
            ComponentHealth("database", True, "OK"),
            ComponentHealth("redis", True, "OK"),
            ComponentHealth("oidc", True, "OK"),
        ]

        status = checker._determine_status(components)

        assert status == HealthStatus.READY

    def test_determine_status_database_unhealthy(self, settings: Settings) -> None:
        """_determine_status() should return DEGRADED when database unhealthy."""
        checker = HealthChecker(settings)
        components = [
            ComponentHealth("database", False, "Failed"),
            ComponentHealth("redis", True, "OK"),
        ]

        status = checker._determine_status(components)

        assert status == HealthStatus.DEGRADED

    def test_determine_status_redis_unhealthy(self, settings: Settings) -> None:
        """_determine_status() should return DEGRADED when Redis unhealthy."""
        checker = HealthChecker(settings)
        components = [
            ComponentHealth("database", True, "OK"),
            ComponentHealth("redis", False, "Failed"),
        ]

        status = checker._determine_status(components)

        assert status == HealthStatus.DEGRADED

    def test_determine_status_oidc_unhealthy(self, settings: Settings) -> None:
        """_determine_status() should return DEGRADED when OIDC unhealthy."""
        checker = HealthChecker(settings)
        components = [
            ComponentHealth("database", True, "OK"),
            ComponentHealth("oidc", False, "Failed"),
        ]

        status = checker._determine_status(components)

        assert status == HealthStatus.DEGRADED
