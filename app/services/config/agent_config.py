"""
agent_config.py
===============
Configuration object for monitoring daily executions of a Beecker agent.

Each agent has its own AgentConfig instance. The monitoring agent
uses this configuration to authenticate platforms, resolve Slack IDs,
and build the daily summary messages.

Example::

    config = AgentConfig(
        agent_name="LUCAS",
        process_name="Candidate processor",
        execution_unit="candidates",
        execution_unit_singular="candidate",
        execution_identifier_field="candidate_name",
        mention_emails=["samuel.villanueva@beecker.ai"],
        max_error_categories=5,
        # Customize which states are considered failures:
        failed_states=["failed", "documents missing", "rejected"],
    )
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AgentConfig:
    """
    Complete configuration for monitoring a Beecker agent's daily executions.

    Attributes
    ----------
    agent_name:
        Short identifier of the agent as it appears in Beecker
        (e.g. "LUCAS", "AIN.005"). Displayed in uppercase in messages.

    process_name:
        Human-readable name of the business process executed by the agent
        (e.g. "Candidate processor", "Policy validator").

    execution_unit:
        Business unit name in **plural** representing an agent execution
        (e.g. "candidates", "files", "policies").
        Used when composing messages in business terminology.

    execution_unit_singular:
        Business unit name in **singular** form (e.g. "candidate").

    execution_identifier_field:
        Field name inside ``extra_fields`` used as a readable identifier
        for each execution in the error list.

        If None or the field does not exist, run_id is used as fallback.

        Examples: "candidate_name", "phone_number", "file_name".

    failed_states:
        List of ``run_state`` values considered failures for the agent.
        Comparison is case-insensitive.

        Adjust the list according to platform behavior.

        Default:
            ["failed", "documents missing"].

    show_error_list:
        If True (default), display the list of individual failed executions
        together with their error description.

    show_error_categories:
        If True (default), display the error categories section grouped
        by semantic similarity.

    max_error_categories:
        Maximum number of error categories shown in the message.

        None = show all categories.

        Default: 5.

    error_similarity_threshold:
        Similarity threshold (0.0–1.0) used to group error messages
        using SequenceMatcher.

        Default: 0.80.

    mention_emails:
        List of email addresses to mention in Slack when executions
        enter a state defined in ``failed_states``.

        Empty list = no mentions.

    channel_name:
        Slack channel where the daily summary is sent.

    include_progress:
        If True, retrieve stage-level execution progress when building
        the agent status.

        This may slow down responses when many executions exist.

        Default: False.

    freshdesk_client_name:
        Client name in FreshDesk used to generate ticket links.

        None = do not include a FreshDesk link.

    freshdesk_status_id:
        Ticket status ID used when filtering FreshDesk tickets.

        Default: 0.

    enable_chart:
        If True (default), generate and send a PNG chart image
        when calling send_status_agent().

        Disable if the Slack channel does not support file uploads
        or charts are not desired.

    enable_freshdesk_link:
        If True and freshdesk_client_name is configured, include the
        FreshDesk link in messages when errors exist.

    email_dash:
        Authentication email for the Beecker Dashboard platform.

    password_dash:
        Authentication password for the Beecker Dashboard platform.

    platform:
        Beecker platform environment: 'cloud' or 'hub'.

        Default: 'cloud'.

    token_slack:
        Slack bot token (loaded from SLACK_BOT_TOKEN).

    username_freshdesk:
        FreshDesk API username (loaded from USERNAME_FRESHDESK).

    password_freshdesk:
        FreshDesk API password (loaded from PASSWORD_FRESHDESK).
    """

    # ── Agent identification ───────────────────────────────────────────────────
    agent_name: str = ""
    process_name: str = ""

    # ── Business execution unit ─────────────────────────────────────────────────
    execution_unit: str = "transacciones"
    execution_unit_singular: str = "transacción"

    # ── Identifier field inside extra_fields (used in the error list) ───────────
    execution_identifier_field: Optional[str] = None

    # ── States considered failures for this agent ───────────────────────────────
    # Adjust according to the behavior of the monitored platform.
    # Comparison is performed in lowercase (case-insensitive).
    failed_states: List[str] = field(
        default_factory=lambda: ["failed", "documents missing"]
    )

    # ── Error display configuration ────────────────────────────────────────────
    show_error_list: bool = True
    show_error_categories: bool = True
    max_error_categories: Optional[int] = 5
    error_similarity_threshold: float = 0.80

    # ── Slack mentions ─────────────────────────────────────────────────────────
    mention_emails: List[str] = field(
        default_factory=lambda: ["samuel.villanueva@beecker.ai"]
    )

    # ── Slack channel ──────────────────────────────────────────────────────────
    channel_name: str = "#agente-monitor-test"

    # ── Per-execution progress (expensive when many executions exist) ──────────
    include_progress: bool = False

    # ── FreshDesk configuration ────────────────────────────────────────────────
    freshdesk_client_name: Optional[str] = 'Premier Logistics'
    freshdesk_status_id: int = 0
    enable_freshdesk_link: bool = True
    enable_chart: bool = True

    # ── Beecker credentials ────────────────────────────────────────────────────
    email_dash: str = "alan.vega@beecker.ai"
    password_dash: str = "Beecker2026."
    platform: str = "hub"

    # ── Third-party credentials (loaded from environment variables) ────────────
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
            Raised when any mandatory configuration field is missing or invalid.
        """
        errors: List[str] = []

        if not self.agent_name:
            errors.append("agent_name no puede estar vacío.")
        if not self.process_name:
            errors.append("process_name no puede estar vacío.")
        if not self.email_dash:
            errors.append("email_dash no puede estar vacío.")
        if not self.password_dash:
            errors.append("password_dash no puede estar vacío.")
        if not self.token_slack:
            errors.append(
                "token_slack no puede estar vacío "
                "(verifica la variable de entorno SLACK_BOT_TOKEN)."
            )
        if not (0.0 <= self.error_similarity_threshold <= 1.0):
            errors.append(
                f"error_similarity_threshold debe estar entre 0.0 y 1.0 "
                f"(recibido: {self.error_similarity_threshold})."
            )

        if errors:
            raise ValueError(
                "Configuración de agente inválida:\n"
                + "\n".join(f"  · {e}" for e in errors)
            )