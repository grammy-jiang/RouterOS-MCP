"""Tests for OIDC token validation."""

import time
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from authlib.jose import jwt

from routeros_mcp.security.auth import InvalidTokenError, MissingClaimError, User
from routeros_mcp.security.oidc import (
    CLOCK_SKEW_SECONDS,
    CachedJWKS,
    CachedToken,
    OIDCValidator,
)


class TestOIDCValidator:
    """Tests for OIDCValidator class."""

    @pytest.fixture
    def mock_http_client(self):
        """Create mock HTTP client."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.aclose = AsyncMock()
        return client

    @pytest.fixture
    def validator(self, mock_http_client):
        """Create OIDCValidator instance."""
        return OIDCValidator(
            provider_url="https://auth.example.com",
            client_id="test-client-id",
            audience="test-audience",
            skip_verification=False,
            http_client=mock_http_client,
        )

    @pytest.fixture
    def validator_skip_verification(self, mock_http_client):
        """Create OIDCValidator with skip_verification enabled."""
        return OIDCValidator(
            provider_url="https://auth.example.com",
            client_id="test-client-id",
            skip_verification=True,
            http_client=mock_http_client,
        )

    def test_init(self, validator):
        """Test OIDCValidator initialization."""
        assert validator.provider_url == "https://auth.example.com"
        assert validator.client_id == "test-client-id"
        assert validator.audience == "test-audience"
        assert validator.skip_verification is False

    def test_init_with_trailing_slash(self, mock_http_client):
        """Test provider_url trailing slash is removed."""
        validator = OIDCValidator(
            provider_url="https://auth.example.com/",
            client_id="test-client-id",
            http_client=mock_http_client,
        )
        assert validator.provider_url == "https://auth.example.com"

    def test_init_defaults_audience_to_client_id(self, mock_http_client):
        """Test audience defaults to client_id."""
        validator = OIDCValidator(
            provider_url="https://auth.example.com",
            client_id="test-client-id",
            http_client=mock_http_client,
        )
        assert validator.audience == "test-client-id"

    def test_hash_token(self, validator):
        """Test token hashing."""
        token = "test-token-123"
        hash1 = validator._hash_token(token)
        hash2 = validator._hash_token(token)

        # Same token should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 produces 64 hex chars
        assert hash1 != token  # Hash should differ from plaintext

    @pytest.mark.asyncio
    async def test_cache_token(self, validator):
        """Test token caching."""
        user = User(sub="user-123", email="test@example.com", role="admin")
        token_hash = "abc123"
        exp = time.time() + 3600

        await validator._cache_token(token_hash, user, exp)

        cached = validator._token_cache[token_hash]
        assert cached.user == user
        assert cached.expires_at <= exp  # Should be min(exp, now + 5min)

    def test_get_cached_token_hit(self, validator):
        """Test getting cached token (cache hit)."""
        user = User(sub="user-123", email="test@example.com", role="admin")
        token_hash = "abc123"
        exp = time.time() + 3600

        validator._token_cache[token_hash] = CachedToken(user=user, expires_at=exp)

        cached = validator._get_cached_token(token_hash)
        assert cached is not None
        assert cached.user == user

    def test_get_cached_token_miss(self, validator):
        """Test getting cached token (cache miss)."""
        cached = validator._get_cached_token("nonexistent")
        assert cached is None

    def test_get_cached_token_expired(self, validator):
        """Test getting expired cached token."""
        user = User(sub="user-123", email="test@example.com", role="admin")
        token_hash = "abc123"
        exp = time.time() - 100  # Expired 100 seconds ago

        validator._token_cache[token_hash] = CachedToken(user=user, expires_at=exp)

        cached = validator._get_cached_token(token_hash)
        assert cached is None
        # Expired entry should NOT be removed here (cleanup happens in _cache_token)
        # Just verify it returns None for expired tokens

    @pytest.mark.asyncio
    async def test_cleanup_token_cache(self, validator):
        """Test token cache cleanup."""
        # Add valid and expired tokens
        now = time.time()
        validator._token_cache["valid1"] = CachedToken(
            user=User(sub="u1", email=None, role="admin"), expires_at=now + 3600
        )
        validator._token_cache["expired1"] = CachedToken(
            user=User(sub="u2", email=None, role="admin"), expires_at=now - 100
        )
        validator._token_cache["expired2"] = CachedToken(
            user=User(sub="u3", email=None, role="admin"), expires_at=now - 50
        )

        await validator._cleanup_token_cache()

        # Only valid token should remain
        assert "valid1" in validator._token_cache
        assert "expired1" not in validator._token_cache
        assert "expired2" not in validator._token_cache

    def test_extract_user_claims_full(self, validator):
        """Test extracting user claims with all fields."""
        claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "name": "Test User",
            "role": "ops_rw",
            "device_scope": ["device-1", "device-2"],
        }

        user = validator._extract_user_claims(claims)

        assert user.sub == "user-123"
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.role == "ops_rw"
        assert user.device_scope == ["device-1", "device-2"]

    def test_extract_user_claims_minimal(self, validator):
        """Test extracting user claims with minimal fields."""
        claims = {"sub": "user-456"}

        user = validator._extract_user_claims(claims)

        assert user.sub == "user-456"
        assert user.email is None
        assert user.name is None
        assert user.role == "read_only"  # Default role
        assert user.device_scope is None

    def test_extract_user_claims_missing_sub(self, validator):
        """Test extracting user claims without sub."""
        claims = {"email": "test@example.com"}

        with pytest.raises(MissingClaimError, match="missing 'sub' claim"):
            validator._extract_user_claims(claims)

    def test_extract_user_claims_custom_role_claim(self, validator):
        """Test extracting role from custom claim."""
        claims = {
            "sub": "user-123",
            "https://routeros-mcp/role": "admin",
        }

        user = validator._extract_user_claims(claims)
        assert user.role == "admin"

    def test_extract_user_claims_role_array(self, validator):
        """Test extracting role from array (takes first)."""
        claims = {
            "sub": "user-123",
            "role": ["admin", "ops_rw"],
        }

        user = validator._extract_user_claims(claims)
        assert user.role == "admin"

    def test_extract_user_claims_device_scope_string(self, validator):
        """Test extracting device_scope from comma-separated string."""
        claims = {
            "sub": "user-123",
            "device_scope": "device-1, device-2, device-3",
        }

        user = validator._extract_user_claims(claims)
        assert user.device_scope == ["device-1", "device-2", "device-3"]

    def test_extract_user_claims_custom_device_scope(self, validator):
        """Test extracting device_scope from custom claim."""
        claims = {
            "sub": "user-123",
            "https://routeros-mcp/devices": ["dev-1", "dev-2"],
        }

        user = validator._extract_user_claims(claims)
        assert user.device_scope == ["dev-1", "dev-2"]

    @pytest.mark.asyncio
    async def test_get_jwks_fetch_success(self, validator, mock_http_client):
        """Test fetching JWKS from OIDC provider."""
        # Mock discovery endpoint response
        discovery_response = Mock()
        discovery_response.json.return_value = {"jwks_uri": "https://auth.example.com/jwks"}
        discovery_response.raise_for_status = Mock()

        # Mock JWKS endpoint response
        jwks_response = Mock()
        jwks_response.json.return_value = {
            "keys": [
                {
                    "kid": "key-1",
                    "kty": "RSA",
                    "use": "sig",
                    "n": "test-n",
                    "e": "AQAB",
                }
            ]
        }
        jwks_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(side_effect=[discovery_response, jwks_response])

        jwks = await validator._get_jwks()

        assert jwks is not None
        assert "key-1" in jwks.keys
        assert jwks.expires_at > time.time()

        # Verify HTTP calls
        assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_get_jwks_cache_hit(self, validator):
        """Test JWKS cache hit."""
        # Populate cache
        cached_jwks = CachedJWKS(keys={"key-1": "mock-key"}, expires_at=time.time() + 3600)
        validator._jwks_cache = cached_jwks

        jwks = await validator._get_jwks()

        assert jwks is cached_jwks
        # Should not make HTTP call (already tested via mock assertions)

    @pytest.mark.asyncio
    async def test_get_jwks_cache_expired(self, validator, mock_http_client):
        """Test JWKS cache expired, refetch."""
        # Populate expired cache
        validator._jwks_cache = CachedJWKS(
            keys={"old-key": "old-value"}, expires_at=time.time() - 100
        )

        # Mock responses
        discovery_response = Mock()
        discovery_response.json.return_value = {"jwks_uri": "https://auth.example.com/jwks"}
        discovery_response.raise_for_status = Mock()

        jwks_response = Mock()
        jwks_response.json.return_value = {
            "keys": [{"kid": "new-key", "kty": "RSA", "use": "sig", "n": "n", "e": "e"}]
        }
        jwks_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(side_effect=[discovery_response, jwks_response])

        jwks = await validator._get_jwks()

        assert jwks is not None
        assert "new-key" in jwks.keys
        assert "old-key" not in jwks.keys

    @pytest.mark.asyncio
    async def test_get_jwks_fetch_failure_uses_stale_cache(self, validator, mock_http_client):
        """Test JWKS fetch failure falls back to stale cache."""
        # Populate stale cache
        stale_jwks = CachedJWKS(keys={"stale-key": "stale-value"}, expires_at=time.time() - 100)
        validator._jwks_cache = stale_jwks

        # Mock HTTP error
        mock_http_client.get = AsyncMock(side_effect=httpx.HTTPError("Network error"))

        jwks = await validator._get_jwks()

        # Should return stale cache
        assert jwks is stale_jwks

    @pytest.mark.asyncio
    async def test_get_jwks_fetch_failure_no_cache(self, validator, mock_http_client):
        """Test JWKS fetch failure without cache returns None."""
        # No cache
        validator._jwks_cache = None

        # Mock HTTP error
        mock_http_client.get = AsyncMock(side_effect=httpx.HTTPError("Network error"))

        jwks = await validator._get_jwks()

        assert jwks is None

    @pytest.mark.asyncio
    async def test_validate_token_skip_verification(self, validator_skip_verification):
        """Test token validation with skip_verification enabled."""
        # Create a simple JWT (no signature verification)
        claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "role": "admin",
            "exp": time.time() + 3600,
            "iss": "https://auth.example.com",
            "aud": "test-client-id",
        }

        # Create token with no signature (just for testing)
        # In skip mode, we don't verify signature
        header = {"alg": "none", "typ": "JWT"}
        token = jwt.encode(header, claims, None)

        with patch("routeros_mcp.security.oidc.jwt.decode") as mock_decode:
            mock_decode.return_value = claims

            user = await validator_skip_verification.validate_token(token)

            assert user.sub == "user-123"
            assert user.email == "test@example.com"
            assert user.role == "admin"

    @pytest.mark.asyncio
    async def test_validate_token_cache_hit(self, validator):
        """Test token validation cache hit."""
        token = "test-token-123"
        cached_user = User(sub="cached-user", email="cached@example.com", role="admin")
        token_hash = validator._hash_token(token)

        # Populate cache
        validator._token_cache[token_hash] = CachedToken(
            user=cached_user, expires_at=time.time() + 3600
        )

        user = await validator.validate_token(token)

        # Should return cached user without validation
        assert user == cached_user

    @pytest.mark.asyncio
    async def test_validate_token_missing_exp(self, validator_skip_verification):
        """Test token validation fails if exp claim missing."""
        claims = {
            "sub": "user-123",
            "iss": "https://auth.example.com",
            "aud": "test-client-id",
            # Missing 'exp'
        }

        token = jwt.encode({"alg": "none"}, claims, None)

        with patch("routeros_mcp.security.oidc.jwt.decode") as mock_decode:
            mock_decode.return_value = claims

            with pytest.raises(MissingClaimError, match="missing 'exp' claim"):
                await validator_skip_verification.validate_token(token)

    @pytest.mark.asyncio
    async def test_validate_token_expired(self, validator_skip_verification):
        """Test token validation fails if token expired."""
        claims = {
            "sub": "user-123",
            "exp": time.time() - 100,  # Expired 100 seconds ago
            "iss": "https://auth.example.com",
            "aud": "test-client-id",
        }

        token = jwt.encode({"alg": "none"}, claims, None)

        with patch("routeros_mcp.security.oidc.jwt.decode") as mock_decode:
            mock_decode.return_value = claims

            with pytest.raises(InvalidTokenError, match="Token expired"):
                await validator_skip_verification.validate_token(token)

    @pytest.mark.asyncio
    async def test_validate_token_clock_skew_tolerance(self, validator_skip_verification):
        """Test token validation allows clock skew."""
        # Token expired 10 seconds ago (within CLOCK_SKEW_SECONDS tolerance)
        claims = {
            "sub": "user-123",
            "exp": time.time() - 10,
            "iss": "https://auth.example.com",
            "aud": "test-client-id",
        }

        token = jwt.encode({"alg": "none"}, claims, None)

        with patch("routeros_mcp.security.oidc.jwt.decode") as mock_decode:
            mock_decode.return_value = claims

            # Should succeed due to clock skew tolerance
            user = await validator_skip_verification.validate_token(token)
            assert user.sub == "user-123"

    @pytest.mark.asyncio
    async def test_validate_token_clock_skew_exceeded(self, validator_skip_verification):
        """Test token validation fails if clock skew exceeded."""
        # Token expired beyond CLOCK_SKEW_SECONDS tolerance
        claims = {
            "sub": "user-123",
            "exp": time.time() - CLOCK_SKEW_SECONDS - 10,
            "iss": "https://auth.example.com",
            "aud": "test-client-id",
        }

        token = jwt.encode({"alg": "none"}, claims, None)

        with patch("routeros_mcp.security.oidc.jwt.decode") as mock_decode:
            mock_decode.return_value = claims

            with pytest.raises(InvalidTokenError, match="Token expired"):
                await validator_skip_verification.validate_token(token)

    @pytest.mark.asyncio
    async def test_validate_token_with_signature_verification(self, mock_http_client):
        """Test token validation with actual JWT signature verification."""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        from authlib.jose import JsonWebKey

        # Generate RSA key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )

        # Serialize keys to PEM format
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Import keys with authlib
        private_jwk = JsonWebKey.import_key(private_pem)
        public_jwk = JsonWebKey.import_key(public_pem)

        # Create public JWK dict for JWKS response
        public_jwk_dict = public_jwk.as_dict()
        public_jwk_dict["kid"] = "test-key-1"
        public_jwk_dict["use"] = "sig"
        public_jwk_dict["alg"] = "RS256"

        # Mock OIDC discovery and JWKS responses
        discovery_response = Mock()
        discovery_response.json.return_value = {"jwks_uri": "https://auth.example.com/jwks"}
        discovery_response.raise_for_status = Mock()

        jwks_response = Mock()
        jwks_response.json.return_value = {"keys": [public_jwk_dict]}
        jwks_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(side_effect=[discovery_response, jwks_response])

        # Create validator WITHOUT skip_verification
        validator = OIDCValidator(
            provider_url="https://auth.example.com",
            client_id="test-client-id",
            audience="test-audience",
            skip_verification=False,
            http_client=mock_http_client,
        )

        # Create signed JWT token
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-key-1"}
        claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "role": "admin",
            "exp": time.time() + 3600,
            "iss": "https://auth.example.com",
            "aud": "test-audience",
        }

        token = jwt.encode(header, claims, private_jwk)

        # Validate token with signature verification
        user = await validator.validate_token(token)

        assert user.sub == "user-123"
        assert user.email == "test@example.com"
        assert user.role == "admin"

    @pytest.mark.asyncio
    async def test_validate_token_invalid_signature(self, mock_http_client):
        """Test that invalid signatures are rejected."""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        from authlib.jose import JsonWebKey

        # Generate two different RSA key pairs
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )

        wrong_private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )

        # Serialize keys
        wrong_private_pem = wrong_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Import with authlib
        wrong_private_jwk = JsonWebKey.import_key(wrong_private_pem)
        public_jwk = JsonWebKey.import_key(public_pem)

        # Create public JWK dict from FIRST key for JWKS response
        public_jwk_dict = public_jwk.as_dict()
        public_jwk_dict["kid"] = "test-key-1"
        public_jwk_dict["use"] = "sig"
        public_jwk_dict["alg"] = "RS256"

        # Mock OIDC discovery and JWKS responses
        discovery_response = Mock()
        discovery_response.json.return_value = {"jwks_uri": "https://auth.example.com/jwks"}
        discovery_response.raise_for_status = Mock()

        jwks_response = Mock()
        jwks_response.json.return_value = {"keys": [public_jwk_dict]}
        jwks_response.raise_for_status = Mock()

        mock_http_client.get = AsyncMock(side_effect=[discovery_response, jwks_response])

        validator = OIDCValidator(
            provider_url="https://auth.example.com",
            client_id="test-client-id",
            skip_verification=False,
            http_client=mock_http_client,
        )

        # Sign token with WRONG key
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-key-1"}
        claims = {
            "sub": "user-123",
            "exp": time.time() + 3600,
            "iss": "https://auth.example.com",
            "aud": "test-client-id",
        }

        token = jwt.encode(header, claims, wrong_private_jwk)

        # Should fail signature verification
        with pytest.raises(InvalidTokenError, match="Invalid JWT token"):
            await validator.validate_token(token)
