"""
monitoring_service.py
=====================
Main monitoring agent responsible for orchestrating authentication across all
platforms, resolving configuration resources at startup (emails → Slack user IDs,
client name → FreshDesk URL), and exposing notification methods.

Configuration loading flows:
    · load_config(RPAConfig)         → initializes monitoring for RPA bots.
    · load_agent_config(AgentConfig) → initializes monitoring for agents.

Public notification methods for RPA:
    - send_initial_rpa(bot_id, run_id) → Execution start message.
    - send_status_rpa(run_id, bot_id)  → Full execution snapshot with alerts.

Public notification methods for Agents:
    - send_status_agent(agent_id)      → Agent summary for a given interval.

Error handling:
    - Any exception raised in public methods is reported to CHANNEL_ERROR in Slack.
    - SlackErrorAuthenticate is NOT reported (Slack may not be available).
    - After reporting the error, the exception is always re-raised for the caller.
"""

from __future__ import annotations

import asyncio
import logging
import os
import traceback as tb
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv

from app.services.beecker import BeeckerAPI, BeeckerAPIError
from app.services.freshdesk.freshdesk_api import FreshDeskAPI, FreshDeskAuthenticateError
from app.services.slack.slack_api import SlackAPI, SlackErrorAuthenticate
from app.services.config.rpa_config import RPAConfig
from app.services.config.agent_config import AgentConfig
from app.services.slack_message_builder import RPAMessageBuilder
from app.services.agent_message_builder import AgentMessageBuilder
from app.services.chart_builder import RPAChartBuilder, AgentChartBuilder
from app.services.beecker.beecker_api import RunNotYetAvailableError

load_dotenv()

logger = logging.getLogger(__name__)

_RPA_IN_PROGRESS_STATES = {"in progress", "pending"}


# ── Mensajes de error ─────────────────────────────────────────────────────────

class _ErrorMessages:
    """Builds error messages sent to the monitoring incident Slack channel."""

    CHANNEL_ERROR: str = os.getenv("CHANNEL_ERROR", "")

    @staticmethod
    def build(
        issue: str,
        bot_name: Optional[str] = None,
        context: Optional[str] = None,
        traceback_str: Optional[str] = None,
    ) -> str:
        now        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name_label = bot_name.upper() if bot_name else "(No identificado)"

        lines = [
            "¡Atención equipo!",
            f"*Se detectó un error en el agente monitor* — `{name_label}`",
            f"*Hora:* {now}",
        ]
        if context:
            lines += ["", f"*Contexto:* `{context}`"]
        if issue:
            lines += ["", f"*Error:* {issue}"]
        if traceback_str:
            lines += ["", f"```{traceback_str[-1500:]}```"]

        return "\n".join(lines)


# ── MonitoringAgent ───────────────────────────────────────────────────────────

class MonitoringAgent:
    """
    Main monitoring orchestrator.

    All public methods are asynchronous and must run inside an event loop.

    Usage for RPA::

        config = RPAConfig(bot_name="AIN.002", process_name="Order entry")
        agent  = MonitoringAgent()
        await agent.load_config(config)
        await agent.send_initial_rpa(bot_id="104", run_id="165685")
        await agent.send_status_rpa(run_id=162389, bot_id="104")

    Usage for Agents::

        config = AgentConfig(
            agent_name="LUCAS",
            process_name="Candidate processor",
            execution_unit="candidates",
            execution_unit_singular="candidate",
        )
        agent = MonitoringAgent()
        await agent.load_agent_config(config)
        await agent.send_status_agent(agent_id="18")
    """

    __rpa_config:    Optional[RPAConfig]
    __agent_config:  Optional[AgentConfig]
    __api_beecker:   Optional[BeeckerAPI]   # RPA
    __agent_beecker: Optional[BeeckerAPI]   # Agent
    __api_slack:     Optional[SlackAPI]
    __api_freshdesk: Optional[FreshDeskAPI]

    _mention_ids:         List[str]
    _agent_mention_ids:   List[str]
    _freshdesk_url:       Optional[str]
    _agent_freshdesk_url: Optional[str]

    def __init__(self) -> None:
        self.__rpa_config        = None
        self.__agent_config      = None
        self.__api_beecker       = None
        self.__agent_beecker     = None
        self.__api_slack         = None
        self.__api_freshdesk     = None

        self._mention_ids         = []
        self._agent_mention_ids   = []
        self._freshdesk_url       = None
        self._agent_freshdesk_url = None

        self._rpa_message_builder   = RPAMessageBuilder()
        self._agent_message_builder = AgentMessageBuilder()
        self._rpa_chart_builder     = RPAChartBuilder()
        self._agent_chart_builder   = AgentChartBuilder()

    # ── Carga de configuración ────────────────────────────────────────────────

    async def load_config(self, config: RPAConfig) -> None:
        """
        Load the RPA configuration and authenticate all required platforms.

        Raises:
            ValueError: If required configuration fields are missing.
            SlackErrorAuthenticate: If the Slack token is invalid.
            BeeckerAPIError: If Beecker authentication fails.
        """
        from app.utils.session_manager import beecker_session, slack_session, freshdesk_session

        config.validate()
        self.__rpa_config = config

        # Slack — singleton, solo autentica la primera vez
        self.__api_slack = await slack_session.get_api(config.token_slack)
        if config.mention_emails:
            self._mention_ids = await self._resolve_mention_ids(config.mention_emails, "RPA")

        # Beecker — singleton con auto-refresh
        api = BeeckerAPI(platform=config.platform)
        await api.login(config.email_dash, config.password_dash)
        self.__api_beecker = api

        # FreshDesk — singleton
        if config.username_freshdesk and config.password_freshdesk:
            self.__api_freshdesk = await freshdesk_session.get_api(
                config.username_freshdesk, config.password_freshdesk
            )

    async def load_agent_config(self, config: AgentConfig) -> None:
        """
        Load the Agent configuration and authenticate all required platforms.

        If Slack is already authenticated (from load_config()), it is reused.

        Raises:
            ValueError: If required configuration fields are missing.
            SlackErrorAuthenticate: If the Slack token is invalid.
            BeeckerAPIError: If Beecker authentication fails.
        """
        try:
            config.validate()
            self.__agent_config = config

            if not self._is_slack_authenticated():
                await self._login_slack(config.token_slack)

            if config.mention_emails:
                self._agent_mention_ids = await self._resolve_mention_ids(
                    config.mention_emails, context="Agente"
                )

            await self._login_beecker(
                email=config.email_dash,
                password=config.password_dash,
                platform=config.platform,
                target="_agent",
            )

            if config.enable_freshdesk_link and config.freshdesk_client_name:
                if self.__api_freshdesk is None:
                    if config.username_freshdesk and config.password_freshdesk:
                        await self._login_fresh(
                            username=config.username_freshdesk,
                            password=config.password_freshdesk,
                        )
                if self.__api_freshdesk is not None:
                    self._agent_freshdesk_url = await self._resolve_freshdesk_url(
                        client_name=config.freshdesk_client_name,
                        status_id=config.freshdesk_status_id,
                    )

        except SlackErrorAuthenticate:
            logger.error("Fallo de autenticación en Slack. No es posible reportar al canal de errores.")
            raise

        except Exception as e:
            await self._send_error_to_slack(
                issue=str(e),
                context="load_agent_config",
                traceback_str=tb.format_exc(),
            )
            raise

    # ── Métodos públicos RPA ──────────────────────────────────────────────────

    async def send_initial_rpa(self, bot_id: str, run_id: str | None = None) -> None:
        """
        Send the execution start notification to the configured Slack channel.
        Includes the #run_id to identify the specific execution.

        Args:
            bot_id:  id_dashboard del bot (para logs).
            run_id:  Identificador numérico de la ejecución (ej: "100036").

        Args:
            bot_id: Numeric dashboard ID used for logging.
            run_id: Execution run ID to display in the message (e.g. "165685"). Optional.

        Raises:
            RuntimeError: If load_config() has not been called previously.
        """
        try:
            if self.__rpa_config is None or self.__api_beecker is None:
                raise RuntimeError("Debes llamar a load_config() antes de send_initial_rpa().")

            message = self._rpa_message_builder.build_initial(
                bot_id=self.__rpa_config.bot_name,
                bot_name=self.__rpa_config.process_name,
                run_id=run_id,
            )
            await self.__api_slack.send_message(
                channel_name=self.__rpa_config.channel_name,
                message=message,
            )
            logger.info(
                f"Mensaje de inicio enviado para bot_id={bot_id} | run_id={run_id} "
                f"en canal {self.__rpa_config.channel_name}."
            )

        except Exception as e:
            await self._send_error_to_slack(
                issue=str(e),
                context=f"send_initial_rpa(bot_id={bot_id}, run_id={run_id})",
                traceback_str=tb.format_exc(),
            )
            raise

    async def send_status_rpa(self, run_id: int, bot_id: str) -> str:
        """
        Retrieve the current RPA execution status and send a single-execution
        notification to Slack. Used by bee_informa.

        Raises:
            RuntimeError: If load_config() has not been called previously.
        """
        try:
            if self.__rpa_config is None or self.__api_beecker is None:
                raise RuntimeError("Debes llamar a load_config() antes de send_status_rpa().")

            config = self.__rpa_config

            # 1. Obtener status completo desde Beecker
            status = await self.__api_beecker.get_rpa_status(run_id=run_id, bot_id=bot_id)

            # 2. Aplicar flag de overtime
            if not config.enable_overtime_check:
                status = {**status, "overtime_flag": False}

            # 3. Construir mensaje
            message = self._rpa_message_builder.build(
                bot_id=config.bot_name,
                bot_name=config.process_name,
                status_dict=status,
                transaction_unit=config.transaction_unit,
                transaction_unit_singular=config.transaction_unit_singular,
                show_error_groups=config.show_error_groups,
                max_error_groups=config.max_error_groups,
                mention_user_ids=self._mention_ids,
                freshdesk_url=self._get_effective_freshdesk_url(),
            )

            # 4. Enviar mensaje de texto
            await self.__api_slack.send_message(
                channel_name=config.channel_name,
                message=message,
            )
            logger.info(
                f"Mensaje de estado enviado para run_id={run_id}, bot_id={bot_id} "
                f"en canal {config.channel_name}."
            )

            # 5. Gráfica — solo si la ejecución finalizó y el flag está activo
            run_state = (status.get("run_state") or "").lower().strip()
            if config.enable_chart and run_state not in _RPA_IN_PROGRESS_STATES:
                await self._send_rpa_chart(status=status, config=config)

            return run_state

        except RunNotYetAvailableError:
            raise

        except Exception as e:
            await self._send_error_to_slack(
                issue=str(e),
                context=f"send_status_rpa(run_id={run_id}, bot_id={bot_id})",
                traceback_str=tb.format_exc(),
            )
            raise

    async def send_status_rpa_multi(
        self,
        run_ids: List[int],
        bot_id: str,
    ) -> Dict[str, str]:
        """
        Obtiene el status de TODAS las run_ids activas y envía UN ÚNICO mensaje
        fusionado al canal Slack. Usado exclusivamente por bee_observa.

        Los run_ids deben llegar ya ordenados cronológicamente (ascendente) —
        el caller (_dispatch_status_multi en rpa_orchestration_service) lo garantiza.

        Args:
            run_ids:  Lista de run_ids numéricos, ya ordenados cronológicamente.
            bot_id:   id_dashboard del bot para llamadas a Beecker API.

        Returns:
            dict {str(run_id): run_state} con el estado de cada ejecución procesada.
            Si ningún run_id está disponible aún, retorna {} sin enviar mensaje.

        Raises:
            RuntimeError: Si load_config() no fue llamado previamente.
        """
        try:
            if self.__rpa_config is None or self.__api_beecker is None:
                raise RuntimeError("Debes llamar a load_config() antes de send_status_rpa_multi().")

            config = self.__rpa_config

            # 1. Obtener status de cada run_id (concurrente para eficiencia)
            skipped: list[int] = []

            async def _fetch_one(rid: int) -> dict | None:
                try:
                    s = await self.__api_beecker.get_rpa_status(run_id=rid, bot_id=bot_id)
                    if not config.enable_overtime_check:
                        s = {**s, "overtime_flag": False}
                    return s
                except RunNotYetAvailableError:
                    logger.warning(
                        f"⏳ [MULTI] run_id={rid} no disponible aún, se omite en este tick"
                    )
                    skipped.append(rid)
                    return None

            fetched = await asyncio.gather(*[_fetch_one(rid) for rid in run_ids])
            status_list = [s for s in fetched if s is not None]

            if not status_list:
                logger.warning(
                    f"⏳ [MULTI] Ningún run_id disponible aún | run_ids={run_ids}"
                )
                return {}

            # 2. Construir mensaje fusionado (un saludo + N bloques en orden cronológico)
            message = self._rpa_message_builder.build_multi(
                bot_id=config.bot_name,
                bot_name=config.process_name,
                status_list=status_list,
                transaction_unit=config.transaction_unit,
                transaction_unit_singular=config.transaction_unit_singular,
                show_error_groups=config.show_error_groups,
                max_error_groups=config.max_error_groups,
                mention_user_ids=self._mention_ids,
                freshdesk_url=self._get_effective_freshdesk_url(),
            )

            # 3. Enviar mensaje
            await self.__api_slack.send_message(
                channel_name=config.channel_name,
                message=message,
            )
            logger.info(
                f"Mensaje fusionado enviado | run_ids={run_ids} | bot_id={bot_id} | "
                f"canal={config.channel_name}."
            )

            # 4. Gráfica — solo para ejecuciones terminadas
            if config.enable_chart:
                for status_dict in status_list:
                    run_state_s = (status_dict.get("run_state") or "").lower().strip()
                    if run_state_s not in _RPA_IN_PROGRESS_STATES:
                        await self._send_rpa_chart(status=status_dict, config=config)

            # 5. Retornar mapa {str(run_id): run_state}
            return {
                str(s["run_id"]): (s.get("run_state") or "").lower().strip()
                for s in status_list
            }

        except Exception as e:
            await self._send_error_to_slack(
                issue=str(e),
                context=f"send_status_rpa_multi(run_ids={run_ids}, bot_id={bot_id})",
                traceback_str=tb.format_exc(),
            )
            raise

    # ── Métodos públicos Agent ────────────────────────────────────────────────

    async def send_status_agent(
        self,
        agent_id: str,
        start_datetime: Optional[str] = None,
        end_datetime: Optional[str] = None,
    ) -> None:
        """
        Retrieve the agent execution summary for the specified interval
        and send the notification to Slack.

        Args:
            agent_id:       Numeric agent ID in the platform (e.g. "18").
            start_datetime: Start of the interval. None = beginning of current day.
            end_datetime:   End of the interval. None = current time.

        Raises:
            RuntimeError: If load_agent_config() has not been called previously.
            BeeckerAPIError: If retrieving agent history fails.
        """
        try:
            if self.__agent_config is None or self.__agent_beecker is None:
                raise RuntimeError("Debes llamar a load_agent_config() antes de send_status_agent().")

            config = self.__agent_config

            agent_status = await self.__agent_beecker.get_agent_status(
                agent_id=agent_id,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
            )

            message = self._agent_message_builder.build(
                agent_status=agent_status,
                agent_name=config.agent_name,
                process_name=config.process_name,
                execution_unit=config.execution_unit,
                execution_unit_singular=config.execution_unit_singular,
                execution_identifier_field=config.execution_identifier_field,
                mention_user_ids=self._agent_mention_ids,
                show_error_list=config.show_error_list,
                show_error_categories=config.show_error_categories,
                max_error_categories=config.max_error_categories,
                error_similarity_threshold=config.error_similarity_threshold,
                failed_states=config.failed_states,
                freshdesk_url=self._agent_freshdesk_url if config.enable_freshdesk_link else None,
            )

            await self.__api_slack.send_message(
                channel_name=config.channel_name,
                message=message,
            )

            start_str = start_datetime or "inicio del día"
            end_str   = end_datetime   or "ahora"
            logger.info(
                f"Mensaje de agente enviado para agent_id={agent_id} en canal {config.channel_name}. "
                f"Intervalo: {start_str} → {end_str}. "
                f"Total: {agent_status.get('total_executions', 0)} ejecuciones."
            )

            if config.enable_chart:
                await self._send_agent_chart(agent_status=agent_status, config=config)

        except Exception as e:
            await self._send_error_to_slack(
                issue=str(e),
                context=f"send_status_agent(agent_id={agent_id})",
                traceback_str=tb.format_exc(),
            )
            raise

    # ── Helpers privados — charts ─────────────────────────────────────────────

    async def _send_rpa_chart(self, status: dict, config: RPAConfig) -> None:
        """Generate and send the RPA execution chart to Slack."""
        try:
            chart_title = f"{config.bot_name.upper()} — {config.process_name}"
            img_bytes   = self._rpa_chart_builder.build(
                status_dict=status,
                bot_name=chart_title,
            )
            run_state = (status.get("run_state") or "").capitalize()
            await self.__api_slack.send_image(
                file=img_bytes,
                channel=config.channel_name,
                tittle=f"Gráfica de ejecución — {chart_title}",
                comment=f"📊 Resumen visual de la ejecución *{run_state}*",
            )
            logger.info(f"Gráfica RPA enviada a {config.channel_name}.")

        except Exception as chart_err:
            logger.warning(f"No se pudo generar/enviar la gráfica RPA: {chart_err}.")
            await self._send_error_to_slack(
                issue=str(chart_err),
                context=f"_send_rpa_chart (bot={config.bot_name})",
                traceback_str=tb.format_exc(),
            )

    async def _send_agent_chart(self, agent_status: dict, config: AgentConfig) -> None:
        """Generate and send the agent execution chart to Slack."""
        try:
            chart_title = f"{config.agent_name.upper()} — {config.process_name}"
            img_bytes   = self._agent_chart_builder.build(
                agent_status=agent_status,
                agent_name=chart_title,
            )
            await self.__api_slack.send_image(
                file=img_bytes,
                channel=config.channel_name,
                tittle=f"Gráfica de ejecuciones — {chart_title}",
                comment="📊 Distribución de ejecuciones del período",
            )
            logger.info(f"Gráfica de agente enviada a {config.channel_name}.")

        except Exception as chart_err:
            logger.warning(f"No se pudo generar/enviar la gráfica del agente: {chart_err}.")
            await self._send_error_to_slack(
                issue=str(chart_err),
                context=f"_send_agent_chart (agente={config.agent_name})",
                traceback_str=tb.format_exc(),
            )

    # ── Helpers privados — autenticación ─────────────────────────────────────

    async def _login_slack(self, token: str) -> None:
        if not token:
            raise ValueError("El token de Slack está vacío.")
        try:
            api_slack = SlackAPI()
            await api_slack.login(token)
            self.__api_slack = api_slack
            logger.info("Slack autenticado correctamente.")
        except SlackErrorAuthenticate:
            logger.error("El token de Slack no es válido.")
            raise

    async def _login_beecker(
        self,
        email: str,
        password: str,
        platform: str = "cloud",
        target: str = "_rpa",
    ) -> None:
        if not (email and password):
            raise ValueError("El email y/o password de Beecker no pueden estar vacíos.")
        try:
            api = BeeckerAPI(platform=platform)
            await api.login(email, password)
            if target == "_rpa":
                self.__api_beecker = api
            else:
                self.__agent_beecker = api
            logger.info(f"Beecker autenticado ({platform}) [{target}] para: {email}")
        except BeeckerAPIError as e:
            await self._send_error_to_slack(
                issue=str(e),
                context=f"_login_beecker(platform={platform}, target={target})",
                traceback_str=tb.format_exc(),
            )
            raise

    async def _login_fresh(self, username: str, password: str) -> None:
        if not (username and password):
            raise ValueError("El usuario y/o password de FreshDesk no pueden estar vacíos.")
        try:
            api_freshdesk = FreshDeskAPI()
            await api_freshdesk.login(username, password)
            self.__api_freshdesk = api_freshdesk
            logger.info("FreshDesk autenticado correctamente.")
        except FreshDeskAuthenticateError:
            logger.error("Error al autenticar en FreshDesk.")
            raise

    # ── Helpers privados — resolución de recursos ─────────────────────────────

    async def _resolve_mention_ids(self, emails: List[str], context: str = "") -> List[str]:
        resolved_ids: List[str] = []
        prefix = f"[{context}] " if context else ""
        for email in emails:
            try:
                user_id = await self.__api_slack.get_id_by_email(email)
                if user_id:
                    resolved_ids.append(user_id)
                    logger.info(f"{prefix}Email resuelto: {email} → {user_id}")
                else:
                    logger.warning(f"{prefix}No se encontró ID de Slack para: {email}")
            except Exception as e:
                logger.warning(f"{prefix}Error al resolver '{email}': {e}. Se omitirá.")
        return resolved_ids

    async def _resolve_freshdesk_url(self, client_name: str, status_id: int = 0) -> Optional[str]:
        try:
            company_id = await self.__api_freshdesk.get_id_by_name_company(client_name)
            if company_id is None:
                logger.warning(f"No se encontró '{client_name}' en FreshDesk.")
                return None
            url = self.__api_freshdesk.build_freshdesk_ui_url(
                company_id=company_id, status_id=status_id
            )
            logger.info(f"URL de FreshDesk resuelta para '{client_name}': {url}")
            return url
        except Exception as e:
            logger.warning(f"Error al resolver URL FreshDesk para '{client_name}': {e}.")
            return None

    async def _send_error_to_slack(
        self,
        issue: str,
        bot_name: Optional[str] = None,
        context: Optional[str] = None,
        traceback_str: Optional[str] = None,
    ) -> None:
        if not self._is_slack_authenticated():
            return
        if not _ErrorMessages.CHANNEL_ERROR:
            logger.warning("CHANNEL_ERROR no está definido. El error no se reportará a Slack.")
            return
        try:
            name = bot_name or (
                getattr(self.__rpa_config,    "bot_name",   None)
                or getattr(self.__agent_config, "agent_name", None)
            )
            await self.__api_slack.send_message(
                channel_name=_ErrorMessages.CHANNEL_ERROR,
                message=_ErrorMessages.build(
                    issue=issue,
                    bot_name=name,
                    context=context,
                ),
            )
        except Exception as slack_err:
            logger.error(f"No se pudo enviar el error a Slack: {slack_err}")

    # ── Helpers privados — utilidades ─────────────────────────────────────────

    def _is_slack_authenticated(self) -> bool:
        return (
            hasattr(self, "_MonitoringAgent__api_slack")
            and self.__api_slack is not None
        )

    def _get_effective_freshdesk_url(self) -> Optional[str]:
        if not self.__rpa_config or not self.__rpa_config.enable_freshdesk_link:
            return None
        return self._freshdesk_url
