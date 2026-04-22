import enum

from sqlalchemy import (
    JSON,
    Enum,
    ForeignKey,
    String
)

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.job import Job
from app.models.client import Client


class PlatformType(str, enum.Enum):
    cloud = "cloud"
    hub = "hub"


class MonitorType(str, enum.Enum):
    bee_observa = "bee-observa"
    bee_informa = "bee-informa"
    bee_comunica = "bee-comunica"


class RPADashboard(Base):
    __tablename__ = "rpa_dashboard"

    id_beecker: Mapped[str] = mapped_column(
        String(10), nullable=False, primary_key=True
    )
    id_dashboard: Mapped[str] = mapped_column(String(40), nullable=False)
    process_name: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[PlatformType] = mapped_column(Enum(PlatformType), nullable=False)
    business_errors: Mapped[list | None] = mapped_column(JSON)
    id_client: Mapped[str] = mapped_column(ForeignKey("client.id"), nullable=False)
    group_by_column: Mapped[str | None] = mapped_column(String(100), nullable=True)

    scheduled_monitoring: Mapped[list["RPADashboardMonitoring"]] = relationship(
        back_populates="rpa", cascade="all, delete"
    )

    client: Mapped["Client"] = relationship(back_populates="rpa_dashboard")


class RPADashboardMonitoring(Base):
    __tablename__ = "rpa_dashboard_monitoring"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, nullable=False)

    id_beecker: Mapped[str] = mapped_column(
        ForeignKey("rpa_dashboard.id_beecker"), nullable=False
    )

    monitor_type: Mapped[MonitorType] = mapped_column(Enum(MonitorType), nullable=False)

    transaction_unit: Mapped[str] = mapped_column(String(100))
    slack_channel: Mapped[str | None] = mapped_column(String(100), nullable=False)
    manage_flags: Mapped[dict | None] = mapped_column(JSON, nullable=False)
    roc_agents: Mapped[list | None] = mapped_column(JSON)
    id_scheduler_job: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))

    rpa: Mapped["RPADashboard"] = relationship(back_populates="scheduled_monitoring")

    job: Mapped["Job"] = relationship(
        cascade="all, delete", back_populates="rpa_dashboard"
    )


class RPAUiPath(Base):
    __tablename__ = "rpa_uipath"

    uipath_robot_name: Mapped[str] = mapped_column(
        String(200), primary_key=True, nullable=False
    )

    id_beecker: Mapped[str] = mapped_column(String(100))
    beecker_name: Mapped[str] = mapped_column(String(200), nullable=False)
    framework: Mapped[str] = mapped_column(String(100), nullable=False)
    business_errors: Mapped[list | None] = mapped_column(JSON)

    id_client: Mapped[str] = mapped_column(ForeignKey("client.id"), nullable=False)

    scheduled_monitoring: Mapped[list["RPAUiPathMonitoring"]] = relationship(
        back_populates="rpa", cascade="all, delete"
    )

    client: Mapped["Client"] = relationship(back_populates="rpa_uipath")


class RPAUiPathMonitoring(Base):
    __tablename__ = "rpa_uipath_monitoring"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    uipath_robot_name: Mapped[str] = mapped_column(
        ForeignKey("rpa_uipath.uipath_robot_name"), nullable=False
    )

    monitor_type: Mapped[MonitorType] = mapped_column(Enum(MonitorType), nullable=False)
    transaction_unit: Mapped[str] = mapped_column(String(100))
    slack_channel: Mapped[str | None] = mapped_column(String(100), nullable=False)
    manage_flags: Mapped[dict | None] = mapped_column(JSON)
    roc_agents: Mapped[list | None] = mapped_column(JSON)

    id_scheduler_job: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))

    rpa: Mapped["RPAUiPath"] = relationship(back_populates="scheduled_monitoring")

    job: Mapped["Job"] = relationship(
        cascade="all, delete", back_populates="rpa_uipath"
    )