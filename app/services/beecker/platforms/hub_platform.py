"""
Implementation of the Beecker Hub platform.

Base endpoint:
    https://app-platform-beecker-prod-cuc5f3ashffecpcj.eastus-01.azurewebsites.net/api

Login endpoint:
    .../api/auth/login/

CURRENT STATUS:
    - login()                  → Implemented ✓
    - get_run_history()        → Pending (RPA endpoints not available)
    - get_transactions()       → Pending (RPA endpoints not available)
    - get_agent_menu()         → Implemented ✓
    - get_agent_run_history()  → Implemented ✓
    - get_agent_progress()     → Pending (endpoint not available)

Hub API notes for Agents:
    - Agent history uses a dynamic URL based on the agent name in lowercase:
        /api/agent/{agent_name}/run_history/

    - The agent name is resolved using the endpoint:
        /api/agents/menu/
      which maps agent_id → agent_name.

    - Pagination is passed as query parameters:
        ?page=N&page_size=N

    - The request body for run history is:
        {"agent_id": int}

    - results.data contains the records (not data_row as in Cloud).

    - Each record uses English property names (run_state, start_run, etc.)
      and may include additional fields specific to the agent.
"""

from typing import Dict, Any, Optional
from .base_platform import (
    BasePlatform,
    PlatformAPIError,
    PlatformAuthError,
    PlatformConnectionError,
    PlatformNotFoundError,
)

# Campos del esquema normalizado base (siempre presentes en cualquier agente)
_AGENT_CORE_PROPS = {"id", "start_run", "run_state", "current_step"}


class HubPlatform(BasePlatform):
    """
    Client implementation for the Beecker Hub platform.

    Example:
        >>> platform = HubPlatform()
        >>> await platform.login("user@beecker.ai", "Beecker2024.")
        >>>
        >>> # Retrieve the list of available agents
        >>> menu = await platform.get_agent_menu()
        >>> for agent in menu["agents"]:
        ...     print(f"ID {agent['id']}: {agent['agent_name']}")
        >>>
        >>> # Retrieve execution history of an agent
        >>> history = await platform.get_agent_run_history(process_id="7")
        >>> for run in history["results"]:
        ...     print(f"ID {run['run_id']}: {run['run_state']}")
    """

    BASE_URL = (
        "https://app-platform-beecker-prod-cuc5f3ashffecpcj.eastus-01.azurewebsites.net/api"
    )

    AGENT_BASE_URL = "https://app-bap-arca-prod-fzdvh8dva2dkdud3.eastus-01.azurewebsites.net/api"

    # Cache interno: agent_id (str) → agent_name (str, en minúsculas)
    _agent_name_cache: Dict[str, str]

    def __init__(self):
        super().__init__()
        self._agent_name_cache = {}

    # ------------------------------------------------------------------
    # Autenticación
    # ------------------------------------------------------------------

    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate against the Hub platform.

        Args:
            email:
                Email registered in hub.beecker.ai.

            password:
                User password.

        Returns
        -------
        dict
            {
                "access_token":  str,
                "refresh_token": str,
            }

        Raises
        ------
        PlatformAuthError
            Invalid credentials (401/403).

        PlatformConnectionError
            Connection failure.

        PlatformAPIError
            Unexpected API error.
        """
        endpoint = f"{self.BASE_URL}/auth/login/"
        payload  = {"email": email, "password": password}

        data = await self._post(endpoint, payload)

        self._access_token  = data.get("access")
        self._refresh_token = data.get("refresh")
        self._http.set_header("Authorization", f"Bearer {self._access_token}")

        return {
            "access_token":  self._access_token,
            "refresh_token": self._refresh_token,
        }

    # ------------------------------------------------------------------
    # RPA — Historial de ejecuciones
    # ------------------------------------------------------------------

    async def get_run_history(
        self,
        process_id: str,
        time_zone: str = "America/Mexico_City",
        page_size: int = 10,
        tags: str = "",
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        TODO: Implement when Hub RPA endpoints become available.

        Expected return schema identical to CloudPlatform.get_run_history().
        """
        raise NotImplementedError(
            "[HubPlatform] get_run_history() pendiente. "
            "Se requiere documentación de endpoints RPA de Hub."
        )

    def _normalize_run_history(self, raw: Dict) -> Dict[str, Any]:
        """TODO: Implement when the Hub response structure becomes known."""
        raise NotImplementedError("[HubPlatform] _normalize_run_history() pendiente.")

    async def get_transactions(
        self,
        run_id: int,
        page_size: int = 100,
        is_paginated: int = 1,
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        TODO: Implementar cuando se tengan los endpoints RPA de Hub.

        Esquema de retorno esperado idéntico al de CloudPlatform.get_transactions().
        """
        raise NotImplementedError(
            "[HubPlatform] get_transactions() pendiente. "
            "Se requiere documentación de endpoints RPA de Hub."
        )

    def _normalize_transactions(self, raw: Dict) -> Dict[str, Any]:
        """TODO: Implementar cuando se conozca la estructura de Hub."""
        raise NotImplementedError("[HubPlatform] _normalize_transactions() pendiente.")

    async def get_agent_menu(self) -> Dict[str, Any]:
        """
        Retrieve the list of agents available for the authenticated user.

        Endpoint:
            GET https://.../api/agents/menu/

        Header:
            Authorization: Bearer {token}

        This method populates the internal cache mapping:

            agent_id → agent_name

        so that `get_agent_run_history()` can resolve the agent name
        from the process_id without additional API calls.

        Returns
        -------
        {
            "agents": [
                {
                    "id":          int,
                    "agent_name":  str,    # Original name (e.g. "Lucas")
                    "description": str,
                    "logo_url":    str,
                },
                ...
            ],
            "type_user": str,
        }

        Raises
        ------
        PlatformAuthError
            If the client is not authenticated.

        PlatformAPIError
            If the API returns an error response.
        """
        self._require_auth()

        endpoint = f"{self.AGENT_BASE_URL}/agents/menu/"
        data = await self._get(endpoint)

        # Poblar cache: agent_id (str) → agent_name en minúsculas
        for agent in data.get("agents", []):
            agent_id   = str(agent.get("id", ""))
            agent_name = agent.get("agent_name", "")
            if agent_id and agent_name:
                self._agent_name_cache[agent_id] = agent_name.lower()

        return data

    async def _resolve_agent_name(self, process_id: str) -> str:
        """
        Resolve the agent name (lowercase) from its ID.

        If the name is not present in the internal cache,
        the agent menu is retrieved first.

        Args:
            process_id:
                Agent ID (string).

        Returns
        -------
        str
            Agent name in lowercase (e.g. "lucas").

        Raises
        ------
        PlatformAPIError
            If the agent ID does not exist in the menu.
        """
        if process_id not in self._agent_name_cache:
            await self.get_agent_menu()

        agent_name = self._agent_name_cache.get(process_id)
        if not agent_name:
            raise PlatformAPIError(
                f"[HubPlatform] No se encontró el agente con ID={process_id} "
                f"en el menú. IDs disponibles: {list(self._agent_name_cache.keys())}"
            )

        return agent_name

    async def get_agent_run_history(
        self,
        process_id: str,
        time_zone: str = "America/Mexico_City",
        page_size: int = 10,
        search_term: str = "",
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve the execution history of an agent in the Hub platform.

        Endpoint:
            POST https://.../api/agent/{agent_name}/run_history/

        Query params:
            ?page=N&page_size=N

        Body:
            {"agent_id": int}

        Args:
            process_id:
                Numeric agent ID (string, e.g. "7").

            time_zone:
                Not used in Hub (accepted for interface compatibility).

            page_size:
                Number of records per page.

            search_term:
                Not used in Hub (accepted for interface compatibility).

            page:
                Page number (None = first page).

        Returns
        -------
        Normalized schema (see BasePlatform.get_agent_run_history).

        Raises
        ------
        PlatformAuthError
            If the client is not authenticated.

        PlatformAPIError
            If the agent does not exist or the API returns an error.
        """
        self._require_auth()

        # Resolver nombre del agente (con cache)
        agent_name = await self._resolve_agent_name(process_id)

        endpoint = f"{self.AGENT_BASE_URL}/agent/{agent_name}/run_history/"
        payload  = {"agent_id": int(process_id)}
        params   = {"page_size": page_size}
        if page is not None:
            params["page"] = page

        raw = await self._post(endpoint, payload, params)
        return self._normalize_agent_run_history(raw, process_id)

    def _normalize_agent_run_history(
        self, raw: Dict, process_id: str
    ) -> Dict[str, Any]:
        """
        Normalize the Hub agent run history to the common schema.

        Raw Hub response structure:

        {
            "count": int,
            "next":  str | None,
            "results": {
                "headers": [ {"name": str, "prop": str}, ... ],
                "data": [
                    {
                        "id":            int,     → run_id
                        "start_run":     str,     → start_run
                        "run_state":     str,     → run_state
                        "current_step":  str,     → description
                        ... (remaining fields → extra_fields)
                    },
                    ...
                ]
            }
        }
        """
        data_rows = raw.get("results", {}).get("data", [])
        normalized = []

        for row in data_rows:
            extra = {
                k: v for k, v in row.items()
                if k not in _AGENT_CORE_PROPS
            }

            normalized.append({
                "process_id":   process_id,
                "run_id":       row.get("id"),
                "run_state":    row.get("run_state"),
                "start_run":    row.get("start_run"),
                "end_run":      None,   # Hub no expone end_run en este endpoint
                "description":  row.get("current_step", ""),
                "extra_fields": extra,
            })

        return {
            "count":        raw.get("count", 0),
            "next":         raw.get("next"),
            "total_pages":  0,   # No disponible en la respuesta de Hub
            "current_page": 1,
            "results":      normalized,
        }

    # ------------------------------------------------------------------
    # Agent — Progreso de ejecución
    # ------------------------------------------------------------------

    async def get_agent_progress(
        self,
        execution_id: int,
    ) -> Dict[str, Any]:
        """
        TODO: Implement when the Hub progress endpoint becomes available.

        Expected return schema identical to CloudPlatform.get_agent_progress().
        """
        raise NotImplementedError(
            "[HubPlatform] get_agent_progress() pendiente. "
            "Se requiere documentación del endpoint de progreso de Hub."
        )

    def _normalize_agent_progress(self, raw_stages, execution_id: int) -> Dict[str, Any]:
        """TODO: Implement when the Hub response structure becomes known."""
        raise NotImplementedError("[HubPlatform] _normalize_agent_progress() pendiente.")