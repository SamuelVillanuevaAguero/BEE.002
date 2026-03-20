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
            return IntervalTrigger(**trigger_args)
        case TriggerType.date:
            return DateTrigger(**trigger_args)
        case _:
            raise ValueError(f"Tipo de trigger no soportado: {trigger_type}")


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
        #output = func(**kwargs)
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
        # Update next_run_time in our table
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

    # Register in APScheduler (jobstore MySQL)
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

    # Save metadata in our table
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

    # If trigger_args change, reconfigure in APScheduler
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
        pass  # El job puede no existir en APScheduler (ej: completado)
    db.delete(db_job)
    db.commit()
    logger.info(f"🗑️  Job eliminado: {job_id}")
    return True


def trigger_job_now(job_id: str) -> None:
    """Executes the job immediately without altering its schedule."""
    scheduler.get_job(job_id)  # Validates that it exists
    scheduler.modify_job(job_id, next_run_time=datetime.now(timezone.utc))


# ── History ─────────────────────────────────────────────────────────────────

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

def activate_observa_job(db, job_id: str, run_id: str, monitoring_id: str | None = None) -> bool:
    """
    Reanuda un job bee_observa pausado e inyecta run_id y monitoring_id en sus kwargs.
 
    monitoring_id identifica el registro exacto de rpa_dashboard_monitoring,
    permitiendo que el scheduler ejecute la configuración correcta (canal, agentes, etc.)
    cuando hay múltiples monitoreos para el mismo bot.
 
    Returns:
        True  → job activado correctamente.
        False → job ya estaba activo (otra ejecución en curso), se ignora.
    """
    from app.core.scheduler import scheduler
    from app.models.job import JobStatus
 
    db_job = db.get(Job, job_id)
    if not db_job:
        raise RuntimeError(f"Job {job_id} no encontrado en la BD")
 
    if db_job.status == JobStatus.active:
        return False  # Ya monitoreando, ignorar
 
    # Inyectar run_id y monitoring_id en kwargs
    new_kwargs = {**db_job.job_kwargs, "run_id": run_id}
    if monitoring_id:
        new_kwargs["monitoring_id"] = monitoring_id
 
    db_job.job_kwargs = new_kwargs
 
    # Actualizar kwargs en APScheduler ANTES de reanudar
    aps_job = scheduler.get_job(job_id)
    if aps_job:
        aps_job.modify(kwargs={
            "job_id": job_id,
            "task_path": db_job.task_path,
            **new_kwargs,
        })
 
    # Reanudar en APScheduler
    aps_job = scheduler.resume_job(job_id)
    db_job.status = JobStatus.active
    db_job.next_run_time = aps_job.next_run_time if aps_job else None
    db.commit()
    db.refresh(db_job)
    logger.info(
        f"🟢 [OBSERVA] Job activado | job_id={job_id} | "
        f"run_id={run_id} | monitoring_id={monitoring_id}"
    )
    return True
def pause_observa_job(db: Session, job_id: str) -> None:
    """
    Pausa un job bee_observa activo y elimina el run_id de sus kwargs.
    Llamado cuando la ejecución monitorada alcanza un estado terminal.
    """
    db_job = db.get(Job, job_id)
    if not db_job or db_job.status != JobStatus.active:
        return

    # Limpiar run_id de kwargs (vuelve al estado base: listo para el próximo inicio)
    clean_kwargs = {k: v for k, v in db_job.job_kwargs.items() if k != "run_id"}
    db_job.job_kwargs = clean_kwargs

    # Actualizar kwargs en APScheduler antes de pausar
    aps_job = scheduler.get_job(job_id)
    if aps_job:
        aps_job.modify(kwargs={
            "job_id": job_id,
            "task_path": db_job.task_path,
            **clean_kwargs,
        })

    scheduler.pause_job(job_id)
    db_job.status = JobStatus.paused
    db_job.next_run_time = None
    db.commit()
    logger.info(f"⏸ [OBSERVA] Job pausado y run_id limpiado | job_id={job_id}")