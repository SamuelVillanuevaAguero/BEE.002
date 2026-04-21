"""
chart_builder.py
================
Standalone module responsible for generating execution charts as PNG images.

Responsibilities:
    - Produce clear visualizations of RPA and Agent execution results.
    - Remain completely transport-agnostic (no knowledge of Slack or other APIs).
    - Receive normalized dictionaries returned by BeeckerAPI as input.
    - Return the generated image as PNG bytes ready to be sent through any channel.

Exported classes:
    - RPAChartBuilder   → Chart for completed RPA executions.
    - AgentChartBuilder → Horizontal bar chart for agent execution summaries.

Example::

    from modules.utils.chart_builder import RPAChartBuilder, AgentChartBuilder

    # RPA — only call when run_state is final (completed / failed)
    rpa_chart = RPAChartBuilder()
    img_bytes = rpa_chart.build(status_dict=status, bot_name="AIN.002 — Order Entry")

    # Agent
    agent_chart = AgentChartBuilder()
    img_bytes = agent_chart.build(agent_status=agent_status, agent_name="LUCAS — Recruiter")

    # Send to Slack
    slack_api.send_image(file=img_bytes, channel="#channel", title="...", comment="...")
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

_PALETTE = {
    "completed":         "#2ECC71",   # green
    "successful":        "#2ECC71",
    "failed":            "#E74C3C",   # red
    "documents missing": "#E74C3C",
    "in progress":       "#3498DB",   # blue
    "pending":           "#95A5A6",   # gray
    "in review":         "#F39C12",   # orange
    "pending approval":  "#9B59B6",   # purple
    "overtime":          "#E67E22",   # dark orange
    "default":           "#BDC3C7",   # light gray
}

_BG_COLOR    = "#1C1C1E"   # dark background
_TEXT_COLOR  = "#ECECEC"   # main text
_GRID_COLOR  = "#2C2C2E"   # grid lines


def _state_color(state: str) -> str:
    """Return the hexadecimal color associated with the given execution state."""
    return _PALETTE.get(state.lower().strip(), _PALETTE["default"])


def _fig_to_bytes(fig: plt.Figure) -> bytes:
    """Convert a matplotlib figure into PNG bytes."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()

class RPAChartBuilder:
    """
    Generate a donut chart plus execution time bar for completed RPA runs.

    This builder must only be invoked when run_state is NOT
    "in progress" or "pending".
    """

    # States considered "in progress" → do not generate a chart
    _IN_PROGRESS_STATES = {"in progress", "pending"}

    # Emoji per state for the title
    _STATE_EMOJI = {
        "completed": "✅",
        "failed":    "❌",
    }

    def build(self, status_dict: dict, bot_name: str) -> bytes:
        """
        Generate the chart for a completed RPA execution.

        Args:
            status_dict:
                Normalized response from BeeckerAPI.get_rpa_status().

                Expected fields:
                    run_state
                    total_transactions
                    failed_transactions
                    start_run
                    end_run
                    overtime_flag
                    avg_duration_minutes (optional)

            bot_name:
                Descriptive bot name used in the chart title
                (e.g. "AIN.002 — Order Entry").

        Returns:
            PNG image as raw bytes.

        Raises:
            ValueError:
                If the execution is still in progress.
        """
        run_state = (status_dict.get("run_state") or "").lower().strip()
        if run_state in self._IN_PROGRESS_STATES:
            raise ValueError(
                f"No se puede generar la gráfica para una ejecución en curso "
                f"(run_state='{run_state}'). "
                "Llama a build() solo cuando la ejecución haya finalizado."
            )

        total     = status_dict.get("total_transactions", 0)
        failed    = status_dict.get("failed_transactions", 0)
        completed = total - failed

        start_run = status_dict.get("start_run", "N/D")
        end_run   = status_dict.get("end_run",   "N/D")

        overtime_flag = status_dict.get("overtime_flag", False)
        avg_minutes   = status_dict.get("avg_duration_minutes")   # puede ser None
        real_minutes  = status_dict.get("duration_minutes")       # puede ser None

        # ── Layout ────────────────────────────────────────────────────────────
        has_time_bar = avg_minutes is not None and real_minutes is not None
        fig = plt.figure(
            figsize=(11, 5) if has_time_bar else (7, 5),
            facecolor=_BG_COLOR,
        )

        if has_time_bar:
            gs = GridSpec(1, 2, figure=fig, width_ratios=[1.2, 1], wspace=0.35)
            ax_donut = fig.add_subplot(gs[0])
            ax_time  = fig.add_subplot(gs[1])
        else:
            gs = GridSpec(1, 1, figure=fig)
            ax_donut = fig.add_subplot(gs[0])
            ax_time  = None

        # ── Main title ──────────────────────────────────────────────────────
        state_emoji = self._STATE_EMOJI.get(run_state, "🔹")
        overtime_tag = "  ⏰ Overtime" if overtime_flag else ""
        fig.suptitle(
            f"{bot_name}  │  {run_state.capitalize()} {state_emoji}{overtime_tag}",
            color=_TEXT_COLOR, fontsize=13, fontweight="bold", y=1.02,
        )

        # ── Donut chart ─────────────────────────────────────────────────────
        self._draw_donut(ax_donut, completed, failed, total)

        # ── Time bar ─────────────────────────────────────────────────────────
        if ax_time is not None:
            self._draw_time_bar(ax_time, avg_minutes, real_minutes, overtime_flag)

        # ── Subtitle with dates ─────────────────────────────────────────────
        fig.text(
            0.5, -0.02,
            f"Inicio: {start_run}   →   Fin: {end_run}",
            ha="center", color="#888888", fontsize=8,
        )

        return _fig_to_bytes(fig)

    @staticmethod
    def _draw_donut(
        ax: plt.Axes,
        completed: int,
        failed: int,
        total: int,
    ) -> None:
        """Draw the donut chart representing completed vs failed transactions."""
        ax.set_facecolor(_BG_COLOR)

        if total == 0:
            # No data: empty donut chart with message
            ax.pie([1], colors=["#2C2C2E"], startangle=90,
                   wedgeprops={"width": 0.5})
            ax.text(0, 0, "Sin datos", ha="center", va="center",
                    color=_TEXT_COLOR, fontsize=11)
            ax.set_title("Transacciones", color=_TEXT_COLOR, fontsize=10, pad=10)
            return

        sizes  = [completed, failed] if failed > 0 else [completed]
        colors = [_PALETTE["completed"], _PALETTE["failed"]] if failed > 0 else [_PALETTE["completed"]]
        labels = ["", ""]  # sin etiquetas en las secciones

        wedges, _ = ax.pie(
            sizes, colors=colors, labels=labels,
            startangle=90,
            wedgeprops={"width": 0.5, "edgecolor": _BG_COLOR, "linewidth": 2},
        )

        # Texto central
        pct = (completed / total * 100) if total else 0
        ax.text(0, 0.1,  f"{pct:.1f}%",  ha="center", va="center",
                color=_TEXT_COLOR, fontsize=16, fontweight="bold")
        ax.text(0, -0.2, "completadas", ha="center", va="center",
                color="#888888", fontsize=8)

        # Manual legend below the donut
        legend_items = [
            mpatches.Patch(color=_PALETTE["completed"],
                           label=f"Completadas:  {completed:,}"),
        ]
        if failed > 0:
            legend_items.append(
                mpatches.Patch(color=_PALETTE["failed"],
                               label=f"Fallidas:         {failed:,}")
            )

        ax.legend(
            handles=legend_items, loc="lower center",
            bbox_to_anchor=(0.5, -0.22), ncol=1,
            framealpha=0, labelcolor=_TEXT_COLOR, fontsize=9,
        )
        ax.set_title("Transacciones", color=_TEXT_COLOR, fontsize=10, pad=10)

    @staticmethod
    def _draw_time_bar(
        ax: plt.Axes,
        avg_minutes: float,
        real_minutes: float,
        overtime_flag: bool,
    ) -> None:
        """Draw the comparison between real execution time and historical average."""
        ax.set_facecolor(_BG_COLOR)

        max_val  = max(avg_minutes, real_minutes) * 1.3 or 1
        bar_color = _PALETTE["overtime"] if overtime_flag else _PALETTE["completed"]

        bars = ax.barh(
            ["Promedio\nhistórico", "Tiempo\nreal"],
            [avg_minutes, real_minutes],
            color=[_PALETTE["default"], bar_color],
            height=0.45,
            edgecolor=_BG_COLOR,
        )

        # Etiquetas de valor al lado de cada barra
        for bar, val in zip(bars, [avg_minutes, real_minutes]):
            h, m = divmod(int(val), 60)
            label = f"{h:02d}h {m:02d}m" if h else f"{m}m"
            ax.text(
                bar.get_width() + max_val * 0.02,
                bar.get_y() + bar.get_height() / 2,
                label, va="center", color=_TEXT_COLOR, fontsize=9,
            )

        ax.set_xlim(0, max_val * 1.25)
        ax.set_xlabel("minutos", color="#888888", fontsize=8)
        ax.tick_params(colors=_TEXT_COLOR, labelsize=8)
        ax.xaxis.label.set_color("#888888")
        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID_COLOR)
        ax.set_facecolor(_BG_COLOR)

        overtime_label = "  ⚠ Overtime" if overtime_flag else ""
        ax.set_title(f"Duración{overtime_label}", color=_TEXT_COLOR, fontsize=10, pad=10)

class AgentChartBuilder:
    """
    Generate a horizontal bar chart showing execution counts by state
    for an agent within the selected interval.
    """

    # Preferred display order and labels in Spanish
    _KNOWN_STATES: List[Tuple[str, str]] = [
        ("completed",        "Completadas"),
        ("successful",       "Exitosas"),
        ("in progress",      "En progreso"),
        ("in review",        "En revisión"),
        ("pending approval", "Pend. aprobación"),
        ("documents missing","Docs. faltantes"),
        ("failed",           "Fallidas"),
        ("pending",          "Pendientes"),
    ]
    _KNOWN_STATE_KEYS = {k for k, _ in _KNOWN_STATES}

    def build(self, agent_status: dict, agent_name: str) -> bytes:
        """
        Generate the agent execution summary chart.

        Args:
            agent_status:
                Normalized response returned by BeeckerAPI.get_agent_status().

                Expected fields:
                    executions (list)
                    total_executions (int)
                    interval_start (str)
                    interval_end (str)

            agent_name:
                Descriptive agent name used in the chart title
                (e.g. "LUCAS — Recruiter").

        Returns:
            PNG image as raw bytes.
        """
        executions     = agent_status.get("executions", [])
        total          = agent_status.get("total_executions", 0)
        interval_start = agent_status.get("interval_start", "N/D")
        interval_end   = agent_status.get("interval_end",   "N/D")

        # ── Group counts by state ─────────────────────────────────────────────
        raw_counts: Dict[str, int] = {}
        for ex in executions:
            state = (ex.get("run_state") or "unknown").lower().strip()
            raw_counts[state] = raw_counts.get(state, 0) + 1

        # Sort: first known states (in defined order), then unknown states
        ordered_labels  = []
        ordered_counts  = []
        ordered_colors  = []
        seen: set        = set()

        for state_key, label in self._KNOWN_STATES:
            if state_key in raw_counts:
                ordered_labels.append(label)
                ordered_counts.append(raw_counts[state_key])
                ordered_colors.append(_state_color(state_key))
                seen.add(state_key)

        for state_key, count in raw_counts.items():
            if state_key not in seen:
                label = " ".join(w.capitalize() for w in state_key.split())
                ordered_labels.append(label)
                ordered_counts.append(count)
                ordered_colors.append(_state_color(state_key))

        n_bars = len(ordered_labels)

        if n_bars == 0:
            # No data
            fig, ax = plt.subplots(figsize=(8, 3), facecolor=_BG_COLOR)
            ax.set_facecolor(_BG_COLOR)
            ax.text(0.5, 0.5, "Sin ejecuciones en el intervalo",
                    ha="center", va="center", transform=ax.transAxes,
                    color=_TEXT_COLOR, fontsize=12)
            ax.axis("off")
            fig.suptitle(agent_name, color=_TEXT_COLOR, fontsize=12,
                         fontweight="bold")
            return _fig_to_bytes(fig)

        fig_height = max(4, 1.0 + n_bars * 0.65)
        fig, ax = plt.subplots(figsize=(9, fig_height), facecolor=_BG_COLOR)
        ax.set_facecolor(_BG_COLOR)

        # ── Barras horizontales ────────────────────────────────────────────────
        y_pos = list(range(n_bars - 1, -1, -1))   # top to bottom
        bars  = ax.barh(
            y_pos, ordered_counts,
            color=ordered_colors,
            height=0.55,
            edgecolor=_BG_COLOR,
        )

        max_count = max(ordered_counts) if ordered_counts else 1

        # Numeric labels at the end of each bar
        for bar, count in zip(bars, ordered_counts):
            ax.text(
                bar.get_width() + max_count * 0.015,
                bar.get_y() + bar.get_height() / 2,
                str(count),
                va="center", color=_TEXT_COLOR, fontsize=9, fontweight="bold",
            )

        # Y-axis labels
        ax.set_yticks(y_pos)
        ax.set_yticklabels(ordered_labels, color=_TEXT_COLOR, fontsize=9)

        # Remove unnecessary borders
        for spine in ["top", "right", "bottom"]:
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_edgecolor(_GRID_COLOR)

        ax.tick_params(axis="x", colors=_GRID_COLOR, labelsize=0,
                       length=0)   # hide X-axis ticks and labels
        ax.set_xlim(0, max_count * 1.18)
        ax.xaxis.set_visible(False)

        # ── Title and subtitle ───────────────────────────────────────────────
        fig.suptitle(
            agent_name,
            color=_TEXT_COLOR, fontsize=12, fontweight="bold", y=1.02,
        )
        ax.set_title(
            f"{interval_start}  →  {interval_end}",
            color="#888888", fontsize=8, pad=8,
        )

        # ── Total note ───────────────────────────────────────────────────────
        fig.text(
            0.5, -0.03,
            f"Total: {total} ejecuciones",
            ha="center", color="#888888", fontsize=8,
        )

        fig.tight_layout()
        return _fig_to_bytes(fig)