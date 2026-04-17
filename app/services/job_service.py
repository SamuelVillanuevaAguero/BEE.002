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
from sqlalchemy.orm import Session, joinedload

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
            raise ValueError(f"Unsupported trigger type: {trigger_type}")


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
    db = SessionLocal()
    execution = JobExecution(
        job_id=job_id,
        status=ExecutionStatus.running,
        started_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    db.commit()

    start = datetime.now(timezone.utc)
    try:
        func = _resolve_func(task_path)
        result = func(job_id=job_id, **kwargs)

        elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        execution.status = ExecutionStatus.success
        execution.result = str(result)[:500] if result else None
        execution.finished_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"✅ Job [{job_id}] executed in {elapsed_ms}ms")
        return result

    except Exception as e:
        elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        execution.status = ExecutionStatus.failure
        execution.error = str(e)[:500]
        execution.finished_at = datetime.now(timezone.utc)
        db.commit()

        logger.error(f"❌ Job [{job_id}] failed in {elapsed_ms}ms: {e}")
        raise

    finally:
        db.close()


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def create_job(db: Session, payload: JobCreate) -> Job:
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


async def list_jobs(db: Session, status: JobStatus | None = None) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc())
    if status:
        stmt = stmt.where(Job.status == status)
    return db.execute(stmt).scalars().all()


async def get_job(db: Session, job_id: str) -> Job | None:
    return db.get(Job, job_id)


async def update_job(db: Session, job_id: str, payload: JobUpdate) -> Job | None:
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


async def pause_job(db: Session, job_id: str) -> Job | None:
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


async def resume_job(db: Session, job_id: str) -> Job | None:
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


async def delete_job(db: Session, job_id: str) -> bool:
    db_job = db.get(Job, job_id)
    if not db_job:
        return False
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    db.delete(db_job)
    db.commit()
    logger.info(f"🗑️  Job deleted: {job_id}")
    return True


async def trigger_job_now(job_id: str) -> None:
    """Executes the job immediately without altering its schedule."""
    scheduler.get_job(job_id)
    scheduler.modify_job(job_id, next_run_time=datetime.now(timezone.utc))


# ── History ───────────────────────────────────────────────────────────────────

async def get_executions(
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
    offset = (page - 1) * page_size
    query = stmt.offset(offset).limit(page_size)

    result = db.execute(query)
    items = result.unique().scalars().all()

    return {"total": total, "page": page, "page_size": page_size, "items": items}


def activate_observa_job(
    db: Session,
    job_id: str,
    run_id: str,
    monitoring_id: str | None = None,
) -> bool:
    """
    Adds run_id to the list of active executions of the bee_observa job
    and resumes it if it was paused.

    resulting job_kwargs: { bot_id, monitoring_id, run_ids: [...] }
    individual run_id is NOT persisted in job_kwargs nor in APScheduler kwargs.

    Supports multiple simultaneous executions: each call adds a run_id
    to job_kwargs["run_ids"]. The job is only paused when the list is empty.

    Returns:
        True  → run_id added successfully.
        False → run_id was already in the list (duplicate ignored).
    """
    db_job = db.get(Job, job_id)
    if not db_job:
        raise RuntimeError(f"Job {job_id} not found in DB")

    existing_run_ids: list[str] = db_job.job_kwargs.get("run_ids", [])

    if run_id in existing_run_ids:
        logger.warning(
            f"⚠️ [OBSERVA] run_id={run_id} already in active list | job_id={job_id}"
        )
        return False

    new_run_ids = existing_run_ids + [run_id]

    # Build clean kwargs — without individual run_id, never
    new_kwargs = {k: v for k, v in db_job.job_kwargs.items() if k != "run_id"}
    new_kwargs["run_ids"] = new_run_ids
    if monitoring_id:
        new_kwargs["monitoring_id"] = monitoring_id

    db_job.job_kwargs = new_kwargs

    aps_job = scheduler.get_job(job_id)
    if aps_job:
        aps_job.modify(kwargs={
            "job_id": job_id,
            "task_path": db_job.task_path,
            **new_kwargs,
        })

    if db_job.status != JobStatus.active:
        aps_job = scheduler.resume_job(job_id)
        db_job.status = JobStatus.active
        db_job.next_run_time = aps_job.next_run_time if aps_job else None

    db.commit()
    db.refresh(db_job)
    logger.info(
        f"🟢 [OBSERVA] run_id added | job_id={job_id} | "
        f"active_run_ids={new_run_ids} | monitoring_id={monitoring_id}"
    )
    return True


def pause_observa_job(
    db: Session,
    job_id: str,
    finished_run_id: str | None = None,
) -> bool:
    """
    Removes finished_run_id from the active list of the bee_observa job.
    Only pauses the job when the list is completely empty.

    resulting job_kwargs: { bot_id, monitoring_id, run_ids: [...remaining] }
    individual run_id is NEVER written.

    Args:
        db:              DB session.
        job_id:          ID of the job to manage.
        finished_run_id: run_id that finished. If None, forces immediate pause.

    Returns:
        True  → list empty, job paused.
        False → still active run_ids remain, job continues.
    """
    db_job = db.get(Job, job_id)
    if not db_job:
        logger.warning(f"⚠️ [OBSERVA] Job {job_id} not found when trying to pause")
        return True  # assume paused to not block the flow

    current_run_ids: list[str] = db_job.job_kwargs.get("run_ids", [])

    remaining = (
        [r for r in current_run_ids if r != finished_run_id]
        if finished_run_id
        else []
    )

    if remaining:
        # There are still active executions — update list, without individual run_id
        new_kwargs = {k: v for k, v in db_job.job_kwargs.items() if k != "run_id"}
        new_kwargs["run_ids"] = remaining
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
            f"🔄 [OBSERVA] run_id={finished_run_id} removed, still active: {remaining} | job_id={job_id}"
        )
        return False  # job NOT paused

    # Empty list → clean kwargs and pause
    clean_kwargs = {
        k: v for k, v in db_job.job_kwargs.items()
        if k not in ("run_id", "run_ids", "seen_errors", "not_found_attempts")
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
        f"⏸ [OBSERVA] Empty list, job paused | "
        f"job_id={job_id} | last_run_id={finished_run_id}"
    )
    return True  # job paused