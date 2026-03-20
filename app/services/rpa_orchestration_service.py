"""
app/services/rpa_orchestration_service.py
==========================================
Flujo de monitoreo RPA con soporte para múltiples configuraciones en paralelo.

Un mismo bot (id_dashboard="104" / id_beecker="AEC.001") puede tener N registros
en rpa_dashboard_monitoring (canales distintos, jobs distintos, agentes distintos).
Todos se ejecutan en paralelo con asyncio.gather.

Puntos de entrada externos:
    - Webhook Beecker (POST/PUT /rpa/execution): bot_id = id_dashboard ("104")
    - Scheduler APScheduler: job_kwargs["bot_id"] = id_beecker ("AEC.001")
      y job_kwargs["monitoring_id"] = id del registro de monitoring específico

Resolución:
    _load_relations_by_dashboard_id(db, "104")
        → devuelve LISTA de RPADashboardMonitoring para ese bot
        → cada uno puede tener su propio job, canal, agentes, etc.

    _load_relation_by_monitoring_id(db, monitoring_id)
        → carga UN registro específico por su PK (usado por el scheduler)
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
        .join(RPADashboard, RPADashboardMonitoring.id_rpa == RPADashboard.id_beecker)
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
    if relation is None:
        raise RuntimeError(
            f"No se encontró registro de monitoring con id='{monitoring_id}'."
        )
    return relation


def _build_config(relation: RPADashboardMonitoring) -> RPAConfig:
    """
    Construye RPAConfig desde los datos de la BD para un monitoring específico.

    - bot_name     → rpa.id_beecker  (visible en Slack, ej: "AEC.001")
    - id_dashboard → rpa.id_dashboard (id numérico para la API, ej: "104")
    """
    rpa = relation.rpa

    raw_unit = relation.transaction_unit or "transacciones|transacción"
    parts = raw_unit.split("|")
    unit_plural = parts[0].strip()
    unit_singular = parts[1].strip() if len(parts) > 1 else parts[0].strip()

    return RPAConfig(
        bot_name=rpa.id_beecker,
        id_dashboard=rpa.id_dashboard,
        process_name=rpa.process_name,
        transaction_unit=unit_plural,
        transaction_unit_singular=unit_singular,
        channel_name=relation.slack_channel or "",
        mention_emails=relation.roc_agents or [],
        platform=rpa.platform.value,
        enable_chart=True,
        enable_freshdesk_link=False,
    )


# ── Lógica de dispatch ────────────────────────────────────────────────────────

async def _resolve_latest_run_id(config: RPAConfig) -> str:
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


async def _dispatch_status(config: RPAConfig, run_id: str, monitoring_id: str) -> str | None:
    """
    Envía el status al Slack para una configuración específica de monitoring.
    monitoring_id se usa solo para identificar en los logs cuál de los N configs ejecutó.
    """
    try:
        monitoring = MonitoringAgent()
        await monitoring.load_config(config)
        run_state = await monitoring.send_status_rpa(
            run_id=int(run_id),
            bot_id=config.id_dashboard,
        )
        logger.info(
            f"✅ [STATUS] Mensaje enviado | bot_name={config.bot_name} | "
            f"id_dashboard={config.id_dashboard} | run_id={run_id} | "
            f"monitoring_id={monitoring_id} | channel={config.channel_name} | "
            f"run_state={run_state}"
        )
        return run_state

    except RunNotYetAvailableError:
        logger.warning(
            f"⏳ [STATUS] run_id={run_id} no disponible aún. "
            f"Lanzando retry | bot_name={config.bot_name} | monitoring_id={monitoring_id}"
        )
        asyncio.create_task(
            _retry_execution_end(config=config, run_id=run_id, monitoring_id=monitoring_id)
        )
        return None

    except BeeckerAPIError as e:
        error_str = str(e).lower()
        if "connection error" in error_str or "no se puede conectar" in error_str:
            logger.warning(
                f"⏳ [STATUS] Error de conexión, lanzando retry | "
                f"bot_name={config.bot_name} | monitoring_id={monitoring_id} | {e}"
            )
            asyncio.create_task(
                _retry_execution_end(config=config, run_id=run_id, monitoring_id=monitoring_id)
            )
            return None
        else:
            logger.error(
                f"❌ [STATUS] Error no recuperable | "
                f"bot_name={config.bot_name} | monitoring_id={monitoring_id} | {e}"
            )
            raise


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


# ── Lógica por monitoring individual ─────────────────────────────────────────

async def _handle_start_one(
    db: Session,
    relation: RPADashboardMonitoring,
    run_id: str,
) -> None:
    """Procesa el inicio para un único registro de monitoring."""
    config = _build_config(relation)

    monitoring = MonitoringAgent()
    await monitoring.load_config(config)
    await monitoring.send_initial_rpa(bot_id=config.id_dashboard)
    logger.info(
        f"✅ [START] Mensaje de inicio enviado | bot_name={config.bot_name} | "
        f"channel={config.channel_name} | monitoring_id={relation.id}"
    )

    if relation.monitor_type == MonitorType.bee_observa:
        await _activate_observa(db=db, relation=relation, run_id=run_id)


async def _handle_end_one(
    db: Session,
    relation: RPADashboardMonitoring,
    run_id: str,
) -> None:
    """Procesa el fin para un único registro de monitoring."""
    config = _build_config(relation)

    if relation.monitor_type == MonitorType.bee_observa:
        await _finalize_observa(db=db, relation=relation, run_id=run_id, config=config)
    else:
        await _dispatch_status(config=config, run_id=run_id, monitoring_id=relation.id)


# ── Activate / Finalize Observa ───────────────────────────────────────────────

async def _activate_observa(
    db: Session,
    relation: RPADashboardMonitoring,
    run_id: str,
) -> None:
    """
    Reanuda el job bee_observa e inyecta run_id y monitoring_id en sus kwargs.
    monitoring_id permite al scheduler saber exactamente qué config ejecutar.
    """
    from app.services import job_service

    job_id = relation.id_scheduler_job
    if not job_id:
        logger.warning(
            f"⚠️ [OBSERVA] monitoring_id={relation.id} no tiene id_scheduler_job. "
            f"No se puede activar el monitoreo automático."
        )
        return

    activated = job_service.activate_observa_job(db, job_id, run_id, monitoring_id=relation.id)

    if activated:
        logger.info(
            f"🟢 [OBSERVA] Job activado | bot_name={relation.rpa.id_beecker} | "
            f"run_id={run_id} | job_id={job_id} | monitoring_id={relation.id}"
        )
    else:
        logger.warning(
            f"⚠️ [OBSERVA] Job ya activo, ignorando nuevo inicio | "
            f"bot_name={relation.rpa.id_beecker} | monitoring_id={relation.id}"
        )


async def _finalize_observa(
    db: Session,
    relation: RPADashboardMonitoring,
    run_id: str,
    config: RPAConfig,
) -> None:
    from app.services import job_service

    job_id = relation.id_scheduler_job

    if job_id:
        db_job = db.get(Job, job_id)
        if db_job and db_job.status != JobStatus.active:
            logger.info(
                f"ℹ️ [OBSERVA] Job ya pausado (scheduler llegó primero), "
                f"omitiendo duplicado | monitoring_id={relation.id} | run_id={run_id}"
            )
            return

    await _dispatch_status(config=config, run_id=run_id, monitoring_id=relation.id)

    if job_id:
        job_service.pause_observa_job(db, job_id)
        logger.info(
            f"⏸ [OBSERVA] Job pausado por endpoint de fin | "
            f"monitoring_id={relation.id} | run_id={run_id}"
        )


# ── API pública ───────────────────────────────────────────────────────────────

async def handle_execution_start(db: Session, run_id: str, bot_id: str) -> None:
    """
    Maneja el inicio de una ejecución RPA (POST /rpa/execution).
    bot_id = id_dashboard numérico ("104").

    Lanza el flujo de inicio en paralelo para TODOS los registros de monitoring
    configurados para ese bot.
    """
    logger.info(f"🐝 [START] id_dashboard={bot_id} | run_id={run_id}")

    relations = _load_relations_by_dashboard_id(db, bot_id)
    logger.info(
        f"🔀 [START] {len(relations)} monitoreo(s) encontrado(s) para id_dashboard={bot_id}"
    )

    await asyncio.gather(
        *[_handle_start_one(db=db, relation=r, run_id=str(run_id)) for r in relations],
        return_exceptions=True,
    )


async def handle_execution_end(db: Session, run_id: str, bot_id: str) -> None:
    """
    Maneja el fin de una ejecución RPA (PUT /rpa/execution/{id}).
    bot_id = id_dashboard numérico ("104").

    Lanza el flujo de fin en paralelo para TODOS los registros de monitoring.
    """
    logger.info(f"🐝 [END] id_dashboard={bot_id} | run_id={run_id}")

    relations = _load_relations_by_dashboard_id(db, bot_id)
    logger.info(
        f"🔀 [END] {len(relations)} monitoreo(s) encontrado(s) para id_dashboard={bot_id}"
    )

    await asyncio.gather(
        *[_handle_end_one(db=db, relation=r, run_id=run_id) for r in relations],
        return_exceptions=True,
    )


async def send_rpa_status(
    db: Session,
    bot_id: str,
    run_id: str | None = None,
    monitoring_id: str | None = None,
) -> str | None:
    """
    Envía el status del RPA para UNA configuración específica.
    Llamado por el scheduler.

    bot_id        = id_beecker ("AEC.001")
    monitoring_id = PK del registro en rpa_dashboard_monitoring
                    Identifica exactamente qué canal/job debe ejecutar.
    run_id        = inyectado por activate_observa_job, o None para resolución automática.
    """
    logger.info(
        f"🐝 [STATUS] id_beecker={bot_id} | monitoring_id={monitoring_id} | "
        f"run_id={run_id or 'pendiente de resolver'}"
    )

    if monitoring_id:
        relation = _load_relation_by_monitoring_id(db, monitoring_id)
    else:
        # Fallback: primer registro del bot (compatibilidad con jobs viejos sin monitoring_id)
        relations = (
            db.query(RPADashboardMonitoring)
            .filter(RPADashboardMonitoring.id_rpa == bot_id)
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

    if run_id is None:
        run_id = await _resolve_latest_run_id(config=config)

    return await _dispatch_status(config=config, run_id=run_id, monitoring_id=relation.id)  