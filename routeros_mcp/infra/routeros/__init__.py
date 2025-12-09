"""RouterOS integration module.

Provides async clients for interacting with MikroTik RouterOS devices:
- rest_client: HTTP REST API client (primary interface)
- ssh_client: SSH/CLI client (tightly-scoped fallback)
- exceptions: Strongly-typed error handling

See docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md
"""

from routeros_mcp.infra.routeros.exceptions import (
    RouterOSAuthenticationError,
    RouterOSAuthorizationError,
    RouterOSClientError,
    RouterOSConnectionError,
    RouterOSError,
    RouterOSNetworkError,
    RouterOSNotFoundError,
    RouterOSServerError,
    RouterOSSSHAuthenticationError,
    RouterOSSSHCommandNotAllowedError,
    RouterOSSSHError,
    RouterOSSSHTimeoutError,
    RouterOSTimeoutError,
    RouterOSValidationError,
)
from routeros_mcp.infra.routeros.rest_client import RouterOSRestClient
from routeros_mcp.infra.routeros.ssh_client import RouterOSSSHClient

__all__ = [
    # Clients
    "RouterOSRestClient",
    "RouterOSSSHClient",
    # Exceptions
    "RouterOSError",
    "RouterOSConnectionError",
    "RouterOSTimeoutError",
    "RouterOSNetworkError",
    "RouterOSClientError",
    "RouterOSAuthenticationError",
    "RouterOSAuthorizationError",
    "RouterOSNotFoundError",
    "RouterOSValidationError",
    "RouterOSServerError",
    "RouterOSSSHError",
    "RouterOSSSHAuthenticationError",
    "RouterOSSSHCommandNotAllowedError",
    "RouterOSSSHTimeoutError",
]
