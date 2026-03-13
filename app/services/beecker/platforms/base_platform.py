"""
Abstract base class for Beecker platforms.

Defines the common interface that all platforms must implement
(Cloud, Hub, etc.) and the normalized response schemas.

Normalized schemas
------------------

RPA — Run history item:
    {
        "process_id": int,
        "run_id":     int,
        "run_state":  str,   # 'completed' | 'in progress' | 'failed' | ...
        "start_run":  str,
        "end_run":    str | None,
    }

RPA — Transactions response:
    {
        "count_data":           int,
        "complete_count":       int,
        "failed_count":         int,
        "completed_percentage": float,
        "failed_percentage":    float,
        "data":                 dict,
    }

Agent — Run history item:
    {
        "process_id":   str,
        "run_id":       int,
        "run_state":    str,   # 'successful' | 'in progress' | 'pending approval' | ...
        "start_run":    str,
        "end_run":      str | None,
        "description":  str,
        "extra_fields": dict,  # Additional agent-specific fields
    }

Agent — Progress response:
    {
        "execution_id":        int,
        "total_stages":        int,
        "completed_stages":    int,
        "progress_percentage": float,
        "is_finished":         bool,   # True if all stages are 'completed'
        "stages": [
            {
                "name":      str,
                "stage":     str,   # 'completed' | 'pending' | 'in progress'
                "active":    float,
                "start_run": str,
                "end_run":   str,
                "steps": [
                    {
                        "name":      str,
                        "status":    str,
                        "start_run": str,
                        "end_run":   str,
                    },
                    ...
                ]
            },
            ...
        ]
    }
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from app.utils.http_client import HttpClient


class BasePlatform(ABC):
    """
    Common interface for all Beecker platforms.

    Each concrete platform (Cloud, Hub) must:
    1. Implement all abstract methods with their real endpoints.
    2. Normalize responses to the common schema before returning them.

    Attributes:
        BASE_URL (str):
            Base URL of the platform for RPA endpoints.

        _http (HttpClient):
            Shared asynchronous HTTP client with authentication headers.

        _access_token (str | None):
            Active JWT token.

        _refresh_token (str | None):
            Refresh token.
    """

    BASE_URL: str = ""  # Subclase define su URL base (RPA)

    def __init__(self):
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._http = HttpClient()

    # ------------------------------------------------------------------
    # Autenticación
    # ------------------------------------------------------------------

    @abstractmethod
    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate against the platform and store the tokens.

        Args:
            email:
                User email.

            password:
                User password.

        Returns
        -------
        {
            "access_token":  str,
            "refresh_token": str,
        }

        Raises
        ------
        PlatformAuthError
            If the credentials are invalid.

        PlatformConnectionError
            If the platform cannot be reached.
        """

    # ------------------------------------------------------------------
    # RPA — Historial de ejecuciones
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_run_history(
        self,
        process_id: str,
        time_zone: str = "America/Mexico_City",
        page_size: int = 10,
        tags: str = "",
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve the execution history of an RPA bot.

        Args:
            process_id:
                RPA bot ID.

            time_zone:
                Time zone used for date formatting.

            page_size:
                Number of records per page.

            tags:
                Tag filter.

            page:
                Page number (None = first page).

        Returns
        -------
        {
            "count":   int,
            "next":    str | None,
            "results": [
                {
                    "process_id": int,
                    "run_id":     int,
                    "run_state":  str,
                    "start_run":  str,
                    "end_run":    str | None,
                },
                ...
            ]
        }

        Raises
        ------
        PlatformAPIError
            If the platform returns an error.
        """

    # ------------------------------------------------------------------
    # RPA — Transacciones
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_transactions(
        self,
        run_id: int,
        page_size: int = 100,
        is_paginated: int = 1,
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve the transactions of an RPA execution.

        Args:
            run_id:
                Execution ID.

            page_size:
                Number of records per page.

            is_paginated:
                1 for paginated results, 0 to retrieve everything at once.

            page:
                Page number.

        Returns
        -------
        {
            "count_data":           int,
            "complete_count":       int,
            "failed_count":         int,
            "completed_percentage": float,
            "failed_percentage":    float,
            "data":                 dict,
        }

        Raises
        ------
        PlatformAPIError
            If the platform returns an error.

        PlatformNotFoundError
            If no transactions are available (404).
        """

    # ------------------------------------------------------------------
    # Agent — Historial de ejecuciones
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_agent_run_history(
        self,
        process_id: str,
        time_zone: str = "America/Mexico_City",
        page_size: int = 10,
        search_term: str = "",
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve the execution history of an agent.

        Args:
            process_id:
                Agent ID.

            time_zone:
                Time zone used for date formatting.

            page_size:
                Number of records per page.

            search_term:
                Search term (equivalent to tags in RPA).

            page:
                Page number (None = first page).

        Returns
        -------
        {
            "count":        int,
            "next":         str | None,
            "total_pages":  int,
            "current_page": int,
            "results": [
                {
                    "process_id":   str,
                    "run_id":       int,
                    "run_state":    str,
                    "start_run":    str,
                    "end_run":      str | None,
                    "description":  str,
                    "extra_fields": dict,
                },
                ...
            ]
        }

        Raises
        ------
        PlatformAPIError
            If the platform returns an error.
        """

    # ------------------------------------------------------------------
    # Agent — Progreso de ejecución
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_agent_progress(self, execution_id: int) -> Dict[str, Any]:
        """
        Retrieve the progress of an agent execution.

        Args:
            execution_id:
                Agent execution ID.

        Returns
        -------
        Normalized schema including stages and steps.

        Raises
        ------
        PlatformNotFoundError
            If the execution does not exist (404).
        """

    def is_authenticated(self) -> bool:
        """Indicates whether the platform has an active authentication token."""
        return self._access_token is not None

    def _require_auth(self) -> None:
        """Raises an exception if the client is not authenticated."""
        if not self.is_authenticated():
            raise PlatformAuthError(
                f"[{self.__class__.__name__}] No autenticado. Ejecuta login() primero."
            )

    async def _post(
    self,
    endpoint: str,
    payload: Dict,
    params: Optional[Dict] = None,
    retries: int = 2,
) -> Any:
        """
        Perform an asynchronous POST request and handle common HTTP errors.

        Note:
            The return type is `Any` because some agent endpoints return a list
            instead of a dictionary.

        Args:
            endpoint:
                Full endpoint URL.

            payload:
                JSON request body.

            params:
                Optional query parameters.

            retries:
                Number of retry attempts on connection errors (status_code = 0).
                Uses exponential backoff (1s, 2s, …). Default: 2.

        Returns
        -------
        JSON response (dict or list depending on the endpoint).

        Raises
        ------
        PlatformNotFoundError
            HTTP 404.

        PlatformAuthError
            HTTP 401/403.

        PlatformConnectionError
            Connection failure (status_code = 0) after all retries exhausted.

        PlatformAPIError
            Any other HTTP error.
        """
        result = await self._http.post(endpoint, json=payload, params=params or {})

        if result["success"]:
            return result["data"]

        status = result["status_code"]
        error  = result.get("error", "")

        if status == 0:
            raise PlatformConnectionError(
                f"[{self.__class__.__name__}] No se puede conectar a {endpoint}: {error}"
            )
        if status == 404:
            raise PlatformNotFoundError(
                f"[{self.__class__.__name__}] 404 Not Found: {endpoint}"
            )
        if status in (401, 403):
            raise PlatformAuthError(
                f"[{self.__class__.__name__}] {status} No autorizado: {endpoint}"
            )
        raise PlatformAPIError(
            f"[{self.__class__.__name__}] Error {status} en petición a {endpoint}: {error}"
        )
    
    async def _get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
    ) -> Any:
        """
        Perform an asynchronous GET request and handle common HTTP errors.

        Args:
            endpoint:
                Full endpoint URL.

            params:
                Optional query parameters.

        Returns
        -------
        JSON response.

        Raises
        ------
        PlatformNotFoundError
            HTTP 404.

        PlatformAuthError
            HTTP 401/403.

        PlatformConnectionError
            Connection failure (status_code = 0).

        PlatformAPIError
            Any other HTTP error.
        """
        result = await self._http.get(endpoint, params=params or {})

        if not result["success"]:
            status = result["status_code"]
            error  = result.get("error", "")

            if status == 0:
                raise PlatformConnectionError(
                    f"[{self.__class__.__name__}] No se puede conectar a {endpoint}: {error}"
                )
            if status == 404:
                raise PlatformNotFoundError(
                    f"[{self.__class__.__name__}] 404 Not Found: {endpoint}"
                )
            if status in (401, 403):
                raise PlatformAuthError(
                    f"[{self.__class__.__name__}] {status} No autorizado: {endpoint}"
                )
            raise PlatformAPIError(
                f"[{self.__class__.__name__}] Error {status} en petición a {endpoint}: {error}"
            )

        return result["data"]

    def __repr__(self) -> str:
        auth_status = "autenticado" if self.is_authenticated() else "no autenticado"
        return f"{self.__class__.__name__}(base_url='{self.BASE_URL}', {auth_status})"


# ---------------------------------------------------------------------------
# Excepciones de plataforma
# ---------------------------------------------------------------------------

class PlatformError(Exception):
    """Base exception for platform errors."""


class PlatformAuthError(PlatformError):
    """Authentication or authorization error."""


class PlatformConnectionError(PlatformError):
    """Connectivity error with the platform."""


class PlatformNotFoundError(PlatformError):
    """Resource not found on the platform (404)."""


class PlatformAPIError(PlatformError):
    """General platform API error."""