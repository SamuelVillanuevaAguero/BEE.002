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

job_kwargs schema (bee_observa):
    {
        "bot_id":        "MME.001",       ← id_beecker
        "monitoring_id": "<uuid>",
        "run_ids":       ["165834", ...]  ← lista canónica; run_id individual eliminado
    }
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


# ── Helpers de carga ──────────────────────────────────────────────────────────

def _load_relations_by_dashboard_id(db: Session, id_dashboard: str) -> list[RPADashboardMonitoring]:
    """
    Devuelve TODOS los registros de monitoring asociados al bot con ese id_dashboard.
    Un bot puede tener múltiples configuraciones (canales, jobs, agentes distintos).
    """
    relations = (
        db.query(RPADashboardMonitoring)
        .join(RPADashboard, RPADashboardMonitoring.id_beecker == RPADashboard.id_beecker)
        .filter(RPADashboard.id_dashboard == id_dashboard)
        .options(joinedload(RPADashboardMonitoring.rpa))
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
    Carga UN registro de monitoring por su PK.
    Usado por el scheduler: job_kwargs["monitoring_id"] identifica exactamente
    qué configuración debe ejecutar ese job.
    """
    relation = (
        db.query(RPADashboardMonitoring)
        .filter(RPADashboardMonitoring.id == monitoring_id)
        .options(joinedload(RPADashboardMonitoring.rpa))
        .first()
    )
    if not relation:
        raise RuntimeError(
            f"No se encontró configuración de monitoreo para monitoring_id='{monitoring_id}'."
        )
    return relation


def _build_config(relation: RPADashboardMonitoring) -> RPAConfig:
    """
    Construye RPAConfig desde los datos de la BD para un monitoring específico.

    - bot_name     → rpa.id_beecker   (visible en Slack, ej: "AEC.001")
    - id_dashboard → rpa.id_dashboard (id numérico para la API, ej: "104")
    """
    rpa = relation.rpa

    raw_unit = relation.transaction_unit or "transacciones|transacción"
    parts = raw_unit.split("|")
    unit_plural   = parts[0].strip()
    unit_singular = parts[1].strip() if len(parts) > 1 else parts[0].strip()

    return RPAConfig(
        bot_name=rpa.id_beecker,
        id_dashboard=rpa.id_dashboard,
        process_name=rpa.process_name,
        transaction_unit=unit_plural,
        transaction_unit_singular=unit_singular,
        channel_name=relation.slack_channel or "",
        mention_emails=relation.roc_agents or [],
        platform=rpa.platform.value if hasattr(rpa.platform, "value") else rpa.platform,
        enable_chart=True,
        enable_freshdesk_link=False,
    )


def _get_manage_flags(relation: RPADashboardMonitoring) -> tuple[bool, bool]:
    """
    Extrae start_active y end_active de manage_flags.
    Defaults: start_active=True, end_active=True.
    """
    flags = relation.manage_flags or {}
    start_active = flags.get("start_active", True)
    end_active = flags.get("end_active", True)
    return bool(start_active), bool(end_active)


# ── Resolve run_id automático (bee_informa) ───────────────────────────────────

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

    logger.info(
        f"🔍 [STATUS] run_id={run_id} resuelto automáticamente | "
        f"bot_name={config.bot_name} | id_dashboard={config.id_dashboard}"
    )
    return run_id


# ── Dispatch: status fusionado para N run_ids (bee_observa) ──────────────────

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

    Los bloques se ordenan cronológicamente (run_id ascendente, que corresponde
    al orden de inicio de las ejecuciones).

    Para cada run_id en estado terminal, llama a pause_observa_job para
    removerlo de la lista (si job_id está disponible).

    Returns:
        dict {run_id: run_state} con el estado final de cada ejecución.
    """
    from app.services import job_service

    monitoring = MonitoringAgent()
    await monitoring.load_config(config)

    # Ordenar cronológicamente (run_id numérico ascendente)
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

    # Procesar estados terminales: remover del job
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


# ── Dispatch: status individual (bee_informa / fallback) ─────────────────────

async def _dispatch_status_single(
    config: RPAConfig,
    run_id: str,
    monitoring_id: str,
) -> str | None:
    """
    Envía el status de UNA ejecución al canal Slack.
    Usado por bee_informa (sin run_ids inyectados) y como fallback de _finalize_observa.
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


# ── Retry para ejecuciones END que aún no aparecen en Beecker ────────────────

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


# ── Handlers de inicio ────────────────────────────────────────────────────────

async def _handle_start_one(
    db: Session,
    relation: RPADashboardMonitoring,
    run_id: str,
) -> None:
    """
    Procesa el inicio de una ejecución para UN registro de monitoring.

    - Respeta manage_flags.start_active: si es False, omite el mensaje de inicio.
    - Para bee_observa: agrega run_id a la lista del job (o reanuda si estaba pausado).
    """
    config = _build_config(relation)
    start_active, _ = _get_manage_flags(relation)

    if start_active:
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
            f"⏭ [START] start_active=False, mensaje omitido | run_id={run_id} | "
            f"bot_name={config.bot_name} | monitoring_id={relation.id}"
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

    - bee_observa: envía mensaje fusionado con todos los run_ids activos.
    - bee_informa: envía mensaje individual con retry si aún no está disponible.
    - Respeta manage_flags.end_active: bee_observa lo usa para omitir
      el mensaje final cuando la lista de run_ids queda vacía.
    """
    config = _build_config(relation)
    _, end_active = _get_manage_flags(relation)

    if relation.monitor_type == MonitorType.bee_observa:
        await _finalize_observa(
            db=db,
            relation=relation,
            run_id=run_id,
            config=config,
            end_active=end_active,
        )
    else:
        # bee_informa: mensaje individual
        try:
            await _dispatch_status_single(
                config=config,
                run_id=run_id,
                monitoring_id=relation.id,
            )
        except RunNotYetAvailableError:
            asyncio.create_task(
                _retry_execution_end(
                    config=config,
                    run_id=run_id,
                    monitoring_id=relation.id,
                )
            )


# ── Lógica interna bee_observa ────────────────────────────────────────────────

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
    end_active: bool = True,
) -> None:
    """
    Maneja el fin de una ejecución en bee_observa.

    1. Lee todos los run_ids activos del job (incluido el que acaba de terminar).
    2. Envía UN mensaje fusionado con el estado de todas (terminadas + en progreso).
    3. _dispatch_status_multi llama a pause_observa_job para remover los terminados.
       Si la lista queda vacía, el job se pausa.

    Si end_active=False: pausa el job pero NO envía el mensaje Slack final.

    Si el job ya está pausado (el scheduler llegó primero y procesó el estado terminal),
    se omite para evitar duplicados.
    """
    from app.services import job_service

    job_id = relation.id_scheduler_job

    if job_id:
        db_job = db.get(Job, job_id)
        if db_job:
            current_run_ids = list(db_job.job_kwargs.get("run_ids") or [])

            # Verificar si el scheduler ya procesó este run_id
            if db_job.status != JobStatus.active and run_id not in current_run_ids:
                logger.info(
                    f"ℹ️ [OBSERVA] run_id={run_id} ya fue procesado por el scheduler, "
                    f"omitiendo duplicado | monitoring_id={relation.id}"
                )
                return

            if current_run_ids:
                if end_active:
                    # Enviar mensaje fusionado con TODOS los run_ids activos
                    # (incluyendo el que acaba de terminar, para mostrar su estado final)
                    await _dispatch_status_multi(
                        db=db,
                        config=config,
                        run_ids=current_run_ids,
                        monitoring_id=relation.id,
                        job_id=job_id,
                    )
                    # _dispatch_status_multi ya llamó pause_observa_job para los terminados
                else:
                    # end_active=False: solo remover el run_id del job, sin mensaje Slack
                    logger.info(
                        f"⏭ [OBSERVA] end_active=False, mensaje omitido | "
                        f"run_id={run_id} | monitoring_id={relation.id}"
                    )
                    job_service.pause_observa_job(db, job_id, run_id)
                return

    # Fallback: no hay job configurado, enviar mensaje individual
    if end_active:
        try:
            await _dispatch_status_single(
                config=config,
                run_id=run_id,
                monitoring_id=relation.id,
            )
        except RunNotYetAvailableError:
            asyncio.create_task(
                _retry_execution_end(
                    config=config,
                    run_id=run_id,
                    monitoring_id=relation.id,
                )
            )


# ── Entry points públicos ─────────────────────────────────────────────────────

async def handle_execution_start(db: Session, run_id: str, bot_id: str) -> None:
    """
    Maneja el inicio de una ejecución RPA (POST /rpa/execution).
    bot_id = id_dashboard numérico (ej: "114").

    - Envía mensaje de inicio con #run_id para CADA configuración de monitoring.
    - Para bee_observa: agrega run_id a run_ids del job (o reanuda si era el primero).
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

    Lanza el flujo de fin en paralelo para TODOS los registros de monitoring.
    Para bee_observa: envía mensaje fusionado inmediato y remueve run_id del job.
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
                    None / vacío → resolución automática del run_id más reciente (bee_informa).
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
            .options(joinedload(RPADashboardMonitoring.rpa))
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
        # bee_observa: mensaje fusionado con todas las ejecuciones activas
        await _dispatch_status_multi(
            db=db,
            config=config,
            run_ids=run_ids,
            monitoring_id=relation.id,
            job_id=job_id,
        )
    else:
        # bee_informa: resolución automática del run_id más reciente
        single_run_id = await _resolve_latest_run_id(config=config)
        await _dispatch_status_single(
            config=config,
            run_id=single_run_id,
            monitoring_id=relation.id,
        )