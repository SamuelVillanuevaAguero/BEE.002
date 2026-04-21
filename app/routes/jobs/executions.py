from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.job import ExecutionResponse
from app.schemas.response import PaginatedResponse
from app.services import job_service

router = APIRouter(prefix="/executions", tags=["Execution History"])


@router.get("/", response_model=PaginatedResponse[ExecutionResponse])
async def list_executions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists the global execution history of all jobs."""
    return await job_service.get_executions(db, job_id=None, page=page, page_size=page_size)

@router.get("/{job_id}/executions", response_model=PaginatedResponse[ExecutionResponse])
async def list_job_executions(
    job_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists the execution history of a specific job."""
    return await job_service.get_executions(db, job_id=job_id, page=page, page_size=page_size)