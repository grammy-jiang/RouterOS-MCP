"""Tests for OIDC callback, token refresh, and logout functionality."""

import time
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from authlib.jose import jwt

from routeros_mcp.security.auth import AuthenticationError, InvalidTokenError, UserSession
from routeros_mcp.security.oidc import (
    exchange_authorization_code,
    parse_id_token_claims,
    refresh_access_token,
    revoke_tokens,
)


class TestExchangeAuthorizationCode:
    """Tests for exchange_authorization_code function."""

    @pytest.fixture
    def mock_http_client(self):
        """Create mock HTTP client."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.aclose = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, mock_http_client):
        """Test successful authorization code exchange."""
        # Mock OIDC discovery response
        discovery_response = Mock()
        discovery_response.json.return_value = {"token_endpoint": "https://auth.example.com/token"}
        discovery_response.raise_for_status = Mock()

        # Mock token endpoint response
        token_response = Mock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "access-token-123",
            "refresh_token": "refresh-token-456",
            "id_token": "id-token-789",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "openid profile email",
        }
        token_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(return_value=discovery_response)
        mock_http_client.post = AsyncMock(return_value=token_response)

        # Exchange code for tokens
        tokens = await exchange_authorization_code(
            issuer="https://auth.example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="http://localhost:8080/callback",
            code="auth-code-123",
            code_verifier="verifier-abc",
            http_client=mock_http_client,
        )

        # Verify tokens
        assert tokens["access_token"] == "access-token-123"
        assert tokens["refresh_token"] == "refresh-token-456"
        assert tokens["id_token"] == "id-token-789"
        assert tokens["expires_in"] == 3600

        # Verify HTTP calls
        assert mock_http_client.get.call_count == 1
        assert mock_http_client.post.call_count == 1

        # Verify token request data
        post_call = mock_http_client.post.call_args
        assert post_call[1]["data"]["grant_type"] == "authorization_code"
        assert post_call[1]["data"]["code"] == "auth-code-123"
        assert post_call[1]["data"]["code_verifier"] == "verifier-abc"
        assert post_call[1]["data"]["client_id"] == "test-client-id"
        assert post_call[1]["data"]["client_secret"] == "test-client-secret"

    @pytest.mark.asyncio
    async def test_exchange_code_missing_token_endpoint(self, mock_http_client):
        """Test exchange fails if discovery missing token_endpoint."""
        # Mock discovery response without token_endpoint
        discovery_response = Mock()
        discovery_response.json.return_value = {}
        discovery_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(return_value=discovery_response)

        with pytest.raises(AuthenticationError, match="missing token_endpoint"):
            await exchange_authorization_code(
                issuer="https://auth.example.com",
                client_id="test-client-id",
                client_secret="test-client-secret",
                redirect_uri="http://localhost:8080/callback",
                code="auth-code-123",
                code_verifier="verifier-abc",
                http_client=mock_http_client,
            )

    @pytest.mark.asyncio
    async def test_exchange_code_token_endpoint_error(self, mock_http_client):
        """Test exchange fails if token endpoint returns error."""
        # Mock discovery response
        discovery_response = Mock()
        discovery_response.json.return_value = {"token_endpoint": "https://auth.example.com/token"}
        discovery_response.raise_for_status = Mock()

        # Mock token endpoint error
        token_response = Mock()
        token_response.status_code = 400
        token_response.text = "invalid_grant: Authorization code expired"
        token_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(return_value=discovery_response)
        mock_http_client.post = AsyncMock(return_value=token_response)

        with pytest.raises(AuthenticationError, match="Token exchange failed"):
            await exchange_authorization_code(
                issuer="https://auth.example.com",
                client_id="test-client-id",
                client_secret="test-client-secret",
                redirect_uri="http://localhost:8080/callback",
                code="invalid-code",
                code_verifier="verifier-abc",
                http_client=mock_http_client,
            )

    @pytest.mark.asyncio
    async def test_exchange_code_http_error(self, mock_http_client):
        """Test exchange fails on HTTP error."""
        # Mock HTTP error
        mock_http_client.get = AsyncMock(side_effect=httpx.HTTPError("Network error"))

        with pytest.raises(AuthenticationError, match="Token exchange failed"):
            await exchange_authorization_code(
                issuer="https://auth.example.com",
                client_id="test-client-id",
                client_secret="test-client-secret",
                redirect_uri="http://localhost:8080/callback",
                code="auth-code-123",
                code_verifier="verifier-abc",
                http_client=mock_http_client,
            )


class TestRefreshAccessToken:
    """Tests for refresh_access_token function."""

    @pytest.fixture
    def mock_http_client(self):
        """Create mock HTTP client."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.aclose = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, mock_http_client):
        """Test successful token refresh."""
        # Mock OIDC discovery response
        discovery_response = Mock()
        discovery_response.json.return_value = {"token_endpoint": "https://auth.example.com/token"}
        discovery_response.raise_for_status = Mock()

        # Mock token endpoint response
        token_response = Mock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "new-access-token-123",
            "refresh_token": "new-refresh-token-456",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        token_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(return_value=discovery_response)
        mock_http_client.post = AsyncMock(return_value=token_response)

        # Refresh token
        tokens = await refresh_access_token(
            issuer="https://auth.example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
            refresh_token="old-refresh-token",
            http_client=mock_http_client,
        )

        # Verify tokens
        assert tokens["access_token"] == "new-access-token-123"
        assert tokens["refresh_token"] == "new-refresh-token-456"
        assert tokens["expires_in"] == 3600

        # Verify HTTP calls
        assert mock_http_client.get.call_count == 1
        assert mock_http_client.post.call_count == 1

        # Verify refresh request data
        post_call = mock_http_client.post.call_args
        assert post_call[1]["data"]["grant_type"] == "refresh_token"
        assert post_call[1]["data"]["refresh_token"] == "old-refresh-token"

    @pytest.mark.asyncio
    async def test_refresh_token_expired(self, mock_http_client):
        """Test refresh fails with expired token."""
        # Mock discovery response
        discovery_response = Mock()
        discovery_response.json.return_value = {"token_endpoint": "https://auth.example.com/token"}
        discovery_response.raise_for_status = Mock()

        # Mock token endpoint error
        token_response = Mock()
        token_response.status_code = 400
        token_response.text = "invalid_grant: Refresh token expired"
        token_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(return_value=discovery_response)
        mock_http_client.post = AsyncMock(return_value=token_response)

        with pytest.raises(AuthenticationError, match="Token refresh failed"):
            await refresh_access_token(
                issuer="https://auth.example.com",
                client_id="test-client-id",
                client_secret="test-client-secret",
                refresh_token="expired-token",
                http_client=mock_http_client,
            )

    @pytest.mark.asyncio
    async def test_refresh_token_http_error(self, mock_http_client):
        """Test refresh fails on HTTP error."""
        mock_http_client.get = AsyncMock(side_effect=httpx.HTTPError("Network error"))

        with pytest.raises(AuthenticationError, match="Token refresh failed"):
            await refresh_access_token(
                issuer="https://auth.example.com",
                client_id="test-client-id",
                client_secret="test-client-secret",
                refresh_token="refresh-token",
                http_client=mock_http_client,
            )


class TestRevokeTokens:
    """Tests for revoke_tokens function."""

    @pytest.fixture
    def mock_http_client(self):
        """Create mock HTTP client."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.aclose = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_revoke_token_success(self, mock_http_client):
        """Test successful token revocation."""
        # Mock OIDC discovery response
        discovery_response = Mock()
        discovery_response.json.return_value = {
            "revocation_endpoint": "https://auth.example.com/revoke"
        }
        discovery_response.raise_for_status = Mock()

        # Mock revocation endpoint response
        revoke_response = Mock()
        revoke_response.status_code = 200
        revoke_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(return_value=discovery_response)
        mock_http_client.post = AsyncMock(return_value=revoke_response)

        # Revoke token (should not raise)
        await revoke_tokens(
            issuer="https://auth.example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
            token="access-token-123",
            token_type_hint="access_token",
            http_client=mock_http_client,
        )

        # Verify HTTP calls
        assert mock_http_client.get.call_count == 1
        assert mock_http_client.post.call_count == 1

        # Verify revocation request data
        post_call = mock_http_client.post.call_args
        assert post_call[1]["data"]["token"] == "access-token-123"
        assert post_call[1]["data"]["token_type_hint"] == "access_token"

    @pytest.mark.asyncio
    async def test_revoke_token_no_revocation_endpoint(self, mock_http_client):
        """Test revocation silently succeeds if provider doesn't support it."""
        # Mock discovery response without revocation_endpoint
        discovery_response = Mock()
        discovery_response.json.return_value = {}
        discovery_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(return_value=discovery_response)

        # Should not raise (graceful handling)
        await revoke_tokens(
            issuer="https://auth.example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
            token="access-token-123",
            http_client=mock_http_client,
        )

        # Should not call post endpoint
        assert mock_http_client.post.call_count == 0

    @pytest.mark.asyncio
    async def test_revoke_token_error(self, mock_http_client):
        """Test revocation fails on error response."""
        # Mock discovery response
        discovery_response = Mock()
        discovery_response.json.return_value = {
            "revocation_endpoint": "https://auth.example.com/revoke"
        }
        discovery_response.raise_for_status = Mock()

        # Mock revocation error
        revoke_response = Mock()
        revoke_response.status_code = 400
        revoke_response.text = "invalid_token"
        revoke_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(return_value=discovery_response)
        mock_http_client.post = AsyncMock(return_value=revoke_response)

        with pytest.raises(AuthenticationError, match="Token revocation failed"):
            await revoke_tokens(
                issuer="https://auth.example.com",
                client_id="test-client-id",
                client_secret="test-client-secret",
                token="invalid-token",
                http_client=mock_http_client,
            )


class TestParseIdTokenClaims:
    """Tests for parse_id_token_claims function."""

    def test_parse_id_token_success(self):
        """Test successful ID token parsing."""
        # Create a simple ID token (no signature verification)
        claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "name": "Test User",
            "iss": "https://auth.example.com",
            "aud": "test-client-id",
            "exp": time.time() + 3600,
            "iat": time.time(),
        }

        # Create unsigned JWT for testing
        header = {"alg": "none", "typ": "JWT"}
        id_token = jwt.encode(header, claims, None)

        # Parse claims
        parsed_claims = parse_id_token_claims(id_token)

        assert parsed_claims["sub"] == "user-123"
        assert parsed_claims["email"] == "test@example.com"
        assert parsed_claims["name"] == "Test User"

    def test_parse_id_token_minimal_claims(self):
        """Test parsing ID token with minimal claims."""
        claims = {
            "sub": "user-456",
            "iss": "https://auth.example.com",
            "aud": "test-client-id",
            "exp": time.time() + 3600,
        }

        header = {"alg": "none", "typ": "JWT"}
        id_token = jwt.encode(header, claims, None)

        parsed_claims = parse_id_token_claims(id_token)

        assert parsed_claims["sub"] == "user-456"
        assert "email" not in parsed_claims
        assert "name" not in parsed_claims

    def test_parse_id_token_invalid(self):
        """Test parsing invalid ID token."""
        with pytest.raises(InvalidTokenError, match="Invalid ID token"):
            parse_id_token_claims("not-a-valid-jwt-token")

    def test_parse_id_token_malformed(self):
        """Test parsing malformed ID token."""
        # Token with wrong number of parts
        with pytest.raises(InvalidTokenError, match="Invalid ID token"):
            parse_id_token_claims("header.payload")

    def test_parse_id_token_with_signature_validation_raises(self):
        """Test that signature validation request raises error."""
        claims = {"sub": "user-123"}
        header = {"alg": "none", "typ": "JWT"}
        id_token = jwt.encode(header, claims, None)

        with pytest.raises(InvalidTokenError, match="Signature validation requires"):
            parse_id_token_claims(id_token, validate_signature=True)


class TestUserSession:
    """Tests for UserSession dataclass."""

    def test_user_session_creation(self):
        """Test creating UserSession object."""
        session = UserSession(
            sub="user-123",
            email="test@example.com",
            display_name="Test User",
            access_token="access-token-123",
            refresh_token="refresh-token-456",
            expires_at=time.time() + 3600,
            id_token="id-token-789",
        )

        assert session.sub == "user-123"
        assert session.email == "test@example.com"
        assert session.display_name == "Test User"
        assert session.access_token == "access-token-123"
        assert session.refresh_token == "refresh-token-456"
        assert session.id_token == "id-token-789"
        assert session.expires_at > time.time()

    def test_user_session_minimal(self):
        """Test creating UserSession with minimal fields."""
        session = UserSession(
            sub="user-456",
            email=None,
            display_name=None,
            access_token="access-token-only",
        )

        assert session.sub == "user-456"
        assert session.email is None
        assert session.display_name is None
        assert session.access_token == "access-token-only"
        assert session.refresh_token is None
        assert session.expires_at is None
        assert session.id_token is None
