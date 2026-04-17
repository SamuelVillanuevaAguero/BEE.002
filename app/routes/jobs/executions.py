from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.job import PaginatedExecutions
from app.services import job_service

router = APIRouter(prefix="/executions", tags=["Execution History"])


@router.get("/", response_model=PaginatedExecutions)
async def list_executions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists the global execution history of all jobs."""
    return await job_service.get_executions(db, job_id=None, page=page, page_size=page_size)
