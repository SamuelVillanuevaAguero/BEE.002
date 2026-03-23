"""
app/tasks/rpa_tasks.py
=======================
Task genérica para monitoreo RPA, invocada por APScheduler.

Cambio respecto a la versión anterior:
    - scheduled_rpa_status ahora acepta monitoring_id (inyectado por activate_observa_job)
    - monitoring_id se pasa a send_rpa_status para que cargue exactamente la configuración
      correcta cuando hay múltiples monitoreos para el mismo bot.

Cómo registrar un job para bee-observa
----------------------------------------
POST /jobs/
{
    "name": "bee-observa | AEC.001 - Canal Aeromexico",
    "task_path": "app.tasks.rpa_tasks:scheduled_rpa_status",
    "trigger_type": "interval",
    "trigger_args": { "minutes": 5 },
    "job_kwargs": {
        "bot_id": "AEC.001",
        "monitoring_id": "<uuid del registro en rpa_dashboard_monitoring>"
    }
}

Al activar el job (POST /rpa/execution), activate_observa_job inyecta además run_id.
"""

import asyncio
import logging
from app.db.session import SessionLocal
from app.services.rpa_orchestration_service import send_rpa_status
from app.services import job_service

logger = logging.getLogger(__name__)


def scheduled_rpa_status(
    job_id: str,
    bot_id: str,
    run_id: str | None = None,
    monitoring_id: str | None = None,
) -> str:
    """
    Task genérica para enviar el status de un RPA.

    Args:
        job_id:        Inyectado automáticamente por _wrapped_task.
        bot_id:        id_beecker del bot (ej: "AEC.001").
        run_id:        Inyectado por activate_observa_job para bee_observa.
                       None para bee_informa/bee_comunica → resuelve automáticamente.
        monitoring_id: PK del registro en rpa_dashboard_monitoring.
                       Identifica exactamente qué canal/config ejecutar.
    """

    logger.info(
        f"⏰ [SCHEDULER] Iniciando status | bot_id={bot_id} | "
        f"run_id={run_id or 'auto'} | monitoring_id={monitoring_id} | job_id={job_id}"
    )

    db = SessionLocal()
    try:
        run_state = asyncio.run(
            send_rpa_status(
                db=db,
                bot_id=bot_id,
                run_id=run_id,
                monitoring_id=monitoring_id,
            )
        )

        # bee_observa: si la ejecución terminó → pausar el job
        if run_id and run_state in ("completed", "failed"):
            job_service.pause_observa_job(db, job_id)
            logger.info(
                f"⏸ [OBSERVA] Ejecución terminada (run_state='{run_state}'), "
                f"job pausado | bot_id={bot_id} | monitoring_id={monitoring_id} | run_id={run_id}"
            )

        result = f"Status enviado correctamente para bot_id={bot_id}"
        logger.info(f"✅ [SCHEDULER] {result} | job_id={job_id}")
        return result

    except Exception as e:
        logger.error(
            f"❌ [SCHEDULER] Error al enviar status | bot_id={bot_id} | "
            f"monitoring_id={monitoring_id} | job_id={job_id} | {e}"
        )
        raise

    finally:
        db.close()