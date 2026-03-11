from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.job import ExecutionStatus, JobStatus, TriggerType


# ── Trigger configs ───────────────────────────────────────────────────────────

class CronTriggerArgs(BaseModel):
    """Arguments for cron trigger."""
    year: str | int | None = None
    month: str | int | None = None
    day: str | int | None = None
    week: str | int | None = None
    day_of_week: str | int | None = None
    hour: str | int | None = None
    minute: str | int | None = None
    second: str | int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None


class IntervalTriggerArgs(BaseModel):
    """Arguments for interval trigger."""
    weeks: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    start_date: datetime | None = None
    end_date: datetime | None = None


class DateTriggerArgs(BaseModel):
    """Arguments for date trigger (single execution)."""
    run_date: datetime


# ── Job Schemas ───────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    task_path: str = Field(
        ...,
        description="Python function path: 'app.tasks.my_module:my_function'",
        examples=["app.tasks.examples:send_report"],
    )
    trigger_type: TriggerType
    trigger_args: dict[str, Any] = Field(
        ..., description="Trigger arguments according to its type"
    )
    job_kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Extra kwargs for the job function"
    )


class JobUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    trigger_args: dict[str, Any] | None = None
    job_kwargs: dict[str, Any] | None = None


class JobResponse(BaseModel):
    id: str
    name: str
    description: str | None
    task_path: str
    trigger_type: TriggerType
    trigger_args: dict[str, Any]
    job_kwargs: dict[str, Any]
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    next_run_time: datetime | None

    model_config = {"from_attributes": True}


# ── Execution Schemas ─────────────────────────────────────────────────────────

class ExecutionResponse(BaseModel):
    id: int
    job_id: str
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    output: str | None
    error: str | None

    model_config = {"from_attributes": True}


class PaginatedExecutions(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ExecutionResponse]
