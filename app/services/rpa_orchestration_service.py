"""
app/services/rpa_orchestration_service.py
==========================================
Servicio de orquestación para monitoreo RPA.

Responsabilidades:
- Cargar configuración desde rpa_dashboard_client (por id_beecker)
- Construir RPAConfig dinámicamente
- Delegar a MonitoringAgent para enviar mensajes a Slack
- Soportar bee_informa (inicio + fin) y bee_observa (futuro)
"""

import logging
from sqlalchemy.orm import Session, joinedload

from app.models.automation import RPADashboardClient, MonitorType
from app.services.monitoring_service import MonitoringAgent
from app.services.config.rpa_config import RPAConfig

import asyncio

from sqlalchemy.orm import Session
from app.services.beecker.beecker_api import RunNotYetAvailableError, BeeckerAPIError

logger = logging.getLogger(__name__)

# Configuración del retry
_RETRY_DELAYS_SECONDS = [10, 30, 60]  # 3 intentos: 30s, 1min, 2min

logger = logging.getLogger(__name__)


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
            f"No se encontró configuración en rpa_dashboard_client "
            f"para bot_id='{bot_id}'"
        )

    return relation

def _build_config(relation: RPADashboardClient) -> RPAConfig:
    """Construye RPAConfig dinámicamente desde los datos de la DB."""
    rpa = relation.rpa

    raw_unit = relation.transaction_unit or "transacciones|transacción"
    parts    = raw_unit.split("|")
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


# ── API pública ───────────────────────────────────────────────────────────────

async def handle_execution_start(db: Session, run_id: str, bot_id: str) -> None:
    """
    Maneja el inicio de una ejecución RPA.

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


async def handle_execution_end(db: Session, run_id: str, bot_id: str) -> None:
    logger.info(f"🐝 [END] bot_id={bot_id} | run_id={run_id}")

    relation = _load_relation(db, bot_id)
    config   = _build_config(relation)

    try:
        monitoring = MonitoringAgent()
        await monitoring.load_config(config)
        await monitoring.send_status_rpa(run_id=int(run_id), bot_id=bot_id)
        logger.info(f"✅ [END] Mensaje de fin enviado | bot_id={bot_id} | run_id={run_id}")

    except RunNotYetAvailableError:
        logger.warning(
            f"⏳ [END] run_id={run_id} no disponible aún en Beecker. "
            f"Lanzando retry en background | bot_id={bot_id}"
        )
        asyncio.create_task(
            _retry_execution_end(config=config, run_id=run_id, bot_id=bot_id)
        )

    except BeeckerAPIError as e:
        # Captura errores de conexión en el intento inicial (ej. login falló)
        error_str = str(e).lower()
        if "connection error" in error_str or "no se puede conectar" in error_str:
            logger.warning(
                f"⏳ [END] Error de conexión en intento inicial, lanzando retry | "
                f"bot_id={bot_id} | run_id={run_id} | {e}"
            )
            asyncio.create_task(
                _retry_execution_end(config=config, run_id=run_id, bot_id=bot_id)
            )
        else:
            logger.error(f"❌ [END] Error no recuperable | bot_id={bot_id} | run_id={run_id} | {e}")
            raise


async def _retry_execution_end(config: RPAConfig, run_id: str, bot_id: str) -> None:
    """
    Reintenta send_status_rpa en background con delays crecientes.
    No bloquea el flujo principal. Se ejecuta hasta 3 veces.
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
                f"✅ [RETRY {attempt}] Mensaje de fin enviado | bot_id={bot_id} | run_id={run_id}"
            )
            return  # ← éxito, salimos

        except RunNotYetAvailableError:
            logger.warning(
                f"⚠️ [RETRY {attempt}] run_id={run_id} sigue sin aparecer en Beecker | bot_id={bot_id}"
            )

        except Exception as e:
            logger.error(
                f"❌ [RETRY {attempt}] Error inesperado | bot_id={bot_id} | run_id={run_id} | {e}"
            )
            return  # Error distinto al de disponibilidad, no tiene sentido seguir

    logger.error(
        f"❌ [RETRY AGOTADO] run_id={run_id} nunca apareció en Beecker "
        f"tras {len(_RETRY_DELAYS_SECONDS)} intentos | bot_id={bot_id}"
    )