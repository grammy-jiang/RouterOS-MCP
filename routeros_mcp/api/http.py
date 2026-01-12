"""HTTP API for RouterOS MCP Service.

Provides REST API for admin operations and integrates OAuth/OIDC
authentication for HTTP/SSE transport.

See docs/02-security-oauth-integration-and-access-control.md for
detailed requirements.
"""

import logging
import time
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from authlib.integrations.starlette_client import OAuth
from authlib.jose import jwt
from authlib.jose.errors import JoseError

from routeros_mcp.config import Settings
from routeros_mcp.infra.observability import get_metrics_text, record_auth_check
from routeros_mcp.infra.observability.logging import get_correlation_id, set_correlation_id
from routeros_mcp.security.auth import AuthenticationError

logger = logging.getLogger(__name__)


def get_settings() -> Settings:  # pragma: no cover
    """Dependency to get application settings.

    Returns:
        Settings instance.
    """
    return Settings()


class OIDCValidator:
    """OIDC token validator for HTTP transport authentication."""

    def __init__(self, settings: Settings) -> None:  # pragma: no cover
        """Initialize OIDC validator.

        Args:
            settings: Application settings with OIDC configuration
        """
        self.settings = settings
        self.oauth = OAuth()

        if settings.oidc_enabled:
            # Register OIDC provider
            self.oauth.register(
                name="oidc",
                client_id=settings.oidc_client_id,
                client_secret=settings.oidc_client_secret,
                server_metadata_url=f"{settings.oidc_issuer}/.well-known/openid-configuration",
                client_kwargs={"scope": "openid profile email"},
            )

    async def validate_token(self, token: str) -> dict[str, Any]:  # pragma: no cover
        """Validate OIDC access token.

        Args:
            token: JWT access token

        Returns:
            Decoded token claims

        Raises:
            HTTPException: If token is invalid
        """
        if not self.settings.oidc_enabled:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OIDC authentication not enabled",
            )

        try:
            # Get OIDC discovery document
            metadata = await self.oauth.oidc.load_server_metadata()

            # Get JWKS
            jwks = metadata.get("jwks")
            if not jwks:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="OIDC JWKS not available",
                )

            # Verify and decode token
            claims = jwt.decode(
                token,
                jwks,
                claims_options={
                    "iss": {"essential": True, "value": self.settings.oidc_issuer},
                    "aud": (
                        {
                            "essential": True,
                            "value": self.settings.oidc_audience,
                        }
                        if self.settings.oidc_audience
                        else {}
                    ),
                },
            )

            logger.info(
                "Token validated successfully",
                extra={
                    "sub": claims.get("sub"),
                    "email": claims.get("email"),
                },
            )

            record_auth_check(success=True)
            return claims

        except JoseError as e:
            logger.warning(f"Token validation failed: {e}")
            record_auth_check(success=False)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
            ) from e

        except Exception as e:
            logger.error(f"Error validating token: {e}", exc_info=True)
            record_auth_check(success=False)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token validation error",
            ) from e


def get_validator(settings: Settings = Depends(get_settings)) -> OIDCValidator:  # pragma: no cover
    """Factory for OIDCValidator with injected settings."""
    return OIDCValidator(settings)


async def get_current_user(  # pragma: no cover
    request: Request,
    settings: Settings = Depends(get_settings),
    validator: OIDCValidator = Depends(get_validator),
) -> dict[str, Any]:
    """Extract and validate user from request.

    Args:
        request: HTTP request
        settings: Application settings
        validator: OIDC validator

    Returns:
        User context with claims

    Raises:
        HTTPException: If authentication fails
    """
    # Skip auth if OIDC not enabled (for development)
    if not settings.oidc_enabled:
        return {
            "sub": "anonymous",
            "email": "anonymous@localhost",
            "role": "admin",  # Default role for dev
        }

    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:]  # Remove "Bearer " prefix

    # Validate token
    claims = await validator.validate_token(token)

    # Extract user info
    user_context = {
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "name": claims.get("name"),
        "role": claims.get("role", "read_only"),  # Default role
    }

    return user_context


def create_http_app(settings: Settings) -> FastAPI:  # pragma: no cover
    """Create FastAPI application for HTTP API.

    Args:
        settings: Application settings

    Returns:
        FastAPI application
    """
    app = FastAPI(
        title="RouterOS MCP Service",
        description="HTTP API for RouterOS management via MCP",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount admin routes
    from routeros_mcp.api.admin import router as admin_router

    app.include_router(admin_router)

    # Mount static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Middleware for correlation ID
    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next: Any) -> Any:
        """Add correlation ID to request context."""
        correlation_id = request.headers.get("X-Correlation-ID", get_correlation_id())
        set_correlation_id(correlation_id)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict[str, Any]:
        """Health check endpoint for load balancer integration.

        Checks:
        - Database connectivity
        - Redis connectivity (if enabled)
        - OIDC provider reachability (if enabled)
        - Service shutdown state

        Returns:
            Service health status with component details

        Status Codes:
            200 OK: Service ready or degraded (non-critical components down)
            503 Service Unavailable: Service shutting down
        """
        from routeros_mcp.infra.health import HealthChecker, HealthStatus
        from routeros_mcp.infra.db.session import get_session_manager

        # Get database engine for health checker
        try:
            manager = get_session_manager(settings)
            db_engine = manager.engine if manager._engine else None
        except RuntimeError:
            db_engine = None

        # Create health checker
        checker = HealthChecker(settings, db_engine=db_engine)

        # Check if we're shutting down (set by signal handler)
        if getattr(app.state, "_is_shutting_down", False):
            checker.set_shutdown()

        # Perform health check
        result = await checker.check_health()

        # Return 503 if shutting down
        if result.status == HealthStatus.SHUTDOWN:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=result.to_dict(),
            )

        # Return 200 for ready or degraded
        return result.to_dict()

    # Metrics endpoint (Prometheus format)
    @app.get("/metrics")
    async def metrics() -> PlainTextResponse:
        """Prometheus metrics endpoint.

        Returns:
            Metrics in Prometheus text format
        """
        return PlainTextResponse(get_metrics_text())

    # User info endpoint (authenticated)
    @app.get("/api/user")
    async def get_user_info(
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        """Get current user information.

        Args:
            user: Current user from token

        Returns:
            User information
        """
        return {
            "sub": user.get("sub"),
            "email": user.get("email"),
            "name": user.get("name"),
            "role": user.get("role"),
        }

    # OAuth 2.1 Authorization Code Flow endpoints
    @app.get("/api/auth/login")
    async def login(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
        """Initiate OAuth 2.1 Authorization Code flow with PKCE.

        This endpoint starts the OAuth login flow by:
        1. Generating PKCE parameters (verifier + challenge)
        2. Building authorization URL with PKCE challenge
        3. Returning the URL for client to redirect to

        Note: This is a stub implementation for Phase 5.1.
        Full implementation will include:
        - Session/cookie storage for PKCE verifier and state
        - Callback endpoint for authorization code exchange
        - Token exchange with PKCE verifier

        Returns:
            JSON with authorization URL and state parameter

        Raises:
            HTTPException: If OIDC is not configured
        """
        from routeros_mcp.security.oidc import build_authorization_url, generate_pkce_params

        # Verify OIDC is enabled
        if not settings.oidc_enabled:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="OAuth authentication not enabled. Set oidc_enabled=true in configuration.",
            )

        # Verify required OIDC config
        issuer = settings.oidc_issuer or settings.oidc_provider_url
        if not issuer or not settings.oidc_client_id or not settings.oidc_redirect_uri:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth not properly configured. Missing issuer, client_id, or redirect_uri.",
            )

        # Generate PKCE parameters
        pkce = generate_pkce_params()

        # Build authorization URL
        auth_url, state = build_authorization_url(
            issuer=issuer,
            client_id=settings.oidc_client_id,
            redirect_uri=settings.oidc_redirect_uri,
            scope=settings.oidc_scopes,
            pkce_challenge=pkce.challenge,
            pkce_challenge_method=pkce.challenge_method,
        )

        # TODO: Store PKCE verifier and state in session for later verification
        # This will be implemented in Phase 5.2 (callback endpoint)

        logger.info(
            "OAuth login initiated",
            extra={
                "issuer": issuer,
                "client_id": settings.oidc_client_id,
                "redirect_uri": settings.oidc_redirect_uri,
            },
        )

        return {
            "authorization_url": auth_url,
            "state": state,
            "message": "Redirect user to authorization_url to complete login",
        }

    @app.get("/api/auth/callback")
    async def callback(
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        """Handle OAuth 2.1 Authorization Code callback.

        This endpoint handles the callback from OIDC provider after user authorization.
        It exchanges the authorization code for tokens and creates a user session.

        Query Parameters:
            code: Authorization code from OIDC provider
            state: CSRF state token (should match the one from login)
            error: Optional error code from provider
            error_description: Optional error description from provider

        Returns:
            JSON with user session information and tokens

        Raises:
            HTTPException: If callback fails (invalid code, state mismatch, etc.)
        """
        # Verify OIDC is enabled
        if not settings.oidc_enabled:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="OAuth authentication not enabled.",
            )

        # Check for error response from provider
        if error:
            logger.error(
                "OAuth callback error",
                extra={"error": error, "description": error_description},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"OAuth error: {error} - {error_description or 'No description'}",
            )

        # Verify required parameters
        if not code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing authorization code in callback",
            )

        if not state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing state parameter in callback",
            )

        # CSRF protection: we currently do not have server-side storage to
        # validate the `state` parameter generated during the login flow.
        # To avoid a false sense of security and prevent CSRF vulnerabilities,
        # we reject all callbacks until proper state validation is implemented.
        logger.error(
            "OAuth callback received but state validation is not implemented",
            extra={"state": state[:16] if state else None},
        )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "OAuth callback state validation not implemented. "
                "Session-backed state storage is required to prevent CSRF attacks. "
                "Login is temporarily disabled until this is implemented."
            ),
        )

    @app.post("/api/auth/refresh")
    async def refresh(
        refresh_token: str = Body(..., embed=True),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        """Refresh access token using refresh token.

        This endpoint exchanges a refresh token for a new access token.

        Request Body (JSON):
            refresh_token: Refresh token from login

        Returns:
            JSON with new access token and optional new refresh token

        Raises:
            HTTPException: If refresh fails (invalid token, expired, etc.)
        """
        from routeros_mcp.security.oidc import refresh_access_token

        # Verify OIDC is enabled
        if not settings.oidc_enabled:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="OAuth authentication not enabled.",
            )

        # Get OIDC config
        issuer = settings.oidc_issuer or settings.oidc_provider_url
        if not issuer or not settings.oidc_client_id or not settings.oidc_client_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth not properly configured.",
            )

        try:
            # Refresh the access token
            tokens = await refresh_access_token(
                issuer=issuer,
                client_id=settings.oidc_client_id,
                client_secret=settings.oidc_client_secret,
                refresh_token=refresh_token,
            )

            # Calculate new expiry
            expires_in = tokens.get("expires_in")
            expires_at = time.time() + expires_in if expires_in else None

            logger.info("Token refresh successful")

            return {
                "success": True,
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token", refresh_token),
                "expires_at": expires_at,
                "message": "Token refreshed successfully",
            }

        except AuthenticationError as e:
            logger.error("Token refresh failed", extra={"error": str(e)})
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token refresh failed: {str(e)}",
            ) from e
        except Exception as e:
            logger.error("Unexpected error in refresh", extra={"error": str(e)}, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token refresh failed",
            ) from e

    @app.post("/api/auth/logout")
    async def logout(
        access_token: str | None = Body(None),
        refresh_token: str | None = Body(None),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        """Logout and revoke tokens.

        This endpoint revokes access and refresh tokens at the OIDC provider.

        Request Body (JSON):
            access_token: Optional access token to revoke
            refresh_token: Optional refresh token to revoke

        Returns:
            JSON with logout confirmation

        Raises:
            HTTPException: If logout fails
        """
        from routeros_mcp.security.oidc import revoke_tokens

        # Verify OIDC is enabled
        if not settings.oidc_enabled:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="OAuth authentication not enabled.",
            )

        # Get OIDC config
        issuer = settings.oidc_issuer or settings.oidc_provider_url
        if not issuer or not settings.oidc_client_id or not settings.oidc_client_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth not properly configured.",
            )

        try:
            # Revoke both tokens if provided
            if access_token:
                await revoke_tokens(
                    issuer=issuer,
                    client_id=settings.oidc_client_id,
                    client_secret=settings.oidc_client_secret,
                    token=access_token,
                    token_type_hint="access_token",
                )

            if refresh_token:
                await revoke_tokens(
                    issuer=issuer,
                    client_id=settings.oidc_client_id,
                    client_secret=settings.oidc_client_secret,
                    token=refresh_token,
                    token_type_hint="refresh_token",
                )

            logger.info("Logout successful")

            return {
                "success": True,
                "message": "Logout successful, tokens revoked",
            }

        except AuthenticationError as e:
            # Token revocation failures are not critical for logout
            # Some providers don't support revocation
            logger.warning("Token revocation failed during logout", extra={"error": str(e)})
            return {
                "success": True,
                "message": "Logout successful (token revocation not supported by provider)",
            }
        except Exception as e:
            logger.error("Unexpected error in logout", extra={"error": str(e)}, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Logout failed",
            ) from e

    # Cache management endpoint
    @app.post("/api/devices/{device_id}/refresh-cache")
    async def refresh_device_cache(
        device_id: str,
        settings: Settings = Depends(get_settings),
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        """Refresh Redis cache for a device.

        This endpoint invalidates all cached resource data (interfaces, IPs, routes)
        for the specified device. The next request for device resources will fetch
        fresh data from the device and repopulate the cache.

        Args:
            device_id: Device identifier
            settings: Application settings
            user: Current authenticated user

        Returns:
            Cache refresh status with number of invalidated keys

        Raises:
            HTTPException: If cache refresh fails or device not found
        """
        if not settings.redis_cache_enabled:
            return {
                "success": False,
                "message": "Redis cache is not enabled",
                "invalidated_keys": 0,
            }

        try:
            # Validate device exists before invalidating cache
            from routeros_mcp.infra.db.session import get_session
            from routeros_mcp.domain.services.device import DeviceService

            async with get_session() as session:
                device_service = DeviceService(session, settings)
                # This will raise DeviceNotFoundError if device doesn't exist
                await device_service.get_device(device_id)

            # Now invalidate the cache
            from routeros_mcp.infra.cache import get_redis_cache

            cache = get_redis_cache()
            invalidated = await cache.invalidate_device(device_id)

            logger.info(
                f"Cache refreshed for device: {device_id}",
                extra={
                    "device_id": device_id,
                    "invalidated_keys": invalidated,
                    "user": user.get("sub"),
                },
            )

            return {
                "success": True,
                "message": f"Cache invalidated for device {device_id}",
                "invalidated_keys": invalidated,
            }

        except RuntimeError as e:
            logger.warning(f"Cache not initialized: {e}")
            return {
                "success": False,
                "message": "Cache not initialized",
                "invalidated_keys": 0,
            }
        except Exception as e:
            logger.error(
                f"Cache refresh failed for device {device_id}",
                extra={"device_id": device_id, "error": str(e)},
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Cache refresh failed: {str(e)}",
            ) from e

    return app


__all__ = [
    "OIDCValidator",
    "get_current_user",
    "create_http_app",
]
