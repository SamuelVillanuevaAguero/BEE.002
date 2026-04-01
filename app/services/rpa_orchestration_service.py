"""
app/services/rpa_orchestration_service.py
==========================================
RPA monitoring workflow with support for multiple configurations running in parallel.

A single bot (id_dashboard="104" / id_beecker="AEC.001") can have N records
in rpa_dashboard_monitoring (different channels, different jobs, different agents).
All of them run in parallel using asyncio.gather.

External entry points:
    - Beecker Webhook (POST/PUT /rpa/execution): bot_id = id_dashboard ("104")
    - APScheduler: job_kwargs["bot_id"] = id_beecker ("AEC.001")
      and job_kwargs["monitoring_id"] = ID of the specific monitoring record

Resolution:
    _load_relations_by_dashboard_id(db, "104")
        → returns a LIST of RPADashboardMonitoring for that bot
        → each one can have its own job, channel, agents, etc.

    _load_relation_by_monitoring_id(db, monitoring_id)
        → loads ONE specific record by its PK (used by the scheduler)

manage_flags JSON → RPAConfig mapping:
    start_active          → controls whether _handle_start_one sends the initial message
    end_active            → controls whether _handle_end_one sends the end message
    enable_overtime_check → RPAConfig.enable_overtime_check
    enable_freshdesk_link → RPAConfig.enable_freshdesk_link (overrides auto-detection)
    enable_chart          → RPAConfig.enable_chart
    show_error_groups     → RPAConfig.show_error_groups
"""

import asyncio
import logging

from sqlalchemy.orm import Session, joinedload

from app.models.automation import MonitorType, RPADashboard, RPADashboardMonitoring
from app.models.job import Job, JobStatus
from app.services.beecker.beecker_api import BeeckerAPIError, RunNotYetAvailableError
from app.services.config.rpa_config import RPAConfig
from app.services.monitoring_service import MonitoringAgent

logger = logging.getLogger(__name__)

_RETRY_DELAYS_SECONDS = [10, 30, 60]
_TERMINAL_STATES = {"completed", "failed"}


# ── Loading helpers ──────────────────────────────────────────────────────────

def _load_relations_by_dashboard_id(db: Session, id_dashboard: str) -> list[RPADashboardMonitoring]:
    """
    Returns ALL monitoring records associated with the bot for the given id_dashboard.
    A bot can have multiple configurations (different channels, jobs, agents).
    Eager-load rpa → client to make id_freshdesk available without additional queries.
    """
    relations = (
        db.query(RPADashboardMonitoring)
        .join(RPADashboard, RPADashboardMonitoring.id_beecker == RPADashboard.id_beecker)
        .filter(RPADashboard.id_dashboard == id_dashboard)
        .options(
            joinedload(RPADashboardMonitoring.rpa)
            .joinedload(RPADashboard.client)
        )
        .all()
    )
    if not relations:
        raise RuntimeError(
            f"No se encontró configuración de monitoreo para id_dashboard='{id_dashboard}'. "
            f"Verifica que el bot esté registrado en rpa_dashboard y rpa_dashboard_monitoring."
        )
    return relations


def _load_relation_by_monitoring_id(db: Session, monitoring_id: str) -> RPADashboardMonitoring:
    """
    Load a single monitoring record by its primary key.
    Used by the scheduler: job_kwargs["monitoring_id"] identifies exactly
    which configuration that job should execute.
    Eager-load rpa → client to make id_freshdesk available without extra queries.
    """
    relation = (
        db.query(RPADashboardMonitoring)
        .filter(RPADashboardMonitoring.id == monitoring_id)
        .options(
            joinedload(RPADashboardMonitoring.rpa)
            .joinedload(RPADashboard.client)
        )
        .first()
    )
    if not relation:
        raise RuntimeError(
            f"No se encontró configuración de monitoreo para monitoring_id='{monitoring_id}'."
        )
    return relation


def _read_flags(relation: RPADashboardMonitoring) -> dict:
    """
    Read and normalize flags from the manage_flags JSON in the database.

    Apply RPAConfig defaults when the flag is not defined in the database,
    ensuring compatibility with records created before the new flags were added.

    Defaults:
        start_active          → True
        end_active            → True
        enable_overtime_check → False
        enable_freshdesk_link → True   (may be ignored if there is no id_freshdesk)
        enable_chart          → True
        show_error_groups     → True
    """
    flags = relation.manage_flags or {}
    return {
        "start_active":          flags.get("start_active",          True),
        "end_active":            flags.get("end_active",            True),
        "enable_overtime_check": flags.get("enable_overtime_check", False),
        "enable_freshdesk_link": flags.get("enable_freshdesk_link", True),
        "enable_chart":          flags.get("enable_chart",          True),
        "show_error_groups":     flags.get("show_error_groups",     True),
    }


def _build_config(relation: RPADashboardMonitoring) -> RPAConfig:
    """
    Construye RPAConfig desde los datos de la BD para un monitoring específico.

    - bot_name             → rpa.id_beecker            (visible en Slack, ej: "AEC.001")
    - id_dashboard         → rpa.id_dashboard           (id numérico para la API, ej: "104")
    - freshdesk_company_id → rpa.client.id_freshdesk    (id numérico empresa en FreshDesk)

    Flags leídas desde manage_flags JSON en BD:
        enable_overtime_check, enable_freshdesk_link, enable_chart, show_error_groups

    Lógica de enable_freshdesk_link:
        True solo si la flag en BD es True Y el cliente tiene id_freshdesk.
        Si la flag es False → link omitido aunque haya id_freshdesk.
        Si la flag es True pero no hay id_freshdesk → link omitido sin error.
    """
    rpa    = relation.rpa
    client = rpa.client  # disponible por el eager load

    raw_unit = relation.transaction_unit or "transacciones|transacción"
    parts = raw_unit.split("|")
    unit_plural   = parts[0].strip()
    unit_singular = parts[1].strip() if len(parts) > 1 else parts[0].strip()

    # Leer flags desde BD con defaults seguros para compatibilidad con registros viejos
    flags = _read_flags(relation)

    # ID de FreshDesk disponible en BD
    freshdesk_company_id = client.id_freshdesk if client and client.id_freshdesk else None

    # enable_freshdesk_link: flag de BD AND disponibilidad del ID en cliente
    effective_freshdesk_link = flags["enable_freshdesk_link"] and bool(freshdesk_company_id)

    return RPAConfig(
        bot_name=rpa.id_beecker,
        id_dashboard=rpa.id_dashboard,
        process_name=rpa.process_name,
        transaction_unit=unit_plural,
        transaction_unit_singular=unit_singular,
        channel_name=relation.slack_channel or "",
        mention_emails=relation.roc_agents or [],
        platform=rpa.platform.value if hasattr(rpa.platform, "value") else rpa.platform,
        # Flags de comportamiento leídas desde manage_flags en BD
        enable_overtime_check=flags["enable_overtime_check"],
        enable_freshdesk_link=effective_freshdesk_link,
        enable_chart=flags["enable_chart"],
        show_error_groups=flags["show_error_groups"],
        # FreshDesk
        freshdesk_company_id=freshdesk_company_id,
    )


async def _resolve_latest_run_id(config: RPAConfig) -> str:
    """
    Resuelve el run_id más reciente para un bot.
    Usado exclusivamente por bee_informa (sin run_ids inyectados).
    """
    from app.services.beecker.beecker_api import BeeckerAPI
    api = BeeckerAPI(platform=config.platform)
    await api.login(config.email_dash, config.password_dash)

    summary = await api.get_run_summary(bot_id=config.id_dashboard)
    last_run = summary.get("last_run")

    if not last_run:
        raise RuntimeError(
            f"No se encontró ningún run reciente para id_dashboard='{config.id_dashboard}'"
        )

    run_id = str(last_run.get("run_id") or last_run.get("id", ""))
    if not run_id:
        raise RuntimeError(
            f"El último run de id_dashboard='{config.id_dashboard}' no tiene run_id válido."
        )

    return run_id


# ── Dispatch helpers ──────────────────────────────────────────────────────────

async def _dispatch_status_single(
    config: RPAConfig,
    run_id: str,
    monitoring_id: str,
) -> str | None:
    """
    Envía el status de UNA ejecución al canal Slack.
    Usado por bee_informa (sin run_ids inyectados) y por _finalize_observa.
    """
    try:
        monitoring = MonitoringAgent()
        await monitoring.load_config(config)
        run_state = await monitoring.send_status_rpa(
            run_id=int(run_id),
            bot_id=config.id_dashboard,
        )
        logger.info(
            f"✅ [STATUS] Mensaje individual enviado | bot_name={config.bot_name} | "
            f"run_id={run_id} | monitoring_id={monitoring_id} | "
            f"channel={config.channel_name} | run_state={run_state}"
        )
        return run_state

    except RunNotYetAvailableError:
        logger.warning(
            f"⏳ [STATUS] run_id={run_id} no disponible aún. "
            f"Se reintentará en el próximo tick | monitoring_id={monitoring_id}"
        )
        raise


async def _dispatch_status_multi(
    db: Session,
    config: RPAConfig,
    run_ids: list[str],
    monitoring_id: str,
    job_id: str | None = None,
) -> dict[str, str]:
    """
    Obtiene el status de TODAS las run_ids activas y envía UN ÚNICO mensaje
    fusionado al canal Slack.

    Los bloques se ordenan cronológicamente (run_id ascendente).
    Para cada run_id en estado terminal, llama a pause_observa_job.

    Returns:
        dict {run_id: run_state} con el estado final de cada ejecución.
    """
    from app.services import job_service

    monitoring = MonitoringAgent()
    await monitoring.load_config(config)

    sorted_run_ids = sorted(run_ids, key=lambda r: int(r) if r.isdigit() else r)

    run_states = await monitoring.send_status_rpa_multi(
        run_ids=[int(r) for r in sorted_run_ids],
        bot_id=config.id_dashboard,
    )

    logger.info(
        f"✅ [STATUS] Mensaje fusionado enviado | bot_name={config.bot_name} | "
        f"run_ids={sorted_run_ids} | monitoring_id={monitoring_id} | "
        f"channel={config.channel_name} | estados={run_states}"
    )

    if job_id:
        for run_id, state in run_states.items():
            if (state or "").lower() in _TERMINAL_STATES:
                job_paused = job_service.pause_observa_job(db, job_id, run_id)
                logger.info(
                    f"{'⏸' if job_paused else '🔄'} [OBSERVA] run_id={run_id} terminal "
                    f"(state='{state}') | job_{'pausado' if job_paused else 'sigue activo'} | "
                    f"job_id={job_id}"
                )

    return run_states


# ── Handlers de inicio ────────────────────────────────────────────────────────

async def _handle_start_one(
    db: Session,
    relation: RPADashboardMonitoring,
    run_id: str,
) -> None:
    """
    Procesa el inicio de una ejecución para UN registro de monitoring.

    - Si start_active=True: envía el mensaje de inicio con #run_id.
    - Para bee_observa: agrega run_id a la lista del job (independiente de start_active).
    """
    flags = _read_flags(relation)

    if flags["start_active"]:
        config = _build_config(relation)
        monitoring = MonitoringAgent()
        await monitoring.load_config(config)
        await monitoring.send_initial_rpa(bot_id=config.id_dashboard, run_id=run_id)
        logger.info(
            f"✅ [START] Mensaje de inicio enviado | run_id={run_id} | "
            f"bot_name={config.bot_name} | channel={config.channel_name} | "
            f"monitoring_id={relation.id}"
        )
    else:
        logger.info(
            f"⏭️ [START] start_active=False, mensaje omitido | "
            f"run_id={run_id} | monitoring_id={relation.id}"
        )

    if relation.monitor_type == MonitorType.bee_observa:
        await _activate_observa(db=db, relation=relation, run_id=run_id)


# ── Handlers de fin ───────────────────────────────────────────────────────────

async def _handle_end_one(
    db: Session,
    relation: RPADashboardMonitoring,
    run_id: str,
) -> None:
    """
    Procesa el fin de una ejecución para UN registro de monitoring.

    - Si end_active=False y NO es bee_observa: omite el mensaje de fin.
    - Para bee_observa: siempre procesa (la lógica de duplicados vive en _finalize_observa).
    """
    flags = _read_flags(relation)

    if not flags["end_active"] and relation.monitor_type != MonitorType.bee_observa:
        logger.info(
            f"⏭️ [END] end_active=False, mensaje omitido | "
            f"run_id={run_id} | monitoring_id={relation.id}"
        )
        return

    config = _build_config(relation)

    if relation.monitor_type == MonitorType.bee_observa:
        await _finalize_observa(db=db, relation=relation, run_id=run_id, config=config)
    else:
        await _dispatch_status_single(config=config, run_id=run_id, monitoring_id=relation.id)


async def _activate_observa(
    db: Session,
    relation: RPADashboardMonitoring,
    run_id: str,
) -> None:
    """
    Agrega run_id al job bee_observa (o lo reanuda si estaba pausado).
    activate_observa_job maneja ambos casos internamente.
    """
    from app.services import job_service

    job_id = relation.id_scheduler_job
    if not job_id:
        logger.warning(
            f"⚠️ [OBSERVA] monitoring_id={relation.id} no tiene id_scheduler_job. "
            f"No se puede activar el monitoreo automático."
        )
        return

    added = job_service.activate_observa_job(db, job_id, run_id, monitoring_id=relation.id)
    if added:
        logger.info(
            f"🟢 [OBSERVA] run_id={run_id} registrado | "
            f"bot={relation.rpa.id_beecker} | job_id={job_id} | monitoring_id={relation.id}"
        )
    else:
        logger.warning(
            f"⚠️ [OBSERVA] run_id={run_id} ya registrado (duplicado ignorado) | "
            f"job_id={job_id}"
        )


async def _finalize_observa(
    db: Session,
    relation: RPADashboardMonitoring,
    run_id: str,
    config: RPAConfig,
) -> None:
    """
    Maneja el fin de una ejecución en bee_observa.

    1. Lee todos los run_ids activos del job (incluido el que acaba de terminar).
    2. Envía UN mensaje fusionado con el estado de todas (terminadas + en progreso).
    3. Llama a pause_observa_job para remover run_id de la lista.
       Si la lista queda vacía, el job se pausa.

    Si el job ya está pausado (el scheduler llegó primero y procesó el estado terminal),
    se omite para evitar duplicados.
    """
    from app.services import job_service

    job_id = relation.id_scheduler_job

    if job_id:
        db_job = db.get(Job, job_id)
        if db_job:
            current_run_ids = list(db_job.job_kwargs.get("run_ids") or [])

            if db_job.status != JobStatus.active and run_id not in current_run_ids:
                logger.info(
                    f"ℹ️ [OBSERVA] run_id={run_id} ya fue procesado por el scheduler, "
                    f"omitiendo duplicado | monitoring_id={relation.id}"
                )
                return

            if current_run_ids:
                await _dispatch_status_multi(
                    db=db,
                    config=config,
                    run_ids=current_run_ids,
                    monitoring_id=relation.id,
                    job_id=job_id,
                )
                return

    # Fallback: no hay job configurado, enviar mensaje individual
    await _dispatch_status_single(config=config, run_id=run_id, monitoring_id=relation.id)


async def _retry_execution_end(config: RPAConfig, run_id: str, monitoring_id: str) -> None:
    for attempt, delay in enumerate(_RETRY_DELAYS_SECONDS, start=1):
        logger.info(
            f"🔁 [RETRY {attempt}/{len(_RETRY_DELAYS_SECONDS)}] "
            f"Esperando {delay}s | bot_name={config.bot_name} | "
            f"monitoring_id={monitoring_id} | run_id={run_id}"
        )
        await asyncio.sleep(delay)
        try:
            monitoring = MonitoringAgent()
            await monitoring.load_config(config)
            await monitoring.send_status_rpa(
                run_id=int(run_id),
                bot_id=config.id_dashboard,
            )
            logger.info(
                f"✅ [RETRY {attempt}] Mensaje enviado | "
                f"bot_name={config.bot_name} | monitoring_id={monitoring_id}"
            )
            return
        except RunNotYetAvailableError:
            logger.warning(
                f"⚠️ [RETRY {attempt}] run_id={run_id} sigue sin aparecer | "
                f"bot_name={config.bot_name} | monitoring_id={monitoring_id}"
            )
        except Exception as e:
            logger.error(
                f"❌ [RETRY {attempt}] Error inesperado | "
                f"bot_name={config.bot_name} | monitoring_id={monitoring_id} | {e}"
            )
            return

    logger.error(
        f"❌ [RETRY AGOTADO] run_id={run_id} nunca apareció | "
        f"bot_name={config.bot_name} | monitoring_id={monitoring_id}"
    )


# ── Entry points públicos ─────────────────────────────────────────────────────

async def handle_execution_start(db: Session, run_id: str, bot_id: str) -> None:
    """
    Maneja el inicio de una ejecución RPA (POST /rpa/execution).
    bot_id = id_dashboard numérico (ej: "114").
    """
    logger.info(f"🐝 [START] id_dashboard={bot_id} | run_id={run_id}")

    relations = _load_relations_by_dashboard_id(db, bot_id)
    logger.info(
        f"🔀 [START] {len(relations)} monitoreo(s) encontrado(s) para id_dashboard={bot_id}"
    )

    results = await asyncio.gather(
        *[_handle_start_one(db=db, relation=r, run_id=str(run_id)) for r in relations],
        return_exceptions=True,
    )

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                f"❌ [START] Error en monitoring No. {i} | "
                f"id_dashboard={bot_id} | run_id={run_id} | {type(result).__name__}: {result}"
            )


async def handle_execution_end(db: Session, run_id: str, bot_id: str) -> None:
    """
    Maneja el fin de una ejecución RPA (PUT /rpa/execution/{id}).
    bot_id = id_dashboard numérico (ej: "114").
    """
    logger.info(f"🐝 [END] id_dashboard={bot_id} | run_id={run_id}")

    relations = _load_relations_by_dashboard_id(db, bot_id)
    logger.info(
        f"🔀 [END] {len(relations)} monitoreo(s) encontrado(s) para id_dashboard={bot_id}"
    )

    results = await asyncio.gather(
        *[_handle_end_one(db=db, relation=r, run_id=run_id) for r in relations],
        return_exceptions=True,
    )

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                f"❌ [END] Error en monitoring No. {i} | "
                f"id_dashboard={bot_id} | run_id={run_id} | {type(result).__name__}: {result}"
            )


async def send_rpa_status(
    db: Session,
    job_id: str,
    bot_id: str,
    run_ids: list[str] | None = None,
    monitoring_id: str | None = None,
) -> None:
    """
    Envía el status del RPA para UNA configuración específica.
    Llamado por el scheduler (scheduled_rpa_status en rpa_tasks.py).

    bot_id        = id_beecker ("AEC.001")
    job_id        = ID del job APScheduler (necesario para pause_observa_job)
    run_ids       = lista de run_ids activos inyectada por activate_observa_job.
                    None → resolución automática del run_id más reciente (bee_informa).
    monitoring_id = PK del registro en rpa_dashboard_monitoring.
    """
    logger.info(
        f"🐝 [STATUS] id_beecker={bot_id} | monitoring_id={monitoring_id} | "
        f"run_ids={run_ids or 'pendiente de resolver'}"
    )

    if monitoring_id:
        relation = _load_relation_by_monitoring_id(db, monitoring_id)
    else:
        relations = (
            db.query(RPADashboardMonitoring)
            .filter(RPADashboardMonitoring.id_beecker == bot_id)
            .options(
                joinedload(RPADashboardMonitoring.rpa)
                .joinedload(RPADashboard.client)
            )
            .all()
        )
        if not relations:
            raise RuntimeError(f"No se encontró monitoring para id_beecker='{bot_id}'.")
        relation = relations[0]
        logger.warning(
            f"⚠️ [STATUS] monitoring_id no proporcionado, usando primer registro | "
            f"monitoring_id={relation.id}"
        )

    config = _build_config(relation)

    if run_ids:
        await _dispatch_status_multi(
            db=db,
            config=config,
            run_ids=run_ids,
            monitoring_id=relation.id,
            job_id=job_id,
        )
    else:
        single_run_id = await _resolve_latest_run_id(config=config)
        await _dispatch_status_single(
            config=config,
            run_id=single_run_id,
            monitoring_id=relation.id,
        )