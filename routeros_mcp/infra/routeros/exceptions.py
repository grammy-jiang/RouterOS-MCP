"""RouterOS client exceptions.

Strongly-typed exceptions for RouterOS REST and SSH clients.
Maps low-level network/HTTP errors to domain-level exceptions.

Exception hierarchy:
- RouterOSError (base)
  - RouterOSConnectionError (network/timeout)
    - RouterOSTimeoutError
    - RouterOSNetworkError
  - RouterOSClientError (4xx responses)
    - RouterOSAuthenticationError (401)
    - RouterOSAuthorizationError (403)
    - RouterOSNotFoundError (404)
    - RouterOSValidationError (400, 422)
  - RouterOSServerError (5xx responses)
  - RouterOSSSHError (SSH-specific)

See docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md
"""


class RouterOSError(Exception):
    """Base exception for all RouterOS client errors."""

    pass


# Connection errors
class RouterOSConnectionError(RouterOSError):
    """Base exception for connection/network failures."""

    pass


class RouterOSTimeoutError(RouterOSConnectionError):
    """Raised when request times out."""

    pass


class RouterOSNetworkError(RouterOSConnectionError):
    """Raised for network connectivity issues (DNS, TCP connection, etc)."""

    pass


# Client errors (4xx)
class RouterOSClientError(RouterOSError):
    """Base exception for client errors (HTTP 4xx).

    Attributes:
        status_code: HTTP status code
        response_body: Raw response body (if available)
    """

    def __init__(self, message: str, status_code: int, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class RouterOSAuthenticationError(RouterOSClientError):
    """Raised for authentication failures (HTTP 401)."""

    def __init__(self, message: str = "Authentication failed", response_body: str | None = None):
        super().__init__(message, 401, response_body)


class RouterOSAuthorizationError(RouterOSClientError):
    """Raised for authorization failures (HTTP 403)."""

    def __init__(self, message: str = "Authorization denied", response_body: str | None = None):
        super().__init__(message, 403, response_body)


class RouterOSNotFoundError(RouterOSClientError):
    """Raised when resource not found (HTTP 404)."""

    def __init__(self, message: str = "Resource not found", response_body: str | None = None):
        super().__init__(message, 404, response_body)


class RouterOSValidationError(RouterOSClientError):
    """Raised for validation errors (HTTP 400, 422)."""

    def __init__(self, message: str, status_code: int = 400, response_body: str | None = None):
        super().__init__(message, status_code, response_body)


# Server errors (5xx)
class RouterOSServerError(RouterOSError):
    """Raised for server errors (HTTP 5xx).

    Attributes:
        status_code: HTTP status code
        response_body: Raw response body (if available)
    """

    def __init__(self, message: str, status_code: int, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


# SSH errors
class RouterOSSSHError(RouterOSError):
    """Base exception for SSH-specific errors."""

    pass


class RouterOSSSHAuthenticationError(RouterOSSSHError):
    """Raised for SSH authentication failures."""

    pass


class RouterOSSSHCommandNotAllowedError(RouterOSSSHError):
    """Raised when SSH command is not in whitelist."""

    pass


class RouterOSSSHTimeoutError(RouterOSSSHError):
    """Raised when SSH command times out."""

    pass
