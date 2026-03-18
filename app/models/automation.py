import enum

from sqlalchemy import (
    JSON,
    Enum,
    ForeignKey,
    Integer,
    String,
)

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.job import Job


# ---------------------------------------------------------
# ENUMS
# ---------------------------------------------------------
class PlatformType(str, enum.Enum):
    cloud = "cloud"
    hub = "hub"


class MonitorType(str, enum.Enum):
    bee_observa = "bee-observa"
    bee_informa = "bee-informa"
    bee_comunica = "bee-comunica"


# ---------------------------------------------------------
# CLIENT
# ---------------------------------------------------------
class Client(Base):
    __tablename__ = "client"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    client_name: Mapped[str] = mapped_column(String(150), nullable=False)

    rpa_dashboard: Mapped[list["rpa_dashboard_monitoring"]] = relationship(back_populates="client")
    rpa_uipath: Mapped[list["RPAUiPathClient"]] = relationship(back_populates="client")


# ---------------------------------------------------------
# RPA DASHBOARD
# ---------------------------------------------------------
class RPADashboard(Base):
    __tablename__ = "rpa_dashboard"

    id_beecker: Mapped[str] = mapped_column(String(10), nullable=False, primary_key=True)
    
    id_dashboard: Mapped[str] = mapped_column(String(40), nullable=False)

    process_name: Mapped[str] = mapped_column(String(200), nullable=False)

    platform: Mapped[PlatformType] = mapped_column(Enum(PlatformType), nullable=False)

    id_client: Mapped[str] = mapped_column(
        ForeignKey("client.id"),
        nullable=False
    )

    scheduled_monitoring: Mapped[list["RPADashboardMonitoring"]] = relationship(
        back_populates="rpa", 
        cascade="all, delete"
    )

    business_errors: Mapped[list["RPADashboardBusinessError"]] = relationship(
        back_populates="rpa",
        cascade="all, delete"
    )

    client: Mapped["Client"] = relationship(back_populates="rpa_dashboard")


# ---------------------------------------------------------
# RPA DASHBOARD MONITORING
# ---------------------------------------------------------
class RPADashboardMonitoring(Base):
    __tablename__ = "rpa_dashboard_monitoring"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, nullable=False)

    id_rpa: Mapped[str] = mapped_column(
        ForeignKey("rpa_dashboard.id_beecker"),
        nullable=False
    )

    monitor_type: Mapped[MonitorType] = mapped_column(Enum(MonitorType), nullable=False)

    transaction_unit: Mapped[str] = mapped_column(String(100))
    slack_channel: Mapped[str | None] = mapped_column(String(100), nullable=False)

    manage_flags: Mapped[dict | None] = mapped_column(JSON, nullable=False)
    roc_agents: Mapped[list | None] = mapped_column(JSON)

    id_scheduler_job: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=True
    )

    rpa: Mapped["RPADashboard"] = relationship(back_populates="scheduled_monitoring")
    job: Mapped["Job"] = relationship(back_populates="rpa_dashboard")


# ---------------------------------------------------------
# RPA DASHBOARD BUSINESS ERROR
# ---------------------------------------------------------
class RPADashboardBusinessError(Base):
    __tablename__ = "rpa_dashboard_business_error"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)

    id_platform: Mapped[str] = mapped_column(
        ForeignKey("rpa_dashboard.id_beecker"),
        nullable=False
    )

    error_message: Mapped[str] = mapped_column(String(500))

    rpa: Mapped["RPADashboard"] = relationship(back_populates="business_errors")


