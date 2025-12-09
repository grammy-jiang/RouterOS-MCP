"""RouterOS REST API client with async HTTP support.

Provides async HTTP client for RouterOS v7 REST API with:
- Connection pooling and keep-alive
- Automatic retries with exponential backoff
- Timeout enforcement
- Error mapping to strongly-typed exceptions
- Request/response logging

Design principles:
- Use httpx for modern async HTTP
- Map HTTP errors to domain exceptions
- Never log credentials or sensitive data
- Retry transient errors, fail fast on permanent errors
- Per-device concurrency and rate limiting

See docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md
"""

import asyncio
import logging
from typing import Any

import httpx

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

logger = logging.getLogger(__name__)


class RouterOSRestClient:
    """Async HTTP client for RouterOS REST API.

    Manages HTTP connections to a single RouterOS device with connection
    pooling, retries, and comprehensive error handling.

    Example:
        client = RouterOSRestClient(
            host="192.168.1.1",
            port=443,
            username="admin",
            password="secret",
        )

        # GET request
        resource = await client.get("/rest/system/resource")

        # PATCH request
        await client.patch("/rest/system/identity", {"name": "new-router-name"})

        # Cleanup
        await client.close()
    """

    def __init__(
        self,
        host: str,
        port: int = 443,
        username: str | None = None,
        password: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize RouterOS REST client.

        Args:
            host: RouterOS device hostname or IP
            port: HTTPS port (default: 443)
            username: RouterOS username (optional, can be set later)
            password: RouterOS password (optional, can be set later)
            timeout_seconds: Request timeout in seconds
            max_retries: Maximum retry attempts for transient errors
            verify_ssl: Verify SSL certificates (set False for self-signed)
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.max_retries = max_retries
        self.verify_ssl = verify_ssl

        # HTTP client configuration
        self.base_url = f"https://{host}:{port}"
        self.timeout = httpx.Timeout(timeout_seconds)
        self.limits = httpx.Limits(
            max_connections=5,
            max_keepalive_connections=3,
            keepalive_expiry=30.0,
        )

        self._client: httpx.AsyncClient | None = None

    def set_credentials(self, username: str, password: str) -> None:
        """Set or update authentication credentials.

        Args:
            username: RouterOS username
            password: RouterOS password
        """
        self.username = username
        self.password = password

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling.

        Returns:
            Configured httpx.AsyncClient

        Raises:
            ValueError: If credentials not set
        """
        if not self.username or not self.password:
            raise ValueError("Credentials not set. Call set_credentials() first.")

        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                auth=(self.username, self.password),
                timeout=self.timeout,
                limits=self.limits,
                verify=self.verify_ssl,
                follow_redirects=False,
            )

        return self._client

    async def close(self) -> None:
        """Close HTTP client and cleanup connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute HTTP request with retries and error handling.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            path: API path (e.g., "/rest/system/resource")
            json: JSON request body (for POST/PUT/PATCH)
            params: Query parameters

        Returns:
            JSON response as dict

        Raises:
            RouterOSTimeoutError: On timeout
            RouterOSNetworkError: On network errors
            RouterOSClientError: On 4xx errors
            RouterOSServerError: On 5xx errors
        """
        client = await self._get_client()

        for attempt in range(self.max_retries):
            try:
                response = await client.request(
                    method=method,
                    url=path,
                    json=json,
                    params=params,
                )

                # Check for errors
                if response.status_code >= 400:
                    self._handle_error_response(response)

                # Success - return JSON
                return response.json() if response.content else {}

            except httpx.TimeoutException as e:
                if attempt == self.max_retries - 1:
                    raise RouterOSTimeoutError(
                        f"Request timeout after {self.timeout.read}s: {method} {path}"
                    ) from e

                # Retry with exponential backoff
                delay = 2**attempt
                logger.warning(
                    f"Timeout on attempt {attempt + 1}/{self.max_retries}, " f"retrying in {delay}s"
                )
                await asyncio.sleep(delay)

            except httpx.NetworkError as e:
                if attempt == self.max_retries - 1:
                    raise RouterOSNetworkError(
                        f"Network error: {method} {path}: {type(e).__name__}"
                    ) from e

                # Retry with exponential backoff
                delay = 2**attempt
                logger.warning(
                    f"Network error on attempt {attempt + 1}/{self.max_retries}, "
                    f"retrying in {delay}s"
                )
                await asyncio.sleep(delay)

            except httpx.HTTPStatusError:
                # Don't retry 4xx errors (client errors are not transient)
                raise

        # Should never reach here
        raise RuntimeError("Retry loop exited unexpectedly")

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Map HTTP error response to appropriate exception.

        Args:
            response: HTTP response with error status

        Raises:
            Appropriate RouterOSError subclass based on status code
        """
        status_code = response.status_code
        response_body = response.text

        # Try to extract error message from response
        try:
            error_data = response.json()
            error_message = error_data.get("error", error_data.get("message", response_body))
        except Exception:
            error_message = response_body

        # Map status codes to exceptions
        if status_code == 401:
            raise RouterOSAuthenticationError(
                f"Authentication failed: {error_message}", response_body
            )
        elif status_code == 403:
            raise RouterOSAuthorizationError(
                f"Authorization denied: {error_message}", response_body
            )
        elif status_code == 404:
            raise RouterOSNotFoundError(f"Resource not found: {error_message}", response_body)
        elif status_code == 400 or status_code == 422:
            raise RouterOSValidationError(
                f"Validation error: {error_message}", status_code, response_body
            )
        elif 400 <= status_code < 500:
            raise RouterOSClientError(
                f"Client error ({status_code}): {error_message}",
                status_code,
                response_body,
            )
        elif 500 <= status_code < 600:
            raise RouterOSServerError(
                f"Server error ({status_code}): {error_message}",
                status_code,
                response_body,
            )
        else:
            raise RouterOSClientError(
                f"Unexpected status code ({status_code}): {error_message}",
                status_code,
                response_body,
            )

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute GET request.

        Args:
            path: API path (e.g., "/rest/system/resource")
            params: Optional query parameters

        Returns:
            JSON response

        Example:
            resource = await client.get("/rest/system/resource")
            print(f"CPU load: {resource['cpu-load']}")
        """
        return await self._request("GET", path, params=params)

    async def post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """Execute POST request.

        Args:
            path: API path
            data: JSON request body

        Returns:
            JSON response

        Example:
            result = await client.post("/rest/tool/ping", {
                "address": "8.8.8.8",
                "count": 3
            })
        """
        return await self._request("POST", path, json=data)

    async def put(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """Execute PUT request.

        Args:
            path: API path
            data: JSON request body

        Returns:
            JSON response
        """
        return await self._request("PUT", path, json=data)

    async def patch(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """Execute PATCH request.

        Args:
            path: API path
            data: JSON request body

        Returns:
            JSON response

        Example:
            await client.patch("/rest/system/identity", {
                "name": "new-router-name"
            })
        """
        return await self._request("PATCH", path, json=data)

    async def delete(self, path: str) -> dict[str, Any]:
        """Execute DELETE request.

        Args:
            path: API path (e.g., "/rest/ip/address/{id}")

        Returns:
            JSON response (usually empty)

        Example:
            await client.delete("/rest/ip/firewall/address-list/123")
        """
        return await self._request("DELETE", path)
