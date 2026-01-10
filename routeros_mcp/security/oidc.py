"""OAuth/OIDC token validation for HTTP transport.

Provides JWT token validation against OIDC provider with:
- Public key fetching and caching
- Token signature verification
- Claims extraction and validation
- Token result caching to reduce OIDC provider calls

See docs/02-security-oauth-integration-and-access-control.md for design.
"""

import asyncio
import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
from authlib.jose import JsonWebKey, jwt
from authlib.jose.errors import JoseError

from routeros_mcp.security.auth import (
    AuthenticationError,
    InvalidTokenError,
    MissingClaimError,
    User,
)

logger = logging.getLogger(__name__)

# Clock skew tolerance (±30 seconds)
CLOCK_SKEW_SECONDS = 30

# Cache TTLs
JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour for public keys
TOKEN_CACHE_TTL_SECONDS = 300  # 5 minutes for validated tokens


@dataclass
class CachedToken:
    """Cached validated token result."""

    user: User
    expires_at: float  # Unix timestamp


@dataclass
class CachedJWKS:
    """Cached JWKS (JSON Web Key Set)."""

    keys: dict[str, Any]  # kid -> key mapping
    expires_at: float  # Unix timestamp


class OIDCValidator:
    """OAuth/OIDC token validator with caching.

    Validates JWT tokens from OIDC provider by:
    1. Fetching public keys from OIDC discovery endpoint (cached)
    2. Verifying JWT signature
    3. Validating expiry, audience, issuer
    4. Extracting user claims

    Example:
        validator = OIDCValidator(
            provider_url="https://auth0.example.com",
            client_id="my-client-id",
            audience="my-api",
        )
        user = await validator.validate_token("eyJhbGc...")
    """

    def __init__(
        self,
        provider_url: str,
        client_id: str,
        audience: str | None = None,
        skip_verification: bool = False,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize OIDC validator.

        Args:
            provider_url: OIDC provider URL (e.g., https://auth0.example.com)
            client_id: OAuth client ID (used for audience validation)
            audience: Expected token audience (defaults to client_id)
            skip_verification: Skip signature verification (dev mode only, DANGEROUS)
            http_client: Optional HTTP client for testing
        """
        self.provider_url = provider_url.rstrip("/")
        self.client_id = client_id
        self.audience = audience or client_id
        self.skip_verification = skip_verification
        self._http_client = http_client

        # Caches
        self._jwks_cache: CachedJWKS | None = None
        self._token_cache: dict[str, CachedToken] = {}

        # Thread safety locks
        self._jwks_lock = asyncio.Lock()
        self._token_cache_lock = asyncio.Lock()

        if skip_verification:
            logger.warning(
                "OIDC signature verification DISABLED - use only in development",
                extra={"provider_url": provider_url},
            )

    async def validate_token(self, token: str | bytes) -> User:
        """Validate JWT bearer token and extract user claims.

        Args:
            token: JWT bearer token from Authorization header (str or bytes)

        Returns:
            User object with claims from token

        Raises:
            InvalidTokenError: If token is invalid, expired, or signature fails
            MissingClaimError: If required claim is missing
            AuthenticationError: If OIDC provider is unreachable
        """
        # Check token cache first
        token_hash = self._hash_token(token)
        cached = self._get_cached_token(token_hash)
        if cached:
            logger.debug("Token cache hit", extra={"token_hash": token_hash[:16]})
            return cached.user

        # Decode token without verification first to get claims
        try:
            # Decode header to get kid (key ID)
            header = self._decode_header(token)
            kid = header.get("kid")

            if self.skip_verification:
                # DANGEROUS: Skip signature verification (dev mode only)
                claims = jwt.decode(token, None, claims_options={"verify_signature": False})
                claims = dict(claims)  # Convert to dict
            else:
                # Fetch JWKS and verify signature
                jwks = await self._get_jwks()
                if not jwks:
                    raise InvalidTokenError("Unable to fetch OIDC provider public keys")

                # Find the right key
                if kid and kid in jwks.keys:
                    key_data = jwks.keys[kid]
                else:
                    # Fallback: try all keys if kid not specified or not found
                    key_data = next(iter(jwks.keys.values())) if jwks.keys else None

                if not key_data:
                    raise InvalidTokenError(f"No matching key found for kid: {kid}")

                # Verify signature and decode
                claims = jwt.decode(
                    token,
                    key_data,
                    claims_options={
                        "iss": {"essential": True, "value": self.provider_url},
                        "aud": {"essential": True, "value": self.audience},
                        "exp": {"essential": True},
                    },
                )
                claims = dict(claims)  # Convert to dict

            # Validate expiry with clock skew
            exp = claims.get("exp")
            if not exp:
                raise MissingClaimError("Token missing 'exp' claim")

            now = time.time()
            if now > exp + CLOCK_SKEW_SECONDS:
                raise InvalidTokenError("Token expired")

            # Extract user claims
            user = self._extract_user_claims(claims)

            # Cache the validated token
            await self._cache_token(token_hash, user, exp)

            logger.info(
                "Token validated successfully",
                extra={
                    "sub": user.sub,
                    "role": user.role,
                    "token_hash": token_hash[:16],
                },
            )

            return user

        except JoseError as e:
            logger.warning(
                "JWT validation failed",
                extra={"error": str(e), "token_hash": token_hash[:16]},
            )
            raise InvalidTokenError(f"Invalid JWT token: {e}") from e
        except (InvalidTokenError, MissingClaimError) as e:
            logger.warning(
                "JWT validation failed",
                extra={"error": str(e), "token_hash": token_hash[:16]},
            )
            raise

    def _decode_header(self, token: str | bytes) -> dict[str, Any]:
        """Decode JWT header without verification.

        Args:
            token: JWT token (str or bytes)

        Returns:
            Header dict

        Raises:
            InvalidTokenError: If header is malformed
        """
        try:
            # Convert bytes to string if needed
            if isinstance(token, bytes):
                token = token.decode("utf-8")

            # JWT format: header.payload.signature
            parts = token.split(".")
            if len(parts) != 3:
                raise InvalidTokenError("Invalid JWT format")

            # Decode header (base64url decode)
            # Add proper padding if needed
            header_b64 = parts[0]
            padding = (4 - len(header_b64) % 4) % 4
            header_b64 += "=" * padding
            header_bytes = base64.urlsafe_b64decode(header_b64)
            return json.loads(header_bytes)
        except Exception as e:
            raise InvalidTokenError(f"Failed to decode JWT header: {e}") from e

    def _extract_user_claims(self, claims: dict[str, Any]) -> User:
        """Extract user information from JWT claims.

        Args:
            claims: Decoded JWT claims

        Returns:
            User object

        Raises:
            MissingClaimError: If required claim is missing
        """
        sub = claims.get("sub")
        if not sub:
            raise MissingClaimError("Token missing 'sub' claim")

        email = claims.get("email")
        name = claims.get("name")

        # Extract role from custom claim or default
        # Common patterns: roles, role, groups, custom claim
        role = claims.get("role") or claims.get("https://routeros-mcp/role") or "read_only"
        if isinstance(role, list):
            # Take first role if multiple
            role = role[0] if role else "read_only"

        # Validate role against allowed roles
        allowed_roles = {"read_only", "ops_rw", "admin"}
        if role not in allowed_roles:
            logger.warning(
                "Invalid role claim value, defaulting to read_only",
                extra={"role": role, "sub": sub},
            )
            role = "read_only"

        # Extract device scope if present
        device_scope = claims.get("device_scope") or claims.get("https://routeros-mcp/devices")
        if device_scope is None:
            pass
        elif isinstance(device_scope, str):
            # Convert comma-separated string to list
            device_scope = [d.strip() for d in device_scope.split(",") if d.strip()]
        elif isinstance(device_scope, list):
            # Ensure all elements are strings
            if all(isinstance(d, str) for d in device_scope):
                device_scope = [d.strip() for d in device_scope if d.strip()]
            else:
                logger.warning(
                    "device_scope claim contains non-string elements; ignoring device_scope",
                    extra={"sub": sub},
                )
                device_scope = None
        else:
            logger.warning(
                "device_scope claim has invalid type; ignoring device_scope",
                extra={"type": type(device_scope).__name__, "sub": sub},
            )
            device_scope = None

        return User(
            sub=sub,
            email=email,
            role=role,
            device_scope=device_scope,
            name=name,
        )

    async def _get_jwks(self) -> CachedJWKS | None:
        """Get JWKS from cache or fetch from OIDC provider.

        Returns:
            Cached JWKS or None if fetch fails
        """
        # Check cache first (read without lock for performance)
        if self._jwks_cache and time.time() < self._jwks_cache.expires_at:
            logger.debug("JWKS cache hit")
            return self._jwks_cache

        # Acquire lock for fetching
        async with self._jwks_lock:
            # Double-check cache after acquiring lock
            if self._jwks_cache and time.time() < self._jwks_cache.expires_at:
                return self._jwks_cache

            # Fetch from OIDC discovery endpoint
            try:
                # First get OIDC configuration
                discovery_url = f"{self.provider_url}/.well-known/openid-configuration"
                client = self._http_client or httpx.AsyncClient()

                try:
                    logger.debug("Fetching OIDC discovery", extra={"url": discovery_url})
                    response = await client.get(discovery_url, timeout=10.0)
                    response.raise_for_status()
                    config = response.json()

                    jwks_uri = config.get("jwks_uri")
                    if not jwks_uri:
                        raise AuthenticationError("OIDC discovery missing jwks_uri")

                    # Fetch JWKS
                    logger.debug("Fetching JWKS", extra={"url": jwks_uri})
                    jwks_response = await client.get(jwks_uri, timeout=10.0)
                    jwks_response.raise_for_status()
                    jwks_data = jwks_response.json()

                    # Parse and cache keys
                    keys = {}
                    for key_data in jwks_data.get("keys", []):
                        kid = key_data.get("kid")
                        if kid:
                            # Parse key with authlib
                            keys[kid] = JsonWebKey.import_key(key_data)

                    # Validate that at least one key was imported
                    if not keys:
                        raise AuthenticationError(
                            "OIDC provider returned empty keys array in JWKS response"
                        )

                    # Cache for 1 hour
                    self._jwks_cache = CachedJWKS(
                        keys=keys, expires_at=time.time() + JWKS_CACHE_TTL_SECONDS
                    )

                    logger.info(
                        "JWKS fetched and cached",
                        extra={"key_count": len(keys), "ttl_seconds": JWKS_CACHE_TTL_SECONDS},
                    )

                    return self._jwks_cache

                finally:
                    if not self._http_client:
                        await client.aclose()

            except httpx.HTTPError as e:
                logger.error(
                    "Failed to fetch JWKS from OIDC provider",
                    extra={"error": str(e), "provider_url": self.provider_url},
                )
                # Return stale cache if available (graceful degradation)
                if self._jwks_cache:
                    logger.warning("Using stale JWKS cache due to fetch failure")
                    return self._jwks_cache
                return None
            except Exception as e:
                logger.error(
                    "Unexpected error fetching JWKS",
                    extra={"error": str(e), "provider_url": self.provider_url},
                )
                # Return stale cache if available
                if self._jwks_cache:
                    logger.warning("Using stale JWKS cache due to unexpected error")
                    return self._jwks_cache
                return None

    def _hash_token(self, token: str | bytes) -> str:
        """Hash token for cache key (don't store plaintext).

        Args:
            token: JWT token (str or bytes)

        Returns:
            SHA256 hash of token
        """
        # Handle both str and bytes
        token_bytes = token if isinstance(token, bytes) else token.encode()
        return hashlib.sha256(token_bytes).hexdigest()

    def _get_cached_token(self, token_hash: str) -> CachedToken | None:
        """Get cached token if valid.

        Args:
            token_hash: Hashed token

        Returns:
            Cached token or None if expired/missing
        """
        cached = self._token_cache.get(token_hash)
        if not cached:
            return None

        # Check if expired
        if time.time() >= cached.expires_at:
            # Don't modify cache here to avoid race conditions
            # Cleanup will be done in _cache_token
            return None

        return cached

    async def _cache_token(self, token_hash: str, user: User, exp: float) -> None:
        """Cache validated token result.

        Args:
            token_hash: Hashed token
            user: Validated user
            exp: Token expiry timestamp
        """
        # Cache for min(token expiry, 5 minutes)
        cache_until = min(exp, time.time() + TOKEN_CACHE_TTL_SECONDS)

        async with self._token_cache_lock:
            self._token_cache[token_hash] = CachedToken(user=user, expires_at=cache_until)

            # Cleanup expired entries (simple strategy)
            await self._cleanup_token_cache()

    async def _cleanup_token_cache(self) -> None:
        """Remove expired tokens from cache.

        Note: This method should be called with _token_cache_lock held.
        """
        now = time.time()
        expired = [k for k, v in self._token_cache.items() if now >= v.expires_at]
        for k in expired:
            del self._token_cache[k]


# ========================================
# OAuth 2.1 Authorization Code Flow (PKCE)
# ========================================


@dataclass
class PKCEParams:
    """PKCE (Proof Key for Code Exchange) parameters for OAuth 2.1 Authorization Code flow.

    Attributes:
        verifier: Random code verifier (43-128 characters, base64url-encoded)
        challenge: SHA256 hash of verifier, base64url-encoded
        challenge_method: Always "S256" for SHA256 hashing
    """

    verifier: str
    challenge: str
    challenge_method: str = "S256"


def generate_pkce_verifier(length: int = 43) -> str:
    """Generate a cryptographically secure PKCE code verifier.

    Per RFC 7636 Section 4.1:
    - Length must be 43-128 characters
    - Characters must be unreserved: [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~"
    - Uses base64url encoding without padding

    Args:
        length: Length of verifier (43-128 characters). Default is 43 (minimum).

    Returns:
        Cryptographically secure random code verifier string

    Raises:
        ValueError: If length is not in range [43, 128]

    Example:
        verifier = generate_pkce_verifier()
        # Returns something like: "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    """
    if not 43 <= length <= 128:
        raise ValueError("PKCE verifier length must be between 43 and 128 characters")

    # Use cryptographically secure random bytes (per RFC 7636)
    import secrets

    random_bytes = secrets.token_bytes(length)

    # Base64url encode and remove padding
    verifier = base64.urlsafe_b64encode(random_bytes).rstrip(b"=").decode("ascii")

    # Truncate to requested length
    return verifier[:length]


def generate_pkce_challenge(verifier: str) -> str:
    """Generate PKCE code challenge from verifier using SHA256.

    Per RFC 7636 Section 4.2:
    - challenge = BASE64URL(SHA256(ASCII(verifier)))
    - No padding (trailing '=' removed)

    Args:
        verifier: PKCE code verifier string

    Returns:
        Base64url-encoded SHA256 hash of verifier (no padding)

    Example:
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        challenge = generate_pkce_challenge(verifier)
        # Returns: "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    """
    # Hash the verifier with SHA256
    verifier_bytes = verifier.encode("ascii")
    challenge_bytes = hashlib.sha256(verifier_bytes).digest()

    # Base64url encode and remove padding
    challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode("ascii")

    return challenge


def generate_pkce_params(verifier_length: int = 43) -> PKCEParams:
    """Generate complete PKCE parameter set (verifier + challenge).

    Convenience function that generates both verifier and challenge.

    Args:
        verifier_length: Length of code verifier (43-128). Default is 43.

    Returns:
        PKCEParams with verifier, challenge, and challenge_method

    Example:
        pkce = generate_pkce_params()
        print(pkce.verifier)   # Random 43-char string
        print(pkce.challenge)  # SHA256 hash of verifier
        print(pkce.challenge_method)  # "S256"
    """
    verifier = generate_pkce_verifier(verifier_length)
    challenge = generate_pkce_challenge(verifier)
    return PKCEParams(verifier=verifier, challenge=challenge, challenge_method="S256")


def build_authorization_url(
    issuer: str,
    client_id: str,
    redirect_uri: str,
    scope: str = "openid profile email",
    state: str | None = None,
    pkce_challenge: str | None = None,
    pkce_challenge_method: str = "S256",
    **extra_params: Any,
) -> str:
    """Build OAuth 2.1 authorization URL with PKCE support.

    Constructs the authorization endpoint URL per OAuth 2.1 spec with PKCE.

    Args:
        issuer: OIDC issuer URL (e.g., "https://auth0.example.com")
        client_id: OAuth client ID
        redirect_uri: OAuth callback URL (e.g., "http://localhost:8080/api/auth/callback")
        scope: Space-separated OAuth scopes (default: "openid profile email")
        state: CSRF protection state parameter (randomly generated if not provided)
        pkce_challenge: PKCE code challenge (auto-generated if not provided)
        pkce_challenge_method: PKCE challenge method (default: "S256")
        **extra_params: Additional query parameters to include

    Returns:
        Complete authorization URL with all parameters

    Example:
        url = build_authorization_url(
            issuer="https://auth.example.com",
            client_id="my-client-id",
            redirect_uri="http://localhost:8080/callback",
            scope="openid profile email",
        )
        # Returns: "https://auth.example.com/authorize?response_type=code&..."
    """
    from urllib.parse import urlencode, urljoin

    # Generate state if not provided (CSRF protection)
    if state is None:
        import secrets

        state = secrets.token_urlsafe(32)

    # Generate PKCE challenge if not provided
    if pkce_challenge is None:
        pkce_params = generate_pkce_params()
        pkce_challenge = pkce_params.challenge
        # Store verifier in session/cookie for later use in token exchange
        # (caller is responsible for this)

    # Build query parameters per OAuth 2.1 spec
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": pkce_challenge,
        "code_challenge_method": pkce_challenge_method,
        **extra_params,
    }

    # Construct authorization endpoint URL
    # Per OIDC discovery spec, authorization endpoint is at /authorize
    authorization_endpoint = urljoin(issuer.rstrip("/") + "/", "authorize")

    # Build full URL with query parameters
    query_string = urlencode(params)
    return f"{authorization_endpoint}?{query_string}"
