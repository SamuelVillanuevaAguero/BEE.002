"""
monitoring_service.py
===================
Main monitoring agent responsible for orchestrating authentication across all
platforms, resolving configuration resources at startup (emails → Slack user IDs,
client name → FreshDesk URL), and exposing notification methods.

Configuration loading flows:
    · load_config(RPAConfig)         → initializes monitoring for RPA bots.
    · load_agent_config(AgentConfig) → initializes monitoring for agents.

Public notification methods for RPA:
    - send_initial_rpa(bot_id)        → Execution start message.
    - send_status_rpa(run_id, bot_id) → Full execution snapshot with alerts.

Public notification methods for Agents:
    - send_status_agent(agent_id)     → Daily agent summary (00:00 → now).

Error handling:
    - Any exception raised in public methods is reported to the CHANNEL_ERROR Slack channel.
    - SlackErrorAuthenticate is NOT reported (Slack may not be available).
    - After reporting the error, the exception is always re-raised for the caller.
"""

from __future__ import annotations

import logging
import os
import traceback as tb
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv

from .beecker import BeeckerAPI, BeeckerAPIError
from .freshdesk.freshdesk_api import (
    FreshDeskAPI,
    FreshDeskAuthenticateError,
    FreshDeskError,
)
from .slack.slack_api import (
    SlackAPI,
    SlackError,
    SlackErrorAuthenticate,
)
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from services.config.rpa_config import RPAConfig
from services.config.agent_config import AgentConfig
from slack_message_builder import RPAMessageBuilder
from agent_message_builder import AgentMessageBuilder
from chart_builder import RPAChartBuilder, AgentChartBuilder

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

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
            "¡Atención equipo! :luz_giratoia_movimiento:",
            f"Se presentó un error en el monitoreo → `{name_label}`",
            "",
        ]

        if context:
            lines.append(f"*Operación:* `{context}`")

        lines.append(f"*Hora:*      {now}")
        lines.append("")
        lines.append(f"*Error:*\n```{issue}```")

        if traceback_str:
            max_tb_chars = 2800
            tb_display = (
                traceback_str[:max_tb_chars] + "\n… (truncado)"
                if len(traceback_str) > max_tb_chars
                else traceback_str
            )
            lines.append(f"\n*Traceback:*\n```{tb_display}```")

        return "\n".join(lines)

_RPA_IN_PROGRESS_STATES = {"in progress", "pending"}

class MonitoringAgent:
    """
    Monitoring agent for Beecker processes (RPA and Agents).

    All public methods are asynchronous and must run inside an event loop
    (e.g. asyncio.run(main())).

    Usage for RPA::

        config = RPAConfig(bot_name="AIN.002", process_name="Order entry")
        agent = MonitoringAgent()
        await agent.load_config(config)
        await agent.send_initial_rpa(bot_id="104")
        await agent.send_status_rpa(run_id=162389, bot_id="104")

    Usage for Agents::

        config = AgentConfig(
            agent_name="LUCAS",
            process_name="Candidate processor",
            execution_unit="candidates",
            execution_unit_singular="candidate",
            execution_identifier_field="candidate_name",
        )
        agent = MonitoringAgent()
        await agent.load_agent_config(config)
        await agent.send_status_agent(agent_id="18")
    """

    __rpa_config:    Optional[RPAConfig]
    __agent_config:  Optional[AgentConfig]
    __api_beecker:   Optional[BeeckerAPI]
    __agent_beecker: Optional[BeeckerAPI]
    __api_slack:     Optional[SlackAPI]
    __api_freshdesk: Optional[FreshDeskAPI]

    _mention_ids:         List[str]
    _agent_mention_ids:   List[str]
    _freshdesk_url:       Optional[str]
    _agent_freshdesk_url: Optional[str]

    _rpa_message_builder:   RPAMessageBuilder
    _agent_message_builder: AgentMessageBuilder
    _rpa_chart_builder:     RPAChartBuilder
    _agent_chart_builder:   AgentChartBuilder

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


    async def load_config(self, config: RPAConfig) -> None:
        """
        Load the RPA configuration and authenticate all required platforms.

        Raises:
            ValueError: If required configuration fields are missing.
            SlackErrorAuthenticate: If the Slack token is invalid.
            BeeckerAPIError: If Beecker authentication fails.
        """
        try:
            config.validate()
            self.__rpa_config = config

            await self._login_slack(config.token_slack)

            if config.mention_emails:
                self._mention_ids = await self._resolve_mention_ids(
                    config.mention_emails, context="RPA"
                )

            await self._login_beecker(
                email=config.email_dash,
                password=config.password_dash,
                platform=config.platform,
                target="_rpa",
            )

            if config.username_freshdesk and config.password_freshdesk:
                await self._login_fresh(
                    username=config.username_freshdesk,
                    password=config.password_freshdesk,
                )
                if config.enable_freshdesk_link and config.freshdesk_client_name:
                    self._freshdesk_url = await self._resolve_freshdesk_url(
                        client_name=config.freshdesk_client_name,
                        status_id=config.freshdesk_status_id,
                    )

        except SlackErrorAuthenticate:
            logger.error(
                "Fallo de autenticación en Slack. "
                "No es posible reportar al canal de errores."
            )
            raise

        except Exception as e:
            await self._send_error_to_slack(
                issue=str(e),
                context="load_config",
                traceback_str=tb.format_exc(),
            )
            raise

    async def load_agent_config(self, config: AgentConfig) -> None:
        """
        Load the agent configuration and authenticate all required platforms.

        If Slack is already authenticated (because load_config() was called before),
        the existing session is reused.

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
            logger.error(
                "Fallo de autenticación en Slack. "
                "No es posible reportar al canal de errores."
            )
            raise

        except Exception as e:
            await self._send_error_to_slack(
                issue=str(e),
                context="load_agent_config",
                traceback_str=tb.format_exc(),
            )
            raise

    async def send_initial_rpa(self, bot_id: str) -> None:
        """
        Send the execution start notification to the configured Slack channel.

        Raises:
            RuntimeError: If load_config() has not been called previously.
        """
        try:
            if self.__rpa_config is None or self.__api_beecker is None:
                raise RuntimeError(
                    "Debes llamar a load_config() antes de send_initial_rpa()."
                )

            message = self._rpa_message_builder.build_initial(
                bot_id=self.__rpa_config.bot_name,
                bot_name=self.__rpa_config.process_name,
            )
            await self.__api_slack.send_message(
                channel_name=self.__rpa_config.channel_name,
                message=message,
            )
            logger.info(
                f"Mensaje de inicio enviado para bot_id={bot_id} "
                f"en canal {self.__rpa_config.channel_name}."
            )

        except Exception as e:
            await self._send_error_to_slack(
                issue=str(e),
                context=f"send_initial_rpa(bot_id={bot_id})",
                traceback_str=tb.format_exc(),
            )
            raise

    async def send_status_rpa(self, run_id: int, bot_id: str) -> None:
        """
        Retrieve the current RPA execution status and send the notification to Slack.

        Raises:
            RuntimeError: If load_config() has not been called previously.
        """
        try:
            if self.__rpa_config is None or self.__api_beecker is None:
                raise RuntimeError(
                    "Debes llamar a load_config() antes de send_status_rpa()."
                )

            config = self.__rpa_config

            # 1. Obtener status desde Beecker
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

        except Exception as e:
            await self._send_error_to_slack(
                issue=str(e),
                context=f"send_status_rpa(run_id={run_id}, bot_id={bot_id})",
                traceback_str=tb.format_exc(),
            )
            raise

    async def send_status_agent(
        self,
        agent_id: str,
        start_datetime: Optional[str] = None,
        end_datetime: Optional[str] = None,
    ) -> None:
        """
        Retrieve the agent execution summary for the specified interval and
        send the notification to Slack. If enable_chart=True, a chart is also attached.

        Args:
            agent_id:       Numeric agent ID in the platform (e.g. "18").
            start_datetime: Start of the interval. None = beginning of the current day.
            end_datetime:   End of the interval. None = current time.

        Raises:
            RuntimeError: If load_agent_config() has not been called previously.
            BeeckerAPIError: If retrieving agent history fails.
        """
        try:
            if self.__agent_config is None or self.__agent_beecker is None:
                raise RuntimeError(
                    "Debes llamar a load_agent_config() antes de send_status_agent()."
                )

            config = self.__agent_config
            now    = datetime.now()

            # ── Resolver intervalo ─────────────────────────────────────────────
            start_str = (
                now.replace(hour=0, minute=0, second=0, microsecond=0)
                .strftime("%Y-%m-%d %H:%M:%S")
                if start_datetime is None
                else start_datetime
            )
            end_str = (
                end_datetime if end_datetime is not None
                else now.strftime("%Y-%m-%d %H:%M:%S")
            )

            logger.info(
                f"Obteniendo status del agente '{agent_id}' "
                f"[{config.agent_name}] para el intervalo {start_str} → {end_str}"
            )

            # ── Consultar status desde Beecker ─────────────────────────────────
            agent_status = await self.__agent_beecker.get_agent_status(
                agent_id=agent_id,
                start_datetime=start_str,
                end_datetime=end_str,
                include_progress=config.include_progress,
            )

            # ── Construir mensaje ──────────────────────────────────────────────
            freshdesk_url = (
                self._agent_freshdesk_url if config.enable_freshdesk_link else None
            )

            message = self._agent_message_builder.build(
                agent_status=agent_status,
                agent_name=config.agent_name,
                process_name=config.process_name,
                execution_unit=config.execution_unit,
                execution_unit_singular=config.execution_unit_singular,
                execution_identifier_field=config.execution_identifier_field,
                show_error_list=config.show_error_list,
                show_error_categories=config.show_error_categories,
                max_error_categories=config.max_error_categories,
                error_similarity_threshold=config.error_similarity_threshold,
                mention_user_ids=self._agent_mention_ids,
                freshdesk_url=freshdesk_url,
                failed_states=config.failed_states,
            )

            # ── Enviar mensaje de texto ────────────────────────────────────────
            await self.__api_slack.send_message(
                channel_name=config.channel_name,
                message=message,
            )
            logger.info(
                f"Resumen del agente '{agent_id}' enviado a {config.channel_name}. "
                f"Intervalo: {start_str} → {end_str}. "
                f"Total: {agent_status.get('total_executions', 0)} ejecuciones."
            )

            # ── Gráfica (si está habilitada) ───────────────────────────────────
            if config.enable_chart:
                await self._send_agent_chart(agent_status=agent_status, config=config)

        except Exception as e:
            await self._send_error_to_slack(
                issue=str(e),
                context=f"send_status_agent(agent_id={agent_id})",
                traceback_str=tb.format_exc(),
            )
            raise

    async def _send_rpa_chart(self, status: dict, config: RPAConfig) -> None:
        """
        Generate and send the chart for a completed RPA execution to Slack.

        Failures in chart generation do not interrupt the main notification flow.
        """
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
            logger.warning(
                f"No se pudo generar/enviar la gráfica RPA: {chart_err}. "
                "El mensaje de texto ya fue enviado correctamente."
            )
            await self._send_error_to_slack(
                issue=str(chart_err),
                context=f"_send_rpa_chart (bot={config.bot_name})",
                traceback_str=tb.format_exc(),
            )

    async def _send_agent_chart(self, agent_status: dict, config: AgentConfig) -> None:
        """
        Generate and send the chart for an agent execution summary to Slack.

        Failures in chart generation do not interrupt the main notification flow.
        """
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
            logger.warning(
                f"No se pudo generar/enviar la gráfica del agente: {chart_err}. "
                "El mensaje de texto ya fue enviado correctamente."
            )
            await self._send_error_to_slack(
                issue=str(chart_err),
                context=f"_send_agent_chart (agente={config.agent_name})",
                traceback_str=tb.format_exc(),
            )

    async def _login_slack(self, token: str) -> None:
        """
        Authenticate the Slack bot.

        Raises:
            ValueError: If the token is empty.
            SlackErrorAuthenticate: If the token is invalid.
        """
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
        """
        Authenticate against the Beecker platform and store the API instance
        depending on the target (RPA or Agent).

        Raises:
            ValueError: If email or password are empty.
            BeeckerAPIError: If authentication fails.
        """
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
            msg = f'No se pudo autenticar "{email}" en Beecker ({platform}) [{target}].'
            logger.error(msg)
            await self._send_error_to_slack(
                issue=str(e),
                context=f"_login_beecker(platform={platform}, target={target})",
                traceback_str=tb.format_exc(),
            )
            raise

    async def _login_fresh(self, username: str, password: str) -> None:
        """
        Authenticate with the FreshDesk API.

        Raises:
            ValueError: If username or password are empty.
            FreshDeskAuthenticateError: If authentication fails.
        """
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

    async def _resolve_mention_ids(
        self, emails: List[str], context: str = ""
    ) -> List[str]:
        """
        Resolve a list of email addresses to Slack user IDs.
        """
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
                logger.warning(
                    f"{prefix}Error al resolver '{email}': {e}. Se omitirá."
                )

        return resolved_ids

    async def _resolve_freshdesk_url(
        self, client_name: str, status_id: int = 0
    ) -> Optional[str]:
        """
        Build the FreshDesk ticket URL for the specified client.
        """
        try:
            company_id = await self.__api_freshdesk.get_id_by_name_company(client_name)
            if company_id is None:
                logger.warning(
                    f"No se encontró '{client_name}' en FreshDesk. "
                    "El link no se incluirá."
                )
                return None

            url = self.__api_freshdesk.build_freshdesk_ui_url(
                company_id=company_id, status_id=status_id
            )
            logger.info(f"URL de FreshDesk resuelta para '{client_name}': {url}")
            return url

        except Exception as e:
            logger.warning(f"Error al resolver URL FreshDesk para '{client_name}': {e}.")
            return None

    def _is_slack_authenticated(self) -> bool:
        """Return whether Slack authentication has already been established."""
        return (
            hasattr(self, "_MonitoringAgent__api_slack")
            and self.__api_slack is not None
        )

    async def _send_error_to_slack(
        self,
        issue: str,
        bot_name: Optional[str] = None,
        context: Optional[str] = None,
        traceback_str: Optional[str] = None,
    ) -> None:
        """
        Send an enriched error message to the incident Slack channel.

        This method only executes if Slack is authenticated and CHANNEL_ERROR
        is configured. It never raises exceptions.
        """
        if not self._is_slack_authenticated():
            return

        if not _ErrorMessages.CHANNEL_ERROR:
            logger.warning(
                "CHANNEL_ERROR no está definido. "
                "El error no se reportará al canal de Slack."
            )
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
                    context=context#,traceback_str=traceback_str,
                ),
            )
        except Exception as slack_err:
            logger.error(f"No se pudo enviar el error a Slack: {slack_err}")

    def _get_effective_freshdesk_url(self) -> Optional[str]:
        """Return the effective FreshDesk URL for RPA notifications if enabled."""
        if not self.__rpa_config or not self.__rpa_config.enable_freshdesk_link:
            return None
        return self._freshdesk_url