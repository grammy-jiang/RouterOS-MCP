"""Authentication middleware for HTTP transport.

Implements Starlette middleware to:
- Extract Bearer token from Authorization header
- Validate token via OIDCValidator
- Attach user to request.state.user
- Return 401 Unauthorized on invalid token

See docs/02-security-oauth-integration-and-access-control.md for design.
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from routeros_mcp.security.auth import AuthenticationError, extract_bearer_token
from routeros_mcp.security.oidc import OIDCValidator

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware for OIDC token authentication.

    Validates JWT tokens on all requests (except health endpoint) and
    attaches user to request.state.user.

    Example:
        app = Starlette()
        validator = OIDCValidator(...)
        app.add_middleware(AuthMiddleware, validator=validator)
    """

    def __init__(self, app, validator: OIDCValidator, exempt_paths: list[str] | None = None):
        """Initialize auth middleware.

        Args:
            app: Starlette application
            validator: OIDC token validator
            exempt_paths: List of paths to exempt from authentication (e.g., ["/health"])
        """
        super().__init__(app)
        self.validator = validator
        self.exempt_paths = exempt_paths or ["/health", "/mcp/health"]

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with authentication.

        Args:
            request: HTTP request
            call_next: Next middleware/handler

        Returns:
            HTTP response
        """
        # Skip auth for exempt paths
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        try:
            # Extract bearer token
            auth_header = request.headers.get("Authorization")
            token = extract_bearer_token(auth_header)

            # Validate token and get user
            user = await self.validator.validate_token(token)

            # Attach user to request state
            request.state.user = user

            logger.debug(
                "Request authenticated",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "user_sub": user.sub,
                    "user_role": user.role,
                },
            )

            # Proceed to next handler
            return await call_next(request)

        except AuthenticationError as e:
            logger.warning(
                "Authentication failed",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "error": str(e),
                },
            )
            # Return 401 Unauthorized without exposing token details
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "message": "Invalid or missing authentication token",
                },
            )
