"""
app/tasks/rpa_tasks.py
=======================
Tasks genéricas para monitoreo RPA, invocadas por el scheduler (APScheduler).

El bot_id se inyecta como job_kwargs al registrar el job en la DB,
por lo que NO hay ningún hardcode en este archivo. La misma task sirve
para cualquier RPA del sistema.

Cómo registrar un job para un RPA
----------------------------------
POST /jobs/
{
    "name": "Status AEC.002 - 8am",
    "task_path": "app.tasks.rpa_tasks:scheduled_rpa_status",
    "trigger_type": "cron",
    "trigger_args": { "hour": 8, "minute": 0 },
    "job_kwargs": { "bot_id": "aec.002" }
}

Para otro RPA, solo cambia bot_id en job_kwargs. La task es la misma.

Notas de implementación
------------------------
- APScheduler ejecuta jobs en un contexto síncrono (_wrapped_task),
  por eso scheduled_rpa_status es síncrona y usa asyncio.run() internamente.
- La sesión de DB se abre y cierra dentro de la task para garantizar
  que cada ejecución tenga su propio contexto transaccional.
- run_id=None indica al servicio que debe resolver el último run
  disponible en Beecker automáticamente.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def scheduled_rpa_status(job_id: str, bot_id: str, run_id: str | None = None) -> str:
    """
    Task genérica para enviar el status del último run de cualquier RPA.

    Args:
        job_id:  Inyectado automáticamente por _wrapped_task.
        bot_id:  id_rpa del RPA en rpa_dashboard_client.
        run_id:  Inyectado por activate_observa_job() cuando el tipo es bee_observa.
                 None para bee_informa/bee_comunica → resuelve el último run automáticamente.
    """
    from app.db.session import SessionLocal
    from app.services.rpa_orchestration_service import send_rpa_status
    from app.services import job_service

    logger.info(
        f"⏰ [SCHEDULER] Iniciando status | bot_id={bot_id} | "
        f"run_id={run_id or 'auto'} | job_id={job_id}"
    )

    db = SessionLocal()
    try:
        run_state = asyncio.run(
            send_rpa_status(db=db, bot_id=bot_id, run_id=run_id)
        )

        # bee_observa: si la ejecución específica terminó → pausar el job
        if run_id and run_state in ("completed", "failed"):
            job_service.pause_observa_job(db, job_id)
            logger.info(
                f"⏸ [OBSERVA] Ejecución terminada (run_state='{run_state}'), "
                f"job pausado | bot_id={bot_id} | run_id={run_id}"
            )

        result = f"Status enviado correctamente para bot_id={bot_id}"
        logger.info(f"✅ [SCHEDULER] {result} | job_id={job_id}")
        return result

    except Exception as e:
        logger.error(
            f"❌ [SCHEDULER] Error al enviar status | bot_id={bot_id} | "
            f"job_id={job_id} | {e}"
        )
        raise

    finally:
        db.close()