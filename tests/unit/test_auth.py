"""Tests for authentication module."""

import pytest

from routeros_mcp.security.auth import (
    AuthenticationError,
    User,
    extract_bearer_token,
    get_phase1_user,
)


class TestUser:
    """Tests for User dataclass."""
    
    def test_user_creation(self) -> None:
        """Test creating a User instance."""
        user = User(
            sub="user-123",
            email="test@example.com",
            role="admin",
            device_scope=["device-1", "device-2"],
            name="Test User",
        )
        
        assert user.sub == "user-123"
        assert user.email == "test@example.com"
        assert user.role == "admin"
        assert user.device_scope == ["device-1", "device-2"]
        assert user.name == "Test User"
        
    def test_user_with_minimal_fields(self) -> None:
        """Test creating a User with minimal fields."""
        user = User(
            sub="user-456",
            email=None,
            role="read_only",
        )
        
        assert user.sub == "user-456"
        assert user.email is None
        assert user.role == "read_only"
        assert user.device_scope is None
        assert user.name is None


class TestGetPhase1User:
    """Tests for get_phase1_user function."""
    
    def test_returns_admin_user(self) -> None:
        """Test that get_phase1_user returns an admin user."""
        user = get_phase1_user()
        
        assert user.sub == "phase1-admin"
        assert user.role == "admin"
        assert user.device_scope is None  # Full access
        assert user.email is None
        assert "Phase 1" in user.name
        
    def test_returns_same_user_each_time(self) -> None:
        """Test that get_phase1_user returns consistent data."""
        user1 = get_phase1_user()
        user2 = get_phase1_user()
        
        assert user1.sub == user2.sub
        assert user1.role == user2.role


class TestExtractBearerToken:
    """Tests for extract_bearer_token function."""
    
    def test_extract_valid_bearer_token(self) -> None:
        """Test extracting a valid bearer token."""
        header = "Bearer abc123xyz"
        token = extract_bearer_token(header)
        
        assert token == "abc123xyz"
        
    def test_extract_bearer_token_case_insensitive(self) -> None:
        """Test that 'Bearer' prefix is case-insensitive."""
        headers = [
            "Bearer token123",
            "bearer token123",
            "BEARER token123",
            "BeArEr token123",
        ]
        
        for header in headers:
            token = extract_bearer_token(header)
            assert token == "token123"
            
    def test_missing_authorization_header(self) -> None:
        """Test that missing header raises AuthenticationError."""
        with pytest.raises(AuthenticationError, match="Missing Authorization header"):
            extract_bearer_token(None)
            
    def test_malformed_header_no_bearer_prefix(self) -> None:
        """Test that header without 'Bearer' prefix raises error."""
        with pytest.raises(AuthenticationError, match="Invalid Authorization header format"):
            extract_bearer_token("Token abc123")
            
    def test_malformed_header_missing_token(self) -> None:
        """Test that header with only 'Bearer' raises error."""
        with pytest.raises(AuthenticationError, match="Invalid Authorization header format"):
            extract_bearer_token("Bearer")
            
    def test_malformed_header_extra_parts(self) -> None:
        """Test that header with extra parts raises error."""
        with pytest.raises(AuthenticationError, match="Invalid Authorization header format"):
            extract_bearer_token("Bearer token1 token2 token3")
            
    def test_empty_string_header(self) -> None:
        """Test that empty string raises error."""
        with pytest.raises(AuthenticationError, match="Missing Authorization header"):
            extract_bearer_token("")
            
    def test_whitespace_only_header(self) -> None:
        """Test that whitespace-only header raises error."""
        with pytest.raises(AuthenticationError, match="Invalid Authorization header format"):
            extract_bearer_token("   ")
            
    def test_bearer_token_with_special_characters(self) -> None:
        """Test extracting token with special characters."""
        header = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        token = extract_bearer_token(header)
        
        assert token.startswith("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
