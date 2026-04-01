"""
app/services/job_service.py
"""
import importlib
import logging
import uuid
from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.scheduler import scheduler
from app.db.session import SessionLocal
from app.models.job import ExecutionStatus, Job, JobExecution, JobStatus, TriggerType
from app.schemas.job import JobCreate, JobUpdate

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_trigger(trigger_type: TriggerType, trigger_args: dict):
    """Builds the APScheduler trigger based on the type."""
    match trigger_type:
        case TriggerType.cron:
            return CronTrigger(**trigger_args)
        case TriggerType.interval:
            normalized_args = _normalize_interval_args(trigger_args)
            return IntervalTrigger(**normalized_args)
        case TriggerType.date:
            return DateTrigger(**trigger_args)
        case _:
            raise ValueError(f"Tipo de trigger no soportado: {trigger_type}")


def _normalize_interval_args(trigger_args: dict) -> dict:
    normalized = dict(trigger_args or {})
    for key in ("weeks", "days", "hours", "minutes", "seconds"):
        value = normalized.get(key)
        if isinstance(value, str):
            try:
                normalized[key] = int(value)
            except ValueError:
                pass
    return normalized


def _resolve_func(task_path: str):
    """
    Resolves the function from its Python path.
    Expected format: 'app.tasks.my_module:my_function'
    """
    try:
        module_path, func_name = task_path.rsplit(":", 1)
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except (ValueError, ImportError, AttributeError) as e:
        raise ValueError(f"Could not resolve '{task_path}': {e}") from e


def _wrapped_task(job_id: str, task_path: str, **kwargs):
    """
    Wraps the actual job function to register execution history.
    This is the function that APScheduler actually executes.
    """
    db: Session = SessionLocal()
    started_at = datetime.now(timezone.utc)
    execution = JobExecution(
        job_id=job_id,
        status=ExecutionStatus.running,
        started_at=started_at,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    try:
        func = _resolve_func(task_path)
        output = func(job_id=job_id, **kwargs)
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        execution.status = ExecutionStatus.success
        execution.finished_at = finished_at
        execution.duration_ms = duration_ms
        execution.output = str(output) if output is not None else None
        logger.info(f"✅ Job [{job_id}] executed in {duration_ms}ms")

    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        execution.status = ExecutionStatus.failure
        execution.finished_at = finished_at
        execution.duration_ms = duration_ms
        execution.error = str(exc)
        logger.error(f"❌ Job [{job_id}] failed: {exc}")

    finally:
        try:
            aps_job = scheduler.get_job(job_id)
            job_record = db.get(Job, job_id)
            if job_record:
                job_record.next_run_time = (
                    aps_job.next_run_time if aps_job else None
                )
                if aps_job is None and job_record.trigger_type == TriggerType.date:
                    job_record.status = JobStatus.completed
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to update next_run_time: {e}")
        finally:
            db.close()


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_job(db: Session, payload: JobCreate) -> Job:
    job_id = str(uuid.uuid4())
    trigger = _build_trigger(payload.trigger_type, payload.trigger_args)

    aps_job = scheduler.add_job(
        func=_wrapped_task,
        trigger=trigger,
        id=job_id,
        name=payload.name,
        kwargs={
            "job_id": job_id,
            "task_path": payload.task_path,
            **payload.job_kwargs,
        },
        replace_existing=True,
    )

    db_job = Job(
        id=job_id,
        name=payload.name,
        description=payload.description,
        task_path=payload.task_path,
        trigger_type=payload.trigger_type,
        trigger_args=payload.trigger_args,
        job_kwargs=payload.job_kwargs,
        status=JobStatus.active,
        next_run_time=aps_job.next_run_time,
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    logger.info(f"🆕 Job created: {job_id} | next execution: {aps_job.next_run_time}")
    return db_job


def list_jobs(db: Session, status: JobStatus | None = None) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc())
    if status:
        stmt = stmt.where(Job.status == status)
    return db.execute(stmt).scalars().all()


def get_job(db: Session, job_id: str) -> Job | None:
    return db.get(Job, job_id)


def update_job(db: Session, job_id: str, payload: JobUpdate) -> Job | None:
    db_job = db.get(Job, job_id)
    if not db_job:
        return None

    if payload.name is not None:
        db_job.name = payload.name
    if payload.description is not None:
        db_job.description = payload.description

    if payload.trigger_args is not None:
        db_job.trigger_args = payload.trigger_args
        trigger = _build_trigger(db_job.trigger_type, payload.trigger_args)
        aps_job = scheduler.reschedule_job(job_id, trigger=trigger)
        db_job.next_run_time = aps_job.next_run_time if aps_job else None

    if payload.job_kwargs is not None:
        db_job.job_kwargs = payload.job_kwargs
        aps_job = scheduler.get_job(job_id)
        if aps_job:
            new_kwargs = {
                "job_id": job_id,
                "task_path": db_job.task_path,
                **payload.job_kwargs,
            }
            aps_job.modify(kwargs=new_kwargs)

    db.commit()
    db.refresh(db_job)
    return db_job


def pause_job(db: Session, job_id: str) -> Job | None:
    db_job = db.get(Job, job_id)
    if not db_job or db_job.status != JobStatus.active:
        return None
    scheduler.pause_job(job_id)
    db_job.status = JobStatus.paused
    db_job.next_run_time = None
    db.commit()
    db.refresh(db_job)
    logger.info(f"⏸  Job paused: {job_id}")
    return db_job


def resume_job(db: Session, job_id: str) -> Job | None:
    db_job = db.get(Job, job_id)
    if not db_job or db_job.status != JobStatus.paused:
        return None
    aps_job = scheduler.resume_job(job_id)
    db_job.status = JobStatus.active
    db_job.next_run_time = aps_job.next_run_time if aps_job else None
    db.commit()
    db.refresh(db_job)
    logger.info(f"▶️  Job resumed: {job_id}")
    return db_job


def delete_job(db: Session, job_id: str) -> bool:
    db_job = db.get(Job, job_id)
    if not db_job:
        return False
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    db.delete(db_job)
    db.commit()
    logger.info(f"🗑️  Job eliminado: {job_id}")
    return True


def trigger_job_now(job_id: str) -> None:
    """Executes the job immediately without altering its schedule."""
    scheduler.get_job(job_id)
    scheduler.modify_job(job_id, next_run_time=datetime.now(timezone.utc))


# ── History ───────────────────────────────────────────────────────────────────

def get_executions(
    db: Session,
    job_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    stmt = select(JobExecution).order_by(JobExecution.started_at.desc())
    count_stmt = select(func.count()).select_from(JobExecution)

    if job_id:
        stmt = stmt.where(JobExecution.job_id == job_id)
        count_stmt = count_stmt.where(JobExecution.job_id == job_id)

    total = db.execute(count_stmt).scalar()
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()

    return {"total": total, "page": page, "page_size": page_size, "items": items}


# ── Bee-Observa helpers ───────────────────────────────────────────────────────

def activate_observa_job(
    db: Session,
    job_id: str,
    run_id: str,
    monitoring_id: str | None = None,
) -> bool:
    """
    Agrega run_id a la lista de ejecuciones activas del job bee_observa
    y lo reanuda si estaba pausado.

    Soporta múltiples ejecuciones simultáneas: cada llamada agrega un run_id
    a `job_kwargs["run_ids"]`. El job solo se pausa cuando la lista queda vacía.

    Returns:
        True  → run_id agregado correctamente.
        False → run_id ya estaba en la lista (duplicado ignorado).
    """
    db_job = db.get(Job, job_id)
    if not db_job:
        raise RuntimeError(f"Job {job_id} no encontrado en la BD")

    # Obtener lista actual de run_ids activos
    existing_run_ids: list[str] = db_job.job_kwargs.get("run_ids", [])

    if run_id in existing_run_ids:
        logger.warning(
            f"⚠️ [OBSERVA] run_id={run_id} ya está en la lista activa | job_id={job_id}"
        )
        return False

    # Agregar el nuevo run_id
    new_run_ids = existing_run_ids + [run_id]
    new_kwargs = {
        **db_job.job_kwargs,
        "run_ids": new_run_ids,
        "run_id": run_id,  # compatibilidad con la task actual
    }
    if monitoring_id:
        new_kwargs["monitoring_id"] = monitoring_id

    db_job.job_kwargs = new_kwargs

    # Actualizar kwargs en APScheduler
    aps_job = scheduler.get_job(job_id)
    if aps_job:
        aps_job.modify(kwargs={
            "job_id": job_id,
            "task_path": db_job.task_path,
            **new_kwargs,
        })

    # Reanudar solo si estaba pausado
    if db_job.status != JobStatus.active:
        aps_job = scheduler.resume_job(job_id)
        db_job.status = JobStatus.active
        db_job.next_run_time = aps_job.next_run_time if aps_job else None

    db.commit()
    db.refresh(db_job)
    logger.info(
        f"🟢 [OBSERVA] run_id agregado | job_id={job_id} | "
        f"run_id={run_id} | run_ids_activos={new_run_ids} | monitoring_id={monitoring_id}"
    )
    return True


def pause_observa_job(
    db: Session,
    job_id: str,
    finished_run_id: str | None = None,
) -> None:
    """
    Elimina finished_run_id de la lista activa del job bee_observa.
    Solo pausa el job cuando la lista queda completamente vacía.

    Args:
        db:              Sesión de BD.
        job_id:          ID del job a gestionar.
        finished_run_id: run_id que terminó. Si es None, fuerza pausa inmediata
                         (comportamiento de emergencia / compatibilidad).
    """
    db_job = db.get(Job, job_id)
    if not db_job:
        logger.warning(f"⚠️ [OBSERVA] Job {job_id} no encontrado al intentar pausar")
        return

    current_run_ids: list[str] = db_job.job_kwargs.get("run_ids", [])

    # Remover el run_id que terminó
    if finished_run_id and finished_run_id in current_run_ids:
        remaining = [r for r in current_run_ids if r != finished_run_id]
    else:
        remaining = current_run_ids

    if remaining:
        # Aún hay ejecuciones activas — actualizar lista pero NO pausar
        # El run_id activo para la task es el primero de la lista restante
        new_kwargs = {
            **db_job.job_kwargs,
            "run_ids": remaining,
            "run_id": remaining[0],
        }
        db_job.job_kwargs = new_kwargs

        aps_job = scheduler.get_job(job_id)
        if aps_job:
            aps_job.modify(kwargs={
                "job_id": job_id,
                "task_path": db_job.task_path,
                **new_kwargs,
            })

        db.commit()
        logger.info(
            f"🔄 [OBSERVA] run_id={finished_run_id} terminado, "
            f"siguen activos: {remaining} | job_id={job_id}"
        )
        return

    # Lista vacía → pausar y limpiar kwargs
    clean_kwargs = {
        k: v for k, v in db_job.job_kwargs.items()
        if k not in ("run_id", "run_ids")
    }
    db_job.job_kwargs = clean_kwargs

    aps_job = scheduler.get_job(job_id)
    if aps_job:
        aps_job.modify(kwargs={
            "job_id": job_id,
            "task_path": db_job.task_path,
            **clean_kwargs,
        })

    if db_job.status == JobStatus.active:
        scheduler.pause_job(job_id)
        db_job.status = JobStatus.paused
        db_job.next_run_time = None

    db.commit()
    logger.info(
        f"⏸ [OBSERVA] Todos los run_ids terminaron, job pausado | "
        f"job_id={job_id} | último_run_id={finished_run_id}"
    )
