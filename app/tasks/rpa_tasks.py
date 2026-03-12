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


def scheduled_rpa_status(job_id: str, bot_id: str) -> str:
    """
    Task genérica para enviar el status del último run de cualquier RPA.

    APScheduler la invoca como función síncrona a través de _wrapped_task.
    Internamente corre la corrutina send_rpa_status() con asyncio.run().

    Args:
        job_id: Inyectado automáticamente por _wrapped_task (no usar directamente).
        bot_id: id_beecker del RPA. Viene de job_kwargs al crear el job.
                Ejemplo: "aec.002", "ain.005"

    Returns:
        Mensaje de resultado (queda registrado en JobExecution.output).

    Raises:
        RuntimeError: Si no hay configuración en DB para el bot_id.
        RuntimeError: Si no hay runs recientes para el bot en Beecker.
        BeeckerAPIError: Si falla la conexión con Beecker.
    """
    from app.db.session import SessionLocal
    from app.services.rpa_orchestration_service import send_rpa_status

    logger.info(f"⏰ [SCHEDULER] Iniciando status | bot_id={bot_id} | job_id={job_id}")

    db = SessionLocal()
    try:
        asyncio.run(
            send_rpa_status(
                db=db,
                bot_id=bot_id,
                run_id=None,  # None → el servicio resuelve el último run automáticamente
            )
        )
        result = f"Status enviado correctamente para bot_id={bot_id}"
        logger.info(f"✅ [SCHEDULER] {result} | job_id={job_id}")
        return result

    except Exception as e:
        logger.error(f"❌ [SCHEDULER] Error al enviar status | bot_id={bot_id} | job_id={job_id} | {e}")
        raise

    finally:
        db.close()