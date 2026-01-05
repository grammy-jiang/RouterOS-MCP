"""Tests for authentication middleware."""

from unittest.mock import AsyncMock, Mock

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

from routeros_mcp.security.auth import AuthenticationError, InvalidTokenError, User
from routeros_mcp.mcp.transport.auth_middleware import AuthMiddleware
from routeros_mcp.security.oidc import OIDCValidator


class TestAuthMiddleware:
    """Tests for AuthMiddleware."""

    @pytest.fixture
    def mock_validator(self):
        """Create mock OIDC validator."""
        validator = Mock(spec=OIDCValidator)
        validator.validate_token = AsyncMock()
        return validator

    @pytest.fixture
    def test_app(self, mock_validator):
        """Create test Starlette app with auth middleware."""

        async def protected_endpoint(request: Request) -> Response:
            """Protected endpoint that requires auth."""
            user = getattr(request.state, "user", None)
            if user:
                return Response(
                    content=f"Hello {user.sub}",
                    status_code=200,
                )
            return Response(content="No user", status_code=500)

        async def health_endpoint(request: Request) -> Response:
            """Health endpoint (exempt from auth)."""
            return Response(content="OK", status_code=200)

        app = Starlette(
            routes=[
                Route("/api/protected", protected_endpoint, methods=["GET"]),
                Route("/health", health_endpoint, methods=["GET"]),
                Route("/mcp/health", health_endpoint, methods=["GET"]),
            ]
        )

        # Add auth middleware
        app.add_middleware(
            AuthMiddleware,
            validator=mock_validator,
            exempt_paths=["/health", "/mcp/health"],
        )

        return app

    def test_exempt_path_no_auth_required(self, test_app, mock_validator):
        """Test exempt paths don't require authentication."""
        client = TestClient(test_app)

        response = client.get("/health")

        assert response.status_code == 200
        assert response.text == "OK"
        # Validator should not be called
        mock_validator.validate_token.assert_not_called()

    def test_exempt_path_with_base_path(self, test_app, mock_validator):
        """Test exempt paths with base path work."""
        client = TestClient(test_app)

        response = client.get("/mcp/health")

        assert response.status_code == 200
        assert response.text == "OK"
        mock_validator.validate_token.assert_not_called()

    def test_protected_path_valid_token(self, test_app, mock_validator):
        """Test protected path with valid token succeeds."""
        # Mock successful validation
        user = User(sub="user-123", email="test@example.com", role="admin")
        mock_validator.validate_token.return_value = user

        client = TestClient(test_app)
        response = client.get(
            "/api/protected",
            headers={"Authorization": "Bearer valid-token"},
        )

        assert response.status_code == 200
        assert "user-123" in response.text
        mock_validator.validate_token.assert_called_once_with("valid-token")

    def test_protected_path_missing_auth_header(self, test_app, mock_validator):
        """Test protected path without auth header returns 401."""
        # Mock extract_bearer_token raising error
        mock_validator.validate_token.side_effect = AuthenticationError(
            "Missing Authorization header"
        )

        client = TestClient(test_app)
        response = client.get("/api/protected")

        assert response.status_code == 401
        assert response.json() == {
            "error": "unauthorized",
            "message": "Missing or invalid Authorization header",
        }

    def test_protected_path_invalid_token(self, test_app, mock_validator):
        """Test protected path with invalid token returns 401."""
        # Mock validation failure
        mock_validator.validate_token.side_effect = InvalidTokenError("Invalid JWT token")

        client = TestClient(test_app)
        response = client.get(
            "/api/protected",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401
        assert response.json() == {
            "error": "unauthorized",
            "message": "Invalid token",
        }

    def test_protected_path_malformed_header(self, test_app, mock_validator):
        """Test protected path with malformed auth header returns 401."""
        mock_validator.validate_token.side_effect = AuthenticationError(
            "Invalid Authorization header format"
        )

        client = TestClient(test_app)
        response = client.get(
            "/api/protected",
            headers={"Authorization": "Token abc123"},
        )

        assert response.status_code == 401

    def test_user_attached_to_request_state(self, test_app, mock_validator):
        """Test that user is attached to request.state."""
        user = User(
            sub="user-456",
            email="test2@example.com",
            role="ops_rw",
            device_scope=["dev-1"],
        )
        mock_validator.validate_token.return_value = user

        client = TestClient(test_app)
        response = client.get(
            "/api/protected",
            headers={"Authorization": "Bearer valid-token"},
        )

        assert response.status_code == 200
        # Response should contain user.sub
        assert "user-456" in response.text

    def test_custom_exempt_paths(self, mock_validator):
        """Test custom exempt paths configuration."""

        async def endpoint(request: Request) -> Response:
            return Response(content="OK")

        app = Starlette(
            routes=[
                Route("/custom/exempt", endpoint, methods=["GET"]),
                Route("/api/protected", endpoint, methods=["GET"]),
            ]
        )

        # Add middleware with custom exempt paths
        app.add_middleware(
            AuthMiddleware,
            validator=mock_validator,
            exempt_paths=["/custom/exempt"],
        )

        client = TestClient(app)

        # Custom exempt path should not require auth
        response = client.get("/custom/exempt")
        assert response.status_code == 200
        mock_validator.validate_token.assert_not_called()

        # Other paths should require auth
        mock_validator.validate_token.side_effect = AuthenticationError("No token")
        response = client.get("/api/protected")
        assert response.status_code == 401

    def test_multiple_requests_same_token(self, test_app, mock_validator):
        """Test multiple requests with same token."""
        user = User(sub="user-123", email="test@example.com", role="admin")
        mock_validator.validate_token.return_value = user

        client = TestClient(test_app)

        # First request
        response1 = client.get(
            "/api/protected",
            headers={"Authorization": "Bearer same-token"},
        )
        assert response1.status_code == 200

        # Second request with same token
        response2 = client.get(
            "/api/protected",
            headers={"Authorization": "Bearer same-token"},
        )
        assert response2.status_code == 200

        # Validator should be called twice (no caching in middleware)
        assert mock_validator.validate_token.call_count == 2

    def test_invalid_bearer_format(self, test_app, mock_validator):
        """Test malformed bearer token format returns 401."""
        mock_validator.validate_token.side_effect = AuthenticationError(
            "Invalid Authorization header format"
        )

        client = TestClient(test_app)
        response = client.get(
            "/api/protected",
            headers={"Authorization": "InvalidFormat token123"},
        )

        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"
        assert "Authorization" in response.json()["message"]

    def test_expired_token(self, test_app, mock_validator):
        """Test expired token returns 401 with correct error."""
        mock_validator.validate_token.side_effect = InvalidTokenError("Token expired")

        client = TestClient(test_app)
        response = client.get(
            "/api/protected",
            headers={"Authorization": "Bearer expired-token"},
        )

        assert response.status_code == 401
        assert response.json() == {
            "error": "unauthorized",
            "message": "Invalid token",
        }

    def test_token_validation_network_timeout(self, test_app, mock_validator):
        """Test network timeout during token validation returns 401."""
        # Simulate OIDC provider timeout
        mock_validator.validate_token.side_effect = AuthenticationError("OIDC provider unreachable")

        client = TestClient(test_app)
        response = client.get(
            "/api/protected",
            headers={"Authorization": "Bearer valid-token"},
        )

        # Should fail closed (return 401)
        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"

    def test_concurrent_token_validation(self, test_app, mock_validator):
        """Test concurrent requests with same token are handled correctly."""
        user = User(sub="user-123", email="test@example.com", role="admin")
        mock_validator.validate_token.return_value = user

        client = TestClient(test_app)

        # Multiple concurrent requests (in test client they're sequential)
        responses = []
        for _ in range(5):
            response = client.get(
                "/api/protected",
                headers={"Authorization": "Bearer same-token"},
            )
            responses.append(response)

        # All should succeed
        for response in responses:
            assert response.status_code == 200

        # Validator should be called for each request
        # (caching happens inside validator, not middleware)
        assert mock_validator.validate_token.call_count == 5
