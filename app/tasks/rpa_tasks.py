"""
app/tasks/rpa_tasks.py
=======================
Task genérica para monitoreo RPA, invocada por APScheduler.

Soporte para múltiples ejecuciones simultáneas (bee-observa):
    - activate_observa_job agrega cada run_id a job_kwargs["run_ids"].
    - pause_observa_job recibe finished_run_id y solo pausa cuando la lista queda vacía.
    - El job sigue activo mientras haya run_ids pendientes.

Cómo registrar un job para bee-observa:
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

    Al activar el job (POST /rpa/execution), activate_observa_job inyecta run_id y run_ids.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def scheduled_rpa_status(
    job_id: str,
    bot_id: str,
    run_id: str | None = None,
    run_ids: list[str] | None = None,
    monitoring_id: str | None = None,
) -> str:
    """
    Task genérica para enviar el status de un RPA.

    Args:
        job_id:        Inyectado automáticamente por _wrapped_task.
        bot_id:        id_beecker del bot (ej: "AEC.001").
        run_id:        run_id activo principal (el primero de run_ids).
                       Inyectado por activate_observa_job.
        run_ids:       Lista completa de run_ids activos simultáneamente.
                       Cada uno que termine en estado final se remueve de la lista.
        monitoring_id: PK del registro en rpa_dashboard_monitoring.
    """
    from app.db.session import SessionLocal
    from app.services.rpa_orchestration_service import send_rpa_status
    from app.services import job_service

    # Usar run_ids si está disponible, sino caer a run_id simple (compatibilidad)
    active_run_ids: list[str] = run_ids if run_ids else ([run_id] if run_id else [])

    logger.info(
        f"⏰ [SCHEDULER] Iniciando status | bot_id={bot_id} | "
        f"run_ids={active_run_ids} | monitoring_id={monitoring_id} | job_id={job_id}"
    )

    db = SessionLocal()
    try:
        for current_run_id in list(active_run_ids):
            try:
                run_state = asyncio.run(
                    send_rpa_status(
                        db=db,
                        bot_id=bot_id,
                        run_id=current_run_id,
                        monitoring_id=monitoring_id,
                    )
                )

                # Si esta ejecución terminó → removerla de la lista activa
                if current_run_id and run_state in ("completed", "failed"):
                    job_service.pause_observa_job(
                        db=db,
                        job_id=job_id,
                        finished_run_id=current_run_id,
                    )
                    logger.info(
                        f"⏸ [OBSERVA] run_id={current_run_id} terminado "
                        f"(run_state='{run_state}') | bot_id={bot_id} | job_id={job_id}"
                    )

            except Exception as e:
                logger.error(
                    f"❌ [SCHEDULER] Error procesando run_id={current_run_id} | "
                    f"bot_id={bot_id} | job_id={job_id} | {e}"
                )

        result = f"Status enviado correctamente para bot_id={bot_id} | run_ids={active_run_ids}"
        logger.info(f"✅ [SCHEDULER] {result} | job_id={job_id}")
        return result

    finally:
        db.close()