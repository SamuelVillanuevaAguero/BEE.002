"""
app/services/job_service.py
Job service with Repository pattern for clean data access abstraction.
"""
import importlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session, joinedload

from app.core.scheduler import scheduler
from app.db.session import SessionLocal
from app.models.job import ExecutionStatus, Job, JobExecution, JobStatus, TriggerType
from app.schemas.job import JobCreate, JobUpdate
from app.repositories import JobRepository
from app.repositories.job_repository import JobExecutionRepository

logger = logging.getLogger(__name__)


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

async def create_job(db: Session, payload: JobCreate) -> Job:
    """
    Create a new job using the Repository pattern.
    
    Args:
        db: Database session
        payload: Job creation payload
        
    Returns:
        The created Job instance
    """
    try:
        repo = JobRepository(db)
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

        db_job = repo.create({
            "id": job_id,
            "name": payload.name,
            "description": payload.description,
            "task_path": payload.task_path,
            "trigger_type": payload.trigger_type,
            "trigger_args": payload.trigger_args,
            "job_kwargs": payload.job_kwargs,
            "status": JobStatus.active,
            "next_run_time": aps_job.next_run_time,
        })
        logger.info(f"🆕 Job created: {job_id} | next execution: {aps_job.next_run_time}")
        return db_job
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TypeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


async def list_jobs(db: Session, status: JobStatus | None = None) -> list[Job]:
    """
    List all jobs, optionally filtered by status.
    Uses Repository pattern for data access.
    
    Args:
        db: Database session
        status: Optional JobStatus filter
        
    Returns:
        List of Job instances
    """
    try:
        repo = JobRepository(db)
        return repo.list_all(status=status)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


async def get_job(db: Session, job_id: str) -> Job:
    """
    Get a job by ID using Repository pattern.
    
    Args:
        db: Database session
        job_id: The job ID
        
    Returns:
        The Job instance
        
    Raises:
        HTTPException: If job not found
    """
    try:
        repo = JobRepository(db)
        job = repo.get_by_id(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job {job_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


async def update_job(db: Session, job_id: str, payload: JobUpdate) -> Job:
    """
    Update a job using Repository pattern with dynamic field mapping.
    
    Args:
        db: Database session
        job_id: The job ID
        payload: Job update payload
        
    Returns:
        The updated Job instance
        
    Raises:
        HTTPException: If job not found or update fails
    """
    try:
        repo = JobRepository(db)
        db_job = repo.get_by_id(job_id)
        if not db_job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        
        special_fields = {"trigger_args", "job_kwargs"}
        
        updates = payload.model_dump(exclude_unset=True)
        
        for field, value in updates.items():
            if field in special_fields:
                continue 
            setattr(db_job, field, value)
        
        if "trigger_args" in updates:
            db_job.trigger_args = updates["trigger_args"]
            trigger = _build_trigger(db_job.trigger_type, updates["trigger_args"])
            aps_job = scheduler.reschedule_job(job_id, trigger=trigger)
            db_job.next_run_time = aps_job.next_run_time if aps_job else None
        
        if "job_kwargs" in updates:
            db_job.job_kwargs = updates["job_kwargs"]
            aps_job = scheduler.get_job(job_id)
            if aps_job:
                new_kwargs = {
                    "job_id": job_id,
                    "task_path": db_job.task_path,
                    **updates["job_kwargs"],
                }
                aps_job.modify(kwargs=new_kwargs)

        repo.commit()
        repo.refresh(db_job)
        return db_job
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TypeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating job {job_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


async def pause_job(db: Session, job_id: str) -> Job:
    """
    Pause a job using Repository pattern.
    
    Args:
        db: Database session
        job_id: The job ID
        
    Returns:
        The updated Job instance
        
    Raises:
        HTTPException: If job not found or not active
    """
    try:
        repo = JobRepository(db)
        db_job = repo.get_by_id(job_id)
        if not db_job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if db_job.status != JobStatus.active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is not active")
        scheduler.pause_job(job_id)
        db_job = repo.update_status(job_id, JobStatus.paused)
        db_job = repo.update_next_run_time(job_id, None)
        logger.info(f"⏸  Job paused: {job_id}")
        return db_job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing job {job_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


async def resume_job(db: Session, job_id: str) -> Job:
    """
    Resume a paused job using Repository pattern.
    
    Args:
        db: Database session
        job_id: The job ID
        
    Returns:
        The updated Job instance
        
    Raises:
        HTTPException: If job not found or not paused
    """
    try:
        repo = JobRepository(db)
        db_job = repo.get_by_id(job_id)
        if not db_job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if db_job.status != JobStatus.paused:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is not paused")
        aps_job = scheduler.resume_job(job_id)
        db_job = repo.update_status(job_id, JobStatus.active)
        db_job = repo.update_next_run_time(job_id, aps_job.next_run_time if aps_job else None)
        logger.info(f"▶️  Job resumed: {job_id}")
        return db_job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming job {job_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


async def delete_job(db: Session, job_id: str) -> bool:
    """
    Delete a job using Repository pattern.
    
    Args:
        db: Database session
        job_id: The job ID
        
    Returns:
        True if deleted successfully
        
    Raises:
        HTTPException: If job not found
    """
    try:
        repo = JobRepository(db)
        if not repo.exists(job_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
        result = repo.delete(job_id)
        logger.info(f"🗑️  Job deleted: {job_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


async def trigger_job_now(job_id: str) -> None:
    """Executes the job immediately without altering its schedule."""
    try:
        job = scheduler.get_job(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        scheduler.modify_job(job_id, next_run_time=datetime.now(timezone.utc))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering job {job_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


# History

async def get_executions(
    db: Session,
    job_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """
    Get execution history using Repository pattern with pagination.
    
    Args:
        db: Database session
        job_id: Optional job ID filter
        page: Page number (1-indexed)
        page_size: Number of items per page
        
    Returns:
        Dictionary with pagination info and execution items
        
    Raises:
        HTTPException: If job not found (when job_id is provided)
    """
    try:
        exec_repo = JobExecutionRepository(db)
        
        if job_id:
            job_repo = JobRepository(db)
            if not job_repo.exists(job_id):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        
        return exec_repo.get_executions_paginated(job_id=job_id, page=page, page_size=page_size)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting executions for job {job_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


def activate_observa_job(
    db: Session,
    job_id: str,
    run_id: str,
    monitoring_id: str | None = None,
) -> bool:
    """
    Adds run_id to the list of active executions of the bee_observa job using Repository pattern.
    Resumes the job if it was paused.

    resulting job_kwargs: { bot_id, monitoring_id, run_ids: [...] }
    individual run_id is NOT persisted in job_kwargs nor in APScheduler kwargs.

    Supports multiple simultaneous executions: each call adds a run_id
    to job_kwargs["run_ids"]. The job is only paused when the list is empty.

    Args:
        db: Database session
        job_id: The job ID
        run_id: The run ID to add
        monitoring_id: Optional monitoring ID

    Returns:
        True  → run_id added successfully.
        False → run_id was already in the list (duplicate ignored).
    """
    repo = JobRepository(db)
    db_job = repo.get_by_id(job_id)
    if not db_job:
        raise RuntimeError(f"Job {job_id} not found in DB")

    existing_run_ids: list[str] = db_job.job_kwargs.get("run_ids", [])

    if run_id in existing_run_ids:
        logger.warning(f"⚠️ [OBSERVA] run_id={run_id} already in active list | job_id={job_id}")
        return False

    new_run_ids = existing_run_ids + [run_id]

    # Build clean kwargs — without individual run_id, never
    new_kwargs = {k: v for k, v in db_job.job_kwargs.items() if k != "run_id"}
    new_kwargs["run_ids"] = new_run_ids
    if monitoring_id:
        new_kwargs["monitoring_id"] = monitoring_id

    db_job = repo.update_job_kwargs(job_id, new_kwargs)

    aps_job = scheduler.get_job(job_id)
    if aps_job:
        aps_job.modify(kwargs={
            "job_id": job_id,
            "task_path": db_job.task_path,
            **new_kwargs,
        })

    if db_job.status != JobStatus.active:
        aps_job = scheduler.resume_job(job_id)
        db_job = repo.update_status(job_id, JobStatus.active)
        db_job = repo.update_next_run_time(job_id, aps_job.next_run_time if aps_job else None)

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
    Removes finished_run_id from the active list of the bee_observa job using Repository pattern.
    Only pauses the job when the list is completely empty.

    resulting job_kwargs: { bot_id, monitoring_id, run_ids: [...remaining] }
    individual run_id is NEVER written.

    Args:
        db: DB session.
        job_id: ID of the job to manage.
        finished_run_id: run_id that finished. If None, forces immediate pause.

    Returns:
        True  → list empty, job paused.
        False → still active run_ids remain, job continues.
    """
    repo = JobRepository(db)
    db_job = repo.get_by_id(job_id)
    if not db_job:
        logger.warning(f"⚠️ [OBSERVA] Job {job_id} not found when trying to pause")
        return True

    current_run_ids: list[str] = db_job.job_kwargs.get("run_ids", [])

    remaining = (
        [r for r in current_run_ids if r != finished_run_id]
        if finished_run_id
        else []
    )

    if remaining:
        new_kwargs = {k: v for k, v in db_job.job_kwargs.items() if k != "run_id"}
        new_kwargs["run_ids"] = remaining
        db_job = repo.update_job_kwargs(job_id, new_kwargs)

        aps_job = scheduler.get_job(job_id)
        if aps_job:
            aps_job.modify(kwargs={
                "job_id": job_id,
                "task_path": db_job.task_path,
                **new_kwargs,
            })

        logger.info(
            f"🔄 [OBSERVA] run_id={finished_run_id} removed, still active: {remaining} | job_id={job_id}"
        )
        return False

    clean_kwargs = {
        k: v for k, v in db_job.job_kwargs.items()
        if k not in ("run_id", "run_ids", "seen_errors", "not_found_attempts")
    }
    db_job = repo.update_job_kwargs(job_id, clean_kwargs)

    aps_job = scheduler.get_job(job_id)
    if aps_job:
        aps_job.modify(kwargs={
            "job_id": job_id,
            "task_path": db_job.task_path,
            **clean_kwargs,
        })

    if db_job.status == JobStatus.active:
        scheduler.pause_job(job_id)
        db_job = repo.update_status(job_id, JobStatus.paused)
        db_job = repo.update_next_run_time(job_id, None)

    logger.info(
        f"⏸ [OBSERVA] Empty list, job paused | "
        f"job_id={job_id} | last_run_id={finished_run_id}"
    )
    return True