"""
agent_message_builder.py
========================
Slack message builder responsible for generating daily execution summaries
for Beecker agents.

Responsibilities:
    - Build the daily summary message of an agent based on the normalized
      dictionary returned by BeeckerAPI.get_agent_status().
    - Remain completely transport-agnostic (no HTTP or Slack SDK usage).
    - Support configurable business terminology (candidates, files, policies, etc.).
    - Group similar errors using semantic similarity and respect configurable limits.
    - Mention Slack users only when failed executions exist.

Differences compared to RPAMessageBuilder:
    - No "execution start" message (agents generate many runs per day).
    - No overtime detection or average runtime comparison.
    - The business unit represents an *agent execution*, not a transaction.
    - Errors are displayed both per execution and grouped by similarity.

Example::

    from agent_message_builder import AgentMessageBuilder

    builder = AgentMessageBuilder()

    message = builder.build(
        agent_status=api.get_agent_status(
            agent_id="18",
            start_datetime="2026-03-02 00:00:00",
            end_datetime="2026-03-02 14:30:00",
        ),
        agent_name="LUCAS",
        process_name="Candidate processor",
        execution_unit="candidates",
        execution_unit_singular="candidate",
        execution_identifier_field="candidate_name",
        mention_user_ids=["U123ABC"],
        max_error_categories=5,
        failed_states=["failed", "documents missing"],
    )
"""

from __future__ import annotations

import random
from difflib import SequenceMatcher
from typing import Dict, Any, List, Optional, Set

# ---------------------------------------------------------------------------
# Default failed states
# ---------------------------------------------------------------------------

# Global list of states considered "failed" when no custom list is provided.
# Comparison is always performed in lowercase.

DEFAULT_FAILED_STATES: List[str] = ["failed", "documents missing"]

_STATE_EMOJI: Dict[str, str] = {
    "completed":        ":white_check_mark:",
    "successful":       ":white_check_mark:",
    "documents missing":           ":warning-icon:",
    "in progress":      ":in_progress:",
    "pending":          ":hourglass_flowing_sand:",
    "pending approval": ":timer_clock:",
    "in review":        ":mag:",
}

_DEFAULT_EMOJI = ":small_blue_diamond:"


def _state_emoji(state: str) -> str:
    # return _STATE_EMOJI.get(state.lower().strip(), _DEFAULT_EMOJI)
    return ''

class _GreetingProvider:
    _GREETINGS: List[str] = [
        "¡Hola equipo!",
        "¡Buen día, equipo!",
        "¡Qué tal, equipo!",
        "¡Atención equipo!",
        "¡Hola a todos!",
    ]

    def get(self) -> str:
        return random.choice(self._GREETINGS)


_GREETING_PROVIDER = _GreetingProvider()

def _group_errors_by_description(
    failed_executions: List[Dict[str, Any]],
    description_field: str = "description",
    threshold: float = 0.80,
) -> List[Dict[str, Any]]:
    """
    Group failed executions based on semantic similarity of their error descriptions.

    Args:
        failed_executions:
            List of executions considered failed.

        description_field:
            Field name containing the error description.
            Default: "description".

        threshold:
            Similarity threshold used by SequenceMatcher (0.0–1.0).
            Default: 0.80.

    Returns:
        List of grouped errors sorted by frequency:

        [
            {
                "representative": str,   # representative message of the group
                "count": int,            # number of executions in the group
                "run_ids": list,         # execution IDs belonging to the group
            },
            ...
        ]
    """
    groups: List[Dict[str, Any]] = []

    for ex in failed_executions:
        msg = str(ex.get(description_field, "")).strip()
        if not msg:
            msg = "(sin descripción)"

        run_id  = ex.get("run_id")
        matched = False

        for group in groups:
            ratio = SequenceMatcher(None, group["representative"], msg).ratio()
            if ratio >= threshold:
                group["count"] += 1
                group["run_ids"].append(run_id)
                matched = True
                break

        if not matched:
            groups.append({
                "representative": msg,
                "count":          1,
                "run_ids":        [run_id],
            })

    groups.sort(key=lambda g: g["count"], reverse=True)
    return groups

class AgentMessageBuilder:
    """
    Slack message builder for daily agent execution summaries.

    Example::

        builder = AgentMessageBuilder()

        msg = builder.build(
            agent_status=status_dict,
            agent_name="LUCAS",
            process_name="Candidate processor",
            execution_unit="candidates",
            execution_unit_singular="candidate",
            execution_identifier_field="candidate_name",
            mention_user_ids=["U123ABC"],
            show_error_list=True,
            show_error_categories=True,
            max_error_categories=5,
            error_similarity_threshold=0.80,
            failed_states=["failed", "documents missing"],
        )
    """

    def build(
        self,
        agent_status: Dict[str, Any],
        agent_name: str,
        process_name: str,
        execution_unit: str = "ejecuciones",
        execution_unit_singular: str = "ejecución",
        execution_identifier_field: Optional[str] = None,
        show_error_list: bool = True,
        show_error_categories: bool = True,
        max_error_categories: Optional[int] = 5,
        error_similarity_threshold: float = 0.80,
        mention_user_ids: Optional[List[str]] = None,
        freshdesk_url: Optional[str] = None,
        failed_states: Optional[List[str]] = None,
    ) -> str:
        """
        Build the daily summary Slack message for an agent.

        Args:
            agent_status:
                Response returned by BeeckerAPI.get_agent_status().

            agent_name:
                Short identifier of the agent (e.g. "LUCAS").

            process_name:
                Human-readable business process name.

            execution_unit:
                Business unit in plural form (e.g. "candidates").

            execution_unit_singular:
                Business unit in singular form (e.g. "candidate").

            execution_identifier_field:
                Field from extra_fields used as a readable identifier in the
                failed execution list. If None, run_id is used.

            show_error_list:
                If True, include the list of failed executions.

            show_error_categories:
                If True, include grouped error categories.

            max_error_categories:
                Maximum number of categories to display.
                None = show all.

            error_similarity_threshold:
                Threshold used to group errors semantically.

            mention_user_ids:
                Slack user IDs to mention when failures exist.

            freshdesk_url:
                Optional FreshDesk link included when failures exist.

            failed_states:
                List of run_state values considered failures.
                If None, DEFAULT_FAILED_STATES is used.
                Comparison is case-insensitive.

        Returns:
            Slack message formatted in mrkdwn.
        """
        # ── Normalizar el set de estados fallidos ──────────────────────────────
        failed_states_set: Set[str] = {
            s.lower().strip()
            for s in (failed_states if failed_states is not None else DEFAULT_FAILED_STATES)
        }

        executions     = agent_status.get("executions", [])
        total          = agent_status.get("total_executions", 0)
        interval_start = agent_status.get("interval_start", "N/D")
        interval_end   = agent_status.get("interval_end", "N/D")

        unit   = execution_unit
        unit_s = execution_unit_singular

        # Filtrar ejecuciones fallidas usando la lista configurable
        failed_executions = [
            ex for ex in executions
            if (ex.get("run_state") or "").lower().strip() in failed_states_set
        ]
        # El conteo correcto viene de la lista filtrada, no del dict del API
        # (el API solo cuenta el estado literal "failed").
        failed_count = len(failed_executions)

        total_u = unit_s if total == 1 else unit

        lines: List[str] = []

        # ── 1. Encabezado ──────────────────────────────────────────────────────
        lines.append(_GREETING_PROVIDER.get())
        lines.append(
            f"Resumen del agente `{agent_name.upper()}` *→ {process_name}*"
        )
        lines.append(
            f":calendar: *Resumen del día:* {interval_start}  —  {interval_end}"
        )
        lines.append("")

        # ── 2. Conteo de estados ───────────────────────────────────────────────
        lines.append(
            f"*Aún sin procesar {unit_s}*"
            if total == 0
            else f"*Estado de la {unit_s} (1 {total_u} procesada):*"
            if total == 1
            else f"*Estado de las {unit} ({total} {total_u} procesados):*"
        )

        # Estados conocidos con etiqueta en español (orden de presentación)
        _KNOWN_STATES: List[tuple] = [
            ("completed",        "Completadas"),
            ("successful",       "Exitosas"),
            ("in progress",      "En progreso"),
            ("in review",        "En revisión"),
            ("pending approval", "Pendiente de aprobación"),
            ("documents missing","Fallidas"),
            ("failed",           "Fallidas"),
        ]
        _KNOWN_STATE_KEYS = {s for s, _ in _KNOWN_STATES}

        # Contar todas las ejecuciones agrupadas por su run_state real
        dynamic_counts: Dict[str, int] = {}
        for ex in executions:
            raw_state = (ex.get("run_state") or "unknown").strip()
            key = raw_state.lower()
            dynamic_counts[key] = dynamic_counts.get(key, 0) + 1

        # Estados de error configurados → agrupar todos bajo la etiqueta "Fallidas"
        # para evitar mostrar cada estado de error por separado.
        combined_failed_count = sum(
            dynamic_counts.get(s, 0) for s in failed_states_set
        )

        # Mostrar primero los estados conocidos NO fallidos (en el orden definido)
        already_shown: Set[str] = set()
        for state_key, label in _KNOWN_STATES:
            if state_key in failed_states_set:
                continue   # Los fallidos se muestran juntos al final
            count = dynamic_counts.get(state_key, 0)
            if count > 0:
                count_u = unit_s if count == 1 else unit
                lines.append(f"➤ *{label}:* {count} {count_u} {_state_emoji(state_key)}")
                already_shown.add(state_key)

        # Mostrar dinámicamente los estados no contemplados que tampoco son fallidos
        for raw_key, count in dynamic_counts.items():
            if raw_key in _KNOWN_STATE_KEYS or raw_key in failed_states_set:
                continue
            display_label = " ".join(w.capitalize() for w in raw_key.split())
            count_u = unit_s if count == 1 else unit
            lines.append(f"➤ *{display_label}:* {count} {count_u} {_state_emoji(raw_key)}")

        # Mostrar bloque unificado de fallidas (si existen)
        if combined_failed_count > 0:
            count_u = unit_s if combined_failed_count == 1 else unit
            lines.append(f"➤ *Fallidas:* {combined_failed_count} {count_u} {_state_emoji('failed')}")

        lines.append("")

        # ── 3. Listado de ejecuciones fallidas ────────────────────────────────
        if show_error_list and failed_executions:
            failed_u = unit_s if failed_count == 1 else unit
            lines.append(
                f"*{unit.capitalize()} con errores ({failed_count} {failed_u}):*"
            )

            for ex in failed_executions:
                identifier = self._get_identifier(ex, execution_identifier_field)
                description = str(ex.get("description") or "").strip() or "(sin descripción)"
                desc_display = (description[:100] + "…") if len(description) > 100 else description
                lines.append(f"  • *{identifier}* → `{desc_display}`")

            lines.append("")

        # ── 4. Categorías de error ─────────────────────────────────────────────
        if show_error_categories and failed_executions:
            error_groups = _group_errors_by_description(
                failed_executions=failed_executions,
                description_field="description",
                threshold=error_similarity_threshold,
            )

            groups_to_show = (
                error_groups[:max_error_categories]
                if max_error_categories is not None
                else error_groups
            )
            omitted = len(error_groups) - len(groups_to_show)

            inner_lines = [f"Categorías de error en {unit} fallidos:", ""]

            for i, group in enumerate(groups_to_show, start=1):
                count       = group.get("count", 0)
                rep         = group.get("representative", "Error desconocido")
                rep_display = (rep[:120] + "…") if len(rep) > 120 else rep
                count_u     = unit_s if count == 1 else unit
                inner_lines.append(f"  {i}. {rep_display}")
                inner_lines.append(f"     → Afecta {count} {count_u}")
                inner_lines.append("")

            if omitted > 0:
                inner_lines.append(
                    f"  … y {omitted} categoría(s) de error adicional(es) omitidas."
                )
                inner_lines.append("")

            block_content = "\n".join(inner_lines).rstrip()
            lines.append(f"```{block_content}```")
            lines.append("")

        # ── 5. Menciones (solo si hay fallos) ─────────────────────────────────
        if failed_count > 0 and mention_user_ids:
            mentions = " ".join(f"<@{uid}>" for uid in mention_user_ids)
            lines.append(
                f":luz_giratoia_movimiento: {mentions} favor de revisar a la brevedad."
            )
            lines.append("")

        # ── 6. Enlace de FreshDesk (solo si hay fallos) ───────────────────────
        if failed_count > 0 and freshdesk_url:
            lines.append(f"Tickets generados <{freshdesk_url}|FreshDesk>")
            lines.append("")

        # ── 7. Advertencias de la API (si existen) ────────────────────────────
        warnings = agent_status.get("warnings", [])
        if warnings:
            lines.append(f"_⚠️ {len(warnings)} advertencia(s) al obtener los datos._")

        # Limpiar líneas vacías finales
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)


    @staticmethod
    def _get_identifier(
        execution: Dict[str, Any],
        identifier_field: Optional[str],
    ) -> str:
        """
        Retrieve a readable identifier for a failed execution.

        Priority:
            1. extra_fields[identifier_field] if configured and available.
            2. run_id as fallback.

        Args:
            execution:
                Normalized execution dictionary.

            identifier_field:
                Field name inside extra_fields.

        Returns:
            Identifier string (e.g. "Juan García" or "#35241").
        """
        if identifier_field:
            extra      = execution.get("extra_fields") or {}
            identifier = extra.get(identifier_field)
            if identifier:
                return str(identifier)

        run_id = execution.get("run_id")
        return f"#{run_id}" if run_id is not None else "(ID desconocido)"