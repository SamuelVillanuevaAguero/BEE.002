"""
app/services/rpa_orchestration_service.py
==========================================
...
handle_execution_start(db, run_id, bot_id)
    → bee_informa : envía mensaje de inicio
    → bee_observa : envía mensaje de inicio + activa el job con el run_id específico
                    (si el job ya está activo, ignora el nuevo inicio)

handle_execution_end(db, run_id, bot_id)
    → bee_informa : envía status final (comportamiento original)
    → bee_observa : si el job aún está activo (endpoint llegó primero)
                        → envía status + pausa el job
                    si el job ya está pausado (scheduler llegó primero)
                        → no hace nada (evitar duplicado)

send_rpa_status(db, bot_id, run_id=None)  →  str | None
    → Ahora retorna el run_state para que el scheduler pueda pausar al detectar fin
"""

import asyncio
import logging

from sqlalchemy.orm import Session, joinedload

from app.models.automation import MonitorType, RPADashboard, RPADashboardClient
from app.models.job import Job, JobStatus
from app.services.beecker.beecker_api import BeeckerAPI, BeeckerAPIError, RunNotYetAvailableError
from app.services.config.rpa_config import RPAConfig
from app.services.monitoring_service import MonitoringAgent

logger = logging.getLogger(__name__)

_RETRY_DELAYS_SECONDS = [10, 30, 60]
_TERMINAL_STATES = {"completed", "failed"}


# ── Helpers privados ──────────────────────────────────────────────────────────

def _load_relation(db: Session, bot_id: str) -> RPADashboardClient:
    relation = (
        db.query(RPADashboardClient)
        .options(
            joinedload(RPADashboardClient.rpa),
            joinedload(RPADashboardClient.client),
        )
        .filter(RPADashboardClient.id_rpa == bot_id)
        .first()
    )
    if relation is None:
        raise RuntimeError(
            f"No se encontró configuración en rpa_dashboard_client para bot_id='{bot_id}'"
        )
    return relation


def _build_config(relation: RPADashboardClient) -> RPAConfig:
    """Construye RPAConfig dinámicamente desde los datos de la DB."""
    rpa = relation.rpa

    raw_unit      = relation.transaction_unit or "transacciones|transacción"
    parts         = raw_unit.split("|")
    unit_plural   = parts[0].strip()
    unit_singular = parts[1].strip() if len(parts) > 1 else parts[0].strip()

    mention_emails: list[str] = relation.roc_agents or []

    return RPAConfig(
        bot_name=rpa.id_beecker,
        process_name=rpa.process_name,
        transaction_unit=unit_plural,
        transaction_unit_singular=unit_singular,
        channel_name=relation.slack_channel or "",
        mention_emails=mention_emails,
        platform=rpa.platform.value,
        enable_chart=True,
        enable_freshdesk_link=False,
    )


async def _resolve_latest_run_id(config: RPAConfig, bot_id: str) -> str:
    api = BeeckerAPI(platform=config.platform)
    await api.login(config.email_dash, config.password_dash)  # ← agregar credenciales

    summary  = await api.get_run_summary(bot_id=bot_id)
    last_run = summary.get("last_run")

    if not last_run:
        raise RuntimeError(
            f"No se encontró ningún run reciente para bot_id='{bot_id}'"
        )

    run_id = str(last_run.get("run_id") or last_run.get("id", ""))

    if not run_id:
        raise RuntimeError(
            f"El último run de bot_id='{bot_id}' no tiene run_id válido: {last_run}"
        )

    logger.info(f"🔍 [STATUS] run_id={run_id} resuelto automáticamente | bot_id={bot_id}")
    return run_id


async def _dispatch_status(config: RPAConfig, run_id: str, bot_id: str) -> str | None:
    """
    Envía el status al Slack y retorna el run_state.

    Returns:
        run_state en minúsculas ('completed', 'failed', 'in progress', ...)
        o None si el run no está disponible aún / error de conexión.
    """
    try:
        monitoring = MonitoringAgent()
        await monitoring.load_config(config)
        run_state = await monitoring.send_status_rpa(run_id=int(run_id), bot_id=bot_id)
        logger.info(f"✅ [STATUS] Mensaje enviado | bot_id={bot_id} | run_id={run_id} | run_state={run_state}")
        return run_state

    except RunNotYetAvailableError:
        logger.warning(
            f"⏳ [STATUS] run_id={run_id} no disponible aún en Beecker. "
            f"Lanzando retry en background | bot_id={bot_id}"
        )
        asyncio.create_task(
            _retry_execution_end(config=config, run_id=run_id, bot_id=bot_id)
        )
        return None

    except BeeckerAPIError as e:
        error_str = str(e).lower()
        if "connection error" in error_str or "no se puede conectar" in error_str:
            logger.warning(
                f"⏳ [STATUS] Error de conexión, lanzando retry | bot_id={bot_id} | run_id={run_id} | {e}"
            )
            asyncio.create_task(
                _retry_execution_end(config=config, run_id=run_id, bot_id=bot_id)
            )
            return None
        else:
            logger.error(f"❌ [STATUS] Error no recuperable | bot_id={bot_id} | run_id={run_id} | {e}")
            raise


async def _retry_execution_end(config: RPAConfig, run_id: str, bot_id: str) -> None:
    """Reintenta _dispatch_status en background. Sin cambios respecto al original."""
    for attempt, delay in enumerate(_RETRY_DELAYS_SECONDS, start=1):
        logger.info(
            f"🔁 [RETRY {attempt}/{len(_RETRY_DELAYS_SECONDS)}] "
            f"Esperando {delay}s | bot_id={bot_id} | run_id={run_id}"
        )
        await asyncio.sleep(delay)
        try:
            monitoring = MonitoringAgent()
            await monitoring.load_config(config)
            await monitoring.send_status_rpa(run_id=int(run_id), bot_id=bot_id)
            logger.info(f"✅ [RETRY {attempt}] Mensaje enviado | bot_id={bot_id} | run_id={run_id}")
            return
        except RunNotYetAvailableError:
            logger.warning(f"⚠️ [RETRY {attempt}] run_id={run_id} sigue sin aparecer | bot_id={bot_id}")
        except Exception as e:
            logger.error(f"❌ [RETRY {attempt}] Error inesperado | bot_id={bot_id} | {e}")
            return

    logger.error(
        f"❌ [RETRY AGOTADO] run_id={run_id} nunca apareció tras "
        f"{len(_RETRY_DELAYS_SECONDS)} intentos | bot_id={bot_id}"
    )


# ── API pública ───────────────────────────────────────────────────────────────

async def handle_execution_start(db: Session, run_id: str, bot_id: str) -> None:
    """
    Maneja el inicio de una ejecución RPA (POST /rpa/execution).

    bee_informa : solo envía mensaje de inicio.
    bee_observa : envía mensaje de inicio + activa el job con el run_id específico.
                  Si el job ya está activo (otra ejecución en curso), ignora la activación.
    """
    logger.info(f"🐝 [START] bot_id={bot_id} | run_id={run_id}")

    relation = _load_relation(db, bot_id)
    config   = _build_config(relation)

    # Mensaje de inicio (igual para todos los tipos)
    monitoring = MonitoringAgent()
    await monitoring.load_config(config)
    await monitoring.send_initial_rpa(bot_id=bot_id)
    logger.info(f"✅ [START] Mensaje de inicio enviado | bot_id={bot_id}")

    # bee_observa: activar el scheduler con el run_id específico
    if relation.monitor_type == MonitorType.bee_observa:
        await _activate_observa(db=db, relation=relation, run_id=str(run_id), bot_id=bot_id)


async def _activate_observa(
    db: Session,
    relation: RPADashboardClient,
    run_id: str,
    bot_id: str,
) -> None:
    """Reanuda el job bee_observa e inyecta el run_id en sus kwargs."""
    from app.services import job_service

    job_id = relation.id_scheduler_job
    if not job_id:
        logger.warning(
            f"⚠️ [OBSERVA] bot_id={bot_id} no tiene id_scheduler_job configurado. "
            f"No se puede activar el monitoreo automático."
        )
        return

    activated = job_service.activate_observa_job(db, job_id, run_id)

    if activated:
        logger.info(
            f"🟢 [OBSERVA] Job activado | bot_id={bot_id} | run_id={run_id} | job_id={job_id}"
        )
    else:
        logger.warning(
            f"⚠️ [OBSERVA] Job ya activo (otra ejecución en curso), "
            f"ignorando nuevo inicio | bot_id={bot_id} | run_id={run_id}"
        )


async def send_rpa_status(
    db: Session,
    bot_id: str,
    run_id: str | None = None,
) -> str | None:
    """
    Envía el status del RPA y retorna el run_state.

    Returns:
        run_state normalizado o None si no se pudo obtener.
    """
    logger.info(f"🐝 [STATUS] bot_id={bot_id} | run_id={run_id or 'pendiente de resolver'}")

    relation = _load_relation(db, bot_id)
    config   = _build_config(relation)

    if run_id is None:
        run_id = await _resolve_latest_run_id(config=config, bot_id=bot_id)

    return await _dispatch_status(config=config, run_id=run_id, bot_id=bot_id)


async def handle_execution_end(db: Session, run_id: str, bot_id: str) -> None:
    """
    Maneja el fin de una ejecución RPA (PUT /rpa/execution/{id}).

    bee_informa : envía status final (comportamiento original).
    bee_observa : si el job sigue activo (endpoint llegó primero)
                      → envía status + pausa el job.
                  si el job ya está pausado (scheduler llegó primero)
                      → no hace nada para evitar duplicado.
    """
    logger.info(f"🐝 [END] bot_id={bot_id} | run_id={run_id}")

    relation = _load_relation(db, bot_id)

    if relation.monitor_type == MonitorType.bee_observa:
        await _finalize_observa(db=db, relation=relation, run_id=run_id, bot_id=bot_id)
    else:
        # bee_informa / bee_comunica: comportamiento original
        await send_rpa_status(db=db, bot_id=bot_id, run_id=run_id)


async def _finalize_observa(
    db: Session,
    relation: RPADashboardClient,
    run_id: str,
    bot_id: str,
) -> None:
    """Lógica de fin para bee_observa: pausa el job si el endpoint llegó primero."""
    from app.services import job_service

    job_id = relation.id_scheduler_job

    # Verificar si el scheduler ya pausó el job
    if job_id:
        db_job = db.get(Job, job_id)
        if db_job and db_job.status != JobStatus.active:
            logger.info(
                f"ℹ️ [OBSERVA] Job ya pausado (scheduler llegó primero), "
                f"omitiendo status duplicado | bot_id={bot_id} | run_id={run_id}"
            )
            return

    # Endpoint llegó primero → enviar status y pausar
    config = _build_config(relation)
    await _dispatch_status(config=config, run_id=run_id, bot_id=bot_id)

    if job_id:
        job_service.pause_observa_job(db, job_id)
        logger.info(
            f"⏸ [OBSERVA] Job pausado por endpoint de fin | bot_id={bot_id} | run_id={run_id}"
        )