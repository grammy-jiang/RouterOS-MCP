"""Tests for RouterOS SSH client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import asyncssh
import pytest

from routeros_mcp.infra.routeros.ssh_client import (
    ALLOWED_SSH_COMMANDS,
    RouterOSSSHClient,
)
from routeros_mcp.infra.routeros.exceptions import (
    RouterOSSSHAuthenticationError,
    RouterOSSSHCommandNotAllowedError,
    RouterOSSSHError,
    RouterOSSSHTimeoutError,
)


class TestRouterOSSSHClient:
    """Tests for RouterOSSSHClient class."""
    
    def test_client_initialization(self) -> None:
        """Test client initialization with default parameters."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        assert client.host == "router.example.com"
        assert client.port == 22
        assert client.username == "admin"
        assert client.password == "secret"
        assert client.timeout_seconds == 60.0
        assert client.max_retries == 3
        
    def test_client_initialization_custom_port(self) -> None:
        """Test client initialization with custom port."""
        client = RouterOSSSHClient(
            host="router2.example.com",
            port=2222,
            username="admin",
            password="secret",
        )
        
        assert client.port == 2222
        
    def test_set_credentials(self) -> None:
        """Test setting credentials after initialization."""
        client = RouterOSSSHClient(host="router.example.com")
        
        assert client.username is None
        assert client.password is None
        
        client.set_credentials("newuser", "newpass")
        
        assert client.username == "newuser"
        assert client.password == "newpass"
        
    def test_allowed_commands_constant(self) -> None:
        """Test that ALLOWED_SSH_COMMANDS contains expected commands."""
        assert "/export" in ALLOWED_SSH_COMMANDS
        assert "/export compact" in ALLOWED_SSH_COMMANDS
        assert len(ALLOWED_SSH_COMMANDS) == 2
        
    @pytest.mark.asyncio
    async def test_validate_command_whitelisted(self) -> None:
        """Test that whitelisted commands pass validation."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        # These should not raise
        client._validate_command("/export")
        client._validate_command("/export compact")
        
    @pytest.mark.asyncio
    async def test_validate_command_not_whitelisted(self) -> None:
        """Test that non-whitelisted commands fail validation."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        with pytest.raises(RouterOSSSHCommandNotAllowedError, match="SSH command not allowed"):
            client._validate_command("/ip address print")
            
    @pytest.mark.asyncio
    async def test_validate_command_with_whitespace(self) -> None:
        """Test that commands with leading/trailing whitespace are normalized."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        # These should not raise (whitespace normalized)
        client._validate_command("  /export  ")
        client._validate_command("\n/export compact\n")
        
    @pytest.mark.asyncio
    async def test_validate_command_similar_but_not_whitelisted(self) -> None:
        """Test that similar but different commands are rejected."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        with pytest.raises(RouterOSSSHCommandNotAllowedError):
            client._validate_command("/export verbose")
            
        with pytest.raises(RouterOSSSHCommandNotAllowedError):
            client._validate_command("/export  compact")  # Two spaces
            
    @pytest.mark.asyncio
    async def test_successful_command_execution(self) -> None:
        """Test successful command execution."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        mock_result = MagicMock()
        mock_result.stdout = "# RouterOS config\n/system identity set name=test"
        
        mock_connection = AsyncMock()
        mock_connection.run.return_value = mock_result
        mock_connection.is_closed.return_value = False
        
        with patch.object(client, '_get_connection', return_value=mock_connection):
            result = await client.execute("/export compact")
            
            assert result == "# RouterOS config\n/system identity set name=test"
            mock_connection.run.assert_called_once_with("/export compact", check=True)
            
    @pytest.mark.asyncio
    async def test_command_execution_with_bytes_output(self) -> None:
        """Test command execution with bytes stdout."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        mock_result = MagicMock()
        mock_result.stdout = b"# RouterOS config"
        
        mock_connection = AsyncMock()
        mock_connection.run.return_value = mock_result
        mock_connection.is_closed.return_value = False
        
        with patch.object(client, '_get_connection', return_value=mock_connection):
            result = await client.execute("/export compact")
            
            assert result == "# RouterOS config"
            
    @pytest.mark.asyncio
    async def test_command_execution_with_empty_output(self) -> None:
        """Test command execution with empty/None stdout."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        mock_result = MagicMock()
        mock_result.stdout = None
        
        mock_connection = AsyncMock()
        mock_connection.run.return_value = mock_result
        mock_connection.is_closed.return_value = False
        
        with patch.object(client, '_get_connection', return_value=mock_connection):
            result = await client.execute("/export compact")
            
            assert result == ""
            
    @pytest.mark.asyncio
    async def test_command_timeout(self) -> None:
        """Test that command timeout raises RouterOSSSHTimeoutError."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
            timeout_seconds=1.0,
        )
        
        mock_connection = AsyncMock()
        # Simulate timeout
        async def slow_run(*args, **kwargs):
            await asyncio.sleep(10)
            
        mock_connection.run = slow_run
        mock_connection.is_closed.return_value = False
        
        with patch.object(client, '_get_connection', return_value=mock_connection):
            with pytest.raises(RouterOSSSHTimeoutError, match="SSH command timeout"):
                await client.execute("/export compact")
                
    @pytest.mark.asyncio
    async def test_command_execution_error(self) -> None:
        """Test that command execution error raises RouterOSSSHError."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        mock_connection = AsyncMock()
        error = asyncssh.ProcessError(
            env="",
            command="/export compact",
            subsystem="",
            exit_status=1,
            exit_signal=None,
            returncode=1,
            stdout="",
            stderr="Error: command failed",
        )
        mock_connection.run.side_effect = error
        mock_connection.is_closed.return_value = False
        
        with patch.object(client, '_get_connection', return_value=mock_connection):
            with pytest.raises(RouterOSSSHError, match="SSH command failed.*exit code 1"):
                await client.execute("/export compact")
                
    @pytest.mark.asyncio
    async def test_connection_retry_on_failure(self) -> None:
        """Test that connection retries on failure."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
            max_retries=3,
        )
        
        with patch('asyncssh.connect') as mock_connect:
            # First two attempts fail, third succeeds
            mock_connection = AsyncMock()
            mock_connection.is_closed.return_value = False
            
            mock_connect.side_effect = [
                Exception("Connection refused"),
                Exception("Connection refused"),
                mock_connection,
            ]
            
            connection = await client._get_connection()
            
            assert connection == mock_connection
            assert mock_connect.call_count == 3
            
    @pytest.mark.asyncio
    async def test_authentication_error(self) -> None:
        """Test that authentication error raises RouterOSSSHAuthenticationError."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="wrong",
        )
        
        with patch('asyncssh.connect') as mock_connect:
            mock_connect.side_effect = asyncssh.PermissionDenied("Authentication failed")
            
            with pytest.raises(RouterOSSSHAuthenticationError, match="SSH authentication failed"):
                await client._get_connection()
                
    @pytest.mark.asyncio
    async def test_connection_reuse(self) -> None:
        """Test that connection is reused if still open."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        mock_connection = AsyncMock()
        mock_connection.is_closed.return_value = False
        
        client._connection = mock_connection
        
        connection = await client._get_connection()
        
        assert connection == mock_connection
        
    @pytest.mark.asyncio
    async def test_connection_recreation_if_closed(self) -> None:
        """Test that connection is recreated if closed."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        old_connection = AsyncMock()
        old_connection.is_closed.return_value = True
        client._connection = old_connection
        
        new_connection = AsyncMock()
        new_connection.is_closed.return_value = False
        
        with patch('asyncssh.connect', return_value=new_connection):
            connection = await client._get_connection()
            
            assert connection == new_connection
            assert connection != old_connection
            
    @pytest.mark.asyncio
    async def test_close_connection(self) -> None:
        """Test closing the connection."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        mock_connection = AsyncMock()
        mock_connection.is_closed.return_value = False
        mock_connection.wait_closed = AsyncMock()
        client._connection = mock_connection
        
        await client.close()
        
        mock_connection.close.assert_called_once()
        mock_connection.wait_closed.assert_called_once()
        assert client._connection is None
        
    @pytest.mark.asyncio
    async def test_export_config_compact(self) -> None:
        """Test export_config with compact format."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        mock_result = MagicMock()
        mock_result.stdout = "# config"
        
        mock_connection = AsyncMock()
        mock_connection.run.return_value = mock_result
        mock_connection.is_closed.return_value = False
        
        with patch.object(client, '_get_connection', return_value=mock_connection):
            result = await client.export_config(compact=True)
            
            assert result == "# config"
            mock_connection.run.assert_called_once_with("/export compact", check=True)
            
    @pytest.mark.asyncio
    async def test_export_config_full(self) -> None:
        """Test export_config with full format."""
        client = RouterOSSSHClient(
            host="router.example.com",
            username="admin",
            password="secret",
        )
        
        mock_result = MagicMock()
        mock_result.stdout = "# full config"
        
        mock_connection = AsyncMock()
        mock_connection.run.return_value = mock_result
        mock_connection.is_closed.return_value = False
        
        with patch.object(client, '_get_connection', return_value=mock_connection):
            result = await client.export_config(compact=False)
            
            assert result == "# full config"
            mock_connection.run.assert_called_once_with("/export", check=True)
            
    @pytest.mark.asyncio
    async def test_credentials_required_for_connection(self) -> None:
        """Test that credentials are required before creating connection."""
        client = RouterOSSSHClient(host="router.example.com")
        
        with pytest.raises(ValueError, match="Credentials not set"):
            await client._get_connection()
