"""Tests for RouterOS SSH client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import asyncssh
import pytest

from routeros_mcp.infra.routeros.exceptions import (
    RouterOSSSHAuthenticationError,
    RouterOSSSHCommandNotAllowedError,
    RouterOSSSHError,
    RouterOSSSHTimeoutError,
)
from routeros_mcp.infra.routeros.ssh_client import (
    ALLOWED_SSH_COMMANDS,
    RouterOSSSHClient,
)


class TestRouterOSSSHClient:
    """Tests for RouterOSSSHClient class."""

    def test_client_initialization(self) -> None:
        """Test client initialization with default parameters."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        assert client.host == "127.0.0.1"
        assert client.port == 22
        assert client.username == "admin"
        assert client.password == "secret"
        assert client.timeout_seconds == 60.0
        assert client.max_retries == 3

    def test_client_initialization_custom_port(self) -> None:
        """Test client initialization with custom port."""
        client = RouterOSSSHClient(
            host="127.0.0.2",
            port=2222,
            username="admin",
            password="secret",
        )

        assert client.port == 2222

    def test_set_credentials(self) -> None:
        """Test setting credentials after initialization."""
        client = RouterOSSSHClient(host="127.0.0.1")

        assert client.username is None
        assert client.password is None

        client.set_credentials("newuser", "newpass")

        assert client.username == "newuser"
        assert client.password == "newpass"

    def test_allowed_commands_constant(self) -> None:
        """Test that ALLOWED_SSH_COMMANDS contains expected commands."""
        assert "/export" in ALLOWED_SSH_COMMANDS
        assert "/export compact" in ALLOWED_SSH_COMMANDS
        assert "/system/resource/print" in ALLOWED_SSH_COMMANDS
        assert "/system/package/print" in ALLOWED_SSH_COMMANDS
        assert "/system/clock/print" in ALLOWED_SSH_COMMANDS
        assert "/system/identity/print" in ALLOWED_SSH_COMMANDS
        assert "/interface/print" in ALLOWED_SSH_COMMANDS
        assert "/ip/address/print" in ALLOWED_SSH_COMMANDS
        assert "/ip/arp/print" in ALLOWED_SSH_COMMANDS
        assert "/ip/firewall/filter/print" in ALLOWED_SSH_COMMANDS
        assert "/ip/firewall/nat/print" in ALLOWED_SSH_COMMANDS
        assert "/ip/firewall/address-list/print" in ALLOWED_SSH_COMMANDS
        assert "/log/print" in ALLOWED_SSH_COMMANDS
        assert "/system/logging/print" in ALLOWED_SSH_COMMANDS
        assert "/ip/route/print" in ALLOWED_SSH_COMMANDS
        assert "/ip/dns/print" in ALLOWED_SSH_COMMANDS
        assert "/system/ntp/client/print" in ALLOWED_SSH_COMMANDS
        assert "/ip/dns/cache/print" in ALLOWED_SSH_COMMANDS
        assert "/interface/monitor-traffic" in ALLOWED_SSH_COMMANDS
        assert "/ping" in ALLOWED_SSH_COMMANDS
        assert "/tool/ping" in ALLOWED_SSH_COMMANDS
        assert "/tool/traceroute" in ALLOWED_SSH_COMMANDS
        assert len(ALLOWED_SSH_COMMANDS) == 22

    @pytest.mark.asyncio
    async def test_validate_command_whitelisted(self) -> None:
        """Test that whitelisted commands pass validation."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
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
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        with pytest.raises(RouterOSSSHCommandNotAllowedError, match="SSH command not allowed"):
            client._validate_command("/ip address print")

    @pytest.mark.asyncio
    async def test_validate_command_with_whitespace(self) -> None:
        """Test that commands with leading/trailing whitespace are normalized."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        # These should not raise (whitespace normalized)
        client._validate_command("  /export  ")
        client._validate_command("\n/export compact\n")

    @pytest.mark.asyncio
    async def test_validate_command_parameterized_monitor_traffic(self) -> None:
        """Test that parameterized monitor-traffic commands are allowed.

        /interface/monitor-traffic is a one-off command that requires
        an interface name and 'once' parameter to return a single snapshot
        instead of continuous output.
        """
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        # These should not raise - parameterized monitor-traffic with 'once' argument
        client._validate_command("/interface/monitor-traffic ether1 once")
        client._validate_command("/interface/monitor-traffic ether2 once")
        client._validate_command("/interface/monitor-traffic bridge1 once")

    @pytest.mark.asyncio
    async def test_validate_command_base_parameterized_allowed(self) -> None:
        """Test that base parameterized commands without args are also allowed."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        # Base command without parameters should also be allowed
        # (even though in practice we use it with parameters)
        client._validate_command("/interface/monitor-traffic")

    @pytest.mark.asyncio
    async def test_validate_command_similar_but_not_whitelisted(self) -> None:
        """Test that similar but different commands are rejected."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        with pytest.raises(RouterOSSSHCommandNotAllowedError):
            client._validate_command("/ip address print")  # Different command

        with pytest.raises(RouterOSSSHCommandNotAllowedError):
            client._validate_command("/interface show")  # Wrong subcommand

    @pytest.mark.asyncio
    async def test_successful_command_execution(self) -> None:
        """Test successful command execution."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        mock_result = MagicMock()
        mock_result.stdout = "# RouterOS config\n/system identity set name=test"

        mock_connection = AsyncMock()
        mock_connection.run.return_value = mock_result
        mock_connection.is_closed.return_value = False

        with patch.object(client, "_get_connection", return_value=mock_connection):
            result = await client.execute("/export compact")

            assert result == "# RouterOS config\n/system identity set name=test"
            mock_connection.run.assert_called_once_with("/export compact", check=True)

    @pytest.mark.asyncio
    async def test_command_execution_with_bytes_output(self) -> None:
        """Test command execution with bytes stdout."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        mock_result = MagicMock()
        mock_result.stdout = b"# RouterOS config"

        mock_connection = AsyncMock()
        mock_connection.run.return_value = mock_result
        mock_connection.is_closed.return_value = False

        with patch.object(client, "_get_connection", return_value=mock_connection):
            result = await client.execute("/export compact")

            assert result == "# RouterOS config"

    @pytest.mark.asyncio
    async def test_command_execution_with_empty_output(self) -> None:
        """Test command execution with empty/None stdout."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        mock_result = MagicMock()
        mock_result.stdout = None

        mock_connection = AsyncMock()
        mock_connection.run.return_value = mock_result
        mock_connection.is_closed.return_value = False

        with patch.object(client, "_get_connection", return_value=mock_connection):
            result = await client.execute("/export compact")

            assert result == ""

    @pytest.mark.asyncio
    async def test_command_timeout(self) -> None:
        """Test that command timeout raises RouterOSSSHTimeoutError."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
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

        with (
            patch.object(
                client,
                "_get_connection",
                return_value=mock_connection,
            ),
            pytest.raises(RouterOSSSHTimeoutError, match="SSH command timeout"),
        ):
            await client.execute("/export compact")

    @pytest.mark.asyncio
    async def test_command_execution_error(self) -> None:
        """Test that command execution error raises RouterOSSSHError."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
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

        with (
            patch.object(
                client,
                "_get_connection",
                return_value=mock_connection,
            ),
            pytest.raises(RouterOSSSHError, match="SSH command failed.*exit code 1"),
        ):
            await client.execute("/export compact")

    @pytest.mark.asyncio
    async def test_connection_retry_on_failure(self, monkeypatch) -> None:
        """Test that connection retries on failure."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
            max_retries=3,
        )

        # First two attempts fail, third succeeds
        mock_connection = AsyncMock()
        mock_connection.is_closed.return_value = False

        call_count = 0

        async def mock_connect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection refused")
            return mock_connection

        import routeros_mcp.infra.routeros.ssh_client as ssh_module

        monkeypatch.setattr(ssh_module.asyncssh, "connect", mock_connect)

        connection = await client._get_connection()

        assert connection == mock_connection
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_authentication_error(self, monkeypatch) -> None:
        """Test that authentication error raises RouterOSSSHAuthenticationError."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="wrong",
        )

        async def mock_connect(*args, **kwargs):
            raise asyncssh.PermissionDenied("Authentication failed")

        import routeros_mcp.infra.routeros.ssh_client as ssh_module

        monkeypatch.setattr(ssh_module.asyncssh, "connect", mock_connect)

        with pytest.raises(RouterOSSSHAuthenticationError, match="SSH authentication failed"):
            await client._get_connection()

    @pytest.mark.asyncio
    async def test_connection_reuse(self) -> None:
        """Test that connection is reused if still open."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        mock_connection = MagicMock()
        mock_connection.is_closed = MagicMock(return_value=False)

        client._connection = mock_connection

        connection = await client._get_connection()

        assert connection == mock_connection
        # Connection is reused, no new connection created

    @pytest.mark.asyncio
    async def test_connection_recreation_if_closed(self, monkeypatch) -> None:
        """Test that connection is recreated if closed."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        old_connection = AsyncMock()
        # Use sync is_closed to avoid un-awaited coroutine warnings
        old_connection.is_closed = MagicMock(return_value=True)
        client._connection = old_connection

        new_connection = AsyncMock()
        new_connection.is_closed.return_value = False

        async def mock_connect(*args, **kwargs):
            return new_connection

        import routeros_mcp.infra.routeros.ssh_client as ssh_module

        monkeypatch.setattr(ssh_module.asyncssh, "connect", mock_connect)

        connection = await client._get_connection()

        assert connection == new_connection

    @pytest.mark.asyncio
    async def test_close_connection(self) -> None:
        """Test closing the connection."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        mock_connection = MagicMock()
        mock_connection.is_closed = MagicMock(return_value=False)
        mock_connection.close = MagicMock()
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
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        mock_result = MagicMock()
        mock_result.stdout = "# config"

        mock_connection = AsyncMock()
        mock_connection.run.return_value = mock_result
        mock_connection.is_closed.return_value = False

        with patch.object(client, "_get_connection", return_value=mock_connection):
            result = await client.export_config(compact=True)

            assert result == "# config"
            mock_connection.run.assert_called_once_with("/export compact", check=True)

    @pytest.mark.asyncio
    async def test_export_config_full(self) -> None:
        """Test export_config with full format."""
        client = RouterOSSSHClient(
            host="127.0.0.1",
            username="admin",
            password="secret",
        )

        mock_result = MagicMock()
        mock_result.stdout = "# full config"

        mock_connection = AsyncMock()
        mock_connection.run.return_value = mock_result
        mock_connection.is_closed.return_value = False

        with patch.object(client, "_get_connection", return_value=mock_connection):
            result = await client.export_config(compact=False)

            assert result == "# full config"
            mock_connection.run.assert_called_once_with("/export", check=True)

    @pytest.mark.asyncio
    async def test_credentials_required_for_connection(self) -> None:
        """Test that credentials are required before creating connection."""
        client = RouterOSSSHClient(host="127.0.0.1")

        with pytest.raises(ValueError, match="Credentials not set"):
            await client._get_connection()
