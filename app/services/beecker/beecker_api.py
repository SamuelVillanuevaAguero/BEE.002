"""
Beecker API main client.

Acts as a facade over the active platform (Cloud or Hub).
The developer specifies the platform when instantiating the client; from that
point on, all calls become transparent and independent of the underlying domain.

Usage:
>>> api = BeeckerAPI(platform='cloud')
>>> await api.login("[user@beecker.ai](mailto:user@beecker.ai)", "secret")
>>>
>>> # RPA
>>> history      = await api.get_run_history("104")
>>> transactions = await api.get_transactions(run_id=161057)
>>>
>>> # Agents (Cloud)
>>> agent_history = await api.get_agent_run_history("1")
>>> progress      = await api.get_agent_progress(execution_id=35239)
>>>
>>> # Agent status by time interval (Cloud)
>>> status = await api.get_agent_status(
...     agent_id="18",
...     start_datetime="2026-02-20 00:00:00",
...     end_datetime="2026-02-20 23:59:59",
... )
>>>
>>> # Agents (Hub)
>>> api_hub = BeeckerAPI(platform='hub')
>>> await api_hub.login("[user@beecker.ai](mailto:user@beecker.ai)", "secret")
>>> menu         = await api_hub.get_agent_menu()
>>> agent_history = await api_hub.get_agent_run_history("7")
"""


from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import logging
from difflib import SequenceMatcher

from .platforms import (
    PLATFORM_MAP,
    BasePlatform,
    PlatformError,
    PlatformAuthError,
    PlatformConnectionError,
    PlatformNotFoundError,
    PlatformAPIError,
)

logger = logging.getLogger(__name__)


class BeeckerAPIError(Exception):
    """
    Public exception raised by the BeeckerAPI client.

    This exception wraps internal platform exceptions (PlatformError and its
    subclasses) so that higher layers (RPA monitoring, agent monitoring, etc.)
    do not depend on the internal implementation details of each platform.
    """

# ── Excepción nueva — agregar junto a BeeckerAPIError ─────────────────────────

class RunNotYetAvailableError(Exception):
    """
    Se lanza cuando el run_id aún no aparece en el historial de Beecker.
    Indica que la ejecución terminó pero Beecker todavía no la registró.
    """
    def __init__(self, run_id: int, bot_id: str):
        self.run_id = run_id
        self.bot_id = bot_id
        super().__init__(
            f"run_id={run_id} para bot_id='{bot_id}' aún no disponible en el historial de Beecker."
        )

class BeeckerAPI:
    """
    Main facade used to interact with the Beecker API.

    All HTTP communication is delegated to the active platform
    implementation (Cloud or Hub) while exposing a unified interface
    independent of the underlying domain.

    Attributes
    ----------
    platform_name : str
        Name of the active platform ("cloud" or "hub").

    _platform : BasePlatform
        Internal platform implementation used to execute API calls.
    """

    def __init__(self, platform: str = "cloud"):
        self._platform: BasePlatform = self._build_platform(platform)
        self.platform_name: str      = platform.lower()

    # ------------------------------------------------------------------
    # Gestión de plataforma
    # ------------------------------------------------------------------

    @staticmethod
    def _build_platform(platform: str) -> BasePlatform:
        """Instantiate the platform implementation associated with the given alias."""
        key = platform.lower().strip()
        platform_cls = PLATFORM_MAP.get(key)
        if platform_cls is None:
            raise ValueError(
                f"Plataforma '{platform}' no reconocida. "
                f"Opciones válidas: {list(PLATFORM_MAP.keys())}"
            )
        return platform_cls()

    def switch_platform(self, platform: str) -> None:
        """
        Switch the active platform.

        IMPORTANT:
        After switching platforms, `login()` must be called again because
        authentication tokens are not shared between domains.
        """
        self._platform     = self._build_platform(platform)
        self.platform_name = platform.lower()
        logger.info(
            f"[BeeckerAPI] Platform changed to '{self.platform_name}'. "
            "Remember to call login() again."
        )

    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate against the active Beecker platform.

        Args:
            email:
                User email.

            password:
                User password.

        Returns
        -------
        dict
            Authentication tokens returned by the platform:
            {"access_token": str, "refresh_token": str}

        Raises
        ------
        BeeckerAPIError
            If authentication fails.
        """
        try:
            return await self._platform.login(email, password)
        except PlatformError as e:
            raise BeeckerAPIError(f"Error al autenticar en '{self.platform_name}': {e}")

    def is_authenticated(self) -> bool:
        """Return True if the client is authenticated with the active platform."""
        return self._platform.is_authenticated()

    # ------------------------------------------------------------------
    # RPA — Historial de ejecuciones
    # ------------------------------------------------------------------

    async def get_run_history(
        self,
        bot_id: str,
        time_zone: str = "America/Mexico_City",
        page_size: int = 10,
        tags: str = "",
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve the execution history of an RPA bot.

        Args:
            bot_id:
                ID of the RPA bot.

            time_zone:
                Time zone used for timestamps.

            page_size:
                Number of records per page.

            tags:
                Optional tag filter.

            page:
                Page number (None = first page).

        Returns
        -------
        dict
            Normalized response containing execution history
            (count, next page reference, results list).

        Raises
        ------
        BeeckerAPIError
            If the request fails.
        """
        try:
            return await self._platform.get_run_history(
                process_id=bot_id,
                time_zone=time_zone,
                page_size=page_size,
                tags=tags,
                page=page,
            )
        except PlatformError as e:
            raise BeeckerAPIError(f"Error al obtener historial del bot '{bot_id}': {e}")

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
                1 = paginated response, 0 = retrieve everything at once.

            page:
                Page number.

        Raises
        ------
        BeeckerAPIError
            If the request fails.
        """
        try:
            return await self._platform.get_transactions(
                run_id=run_id,
                page_size=page_size,
                is_paginated=is_paginated,
                page=page,
            )
        except PlatformNotFoundError as e:
            raise BeeckerAPIError(f"404 - Transacciones no encontradas para run_id={run_id}: {e}")
        except PlatformError as e:
            raise BeeckerAPIError(f"Error al obtener transacciones de run_id={run_id}: {e}")

    async def get_all_transactions(
        self,
        run_id: int,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Retrieve ALL transactions of an execution by iterating through every page.

        Args:
            run_id:
                Execution ID.

            page_size:
                Number of records per page.

        Returns
        -------
        dict
            {
                "transactions": list,
                "headers": list,
                "statistics": dict,
                "total_transactions": int
            }
        """
        all_transactions = []
        final_stats      = {}
        current_page     = 1
        last_response    = {}

        while True:
            response      = await self.get_transactions(run_id=run_id, page_size=page_size, page=current_page)
            last_response = response

            if not final_stats:
                final_stats = {
                    "count_data":           response.get("count_data"),
                    "completed_percentage": response.get("completed_percentage"),
                    "failed_percentage":    response.get("failed_percentage"),
                    "failed_count":         response.get("failed_count"),
                    "complete_count":       response.get("complete_count"),
                }

            data_raw = (
                response.get("data", {})
                        .get("results", {})
                        .get("data_raw", [])
            )
            all_transactions.extend(data_raw)

            if not response.get("data", {}).get("next"):
                break
            current_page += 1

        return {
            "transactions":       all_transactions,
            "headers":            last_response.get("data", {}).get("results", {}).get("headers", []),
            "statistics":         final_stats,
            "total_transactions": len(all_transactions),
        }

    async def get_run_summary(self, bot_id: str) -> Dict[str, Any]:
        """
        Retrieve a quick summary of the most recent RPA executions of a process.

            Args:
                bot_id:
                    ID of the RPA bot.

            Returns
            -------
            dict
                {
                    "process_id": str,
                    "total_executions": int,
                    "latest_executions": list,
                    "last_run": dict | None,
                    "in_progress": bool
                }
            """
        history = await self.get_run_history(bot_id, page_size=5)
        results = history.get("results", [])

        return {
            "process_id":        bot_id,
            "total_executions":  history.get("count", 0),
            "latest_executions": results,
            "last_run":          results[0] if results else None,
            "in_progress":       any(r.get("run_state") == "in progress" for r in results),
        }

    async def get_execution_performance_analysis(
        self,
        bot_id: str,
        min_completion_percentage: float = 90.0,
        max_executions: int = 3,
        min_execution: int = 2,
        time_zone: str = "America/Mexico_City",
        exclude_run_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Analyze the performance of completed RPA executions.

        This method searches for the first N executions whose completion
        percentage is above the specified threshold and calculates the
        average duration per transaction.

        Args:
            bot_id:
                RPA bot identifier.

            min_completion_percentage:
                Minimum completion percentage required.

            max_executions:
                Maximum number of executions used to compute the average.

            min_execution:
                Minimum acceptable executions before early exit.

            time_zone:
                Time zone used for API calls.

            exclude_run_id:
                Optional execution ID excluded from the analysis.
        """
        qualified_executions = []
        analyzed_count       = 0
        current_page         = 1

        while len(qualified_executions) < max_executions:
            history = await self.get_run_history(
                bot_id=bot_id,
                time_zone=time_zone,
                page_size=10,
                page=current_page,
            )
            results = history.get("results", [])
            if not results:
                break

            for run in results:
                analyzed_count += 1
                run_id    = str(run.get("run_id", ""))
                run_state = (run.get("run_state") or "").lower()

                if exclude_run_id and str(exclude_run_id) == run_id:
                    continue

                if run_state not in ("completed", "failed"):
                    continue

                transactions = await self.get_transactions(run_id=int(run_id))
                pct          = transactions.get("completed_percentage", 0.0) or 0.0

                if pct < min_completion_percentage:
                    continue

                start = self._parse_datetime_flexible(run.get("start_run", ""))
                end   = self._parse_datetime_flexible(run.get("end_run", ""))

                if start and end:
                    elapsed_minutes  = (end - start).total_seconds() / 60
                    total_tx         = transactions.get("count_data", 1) or 1
                    avg_min_per_tx   = elapsed_minutes / total_tx
                else:
                    elapsed_minutes  = 0.0
                    avg_min_per_tx   = 0.0

                qualified_executions.append({
                    "run_id":                      run_id,
                    "run_state":                   run_state,
                    "completion_percentage":        pct,
                    "elapsed_minutes":              elapsed_minutes,
                    "total_transactions":           transactions.get("count_data", 0),
                    "avg_minutes_per_transaction":  avg_min_per_tx,
                })

                if len(qualified_executions) >= max_executions:
                    break

                if len(qualified_executions) >= min_execution:
                    break

            if not history.get("next"):
                break
            current_page += 1

        list_avg    = [e["avg_minutes_per_transaction"] for e in qualified_executions]
        avg_minutes = sum(list_avg) / len(list_avg) if list_avg else 0.0

        return {
            "process_id":                bot_id,
            "platform":                  self.platform_name,
            "analyzed_executions":       analyzed_count,
            "qualified_executions":      len(qualified_executions),
            "min_completion_percentage": min_completion_percentage,
            "avg_minutes_transaction":   avg_minutes,
            "executions":                qualified_executions,
        }

    async def get_agent_menu(self) -> Dict[str, Any]:
        """
        Retrieve the list of agents available in the active platform.

        This endpoint is only available in Hub.
        Cloud does not expose this endpoint.

        Raises
        ------
        BeeckerAPIError
            If the request fails or the platform does not support the method.
        """
        try:
            return await self._platform.get_agent_menu()
        except NotImplementedError:
            raise BeeckerAPIError(
                f"get_agent_menu() no está disponible en la plataforma '{self.platform_name}'. "
                "Este método solo está implementado para Hub."
            )
        except PlatformError as e:
            raise BeeckerAPIError(f"Error al obtener menú de agentes: {e}")

    async def get_agent_run_history(
        self,
        agent_id: str,
        time_zone: str = "America/Mexico_City",
        page_size: int = 10,
        search_term: str = "",
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve the execution history of an agent.

        Args:
            agent_id:
                Agent identifier.

            time_zone:
                Time zone used for timestamps.

            page_size:
                Number of records per page.

            search_term:
                Optional search filter.

            page:
                Page number (None = first page).

        Raises
        ------
        BeeckerAPIError
            If the request fails.
        """
        try:
            return await self._platform.get_agent_run_history(
                process_id=agent_id,
                time_zone=time_zone,
                page_size=page_size,
                search_term=search_term,
                page=page,
            )
        except PlatformError as e:
            raise BeeckerAPIError(f"Error al obtener historial del agente '{agent_id}': {e}")

    async def get_all_agent_run_history(
        self,
        agent_id: str,
        time_zone: str = "America/Mexico_City",
        page_size: int = 100,
        search_term: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Retrieve ALL executions of an agent by iterating through all pages.

        Returns
        -------
        list
            List containing all normalized execution results.
        """
        all_results  = []
        current_page = 1

        while True:
            response = await self.get_agent_run_history(
                agent_id=agent_id,
                time_zone=time_zone,
                page_size=page_size,
                search_term=search_term,
                page=current_page,
            )
            all_results.extend(response.get("results", []))
            if not response.get("next"):
                break
            current_page += 1

        return all_results

    async def get_agent_progress(self, execution_id: int) -> Dict[str, Any]:
        """
        Retrieve detailed progress information for a specific agent execution.

        Args:
            execution_id:
                Agent execution ID.

        Raises
        ------
        BeeckerAPIError
            If the request fails or the execution does not exist.
        """
        try:
            return await self._platform.get_agent_progress(execution_id=execution_id)
        except NotImplementedError:
            raise BeeckerAPIError(
                f"get_agent_progress() no está implementado en la plataforma "
                f"'{self.platform_name}'."
            )
        except PlatformNotFoundError as e:
            raise BeeckerAPIError(
                f"404 - Ejecución no encontrada para execution_id={execution_id}: {e}"
            )
        except PlatformError as e:
            raise BeeckerAPIError(
                f"Error al obtener progreso de execution_id={execution_id}: {e}"
            )

    async def get_agent_status(
        self,
        agent_id: str,
        start_datetime: str,
        end_datetime: Optional[str] = None,
        time_zone: str = "America/Mexico_City",
        page_size: int = 100,
        include_progress: bool = True,
    ) -> Dict[str, Any]:
        """
        Analyze the status of an agent within a given time interval.

        Args:
            agent_id:
                Agent identifier.

            start_datetime:
                Start of the interval (inclusive).

            end_datetime:
                End of the interval (inclusive). Default: current time.

            time_zone:
                Time zone used when retrieving execution history.

            page_size:
                Number of records per page.

            include_progress:
                If True, fetch execution progress for each run.

        Raises
        ------
        BeeckerAPIError
            If authentication fails or execution history cannot be retrieved.

        ValueError
            If the provided datetime values cannot be parsed.
        """
        warnings: List[str] = []

        # ── 1. Parsear intervalo ──────────────────────────────────────────────
        interval_start = self._parse_datetime_flexible(start_datetime)
        if interval_start is None:
            raise ValueError(
                f"No se pudo parsear start_datetime='{start_datetime}'. "
                "Formatos aceptados: 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DDTHH:MM:SS', 'YYYY-MM-DD'."
            )

        if end_datetime:
            interval_end = self._parse_datetime_flexible(end_datetime)
            if interval_end is None:
                raise ValueError(
                    f"No se pudo parsear end_datetime='{end_datetime}'. "
                    "Formatos aceptados: 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DDTHH:MM:SS', 'YYYY-MM-DD'."
                )
        else:
            interval_end = datetime.now()

        interval_start_str = interval_start.strftime("%Y-%m-%d %H:%M:%S")
        interval_end_str   = interval_end.strftime("%Y-%m-%d %H:%M:%S")

        logger.info(
            f"[{self.platform_name.upper()}] get_agent_status "
            f"agent_id={agent_id} | {interval_start_str} → {interval_end_str}"
        )

        # ── 2. Recolectar ejecuciones en el intervalo ─────────────────────────
        executions_in_range: List[Dict] = []
        current_page = 1
        stop_paging  = False

        while not stop_paging:
            try:
                history = await self.get_agent_run_history(
                    agent_id=agent_id,
                    time_zone=time_zone,
                    page_size=page_size,
                    page=current_page,
                )
            except BeeckerAPIError as e:
                raise BeeckerAPIError(
                    f"Error al obtener historial del agente '{agent_id}': {e}"
                )

            results = history.get("results", [])
            if not results:
                break

            for run in results:
                start_run_str = run.get("start_run", "")
                run_dt = self._parse_datetime_flexible(start_run_str)

                if run_dt is None:
                    warnings.append(
                        f"run_id={run.get('run_id')} — no se pudo parsear "
                        f"start_run='{start_run_str}', omitido."
                    )
                    continue

                if run_dt < interval_start:
                    stop_paging = True
                    break

                if run_dt <= interval_end:
                    executions_in_range.append(run)

            if not history.get("next"):
                break
            current_page += 1

        logger.info(f"  → {len(executions_in_range)} executions found in the interval.")

        # ── 3. Contadores por estado ──────────────────────────────────────────
        STATE_COMPLETED         = "completed"
        STATE_FAILED            = "failed"
        STATE_IN_PROGRESS       = "in progress"
        STATE_SUCCESSFUL        = "successful"
        STATE_IN_REVIEW         = "in review"
        STATE_PENDING_APPROVAL  = "pending approval"

        counters = {
            STATE_COMPLETED:        0,
            STATE_FAILED:           0,
            STATE_IN_PROGRESS:      0,
            STATE_SUCCESSFUL:       0,
            STATE_IN_REVIEW:        0,
            STATE_PENDING_APPROVAL: 0,
            "_other":               0,
        }

        for run in executions_in_range:
            state = (run.get("run_state") or "").lower().strip()
            if state in counters:
                counters[state] += 1
            else:
                counters["_other"] += 1

        # ── 4. Enriquecer con progreso ────────────────────────────────────────
        enriched_executions = []
        progress_not_available_warned = False

        for run in executions_in_range:
            run_id    = run.get("run_id")
            start_run = run.get("start_run")
            end_run   = run.get("end_run")

            start_dt = self._parse_datetime_flexible(start_run or "")
            end_dt   = self._parse_datetime_flexible(end_run or "")
            elapsed  = round((end_dt - start_dt).total_seconds() / 60, 2) if start_dt and end_dt else 0.0

            progress_fields = {
                "total_stages":        None,
                "completed_stages":    None,
                "progress_percentage": None,
                "is_finished":         None,
                "current_stage":       None,
                "current_step":        None,
                "stages":              None,
            }

            if include_progress and run_id is not None:
                try:
                    prog = await self.get_agent_progress(execution_id=int(run_id))
                    progress_fields = {
                        "total_stages":        prog.get("total_stages"),
                        "completed_stages":    prog.get("completed_stages"),
                        "progress_percentage": prog.get("progress_percentage"),
                        "is_finished":         prog.get("is_finished"),
                        "current_stage":       prog.get("current_stage"),
                        "current_step":        prog.get("current_step"),
                        "stages":              prog.get("stages"),
                    }
                except BeeckerAPIError as e:
                    if "no está implementado" in str(e) and not progress_not_available_warned:
                        progress_not_available_warned = True
                        warnings.append(
                            f"get_agent_progress() no disponible en '{self.platform_name}'. "
                            "El campo 'progress' de todas las ejecuciones quedará en None."
                        )
                    else:
                        warnings.append(f"run_id={run_id} — error al obtener progreso: {e}")

            enriched_executions.append({
                "run_id":          run_id,
                "run_state":       run.get("run_state"),
                "start_run":       start_run,
                "end_run":         end_run,
                "elapsed_minutes": elapsed,
                "description":     run.get("description", ""),
                "extra_fields":    run.get("extra_fields", {}),
                **progress_fields,
            })

        # ── 5. Promedio de duración ───────────────────────────────────────────
        durations = [
            ex["elapsed_minutes"]
            for ex in enriched_executions
            if ex["elapsed_minutes"] > 0
        ]
        avg_duration = round(sum(durations) / len(durations), 2) if durations else None

        return {
            "agent_id":                    agent_id,
            "platform":                    self.platform_name,
            "interval_start":              interval_start_str,
            "interval_end":                interval_end_str,
            "total_executions":            len(executions_in_range),
            "completed_executions":        counters[STATE_COMPLETED],
            "failed_executions":           counters[STATE_FAILED],
            "in_progress_executions":      counters[STATE_IN_PROGRESS],
            "successful_executions":       counters[STATE_SUCCESSFUL],
            "in_review_executions":        counters[STATE_IN_REVIEW],
            "pending_approval_executions": counters[STATE_PENDING_APPROVAL],
            "other_executions":            counters["_other"],
            "avg_duration_minutes":        avg_duration,
            "executions":                  enriched_executions,
            "warnings":                    warnings,
        }

    async def export_transactions_to_json(
        self,
        run_id: int,
        filename: Optional[str] = None,
    ) -> str:
        """
        Export all RPA transactions of an execution to a JSON file.

        Args:
            run_id:
                Execution ID.

            filename:
                Output filename (auto-generated if None).

        Returns
        -------
        str
            Path of the generated file.
        """
        data = await self.get_all_transactions(run_id=run_id)

        if filename is None:
            filename = f"transactions_{run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"[BeeckerAPI] Exported: {filename} ({data['total_transactions']} transactions)")
        return filename

    @staticmethod
    def _parse_datetime_flexible(value: str) -> Optional[datetime]:
        """Attempt to parse a datetime string using several supported formats."""
        if not value:
            return None

        formats = [
            "%b %d, %Y, %I:%M:%S %p",   # Mar 12, 2026, 07:08:13 PM  ← este es el que falta
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d, %H:%M:%S",   # ← NUEVO: formato de la API Cloud para agentes
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value.strip(), fmt)
            except (ValueError, TypeError):
                continue

        return None

    @staticmethod
    def group_errors_by_similarity(
        error_messages: List[str],
        threshold: float = 0.85,
    ) -> List[Dict[str, Any]]:
        """
        Group similar error messages using SequenceMatcher similarity.

        Args:
            error_messages:
                List of error messages.

            threshold:
                Similarity threshold (0–1). Default: 0.85.

        Returns
        -------
        list
            List of grouped errors:
            [
                {
                    "representative": str,
                    "count": int,
                    "messages": list
                }
            ]
        """
        groups: List[Dict] = []

        for msg in error_messages:
            matched = False
            for group in groups:
                ratio = SequenceMatcher(None, msg, group["representative"]).ratio()
                if ratio >= threshold:
                    group["count"] += 1
                    group["messages"].append(msg)
                    matched = True
                    break
            if not matched:
                groups.append({
                    "representative": msg,
                    "count": 1,
                    "messages": [msg],
                })

        return sorted(groups, key=lambda g: g["count"], reverse=True)
    
# ------------------------------------------------------------------
    # RPA — Status completo de una ejecución  (AGREGAR en beecker_api.py)
    # ------------------------------------------------------------------

    async def get_rpa_status(
        self,
        run_id: int,
        bot_id: str,
        avg_minutes_per_transaction: Optional[float] = None,
        similarity_threshold: float = 0.80,
        status_field: str = "status",
        details_field: str = "details",
        failed_value: str = "failed",
    ) -> Dict[str, Any]:
        """
        Devuelve un snapshot completo del estado de una ejecución RPA.

        Combina historial + transacciones para producir un dict compatible
        con RPAMessageBuilder.build().

        Args:
            run_id:                      ID numérico de la ejecución en Beecker.
            bot_id:                      ID del bot (id_beecker, ej. "aec.002").
            avg_minutes_per_transaction: Referencia histórica precomputada (opcional).
            similarity_threshold:        Umbral de similitud para agrupar errores.
            status_field:                Campo de estado en transacciones.
            details_field:               Campo de detalle/error en transacciones.
            failed_value:                Valor que indica fallo en status_field.

        Returns:
            {
                "run_id":                      int,
                "bot_id":                      str,
                "start_run":                   str | None,
                "end_run":                     str | None,
                "elapsed_minutes":             float,
                "run_state":                   str,
                "details":                     str | None,
                "total_transactions":          int,
                "completed_transactions":      int,
                "failed_transactions":         int,
                "completion_percentage":       float,
                "failed_percentage":           float,
                "avg_minutes_per_transaction": float,
                "reference_avg_minutes":       float | None,
                "overtime_flag":               bool | None,
                "error_groups":                list[dict],
            }
        """
        try:
            # ── 1. Buscar el run en el historial ──────────────────────────────
            run_info  = await self._find_run_in_history(bot_id=bot_id, run_id=run_id)
            start_run = run_info.get("start_run")
            end_run   = run_info.get("end_run")
            run_state = run_info.get("run_state", "unknown")
            details   = run_info.get("details")

            # ── 2. Tiempo transcurrido ─────────────────────────────────────────
            elapsed_minutes = self._compute_elapsed_minutes(
                start_run=start_run,
                end_run=end_run,
            )

            # ── 3. Transacciones ───────────────────────────────────────────────
            trans_stats: Dict[str, Any] = {
                "count_data":           0,
                "complete_count":       0,
                "failed_count":         0,
                "completed_percentage": 0.0,
                "failed_percentage":    0.0,
            }
            all_transactions: List[Dict] = []

            if run_state.lower() != "failed":
                try:
                    raw              = await self.get_all_transactions(run_id=run_id)
                    all_transactions = raw.get("transactions", [])
                    stats            = raw.get("statistics", {})
                    trans_stats = {
                        "count_data":           stats.get("count_data", len(all_transactions)),
                        "complete_count":       stats.get("complete_count", 0),
                        "failed_count":         stats.get("failed_count", 0),
                        "completed_percentage": stats.get("completed_percentage", 0.0),
                        "failed_percentage":    stats.get("failed_percentage", 0.0),
                    }
                except BeeckerAPIError as e:
                    if "404" not in str(e):
                        raise

            total_transactions     = trans_stats["count_data"] or 0
            completed_transactions = trans_stats["complete_count"] or 0
            failed_transactions    = trans_stats["failed_count"] or 0
            completion_pct         = trans_stats["completed_percentage"] or 0.0
            failed_pct             = trans_stats["failed_percentage"] or 0.0

            # ── 4. Promedio real de esta ejecución ─────────────────────────────
            avg_current = 0.0
            if total_transactions > 0 and elapsed_minutes > 0:
                avg_current = round(elapsed_minutes / total_transactions, 4)

            # ── 5. Referencia histórica (excluyendo run_id actual) ─────────────
            reference_avg: Optional[float] = avg_minutes_per_transaction
            if reference_avg is None:
                try:
                    analysis  = await self.get_execution_performance_analysis(
                        bot_id=bot_id,
                        min_completion_percentage=90.0,
                        max_executions=3,
                        exclude_run_id=int(run_id),
                    )
                    ref = analysis.get("avg_minutes_transaction", 0.0)
                    reference_avg = ref if ref > 0 else None
                except BeeckerAPIError:
                    reference_avg = None

            # ── 6. Bandera de overtime ─────────────────────────────────────────
            overtime_flag: Optional[bool] = None
            if reference_avg is not None and total_transactions > 0 and elapsed_minutes > 0:
                expected      = reference_avg * total_transactions
                overtime_flag = elapsed_minutes > expected

            # ── 7. Agrupación de errores ───────────────────────────────────────
            error_groups = self._group_errors(
                transactions=all_transactions,
                status_field=status_field,
                details_field=details_field,
                failed_value=failed_value,
                threshold=similarity_threshold,
            )

            return {
                "run_id":                      run_id,
                "bot_id":                      bot_id,
                "start_run":                   start_run,
                "end_run":                     end_run,
                "elapsed_minutes":             elapsed_minutes,
                "run_state":                   run_state,
                "details":                     details,
                "total_transactions":          total_transactions,
                "completed_transactions":      completed_transactions,
                "failed_transactions":         failed_transactions,
                "completion_percentage":       completion_pct,
                "failed_percentage":           failed_pct,
                "avg_minutes_per_transaction": avg_current,
                "reference_avg_minutes":       reference_avg,
                "overtime_flag":               overtime_flag,
                "error_groups":                error_groups,
            }

        except BeeckerAPIError:
            raise
        except RunNotYetAvailableError:   # ← agregar ANTES del except genérico
            raise
        except Exception as e:
            raise BeeckerAPIError(f"Error al obtener status de run_id={run_id}: {e}")

    async def _find_run_in_history(self, bot_id: str, run_id: int, max_pages: int = 10) -> Dict[str, Any]:
            run_id_str = str(run_id)
            logger.info(f"🔍 Buscando run_id={run_id_str} en historial de bot_id='{bot_id}'")

            for page in range(1, max_pages + 1):
                try:
                    history = await self.get_run_history(bot_id=bot_id, page_size=50, page=page)
                except BeeckerAPIError:
                    break

                results = history.get("results", [])
                logger.info(f"  Página {page}: {len(results)} resultados — run_ids: {[r.get('run_id') for r in results]}")

                for run in results:
                    if str(run.get("run_id", "")) == run_id_str:
                        return run

                if not history.get("next"):
                    break

            # ── Antes retornaba dict vacío; ahora avisa explícitamente ────────────
            logger.warning(f"  ⚠️ run_id={run_id} NO encontrado para bot_id='{bot_id}'")
            raise RunNotYetAvailableError(run_id=run_id, bot_id=bot_id)
    
    def _compute_elapsed_minutes(
        self,
        start_run: Optional[str],
        end_run: Optional[str],
    ) -> float:
        """Calcula minutos entre start_run y end_run (usa now() si end_run es None)."""
        from zoneinfo import ZoneInfo
        from app.core.config import settings

        start_dt = self._parse_datetime_flexible(start_run)
        if start_dt is None:
            return 0.0

        if end_run:
            ref_dt = self._parse_datetime_flexible(end_run)
            if ref_dt is None:
                return 0.0
        else:
            tz = ZoneInfo(settings.SCHEDULER_TIMEZONE)
            ref_dt = datetime.now(tz=tz).replace(tzinfo=None)

        return round(max((ref_dt - start_dt).total_seconds() / 60, 0.0), 2)

    def _group_errors(
        self,
        transactions: List[Dict],
        status_field: str,
        details_field: str,
        failed_value: str,
        threshold: float,
    ) -> List[Dict[str, Any]]:
        """Agrupa mensajes de error por similitud semántica (SequenceMatcher)."""
        groups: List[Dict[str, Any]] = []

        for txn in transactions:
            if txn.get(status_field) != failed_value:
                continue
            msg = str(txn.get(details_field, "")).strip()
            if not msg:
                continue

            matched = False
            for group in groups:
                ratio = SequenceMatcher(None, group["representative"], msg).ratio()
                if ratio >= threshold:
                    group["count"] += 1
                    group["indices"].append(txn.get("n"))
                    matched = True
                    break

            if not matched:
                groups.append({
                    "representative": msg,
                    "count":          1,
                    "indices":        [txn.get("n")],
                })

        groups.sort(key=lambda g: g["count"], reverse=True)
        return groups