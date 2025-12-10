"""Authentication module for OAuth/OIDC integration (Phase 4).

This module provides OAuth 2.1 / OIDC authentication scaffolding:
- Token validation
- User model
- Claims extraction

Phase 1: Placeholder implementation (OS-level auth only)
Phase 4: Full OAuth/OIDC integration with Authlib

See docs/02-security-oauth-integration-and-access-control.md for design.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Base exception for authentication failures."""

    pass


class InvalidTokenError(AuthenticationError):
    """Raised when JWT token is invalid or expired."""

    pass


class MissingClaimError(AuthenticationError):
    """Raised when required claim is missing from token."""

    pass


@dataclass
class User:
    """User identity from OAuth/OIDC token.

    Phase 1: Minimal implementation with hardcoded admin user
    Phase 4: Full implementation with actual OIDC claims

    Attributes:
        sub: OIDC subject (unique user ID)
        email: User's email address
        role: User's role (read_only/ops_rw/admin)
        device_scope: Optional list of allowed device IDs
        name: Optional display name
    """

    sub: str
    email: str | None
    role: str
    device_scope: list[str] | None = None
    name: str | None = None


class OIDCTokenValidator:
    """OAuth/OIDC token validator (Phase 4).

    Phase 1: Not implemented
    Phase 4: Validates JWT tokens from OIDC provider

    Example (Phase 4):
        validator = OIDCTokenValidator(settings)
        user = await validator.validate_token(bearer_token)
    """

    def __init__(
        self,
        issuer: str,
        client_id: str,
        client_secret: str,
        audience: str | None = None,
    ) -> None:
        """Initialize OIDC validator.

        Args:
            issuer: OIDC issuer URL
            client_id: OAuth client ID
            client_secret: OAuth client secret
            audience: Expected token audience

        Note:
            Phase 1: Raises NotImplementedError
            Phase 4: Full implementation with Authlib
        """
        raise NotImplementedError(
            "OIDC authentication not implemented in Phase 1. "
            "Phase 1 uses OS-level authentication (stdio transport). "
            "OAuth/OIDC support will be added in Phase 4 with HTTP transport."
        )

    async def validate_token(self, token: str) -> User:
        """Validate bearer token and extract user claims.

        Args:
            token: JWT bearer token from Authorization header

        Returns:
            User object with claims

        Raises:
            InvalidTokenError: If token is invalid or expired
            MissingClaimError: If required claim is missing

        Note:
            Phase 1: Not implemented
            Phase 4: Full JWT validation
        """
        raise NotImplementedError("See __init__ for details")


def get_phase1_user() -> User:
    """Get implicit admin user for Phase 1.

    Phase 1 uses OS-level authentication with stdio transport.
    The user who can run the MCP server has implicit admin privileges.

    Returns:
        User object with admin role

    Example:
        user = get_phase1_user()
        # Use for audit logging in Phase 1
    """
    return User(
        sub="phase1-admin",
        email=None,
        role="admin",
        device_scope=None,  # Full access
        name="Phase 1 Admin (OS-level auth)",
    )


def extract_bearer_token(authorization_header: str | None) -> str:
    """Extract bearer token from Authorization header.

    Args:
        authorization_header: HTTP Authorization header value

    Returns:
        Bearer token string

    Raises:
        AuthenticationError: If header is missing or malformed

    Example (Phase 4):
        token = extract_bearer_token(request.headers.get("Authorization"))
        user = await validator.validate_token(token)
    """
    if not authorization_header:
        raise AuthenticationError("Missing Authorization header")

    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError("Invalid Authorization header format. Expected: Bearer <token>")

    return parts[1]
