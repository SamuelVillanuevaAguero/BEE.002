from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, JSON, Integer, Time, ForeignKey, Enum

from app.models.job import Job
from app.db.session import Base

from app.models.rpa_dashboard import PlatformType

from datetime import time

class AgentMonitoring(Base):
    __tablename__ = "agent_monitoring"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    beecker_id: Mapped[str] = mapped_column(String(10), nullable=False)
    platform_id: Mapped[str] = mapped_column(String(10), nullable=False)
    platform: Mapped[PlatformType] = mapped_column(Enum(PlatformType), nullable=False)

    transaction_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    manage_flags: Mapped[dict] = mapped_column(JSON, nullable=False)
    roc_agents: Mapped[list] = mapped_column(JSON, nullable=True)

    SLA_time: Mapped[int] = mapped_column(Integer, nullable=False)
    transactions_exceeded_sla: Mapped[list] = mapped_column(JSON, nullable=True)

    error_status: Mapped[dict] = mapped_column(JSON, nullable=True)
    transactions_with_errors: Mapped[list] = mapped_column(JSON, nullable=True)
    completed_status: Mapped[dict] = mapped_column(JSON, nullable=True)
    cut_off_time: Mapped[time] = mapped_column(Time, nullable=False)
    
    slack_message_id: Mapped[str] = mapped_column(String(100), nullable=True)
    slack_channel_id: Mapped[str] = mapped_column(String(100), nullable=False)

    job_id: Mapped[str] = mapped_column(String(100), ForeignKey("jobs.id"))

    job: Mapped["Job"] = relationship(
        cascade="all, delete", back_populates="agent"
    )