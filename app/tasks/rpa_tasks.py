"""
app/tasks/rpa_tasks.py
=======================
Task genérica para monitoreo RPA, invocada por APScheduler.

Soporte para múltiples ejecuciones simultáneas (bee-observa):
    - activate_observa_job agrega cada run_id a job_kwargs["run_ids"].
    - pause_observa_job remueve run_ids terminados; pausa el job cuando la lista queda vacía.
    - El job sigue activo mientras haya run_ids pendientes.

job_kwargs en BD/APScheduler contiene únicamente:
    {
        "bot_id":        "MME.001",
        "monitoring_id": "<uuid>",
        "run_ids":       ["165834", "165835"]   ← lista canónica; run_id individual eliminado
    }

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

    Al recibir POST /rpa/execution, activate_observa_job agrega el run_id a run_ids
    y reanuda el job. Al recibir PUT /rpa/execution, _finalize_observa envía el
    mensaje de estado final y remueve el run_id de la lista.
"""

import asyncio
import logging

from app.db.session import SessionLocal
from app.services.rpa_orchestration_service import send_rpa_status

logger = logging.getLogger(__name__)


def scheduled_rpa_status(
    job_id: str,
    bot_id: str,
    run_ids: list[str] | None = None,
    monitoring_id: str | None = None,
    **kwargs,  # absorbe 'run_id' legacy de jobs que aún lo tengan en memoria APScheduler
) -> str:
    """
    Task genérica invocada periódicamente por APScheduler.

    Delega completamente a send_rpa_status (rpa_orchestration_service):
      - Si run_ids tiene elementos → bee_observa: envía UN mensaje fusionado
        con el estado de todas las ejecuciones activas.
      - Si run_ids está vacío/None → bee_informa: resuelve el último run_id
        automáticamente desde Beecker.

    La lógica de pause_observa_job (remover run_ids terminados) la ejecuta
    _dispatch_status_multi internamente. Esta task no la duplica.

    Args:
        job_id:        Inyectado automáticamente por _wrapped_task.
        bot_id:        id_beecker del bot (ej: "MME.001").
        run_ids:       Lista de run_ids activos inyectada por activate_observa_job.
                       None / lista vacía → resolución automática (bee_informa).
        monitoring_id: PK del registro en rpa_dashboard_monitoring.
        **kwargs:      Absorbe campos legacy (ej: run_id) sin romper la task.
    """
    if kwargs:
        logger.debug(
            f"⚠️ [SCHEDULER] kwargs legacy ignorados: {list(kwargs.keys())} | job_id={job_id}"
        )

    logger.info(
        f"⏰ [SCHEDULER] Iniciando status | bot_id={bot_id} | "
        f"run_ids={run_ids} | monitoring_id={monitoring_id} | job_id={job_id}"
    )

    db = SessionLocal()
    try:
        asyncio.run(
            send_rpa_status(
                db=db,
                job_id=job_id,
                bot_id=bot_id,
                run_ids=run_ids if run_ids else None,
                monitoring_id=monitoring_id,
            )
        )

        result = f"Status enviado | bot_id={bot_id} | run_ids={run_ids}"
        logger.info(f"✅ [SCHEDULER] {result} | job_id={job_id}")
        return result

    except Exception as e:
        logger.error(
            f"❌ [SCHEDULER] Error enviando status | bot_id={bot_id} | "
            f"run_ids={run_ids} | job_id={job_id} | {e}"
        )
        raise

    finally:
        db.close()


'''# Alias para jobs creados vía POST /rpa-dashboard/full (endpoint atómico)
send_rpa_status_task = scheduled_rpa_status'''