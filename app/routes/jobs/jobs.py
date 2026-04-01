from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.job import JobStatus
from app.schemas.job import (
    ExecutionResponse,
    JobCreate,
    JobResponse,
    JobUpdate,
    PaginatedExecutions,
)
from app.services import job_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Jobs"])

# ── CRUD ──────────────────────────────────────────────────────────────────────
@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    """Creates a new job and registers it in the scheduler."""
    try:
        return job_service.create_job(db, payload)
    except HTTPException as http_exception:
        raise http_exception
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TypeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Server error")


@router.get("/", response_model=list[JobResponse])
def list_jobs(
    status: JobStatus | None = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    """Lists all jobs (optionally filters by status)."""
    try:
        return job_service.list_jobs(db, status=status)
    except HTTPException as http_exception:
        raise http_exception
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Server error")


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Gets the details of a specific job."""
    try:
        job = job_service.get_job(db, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except HTTPException as http_exception:
        raise http_exception
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Server error")


@router.patch("/{job_id}", response_model=JobResponse)
def update_job(job_id: str, payload: JobUpdate, db: Session = Depends(get_db)):
    """Updates the name, description, trigger_args, or job_kwargs of a job."""
    try:
        job = job_service.update_job(db, job_id, payload)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except HTTPException as http_exception:
        raise http_exception
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TypeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Server error")


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db)):
    """Deletes a job permanently."""
    try:
        deleted = job_service.delete_job(db, job_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Job not found")
    except HTTPException as http_exception:
        raise http_exception
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Server error")


# ── Actions ──────────────────────────────────────────────────────────────────

@router.post("/{job_id}/pause", response_model=JobResponse)
def pause_job(job_id: str, db: Session = Depends(get_db)):
    """Pauses an active job."""
    try:
        job = job_service.pause_job(db, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found or not active")
        return job
    except HTTPException as http_exception:
        raise http_exception
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Server error")


@router.post("/{job_id}/resume", response_model=JobResponse)
def resume_job(job_id: str, db: Session = Depends(get_db)):
    """Resumes a paused job."""
    try:
        job = job_service.resume_job(db, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found or not paused")
        return job
    except HTTPException as http_exception:
        raise http_exception
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Server error")


@router.post("/{job_id}/trigger", status_code=status.HTTP_202_ACCEPTED)
def trigger_job(job_id: str, db: Session = Depends(get_db)):
    """Triggers the job immediately without altering its schedule."""
    try:
        job = job_service.get_job(db, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job_service.trigger_job_now(job_id)
        return {"message": f"Job '{job.name}' triggered manually"}
    except HTTPException as http_exception:
        raise http_exception
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/{job_id}/executions", response_model=PaginatedExecutions)
def get_job_executions(
    job_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Gets the execution history of a specific job."""
    try:
        job = job_service.get_job(db, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job_service.get_executions(db, job_id=job_id, page=page, page_size=page_size)
    except HTTPException as http_exception:
        raise http_exception
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Server error")
