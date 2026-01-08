"""RouterOS SSH client with tightly-scoped command whitelisting.

Provides minimal SSH/CLI access to RouterOS devices for operations
that cannot be done via REST API. All commands must be whitelisted.

Design principles:
- Minimize SSH usage (prefer REST API)
- Strict command whitelist (fail-safe: deny by default)
- No arbitrary command execution
- Connection pooling and retries
- Comprehensive error mapping

Whitelisted commands:
- /export (configuration export)
- /export compact (compact configuration export)
- /export hide-sensitive (redacted configuration export)
- /export hide-sensitive compact (redacted compact configuration export)

See docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md
"""

import asyncio
import logging
from typing import Final

import asyncssh

from routeros_mcp.infra.routeros.exceptions import (
    RouterOSSSHAuthenticationError,
    RouterOSSSHCommandNotAllowedError,
    RouterOSSSHError,
    RouterOSSSHTimeoutError,
)

logger = logging.getLogger(__name__)

# Whitelisted SSH commands (fail-safe: deny by default)
ALLOWED_SSH_COMMANDS: Final[set[str]] = {
    "/export",  # Full configuration export
    "/export compact",  # Compact configuration export
    "/export hide-sensitive",  # Redacted configuration export
    "/export hide-sensitive compact",  # Redacted compact configuration export
    "/system/resource/print",  # Read-only health probe (standard format: key: value)
    "/system/package/print",  # Package listing (standard table format)
    "/system/clock/print",  # Clock info (standard format: key: value)
    "/system/identity/print",  # Identity (standard format: key: value)
    "/interface/print",  # Interface listing (standard table format)
    "/ip/address/print",  # IP address listing (standard table format)
    "/ip/arp/print",  # ARP table (standard table format)
    "/ip/firewall/filter/print",  # Firewall filter rules (standard table format)
    "/ip/firewall/nat/print",  # NAT rules (standard table format)
    "/ip/firewall/address-list/print",  # Address lists (standard table format)
    "/log/print",  # System logs (standard table format)
    "/system/logging/print",  # Logging configuration (standard table format)
    "/ip/route/print",  # Routing table (standard table format)
    "/ip/dns/print",  # DNS configuration (standard format: key: value)
    "/system/ntp/client/print",  # NTP configuration (standard format: key: value)
    "/ip/dns/cache/print",  # DNS cache (all formats: table, as-value, detail, with/without-paging)
    "/interface/bridge/print",  # Bridge configuration (standard table format with multi-line detail)
    "/interface/bridge/port/print",  # Bridge port assignments (standard table format)
    "/ip/dhcp-server/print",  # DHCP server configuration (standard table format)
    "/ip/dhcp-server/lease/print",  # DHCP leases (standard table format)
    "/interface/monitor-traffic",  # Interface traffic statistics (with 'once' parameter)
    "/interface/wireless/print",  # Wireless interface listing (legacy wireless package)
    "/interface/wifi/print",  # WiFi interface listing (RouterOS v7 WiFi package)
    "/interface/wireless/registration-table/print",  # Connected wireless clients (legacy wireless)
    "/interface/wifi/registration-table/print",  # Connected WiFi clients (RouterOS v7 WiFi package)
    "/caps-man/remote-cap/print",  # CAPsMAN-managed CAP devices (APs)
    "/ping",  # ICMP ping
    "/tool/ping",  # ICMP ping via tool
    "/tool/traceroute",  # Traceroute
}


class RouterOSSSHClient:
    """Async SSH client for RouterOS CLI with command whitelisting.

    Provides tightly-scoped SSH access for commands not available via REST API.
    All commands must be in the whitelist.

    Example:
        client = RouterOSSSHClient(
            host="192.168.1.1",
            username="admin",
            password="secret",
        )

        # Execute whitelisted command
        config = await client.execute("/export compact")

        # Cleanup
        await client.close()
    """

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str | None = None,
        password: str | None = None,
        private_key: str | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        """Initialize RouterOS SSH client.

        Args:
            host: RouterOS device hostname or IP
            port: SSH port (default: 22)
            username: RouterOS username
            password: RouterOS password (optional if private_key provided)
            private_key: SSH private key in PEM format (Phase 4)
            timeout_seconds: Command execution timeout
            max_retries: Maximum retry attempts for connection
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.private_key = private_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

        self._connection: asyncssh.SSHClientConnection | None = None

    def set_credentials(self, username: str, password: str | None = None, private_key: str | None = None) -> None:
        """Set or update authentication credentials.

        Args:
            username: RouterOS username
            password: RouterOS password (optional if private_key provided)
            private_key: SSH private key in PEM format (Phase 4)
        """
        self.username = username
        self.password = password
        self.private_key = private_key

    async def _get_connection(self) -> asyncssh.SSHClientConnection:
        """Get or create SSH connection with retries.

        Tries key authentication first (if private_key is provided),
        then falls back to password authentication.

        Returns:
            SSH connection

        Raises:
            RouterOSSSHAuthenticationError: On auth failure
            RouterOSSSHError: On connection errors
        """
        if not self.username:
            raise ValueError("Username not set. Call set_credentials() first.")
        
        if not self.private_key and not self.password:
            raise ValueError("Either private_key or password must be set. Call set_credentials() first.")

        # Reuse existing connection if still alive
        if self._connection is not None and not self._connection.is_closed():
            return self._connection

        # Create new connection with retries
        for attempt in range(self.max_retries):
            try:
                # Phase 4: Try key auth first, fallback to password
                if self.private_key:
                    try:
                        # Import asyncssh key from PEM string
                        from asyncssh import public_key
                        key = public_key.import_private_key(self.private_key)
                        
                        self._connection = await asyncssh.connect(
                            self.host,
                            port=self.port,
                            username=self.username,
                            client_keys=[key],
                            known_hosts=None,  # Skip host key verification (lab usage)
                        )
                        logger.info(f"SSH connection established (key auth): {self.host}:{self.port}")
                        return self._connection
                    except asyncssh.PermissionDenied:
                        # Key auth failed, try password if available
                        logger.warning(f"SSH key authentication failed for {self.host}, trying password fallback")
                        if not self.password:
                            raise  # Re-raise if no password fallback
                
                # Try password authentication (either as fallback or primary method)
                if self.password:
                    self._connection = await asyncssh.connect(
                        self.host,
                        port=self.port,
                        username=self.username,
                        password=self.password,
                        known_hosts=None,  # Skip host key verification (lab usage)
                    )
                    logger.info(f"SSH connection established (password auth): {self.host}:{self.port}")
                    return self._connection

            except asyncssh.PermissionDenied as e:
                raise RouterOSSSHAuthenticationError(
                    f"SSH authentication failed: {self.host}"
                ) from e

            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise RouterOSSSHError(
                        f"SSH connection failed after {self.max_retries} attempts: {self.host}"
                    ) from e

                # Retry with exponential backoff
                delay = 2**attempt
                logger.warning(
                    f"SSH connection attempt {attempt + 1}/{self.max_retries} failed, "
                    f"retrying in {delay}s"
                )
                await asyncio.sleep(delay)

        # Should never reach here
        raise RuntimeError("Retry loop exited unexpectedly")

    async def close(self) -> None:
        """Close SSH connection."""
        if self._connection is not None and not self._connection.is_closed():
            self._connection.close()
            await self._connection.wait_closed()
            self._connection = None
            logger.info(f"SSH connection closed: {self.host}")

    def _validate_command(self, command: str) -> None:
        """Validate that command is in whitelist.

        Args:
            command: Command to validate

        Raises:
            RouterOSSSHCommandNotAllowedError: If command not whitelisted
        """
        # Normalize command (strip leading/trailing whitespace)
        normalized_command = command.strip()

        # Check whitelist - exact match or prefix match for parameterized commands
        exact_match = normalized_command in ALLOWED_SSH_COMMANDS
        if exact_match:
            return
        
        # Allow prefix matching for commands with parameters
        # e.g., "/interface/monitor-traffic ether1 once" matches "/interface/monitor-traffic"
        for allowed_cmd in ALLOWED_SSH_COMMANDS:
            if normalized_command.startswith(allowed_cmd + " "):
                return
        
        raise RouterOSSSHCommandNotAllowedError(
            f"SSH command not allowed: '{command}'. "
            f"Allowed commands: {', '.join(ALLOWED_SSH_COMMANDS)}"
        )

    async def execute(self, command: str) -> str:
        """Execute whitelisted SSH command.

        Args:
            command: Command to execute (must be in whitelist)

        Returns:
            Command output (stdout)

        Raises:
            RouterOSSSHCommandNotAllowedError: If command not whitelisted
            RouterOSSSHTimeoutError: If command times out
            RouterOSSSHError: On other execution errors

        Example:
            # Export configuration
            config = await client.execute("/export compact")
            print(config)
        """
        # Validate command is whitelisted
        self._validate_command(command)

        # Get connection
        connection = await self._get_connection()

        try:
            # Execute command with timeout
            result = await asyncio.wait_for(
                connection.run(command, check=True),
                timeout=self.timeout_seconds,
            )

            # Ensure stdout is string
            if result.stdout is None:
                output = ""
            elif isinstance(result.stdout, str):
                output = result.stdout
            else:
                output = result.stdout.decode("utf-8")

            logger.info(f"SSH command executed: {command} (output: {len(output)} bytes)")
            return output

        except TimeoutError as e:
            raise RouterOSSSHTimeoutError(
                f"SSH command timeout after {self.timeout_seconds}s: {command}"
            ) from e

        except asyncssh.ProcessError as e:
            # Extract stderr message (handle bytes/str/None)
            stderr: str | bytes | None = e.stderr
            if stderr is None:
                stderr_text = "No stderr"
            elif isinstance(stderr, bytes):
                stderr_text = stderr.decode("utf-8")
            else:
                stderr_text = stderr

            raise RouterOSSSHError(
                f"SSH command failed (exit code {e.exit_status}): {command}. "
                f"Error: {stderr_text}"
            ) from e

        except Exception as e:
            raise RouterOSSSHError(f"SSH command execution error: {command}") from e

    async def export_config(self, compact: bool = True) -> str:
        """Export device configuration via SSH.

        Args:
            compact: Use compact export format (default: True)

        Returns:
            Configuration export as string

        Example:
            config = await client.export_config(compact=True)
            with open("backup.rsc", "w") as f:
                f.write(config)
        """
        command = "/export compact" if compact else "/export"
        return await self.execute(command)
