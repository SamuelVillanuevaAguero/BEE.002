from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.job import JobStatus
from app.schemas.job import (
    JobCreate,
    JobResponse,
    JobUpdate,
)
from app.schemas.job import ExecutionResponse
from app.schemas.response import PaginatedResponse
from app.services import job_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post(
    path="/", 
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    """Creates a new job and registers it in the scheduler."""
    return await job_service.create_job(db, payload)


@router.get(
    path="/",
    response_model=list[JobResponse]
)
async def list_jobs(status: JobStatus | None = Query(None, description="Filter by status"), db: Session = Depends(get_db)):
    """Lists all jobs (optionally filters by status)."""
    return await job_service.list_jobs(db, status=status)


@router.get(
    path="/{job_id}",
    response_model=JobResponse
)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Gets the details of a specific job."""
    return await job_service.get_job(db, job_id)


@router.patch(
    path="/{job_id}",
    response_model=JobResponse
)
async def update_job(job_id: str, payload: JobUpdate, db: Session = Depends(get_db)):
    """Updates the name, description, trigger_args, or job_kwargs of a job."""
    return await job_service.update_job(db, job_id, payload)


@router.delete(
    path="/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_job(job_id: str, db: Session = Depends(get_db)):
    """Deletes a job permanently."""
    await job_service.delete_job(db, job_id)


@router.post(
    path="/{job_id}/pause",
    response_model=JobResponse
)
async def pause_job(job_id: str, db: Session = Depends(get_db)):
    """Pauses an active job."""
    return await job_service.pause_job(db, job_id)


@router.post(
    path="/{job_id}/resume",
    response_model=JobResponse
)
async def resume_job(job_id: str, db: Session = Depends(get_db)):
    """Resumes a paused job."""
    return await job_service.resume_job(db, job_id)


@router.post(
    path="/{job_id}/trigger",
    status_code=status.HTTP_202_ACCEPTED
)
async def trigger_job(job_id: str, db: Session = Depends(get_db)):
    """Triggers the job immediately without altering its schedule."""
    await job_service.trigger_job_now(job_id)
    job = await job_service.get_job(db, job_id)
    return {"message": f"Job '{job.name}' triggered manually"}

@router.post(
    "/recover",
    summary="Re-register all jobs in APScheduler",
    description="Reads all jobs from DB and re-registers them in APScheduler as paused. Use after a scheduler data loss.",
)
def recover_jobs(
    db: Session = Depends(get_db)
):
    from app.services import job_service
    result = job_service.recover_all_jobs(db)
    return result


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/{job_id}/executions", response_model=PaginatedResponse[ExecutionResponse])
async def get_job_executions(
    job_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Gets the execution history of a specific job."""
    return await job_service.get_executions(db, job_id=job_id, page=page, page_size=page_size)