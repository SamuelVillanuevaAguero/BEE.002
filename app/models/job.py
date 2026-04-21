import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.automation import RPADashboardMonitoring, RPAUiPathMonitoring


class TriggerType(str, enum.Enum):
    cron = "cron"
    interval = "interval"
    date = "date"


class JobStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    completed = "completed"
    error = "error"


class ExecutionStatus(str, enum.Enum):
    success = "success"
    failure = "failure"
    running = "running"


class Job(Base):

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(191), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    task_path: Mapped[str] = mapped_column(String(500), nullable=False)

    trigger_type: Mapped[TriggerType] = mapped_column(Enum(TriggerType), nullable=False)
    trigger_args: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    job_kwargs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), nullable=False, default=JobStatus.active
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    next_run_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    rpa_dashboard: Mapped["RPADashboardMonitoring"] = relationship(
        back_populates="job"
    )

    rpa_uipath: Mapped["RPAUiPathMonitoring"] = relationship(
        back_populates="job"
    )

    executions: Mapped[list["JobExecution"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan"
    )


class JobExecution(Base):

    __tablename__ = "job_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    job_id: Mapped[str] = mapped_column(
        String(191),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False
    )

    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus),
        nullable=False
    )

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    output: Mapped[str | None] = mapped_column(Text, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="executions")