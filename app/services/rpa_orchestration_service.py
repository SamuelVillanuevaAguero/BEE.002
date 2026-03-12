"""
app/services/rpa_orchestration_service.py
==========================================
Servicio de orquestación para monitoreo RPA.

Responsabilidades:
- Cargar configuración desde rpa_dashboard_client (por id_beecker)
- Construir RPAConfig dinámicamente
- Delegar a MonitoringAgent para enviar mensajes a Slack
- Soportar bee_informa (inicio + fin) y bee_observa (futuro)

Puntos de entrada públicos
--------------------------
handle_execution_start(db, run_id, bot_id)
    → Invocado por el endpoint POST /rpa/execution
    → Envía mensaje de inicio a Slack

send_rpa_status(db, bot_id, run_id=None)
    → Función GENÉRICA para enviar el status final de cualquier RPA
    → Endpoint PUT /rpa/execution/{id}  : pasa run_id desde el payload
    → Scheduler                         : omite run_id, se resuelve automáticamente
      consultando el último run en Beecker via get_run_summary()

handle_execution_end(db, run_id, bot_id)
    → Mantiene compatibilidad con el endpoint existente
    → Internamente delega a send_rpa_status()
"""

import asyncio
import logging

from sqlalchemy.orm import Session, joinedload

from app.models.automation import RPADashboardClient
from app.services.beecker.beecker_api import BeeckerAPI, BeeckerAPIError, RunNotYetAvailableError
from app.services.config.rpa_config import RPAConfig
from app.services.monitoring_service import MonitoringAgent
from app.models.automation import RPADashboardClient, RPADashboard

logger = logging.getLogger(__name__)

# Delays entre reintentos: 10s → 30s → 60s  (3 intentos máximo)
_RETRY_DELAYS_SECONDS = [10, 30, 60]


# ── Helpers privados ──────────────────────────────────────────────────────────

def _load_relation(db: Session, bot_id: str) -> RPADashboardClient:
    relation = (
        db.query(RPADashboardClient)
        .options(
            joinedload(RPADashboardClient.rpa),
            joinedload(RPADashboardClient.client),
        )
        .filter(RPADashboardClient.id_rpa == bot_id)  # ← filtro original
        .first()
    )

    if relation is None:
        raise RuntimeError(
            f"No se encontró configuración en rpa_dashboard_client "
            f"para bot_id='{bot_id}'"
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

async def _dispatch_status(config: RPAConfig, run_id: str, bot_id: str) -> None:
    """
    Núcleo compartido: instancia MonitoringAgent, envía el status y
    lanza retry en background si el run aún no está disponible en Beecker.

    Extraído para evitar duplicación entre send_rpa_status() y
    handle_execution_end().
    """
    try:
        monitoring = MonitoringAgent()
        await monitoring.load_config(config)
        await monitoring.send_status_rpa(run_id=int(run_id), bot_id=bot_id)
        logger.info(f"✅ [STATUS] Mensaje enviado | bot_id={bot_id} | run_id={run_id}")

    except RunNotYetAvailableError:
        logger.warning(
            f"⏳ [STATUS] run_id={run_id} no disponible aún en Beecker. "
            f"Lanzando retry en background | bot_id={bot_id}"
        )
        asyncio.create_task(
            _retry_execution_end(config=config, run_id=run_id, bot_id=bot_id)
        )

    except BeeckerAPIError as e:
        error_str = str(e).lower()
        if "connection error" in error_str or "no se puede conectar" in error_str:
            logger.warning(
                f"⏳ [STATUS] Error de conexión en intento inicial, lanzando retry | "
                f"bot_id={bot_id} | run_id={run_id} | {e}"
            )
            asyncio.create_task(
                _retry_execution_end(config=config, run_id=run_id, bot_id=bot_id)
            )
        else:
            logger.error(f"❌ [STATUS] Error no recuperable | bot_id={bot_id} | run_id={run_id} | {e}")
            raise


async def _retry_execution_end(config: RPAConfig, run_id: str, bot_id: str) -> None:
    """
    Reintenta _dispatch_status en background con delays crecientes.
    No bloquea el flujo principal. Máximo 3 intentos.
    """
    for attempt, delay in enumerate(_RETRY_DELAYS_SECONDS, start=1):
        logger.info(
            f"🔁 [RETRY {attempt}/{len(_RETRY_DELAYS_SECONDS)}] "
            f"Esperando {delay}s antes de reintentar | bot_id={bot_id} | run_id={run_id}"
        )
        await asyncio.sleep(delay)

        try:
            monitoring = MonitoringAgent()
            await monitoring.load_config(config)
            await monitoring.send_status_rpa(run_id=int(run_id), bot_id=bot_id)
            logger.info(
                f"✅ [RETRY {attempt}] Mensaje enviado | bot_id={bot_id} | run_id={run_id}"
            )
            return  # éxito → salimos

        except RunNotYetAvailableError:
            logger.warning(
                f"⚠️ [RETRY {attempt}] run_id={run_id} sigue sin aparecer en Beecker | bot_id={bot_id}"
            )

        except Exception as e:
            logger.error(
                f"❌ [RETRY {attempt}] Error inesperado | bot_id={bot_id} | run_id={run_id} | {e}"
            )
            return  # Error distinto al de disponibilidad → no tiene sentido seguir

    logger.error(
        f"❌ [RETRY AGOTADO] run_id={run_id} nunca apareció en Beecker "
        f"tras {len(_RETRY_DELAYS_SECONDS)} intentos | bot_id={bot_id}"
    )


# ── API pública ───────────────────────────────────────────────────────────────

async def handle_execution_start(db: Session, run_id: str, bot_id: str) -> None:
    """
    Maneja el inicio de una ejecución RPA.

    Invocado por: endpoint POST /rpa/execution

    - Carga config desde DB
    - Envía mensaje de inicio a Slack via send_initial_rpa()

    Args:
        db:     Sesión de DB.
        run_id: ID de la ejecución en Beecker (recibido del payload).
        bot_id: id_beecker del RPA (ej. "aec.002").
    """
    logger.info(f"🐝 [START] bot_id={bot_id} | run_id={run_id}")

    relation = _load_relation(db, bot_id)
    config   = _build_config(relation)

    monitoring = MonitoringAgent()
    await monitoring.load_config(config)
    await monitoring.send_initial_rpa(bot_id=bot_id)

    logger.info(f"✅ [START] Mensaje de inicio enviado | bot_id={bot_id}")


async def send_rpa_status(
    db: Session,
    bot_id: str,
    run_id: str | None = None,
) -> None:
    logger.info(f"🐝 [STATUS] bot_id={bot_id} | run_id={run_id or 'pendiente de resolver'}")

    relation = _load_relation(db, bot_id)
    config   = _build_config(relation)

    if run_id is None:
        run_id = await _resolve_latest_run_id(config=config, bot_id=bot_id)

    await _dispatch_status(config=config, run_id=run_id, bot_id=bot_id)


async def handle_execution_end(db: Session, run_id: str, bot_id: str) -> None:
    """
    Mantiene compatibilidad con el endpoint PUT /rpa/execution/{execution_id}.

    Delega internamente a send_rpa_status() para no duplicar lógica.

    Args:
        db:     Sesión de DB.
        run_id: ID de la ejecución en Beecker (recibido del payload).
        bot_id: id_beecker del RPA (ej. "aec.002").
    """
    logger.info(f"🐝 [END] bot_id={bot_id} | run_id={run_id}")
    await send_rpa_status(db=db, bot_id=bot_id, run_id=run_id)