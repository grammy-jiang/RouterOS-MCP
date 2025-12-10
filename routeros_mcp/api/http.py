"""HTTP API for RouterOS MCP Service.

Provides REST API for admin operations and integrates OAuth/OIDC
authentication for HTTP/SSE transport.

See docs/02-security-oauth-integration-and-access-control.md for
detailed requirements.
"""

import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from authlib.integrations.starlette_client import OAuth
from authlib.jose import jwt
from authlib.jose.errors import JoseError

from routeros_mcp.config import Settings
from routeros_mcp.infra.observability import get_metrics_text, record_auth_check
from routeros_mcp.infra.observability.logging import get_correlation_id, set_correlation_id

logger = logging.getLogger(__name__)


class OIDCValidator:
    """OIDC token validator for HTTP transport authentication."""

    def __init__(self, settings: Settings) -> None:
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

    async def validate_token(self, token: str) -> dict[str, Any]:
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
                    "aud": {
                        "essential": True,
                        "value": self.settings.oidc_audience,
                    }
                    if self.settings.oidc_audience
                    else {},
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
            )

        except Exception as e:
            logger.error(f"Error validating token: {e}", exc_info=True)
            record_auth_check(success=False)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token validation error",
            )


def get_validator(settings: Settings = Depends()) -> OIDCValidator:
    """Factory for OIDCValidator with injected settings."""
    return OIDCValidator(settings)


async def get_current_user(
    request: Request,
    settings: Settings = Depends(),
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


def create_http_app(settings: Settings) -> FastAPI:
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

    # Middleware for correlation ID
    @app.middleware("http")
    async def correlation_id_middleware(
        request: Request, call_next: Any
    ) -> Any:
        """Add correlation ID to request context."""
        correlation_id = request.headers.get("X-Correlation-ID", get_correlation_id())
        set_correlation_id(correlation_id)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict[str, Any]:
        """Health check endpoint.

        Returns:
            Service health status
        """
        return {
            "status": "healthy",
            "environment": settings.environment,
            "transport": settings.mcp_transport,
        }

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

    return app


__all__ = [
    "OIDCValidator",
    "get_current_user",
    "create_http_app",
]
