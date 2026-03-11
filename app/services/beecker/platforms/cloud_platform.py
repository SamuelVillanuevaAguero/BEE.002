"""
Implementation of the Beecker Cloud platform.

Base URLs:
    RPA:    https://api.dashboard.beecker.ai/api
    Agents: https://api.beecker.ai/api

Both share the same authentication token (login via dashboard).
The HttpClient automatically persists the Authorization header.
"""

from typing import Dict, Any, List, Optional
from .base_platform import (
    BasePlatform,
    PlatformAPIError,
    PlatformAuthError,
    PlatformConnectionError,
    PlatformNotFoundError,
)

# Fields from the raw agent JSON that are NOT part of the normalized
# schema — they are stored in extra_fields
_AGENT_CORE_FIELDS = {"ID", "Execution start", "Execution end", "Status", "Details"}


class CloudPlatform(BasePlatform):
    """
    Client for the Beecker Cloud platform.

    Handles two internal BASE_URLs that share the same token:

    - BASE_URL       → RPA  (api.dashboard.beecker.ai)
    - AGENT_BASE_URL → Agents (api.beecker.ai)

    Example:
        >>> platform = CloudPlatform()
        >>> await platform.login("user@beecker.ai", "secret")
        >>>
        >>> # RPA
        >>> history = await platform.get_run_history(process_id="104")
        >>> transactions = await platform.get_transactions(run_id=161057)
        >>>
        >>> # Agents
        >>> agent_history = await platform.get_agent_run_history(process_id="1")
        >>> progress = await platform.get_agent_progress(execution_id=35239)
    """

    BASE_URL       = "https://api.dashboard.beecker.ai/api"
    AGENT_BASE_URL = "https://api.beecker.ai/api"

    # ------------------------------------------------------------------
    # Autenticación
    # ------------------------------------------------------------------

    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate against the Cloud platform.

        The returned token is valid for both RPA endpoints (dashboard)
        and Agents endpoints (api).

        Args:
            email:
                Email registered in cloud.beecker.ai.

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


    async def get_run_history(
        self,
        process_id: str,
        time_zone: str = "America/Mexico_City",
        page_size: int = 10,
        tags: str = "",
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve the execution history of an RPA bot in Cloud.

        Args:
            process_id:
                RPA bot ID.

            time_zone:
                Time zone used for date formatting.

            page_size:
                Number of records per page.

            tags:
                Filter by tags.

            page:
                Page number (None = first page).

        Returns
        -------
        Normalized schema (see BasePlatform.get_run_history).

        Raises
        ------
        PlatformAuthError
            If the client is not authenticated.

        PlatformAPIError
            If the API returns an error response.
        """
        self._require_auth()

        endpoint = f"{self.BASE_URL}/insights/run_history_bots/"
        payload  = {
            "id":        process_id,
            "time_zone": time_zone,
            "page_size": page_size,
            "tags":      tags,
        }
        params = {"page": page} if page is not None else {}

        raw = await self._post(endpoint, payload, params)
        return self._normalize_run_history(raw)

    def _normalize_run_history(self, raw: Dict) -> Dict[str, Any]:
        """
        Normalize the Cloud RPA run history.

        Cloud returns `results` as a direct list containing:

            - "id"        → run_id
            - "bot_id"    → process_id (if available, otherwise uses "id")
            - "run_state" → run_state
            - "start_run" → start_run
            - "end_run"   → end_run
        """
        normalized = []
        for item in raw.get("results", []):
            normalized.append({
                "process_id": item.get("bot_id", item.get("id")),
                "run_id":     item.get("id"),
                "run_state":  item.get("run_state"),
                "start_run":  item.get("start_run"),
                "end_run":    item.get("end_run"),
                "details":    item.get("details"),
            })

        return {
            "count":   raw.get("count", 0),
            "next":    raw.get("next"),
            "results": normalized,
        }

    # ------------------------------------------------------------------
    # RPA — Transacciones
    # ------------------------------------------------------------------

    async def get_transactions(
        self,
        run_id: int,
        page_size: int = 100,
        is_paginated: int = 1,
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve transactions of an RPA execution in Cloud.

        Args:
            run_id:
                Execution ID.

            page_size:
                Number of records per page.

            is_paginated:
                1 = paginated, 0 = return all at once.

            page:
                Page number.

        Returns
        -------
        Normalized schema (see BasePlatform.get_transactions).

        Raises
        ------
        PlatformAuthError
            If the client is not authenticated.

        PlatformNotFoundError
            No transactions available (404).

        PlatformAPIError
            If the API returns an error response.
        """
        self._require_auth()

        endpoint = f"{self.BASE_URL}/insights/transactions_table_run_history/"
        payload  = {
            "id":           run_id,
            "page_size":    page_size,
            "is_paginated": is_paginated,
        }
        params = {"page": page} if page is not None else {}

        raw = await self._post(endpoint, payload, params)
        return self._normalize_transactions(raw)

    def _normalize_transactions(self, raw: Dict) -> Dict[str, Any]:
        """Normalize the Cloud RPA transactions response."""
        return {
            "count_data":           raw.get("count_data", 0),
            "complete_count":       raw.get("complete_count", 0),
            "failed_count":         raw.get("failed_count", 0),
            "completed_percentage": raw.get("completed_percentage", 0.0),
            "failed_percentage":    raw.get("failed_percentage", 0.0),
            "data":                 raw.get("data", {}),
        }

    # ------------------------------------------------------------------
    # Agent — Historial de ejecuciones
    # ------------------------------------------------------------------

    async def get_agent_run_history(
        self,
        process_id: str,
        time_zone: str = "America/Mexico_City",
        page_size: int = 10,
        search_term: str = "",
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve the execution history of an agent in Cloud.

        Endpoint:
            POST https://api.beecker.ai/api/agents/run_history/

        Payload:
            {
                "agent_id": str,
                "time_zone": str,
                "page_size": int,
                "search_term": str
            }

        Args:
            process_id:
                Agent ID.

            time_zone:
                Time zone used for date formatting.

            page_size:
                Number of records per page.

            search_term:
                Search filter.

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
            If the API returns an error response.
        """
        self._require_auth()

        endpoint = f"{self.AGENT_BASE_URL}/agents/run_history/"
        payload  = {
            "agent_id":    process_id,
            "time_zone":   time_zone,
            "page_size":   page_size,
            "search_term": search_term,
        }
        params = {"page": page} if page is not None else {}

        raw = await self._post(endpoint, payload, params)
        return self._normalize_agent_run_history(raw, process_id)

    def _normalize_agent_run_history(
        self, raw: Dict, process_id: str
    ) -> Dict[str, Any]:
        """
        Normalize the Cloud agent run history.

        Raw structure:

        {
            "count": int,
            "next":  str | None,
            "total_pages":  int,
            "current_page": int,
            "results": {
                "headers":  [...],
                "data_row": [
                    {
                        "ID":              int,      → run_id
                        "Execution start": str,      → start_run
                        "Execution end":   str|null, → end_run
                        "Status":          str,      → run_state
                        "Details":         str,      → description
                        ... (remaining fields → extra_fields)
                    },
                    ...
                ]
            }
        }
        """
        data_rows = raw.get("results", {}).get("data_row", [])
        normalized = []

        for row in data_rows:
            extra = {
                k: v for k, v in row.items()
                if k not in _AGENT_CORE_FIELDS and k != "Execution No."
            }

            normalized.append({
                "process_id":   process_id,
                "run_id":       row.get("ID"),
                "run_state":    row.get("Status"),
                "start_run":    row.get("Execution start"),
                "end_run":      row.get("Execution end"),
                "description":  row.get("Details", ""),
                "extra_fields": extra,
            })

        return {
            "count":        raw.get("count", 0),
            "next":         raw.get("next"),
            "total_pages":  raw.get("total_pages", 1),
            "current_page": raw.get("current_page", 1),
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
        Retrieve the execution progress of an agent in Cloud.

        Endpoint:
            POST https://api.beecker.ai/api/agents/get_progress/

        Payload:
            {"execution_id": int}

        Args:
            execution_id:
                Agent execution ID.

        Returns
        -------
        Normalized schema (see BasePlatform.get_agent_progress).

        Raises
        ------
        PlatformAuthError
            If the client is not authenticated.

        PlatformNotFoundError
            If the execution does not exist (404).

        PlatformAPIError
            If the API returns an error response.
        """
        self._require_auth()

        endpoint = f"{self.AGENT_BASE_URL}/agents/get_progress/"
        payload  = {"execution_id": execution_id}

        raw_stages: List[Dict] = await self._post(endpoint, payload)
        return self._normalize_agent_progress(raw_stages, execution_id)

    def _normalize_agent_progress(
        self, raw_stages: List[Dict], execution_id: int
    ) -> Dict[str, Any]:
        """
        Normalize the response of agent execution progress.

        Raw structure (list):

        [
            {
                "name":      str,
                "stage":     str,   # 'completed' | 'pending' | 'in progress'
                "active":    float,
                "start_run": str,
                "end_run":   str,
                "descData": [
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

        Logic for is_finished:
            All stages must have stage='completed'.
        """
        stages = []
        for s in raw_stages:
            steps = [
                {
                    "name":      step.get("name"),
                    "status":    step.get("status"),
                    "start_run": step.get("start_run"),
                    "end_run":   step.get("end_run"),
                }
                for step in s.get("descData", [])
            ]
            stages.append({
                "name":      s.get("name"),
                "stage":     s.get("stage"),
                "active":    s.get("active"),
                "start_run": s.get("start_run"),
                "end_run":   s.get("end_run"),
                "steps":     steps,
            })

        total_stages     = len(stages)
        completed_stages = sum(1 for s in stages if s["stage"] == "completed")
        is_finished      = total_stages > 0 and completed_stages == total_stages
        progress_pct     = (completed_stages / total_stages * 100) if total_stages else 0.0

        current_stage = None
        current_step  = None
        if not is_finished:
            for s in stages:
                if s["stage"] != "completed":
                    current_stage = s["name"]
                    for step in s["steps"]:
                        if step["status"] in ("pending", "in progress"):
                            current_step = step["name"]
                            break
                    break

        return {
            "execution_id":        execution_id,
            "total_stages":        total_stages,
            "completed_stages":    completed_stages,
            "progress_percentage": round(progress_pct, 2),
            "is_finished":         is_finished,
            "current_stage":       current_stage,
            "current_step":        current_step,
            "stages":              stages,
        }