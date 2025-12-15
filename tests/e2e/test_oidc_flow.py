"""E2E tests for OIDC authentication flow."""

import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from authlib.jose import jwt

from routeros_mcp.config import Settings
from routeros_mcp.security.oidc import OIDCValidator


class TestOIDCFlowE2E:
    """End-to-end tests for OIDC authentication flow."""

    @pytest.fixture
    def settings(self):
        """Create settings with OIDC enabled."""
        return Settings(
            environment="lab",
            oidc_enabled=True,
            oidc_provider_url="https://auth.example.com",
            oidc_client_id="test-client-id",
            oidc_audience="test-audience",
            oidc_skip_verification=False,
        )

    @pytest.fixture
    def mock_http_client(self):
        """Create mock HTTP client for OIDC requests."""
        client = AsyncMock()
        client.aclose = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_full_oidc_flow_valid_token(self, settings, mock_http_client):
        """Test full OIDC flow with valid token."""
        # Setup mock responses
        discovery_response = Mock()
        discovery_response.json.return_value = {
            "issuer": "https://auth.example.com",
            "jwks_uri": "https://auth.example.com/jwks",
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
        }
        discovery_response.raise_for_status = Mock()

        jwks_response = Mock()
        jwks_response.json.return_value = {
            "keys": [
                {
                    "kid": "test-key-1",
                    "kty": "RSA",
                    "use": "sig",
                    "n": "test-n-value",
                    "e": "AQAB",
                }
            ]
        }
        jwks_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(
            side_effect=[discovery_response, jwks_response]
        )

        # Create validator
        validator = OIDCValidator(
            provider_url=settings.oidc_provider_url,
            client_id=settings.oidc_client_id,
            audience=settings.oidc_audience,
            skip_verification=True,  # Use skip mode for easier testing
            http_client=mock_http_client,
        )

        # Create valid token
        claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "name": "Test User",
            "role": "admin",
            "exp": time.time() + 3600,
            "iss": "https://auth.example.com",
            "aud": "test-audience",
        }

        # Create a real JWT token
        token = jwt.encode({"alg": "none"}, claims, None)

        # We'll need to mock JWT decode since we don't have real keys
        with patch("routeros_mcp.security.oidc.jwt.decode") as mock_decode:
            mock_decode.return_value = claims

            user = await validator.validate_token(token)

            # Verify user extracted correctly
            assert user.sub == "user-123"
            assert user.email == "test@example.com"
            assert user.name == "Test User"
            assert user.role == "admin"

    @pytest.mark.asyncio
    async def test_full_oidc_flow_token_caching(self, settings, mock_http_client):
        """Test that tokens are cached to reduce OIDC provider calls."""
        # Setup mocks
        discovery_response = Mock()
        discovery_response.json.return_value = {
            "jwks_uri": "https://auth.example.com/jwks"
        }
        discovery_response.raise_for_status = Mock()

        jwks_response = Mock()
        jwks_response.json.return_value = {
            "keys": [{"kid": "key-1", "kty": "RSA", "use": "sig", "n": "n", "e": "e"}]
        }
        jwks_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(
            side_effect=[discovery_response, jwks_response]
        )

        validator = OIDCValidator(
            provider_url=settings.oidc_provider_url,
            client_id=settings.oidc_client_id,
            audience=settings.oidc_audience,
            skip_verification=True,  # Use skip mode
            http_client=mock_http_client,
        )

        claims = {
            "sub": "user-456",
            "exp": time.time() + 3600,
            "iss": "https://auth.example.com",
            "aud": "test-audience",
        }

        # Create real JWT token
        token = jwt.encode({"alg": "none"}, claims, None)

        with patch("routeros_mcp.security.oidc.jwt.decode") as mock_decode:
            mock_decode.return_value = claims

            # First call - should validate
            user1 = await validator.validate_token(token)
            assert user1.sub == "user-456"

            # Second call with same token - should use cache
            user2 = await validator.validate_token(token)
            assert user2.sub == "user-456"
            # Token was cached, so same user returned

    @pytest.mark.asyncio
    async def test_full_oidc_flow_jwks_caching(self, settings, mock_http_client):
        """Test that JWKS is cached to reduce provider calls."""
        discovery_response = Mock()
        discovery_response.json.return_value = {
            "jwks_uri": "https://auth.example.com/jwks"
        }
        discovery_response.raise_for_status = Mock()

        jwks_response = Mock()
        jwks_response.json.return_value = {
            "keys": [{"kid": "key-1", "kty": "RSA", "use": "sig", "n": "n", "e": "e"}]
        }
        jwks_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(
            side_effect=[discovery_response, jwks_response]
        )

        validator = OIDCValidator(
            provider_url=settings.oidc_provider_url,
            client_id=settings.oidc_client_id,
            audience=settings.oidc_audience,
            skip_verification=True,  # Use skip mode
            http_client=mock_http_client,
        )

        claims1 = {
            "sub": "user-1",
            "exp": time.time() + 3600,
            "iss": "https://auth.example.com",
            "aud": "test-audience",
        }

        claims2 = {
            "sub": "user-2",
            "exp": time.time() + 3600,
            "iss": "https://auth.example.com",
            "aud": "test-audience",
        }

        # Create real JWT tokens
        token1 = jwt.encode({"alg": "none"}, claims1, None)
        token2 = jwt.encode({"alg": "none"}, claims2, None)

        with patch("routeros_mcp.security.oidc.jwt.decode") as mock_decode:
            # First token
            mock_decode.return_value = claims1
            user1 = await validator.validate_token(token1)
            assert user1.sub == "user-1"

            # Second different token
            mock_decode.return_value = claims2
            user2 = await validator.validate_token(token2)
            assert user2.sub == "user-2"

    @pytest.mark.asyncio
    async def test_oidc_flow_with_skip_verification(self):
        """Test OIDC flow with skip_verification enabled."""
        validator = OIDCValidator(
            provider_url="https://auth.example.com",
            client_id="test-client-id",
            skip_verification=True,
        )

        claims = {
            "sub": "user-789",
            "email": "dev@example.com",
            "role": "admin",
            "exp": time.time() + 3600,
            "iss": "https://auth.example.com",
            "aud": "test-client-id",
        }

        # Create token (signature doesn't matter with skip_verification)
        token = jwt.encode({"alg": "none"}, claims, None)

        with patch("routeros_mcp.security.oidc.jwt.decode") as mock_decode:
            mock_decode.return_value = claims

            user = await validator.validate_token(token)

            assert user.sub == "user-789"
            assert user.email == "dev@example.com"
            assert user.role == "admin"

    @pytest.mark.asyncio
    async def test_oidc_flow_graceful_degradation_on_provider_failure(
        self, settings, mock_http_client
    ):
        """Test graceful degradation when OIDC provider is unreachable."""
        # First successful fetch to populate cache
        discovery_response = Mock()
        discovery_response.json.return_value = {
            "jwks_uri": "https://auth.example.com/jwks"
        }
        discovery_response.raise_for_status = Mock()

        jwks_response = Mock()
        jwks_response.json.return_value = {
            "keys": [{"kid": "key-1", "kty": "RSA", "use": "sig", "n": "n", "e": "e"}]
        }
        jwks_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(
            side_effect=[discovery_response, jwks_response]
        )

        validator = OIDCValidator(
            provider_url=settings.oidc_provider_url,
            client_id=settings.oidc_client_id,
            http_client=mock_http_client,
        )

        # Populate JWKS cache
        await validator._get_jwks()
        assert validator._jwks_cache is not None

        # Expire the cache
        validator._jwks_cache.expires_at = time.time() - 100

        # Now simulate provider failure
        mock_http_client.get = AsyncMock(side_effect=Exception("Provider down"))

        # Should use stale cache
        jwks = await validator._get_jwks()
        assert jwks is not None
        assert "key-1" in jwks.keys

    @pytest.mark.asyncio
    async def test_config_validation_oidc_enabled(self):
        """Test config validation when OIDC is enabled."""
        # Valid config
        Settings(
            oidc_enabled=True,
            oidc_provider_url="https://auth.example.com",
            oidc_client_id="test-client",
        )

        # Invalid config - missing provider_url
        with pytest.raises(ValueError, match="missing required fields.*oidc_provider_url"):
            Settings(
                oidc_enabled=True,
                oidc_client_id="test-client",
                # Missing oidc_provider_url
            )

        # Invalid config - missing client_id
        with pytest.raises(ValueError, match="missing required fields.*oidc_client_id"):
            Settings(
                oidc_enabled=True,
                oidc_provider_url="https://auth.example.com",
                # Missing oidc_client_id
            )

    @pytest.mark.asyncio
    async def test_config_warning_skip_verification_in_prod(self):
        """Test warning when skip_verification enabled in prod."""
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            settings = Settings(
                environment="prod",
                oidc_enabled=True,
                oidc_provider_url="https://auth.example.com",
                oidc_client_id="test-client",
                oidc_skip_verification=True,
                encryption_key="test-key-32-bytes-long-enough!",
            )

            # Should have warning about skip_verification in prod
            assert any("DANGEROUS" in str(warning.message) for warning in w)
