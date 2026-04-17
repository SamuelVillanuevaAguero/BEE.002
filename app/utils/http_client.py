"""
Asynchronous HTTP client wrapper built on top of httpx.

Provides a lightweight utility for performing HTTP requests with support
for persistent headers and configurable automatic retries (similar to
axios-retry in JS).

Retry behavior (configurable via .env):
    HTTP_RETRY_MAX          → number of retry attempts (default: 2)
    HTTP_RETRY_BACKOFF      → base seconds for exponential backoff (default: 1.0)
    HTTP_RETRY_ON_STATUS    → comma-separated HTTP status codes to retry (default: 429,502,503,504)

Retries are triggered by:
    - Connection errors    (status_code = 0)
    - Configured HTTP codes (e.g. 429, 502, 503, 504)

Non-retriable errors (400, 401, 403, 404, 500, etc.) fail immediately.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _parse_retry_statuses(raw: str) -> set[int]:
    """Parse comma-separated status codes string into a set of ints."""
    result = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.add(int(part))
    return result


class HttpClient:
    """
    Asynchronous HTTP client with persistent headers and automatic retries.

    Retry policy (loaded from settings at instantiation):
        - Retries on connection errors (status_code = 0) and configured HTTP codes.
        - Exponential backoff: wait = backoff * (2 ** attempt).
        - Non-retriable errors fail immediately without consuming retry budget.
    """

    def __init__(self):
        self._base_headers: Dict[str, str] = {
            "Content-Type": "application/json",
        }
        self._max_retries: int         = settings.HTTP_RETRY_MAX
        self._backoff: float           = settings.HTTP_RETRY_BACKOFF
        self._retry_statuses: set[int] = _parse_retry_statuses(settings.HTTP_RETRY_ON_STATUS)
        self._timeout: float           = settings.HTTP_TIMEOUT

    def set_header(self, key: str, value: str) -> None:
        self._base_headers[key] = value

    def set_headers(self, headers: Dict[str, str]) -> None:
        self._base_headers.update(headers)

    def clear_auth(self) -> None:
        self._base_headers.pop("Authorization", None)

    def _should_retry(self, status_code: int) -> bool:
        """Return True if the response warrants a retry attempt."""
        return status_code == 0 or status_code in self._retry_statuses

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
        Perform an HTTP request with automatic retry support.

        Retries are attempted with exponential backoff for connection errors
        and configured HTTP status codes. All other errors fail immediately.

        Returns:
            Dictionary with keys: success, status_code, data, headers, error.
        """
        merged_headers = {**self._base_headers, **(headers or {})}
        last_result: Dict[str, Any] = {}

        for attempt in range(self._max_retries + 1):

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                try:
                    logger.debug(f"fetching {method} {url}" + (f" (retry {attempt})" if attempt else ""))

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

                    logger.debug(f"Response {response.status_code}")
                    return {
                        "success":     True,
                        "status_code": response.status_code,
                        "data":        content,
                        "headers":     dict(response.headers),
                    }

                except httpx.HTTPStatusError as e:
                    status_code = e.response.status_code
                    logger.error(f"HTTP error {status_code}: {e}")
                    last_result = {
                        "success":     False,
                        "status_code": status_code,
                        "error":       str(e),
                        "data":        None,
                    }

                except httpx.RequestError as e:
                    logger.error(f"Request error: {str(e)}")
                    last_result = {
                        "success":     False,
                        "status_code": 0,
                        "error":       f"Connection error: {str(e)}",
                        "data":        None,
                    }

                except Exception as e:
                    logger.error(f"Unexpected error: {str(e)}")
                    last_result = {
                        "success":     False,
                        "status_code": 0,
                        "error":       f"Unexpected error: {str(e)}",
                        "data":        None,
                    }

            status_code = last_result["status_code"]

            if not self._should_retry(status_code):
                return last_result

            if attempt < self._max_retries:
                wait = self._backoff * (2 ** attempt)
                logger.warning(
                    f"[HttpClient] Reintento {attempt + 1}/{self._max_retries} "
                    f"en {wait:.1f}s para {url}... (status={status_code})"
                )
                await asyncio.sleep(wait)

        logger.error(
            f"[HttpClient] Agotados {self._max_retries} reintentos para {url} "
            f"(último status={last_result.get('status_code')})"
        )
        return last_result

    async def get(self, url: str, **kwargs) -> Dict[str, Any]:
        return await self.fetch("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> Dict[str, Any]:
        return await self.fetch("POST", url, **kwargs)