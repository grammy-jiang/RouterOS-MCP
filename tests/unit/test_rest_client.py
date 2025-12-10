"""Tests for RouterOS REST client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from routeros_mcp.infra.routeros.rest_client import RouterOSRestClient
from routeros_mcp.infra.routeros.exceptions import (
    RouterOSAuthenticationError,
    RouterOSAuthorizationError,
    RouterOSClientError,
    RouterOSNetworkError,
    RouterOSNotFoundError,
    RouterOSServerError,
    RouterOSTimeoutError,
    RouterOSValidationError,
)


class TestRouterOSRestClient:
    """Tests for RouterOSRestClient class."""
    
    def test_client_initialization(self) -> None:
        """Test client initialization with default parameters."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )
        
        assert client.host == "127.0.0.1"
        assert client.port == 443
        assert client.username == "admin"
        assert client.password == "secret"
        assert client.max_retries == 3
        assert client.base_url == "https://127.0.0.1:443"
        
    def test_client_initialization_custom_port(self) -> None:
        """Test client initialization with custom port."""
        client = RouterOSRestClient(
            host="127.0.0.2",
            port=8443,
            username="admin",
            password="secret",
        )
        
        assert client.port == 8443
        assert client.base_url == "https://127.0.0.2:8443"
        
    def test_set_credentials(self) -> None:
        """Test setting credentials after initialization."""
        client = RouterOSRestClient(host="127.0.0.1")
        
        assert client.username is None
        assert client.password is None
        
        client.set_credentials("newuser", "newpass")
        
        assert client.username == "newuser"
        assert client.password == "newpass"
        
    @pytest.mark.asyncio
    async def test_successful_get_request(self) -> None:
        """Test successful GET request."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"cpu-load": 10}'
        mock_response.json.return_value = {"cpu-load": 10}
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            result = await client.get("/rest/system/resource")
            
            assert result == {"cpu-load": 10}
            mock_client.request.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_successful_post_request(self) -> None:
        """Test successful POST request."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"status": "ok"}'
        mock_response.json.return_value = {"status": "ok"}
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            result = await client.post("/rest/tool/ping", {"address": "8.8.8.8"})
            
            assert result == {"status": "ok"}
            
    @pytest.mark.asyncio
    async def test_empty_response_handling(self) -> None:
        """Test handling of empty response."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.content = b''
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            result = await client.delete("/rest/ip/address/123")
            
            assert result == {}
            
    @pytest.mark.asyncio
    async def test_401_authentication_error(self) -> None:
        """Test that 401 response raises RouterOSAuthenticationError."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="wrong",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid credentials"
        mock_response.json.side_effect = ValueError()
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            with pytest.raises(RouterOSAuthenticationError, match="Authentication failed"):
                await client.get("/rest/system/resource")
                
    @pytest.mark.asyncio
    async def test_403_authorization_error(self) -> None:
        """Test that 403 response raises RouterOSAuthorizationError."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="readonly",
            password="secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Access denied"
        mock_response.json.side_effect = ValueError()
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            with pytest.raises(RouterOSAuthorizationError, match="Authorization denied"):
                await client.patch("/rest/system/identity", {"name": "test"})
                
    @pytest.mark.asyncio
    async def test_404_not_found_error(self) -> None:
        """Test that 404 response raises RouterOSNotFoundError."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Resource not found"
        mock_response.json.side_effect = ValueError()
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            with pytest.raises(RouterOSNotFoundError, match="Resource not found"):
                await client.get("/rest/nonexistent/resource")
                
    @pytest.mark.asyncio
    async def test_400_validation_error(self) -> None:
        """Test that 400 response raises RouterOSValidationError."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid parameters"
        mock_response.json.side_effect = ValueError()
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            with pytest.raises(RouterOSValidationError, match="Validation error"):
                await client.post("/rest/tool/ping", {"invalid": "param"})
                
    @pytest.mark.asyncio
    async def test_500_server_error(self) -> None:
        """Test that 500 response raises RouterOSServerError."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_response.json.side_effect = ValueError()
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            with pytest.raises(RouterOSServerError, match="Server error"):
                await client.get("/rest/system/resource")
                
    @pytest.mark.asyncio
    async def test_timeout_with_retries(self) -> None:
        """Test that timeout triggers retries and eventually raises RouterOSTimeoutError."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
            max_retries=3,
        )
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.TimeoutException("Timeout")
            mock_get_client.return_value = mock_client
            
            with pytest.raises(RouterOSTimeoutError, match="Request timeout"):
                await client.get("/rest/system/resource")
                
            # Should have retried 3 times
            assert mock_client.request.call_count == 3
            
    @pytest.mark.asyncio
    async def test_network_error_with_retries(self) -> None:
        """Test that network error triggers retries."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
            max_retries=3,
        )
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.NetworkError("Connection refused")
            mock_get_client.return_value = mock_client
            
            with pytest.raises(RouterOSNetworkError, match="Network error"):
                await client.get("/rest/system/resource")
                
            # Should have retried 3 times
            assert mock_client.request.call_count == 3
            
    @pytest.mark.asyncio
    async def test_invalid_json_response(self) -> None:
        """Test handling of invalid JSON response."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'not valid json'
        mock_response.text = 'not valid json'
        mock_response.json.side_effect = ValueError("Invalid JSON")
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            with pytest.raises(RouterOSClientError, match="Invalid JSON response"):
                await client.get("/rest/system/resource")
                
    @pytest.mark.asyncio
    async def test_successful_retry_after_transient_error(self) -> None:
        """Test that client succeeds after transient error."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
            max_retries=3,
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"status": "ok"}'
        mock_response.json.return_value = {"status": "ok"}
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            # First call fails, second succeeds
            mock_client.request.side_effect = [
                httpx.TimeoutException("Timeout"),
                mock_response,
            ]
            mock_get_client.return_value = mock_client
            
            result = await client.get("/rest/system/resource")
            
            assert result == {"status": "ok"}
            assert mock_client.request.call_count == 2
            
    @pytest.mark.asyncio
    async def test_client_methods(self) -> None:
        """Test all HTTP method wrappers."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"result": "ok"}'
        mock_response.json.return_value = {"result": "ok"}
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            # Test all methods
            await client.get("/path")
            await client.post("/path", {"data": "value"})
            await client.put("/path", {"data": "value"})
            await client.patch("/path", {"data": "value"})
            await client.delete("/path")
            
            assert mock_client.request.call_count == 5
            
    @pytest.mark.asyncio
    async def test_close_client(self) -> None:
        """Test closing the client."""
        client = RouterOSRestClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )
        
        # Initialize internal client
        mock_httpx_client = AsyncMock()
        client._client = mock_httpx_client
        
        await client.close()
        
        mock_httpx_client.aclose.assert_called_once()
        assert client._client is None
