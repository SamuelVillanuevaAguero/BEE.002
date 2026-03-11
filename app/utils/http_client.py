"""
Asynchronous HTTP client wrapper built on top of httpx.

Provides a lightweight utility for performing HTTP requests with support
for persistent headers (similar to requests.Session). This allows shared
headers such as Authorization tokens to be reused across multiple requests.

Example::

    client = HttpClient()
    client.set_header("Authorization", "Bearer token123")

    result = await client.post(
        "https://api.example.com/endpoint",
        json={"key": "value"}
    )
"""

import httpx
from typing import Optional, Dict, Any


class HttpClient:
    """
    Asynchronous HTTP client with support for persistent headers.

    The client maintains a set of base headers that are automatically included
    in every request. These headers can be modified dynamically during runtime,
    which is useful for authentication tokens or shared request metadata.
    """

    def __init__(self):
        self._base_headers: Dict[str, str] = {
            "Content-Type": "application/json",
        }

    def set_header(self, key: str, value: str) -> None:
        """Add or update a persistent header."""
        self._base_headers[key] = value

    def set_headers(self, headers: Dict[str, str]) -> None:
        """Update multiple persistent headers at once."""
        self._base_headers.update(headers)

    def clear_auth(self) -> None:
        """Remove the Authorization header (useful during logout or token refresh)."""
        self._base_headers.pop("Authorization", None)

    async def fetch(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Perform an HTTP request using the specified method.

        This method merges the base headers configured in the client with
        request-specific headers and executes the request using httpx.AsyncClient.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.).
            url: Target endpoint URL.
            headers: Optional request-specific headers.
            params: Optional query parameters.
            json: Optional JSON body payload.
            data: Optional form data payload.

        Returns:
            Dictionary containing:
                success:     Whether the request succeeded.
                status_code: HTTP response status code.
                data:        Parsed JSON response or raw text.
                headers:     Response headers (only on success).
                error:       Error message when success=False.
        """

        merged_headers = {**self._base_headers, **(headers or {})}

        async with httpx.AsyncClient() as client:
            try:
                print(f"fetching {method} {url}")
                response = await client.request(
                    method=method,
                    url=url,
                    headers=merged_headers,
                    params=params or {},
                    data=data or {},
                    json=json,
                )
                response.raise_for_status()

                try:
                    content = response.json()
                except Exception:
                    content = response.text

                print(f"Response {response.status_code}")
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": content,
                    "headers": dict(response.headers),
                }

            except httpx.HTTPStatusError as e:
                print(f"HTTP error {e.response.status_code}: {e}")
                return {
                    "success": False,
                    "status_code": e.response.status_code,
                    "error": str(e),
                    "data": None,
                }
            except httpx.RequestError as e:
                print(f"Request error: {str(e)}")
                return {
                    "success": False,
                    "status_code": 0,
                    "error": f"Connection error: {str(e)}",
                    "data": None,
                }
            except Exception as e:
                print(f"Unexpected error: {str(e)}")
                return {
                    "success": False,
                    "status_code": 0,
                    "error": f"Unexpected error: {str(e)}",
                    "data": None,
                }

    async def get(self, url: str, **kwargs) -> Dict[str, Any]:
        """Shortcut method for performing a GET request."""
        return await self.fetch("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> Dict[str, Any]:
        """Shortcut method for performing a POST request."""
        return await self.fetch("POST", url, **kwargs)