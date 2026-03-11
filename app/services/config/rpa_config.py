"""
rpa_config.py
=============
Configuration object used by the monitoring agent to define the behavior
of a monitored RPA process or agent.

Each bot/process has its own RPAConfig instance. Fields can be overridden
either by subclassing the configuration or by instantiating it with the
desired values.

Example::

    config = RPAConfig(
        bot_name="AIN.002",
        process_name="Order entry - Performer",
        transaction_unit="files",
        transaction_unit_singular="file",
        freshdesk_client_name="Acme Corp",
        mention_emails=["samuel.villanueva@beecker.ai", "alan.vega@beecker.ai"],
        enable_overtime_check=True,
        enable_freshdesk_link=True,
    )
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class RPAConfig:
    """
    Configuration container for a monitorable process (RPA or Agent).

    Attributes
    ----------
    bot_name:
        Short identifier of the bot (e.g. "AIN.002"). Displayed in uppercase
        in Slack messages.

    process_name:
        Human-readable name of the monitored process
        (e.g. "Order entry - Performer").

    transaction_unit:
        Transaction unit in plural form (e.g. "files", "records").

    transaction_unit_singular:
        Transaction unit in singular form (e.g. "file", "record").

    show_error_groups:
        If True, include grouped error details in Slack messages.

    max_error_groups:
        Maximum number of error groups to display. None means all groups.

    mention_emails:
        List of email addresses to mention in critical failure alerts.
        The MonitoringAgent resolves them to Slack user IDs when loading
        the configuration.

    channel_name:
        Slack channel where notifications will be sent.

    freshdesk_client_name:
        Client name in FreshDesk (exactly as registered in the platform).
        Used to build the FreshDesk ticket link. If None and
        enable_freshdesk_link is True, the link will not be included.

    freshdesk_status_id:
        Ticket status ID used when filtering FreshDesk tickets (default: 0).

    enable_overtime_check:
        Enables detection of executions exceeding the historical average
        runtime, which may trigger the OVERTIME scenario.

    enable_freshdesk_link:
        If True, include a FreshDesk ticket link in messages when failed
        transactions exist.

    enable_chart:
        If True (default), generate and send a PNG chart as an image attachment
        in Slack when send_status_rpa() finishes (run_state != in_progress/pending).
        Disable if the channel does not support files or charts are not desired.

    email_dash:
        Authentication email used to access the Beecker Dashboard.

    password_dash:
        Authentication password used to access the Beecker Dashboard.

    platform:
        Beecker platform to connect to: 'cloud' or 'hub'. Default: 'cloud'.

    token_slack:
        Slack bot authentication token (read from SLACK_BOT_TOKEN).

    username_freshdesk:
        FreshDesk API username (read from USERNAME_FRESHDESK).

    password_freshdesk:
        FreshDesk API password (read from PASSWORD_FRESHDESK).
    """

        # ── Process identification ──────────────────────────────────────────────────
    bot_name: str = ""
    process_name: str = ""

    # ── Transaction units ───────────────────────────────────────────────────────
    transaction_unit: str = "Transacciones"
    transaction_unit_singular: str = "Transacción"

    # ── Error message configuration ─────────────────────────────────────────────
    show_error_groups: bool = True
    max_error_groups: Optional[int] = None

    # ── Slack mentions (email → ID resolution occurs at load time) ──────────────
    mention_emails: list[str] = field(
        default_factory=lambda: ["samuel.villanueva@beecker.ai"]
    )

    # ── Slack channel ───────────────────────────────────────────────────────────
    channel_name: str = "#agente-monitor-test"

    # ── FreshDesk ───────────────────────────────────────────────────────────────
    freshdesk_client_name: Optional[str] = 'Aeroméxico'
    freshdesk_status_id: int = 0

    # ── Feature flags ───────────────────────────────────────────────────────────
    enable_overtime_check: bool = True
    enable_freshdesk_link: bool = True
    enable_chart: bool = True

    # ── Beecker credentials ─────────────────────────────────────────────────────
    email_dash: str = "roc@beecker.ai"
    password_dash: str = "Z^t8)IE:146_"
    platform: str = "cloud"

    # ── Third-party credentials (loaded from environment variables) ─────────────
    token_slack: str = field(default_factory=lambda: os.getenv("SLACK_BOT_TOKEN", ""))
    username_freshdesk: str = field(
        default_factory=lambda: os.getenv("USERNAME_FRESHDESK", "")
    )
    password_freshdesk: str = field(
        default_factory=lambda: os.getenv("PASSWORD_FRESHDESK", "")
    )

    def validate(self) -> None:
        """
        Validate that required configuration fields are present.

        Raises
        ------
        ValueError
            Raised if any required configuration field is missing or empty.
        """
        errors: List[str] = []

        if not self.bot_name:
            errors.append("bot_name no puede estar vacío.")
        if not self.process_name:
            errors.append("process_name no puede estar vacío.")
        if not self.email_dash:
            errors.append(
                "email_dash no puede estar vacío "
                "(verifica la variable de entorno BEECKER_EMAIL)."
            )
        if not self.password_dash:
            errors.append(
                "password_dash no puede estar vacío "
                "(verifica la variable de entorno BEECKER_PASSWORD)."
            )
        if not self.token_slack:
            errors.append(
                "token_slack no puede estar vacío "
                "(verifica la variable de entorno SLACK_BOT_TOKEN)."
            )

        if errors:
            raise ValueError(
                "Configuración inválida:\n" + "\n".join(f"  · {e}" for e in errors)
            )