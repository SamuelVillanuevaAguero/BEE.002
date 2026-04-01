"""
app/tasks/rpa_tasks.py
=======================
Generic task for RPA monitoring, invoked by APScheduler.

Support for multiple simultaneous executions (bee-observa):
    - activate_observa_job adds each run_id to job_kwargs["run_ids"].
    - pause_observa_job removes finished run_ids; pauses the job when the list becomes empty.
    - The job remains active while there are pending run_ids.

job_kwargs in DB/APScheduler contains only:
    {
        "bot_id":        "MME.001",
        "monitoring_id": "<uuid>",
        "run_ids":       ["165834", "165835"]   ← canonical list; individual run_id removed
    }

How to register a job for bee-observa:
    POST /jobs/
    {
        "name": "bee-observa | AEC.001 - Canal Aeromexico",
        "task_path": "app.tasks.rpa_tasks:scheduled_rpa_status",
        "trigger_type": "interval",
        "trigger_args": { "minutes": 5 },
        "job_kwargs": {
            "bot_id": "AEC.001",
            "monitoring_id": "<uuid of the record in rpa_dashboard_monitoring>"
        }
    }

    On POST /rpa/execution, activate_observa_job adds the run_id to run_ids
    and resumes the job. On PUT /rpa/execution, _finalize_observa sends the
    final status message and removes the run_id from the list.
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
    **kwargs,  # absorbs legacy 'run_id' from jobs still held in APScheduler memory
) -> str:
    """
    Generic task invoked periodically by APScheduler.

    Delegates entirely to send_rpa_status (rpa_orchestration_service):
      - If run_ids has elements → bee_observa: sends ONE merged message
        with the state of all active executions.
      - If run_ids is empty/None → bee_informa: resolves the latest run_id
        automatically from Beecker.

    The pause_observa_job logic (removing finished run_ids) is executed
    internally by _dispatch_status_multi. This task does not duplicate it.

    Args:
        job_id:        Injected automatically by _wrapped_task.
        bot_id:        id_beecker of the bot (e.g. "MME.001").
        run_ids:       List of active run_ids injected by activate_observa_job.
                       None / empty list → automatic resolution (bee_informa).
        monitoring_id: PK of the record in rpa_dashboard_monitoring.
        **kwargs:      Absorbs legacy fields (e.g. run_id) without breaking the task.
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