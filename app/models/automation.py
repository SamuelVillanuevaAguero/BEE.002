"""
app/models/automation.py
=========================
Modelos SQLAlchemy para el dominio de automatización RPA.

MonitorType acepta tanto guión bajo (bee_informa) como guión medio (bee-informa).
El valor persistido en BD siempre usa guión bajo.
"""

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
    bee_observa  = "bee_observa"
    bee_informa  = "bee_informa"
    bee_comunica = "bee_comunica"

    @classmethod
    def _missing_(cls, value):
        """
        Permite recibir tanto guión medio como guión bajo.

        Ejemplos aceptados:
            "bee-informa"  → MonitorType.bee_informa
            "bee_informa"  → MonitorType.bee_informa
            "bee-observa"  → MonitorType.bee_observa
        """
        if isinstance(value, str):
            normalized = value.replace("-", "_")
            for member in cls:
                if member.value == normalized:
                    return member
        return None


# ---------------------------------------------------------
# CLIENT
# ---------------------------------------------------------
class Client(Base):
    __tablename__ = "client"

    id_client: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_name: Mapped[str] = mapped_column(String(150), nullable=False)

    rpa_dashboards: Mapped[list["RPADashboardClient"]] = relationship(back_populates="client")
    rpa_uipaths: Mapped[list["RPAUiPathClient"]] = relationship(back_populates="client")
    agents: Mapped[list["AgentClient"]] = relationship(back_populates="client")


# ---------------------------------------------------------
# RPA DASHBOARD
# ---------------------------------------------------------
class RPADashboard(Base):
    __tablename__ = "rpa_dashboard"

    id_rpa: Mapped[str] = mapped_column(String(100), primary_key=True)

    id_beecker: Mapped[str] = mapped_column(String(100))
    process_name: Mapped[str] = mapped_column(String(200))

    platform: Mapped[PlatformType] = mapped_column(Enum(PlatformType))

    clients: Mapped[list["RPADashboardClient"]] = relationship(back_populates="rpa")

    business_errors: Mapped[list["RPADashboardBusinessError"]] = relationship(
        back_populates="rpa",
        cascade="all, delete"
    )


# ---------------------------------------------------------
# RPA DASHBOARD CLIENT
# ---------------------------------------------------------
class RPADashboardClient(Base):
    __tablename__ = "rpa_dashboard_client"

    id_rpa: Mapped[str] = mapped_column(
        ForeignKey("rpa_dashboard.id_rpa"),
        primary_key=True
    )

    id_client: Mapped[int] = mapped_column(
        ForeignKey("client.id_client"),
        primary_key=True
    )

    monitor_type: Mapped[MonitorType] = mapped_column(Enum(MonitorType), nullable=False)

    transaction_unit: Mapped[str] = mapped_column(String(100))
    slack_channel: Mapped[str | None] = mapped_column(String(100))

    manage_flags: Mapped[dict | None] = mapped_column(JSON)
    roc_agents: Mapped[list | None] = mapped_column(JSON)

    id_scheduler_job: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=True
    )

    rpa: Mapped["RPADashboard"] = relationship(back_populates="clients")
    client: Mapped["Client"] = relationship(back_populates="rpa_dashboards")
    job: Mapped["Job"] = relationship()


# ---------------------------------------------------------
# RPA DASHBOARD BUSINESS ERROR
# ---------------------------------------------------------
class RPADashboardBusinessError(Base):
    __tablename__ = "rpa_dashboard_business_error"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    id_rpa: Mapped[str] = mapped_column(
        ForeignKey("rpa_dashboard.id_rpa"),
        nullable=False
    )

    error_message: Mapped[str] = mapped_column(String(500))

    rpa: Mapped["RPADashboard"] = relationship(back_populates="business_errors")


# ---------------------------------------------------------
# RPA UIPATH
# ---------------------------------------------------------
class RPAUiPath(Base):
    __tablename__ = "rpa_uipath"

    id_rpa: Mapped[str] = mapped_column(String(100), primary_key=True)

    id_beecker: Mapped[str] = mapped_column(String(100))

    framework: Mapped[str] = mapped_column(String(100))
    robot_name: Mapped[str] = mapped_column(String(200))
    process_name: Mapped[str] = mapped_column(String(200))

    clients: Mapped[list["RPAUiPathClient"]] = relationship(back_populates="rpa")

    business_errors: Mapped[list["RPAUiPathBusinessError"]] = relationship(
        back_populates="rpa",
        cascade="all, delete"
    )


# ---------------------------------------------------------
# RPA UIPATH CLIENT
# ---------------------------------------------------------
class RPAUiPathClient(Base):
    __tablename__ = "rpa_uipath_client"

    id_rpa: Mapped[str] = mapped_column(
        ForeignKey("rpa_uipath.id_rpa"),
        primary_key=True
    )

    id_client: Mapped[int] = mapped_column(
        ForeignKey("client.id_client"),
        primary_key=True
    )

    monitor_type: Mapped[MonitorType] = mapped_column(Enum(MonitorType), nullable=False)

    transaction_unit: Mapped[str] = mapped_column(String(100))
    slack_channel: Mapped[str | None] = mapped_column(String(100))

    manage_flags: Mapped[dict | None] = mapped_column(JSON)
    roc_agents: Mapped[list | None] = mapped_column(JSON)

    id_scheduler_job: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=True
    )

    rpa: Mapped["RPAUiPath"] = relationship(back_populates="clients")
    client: Mapped["Client"] = relationship(back_populates="rpa_uipaths")
    job: Mapped["Job"] = relationship()


# ---------------------------------------------------------
# RPA UIPATH BUSINESS ERROR
# ---------------------------------------------------------
class RPAUiPathBusinessError(Base):
    __tablename__ = "rpa_uipath_business_error"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    id_rpa: Mapped[str] = mapped_column(
        ForeignKey("rpa_uipath.id_rpa"),
        nullable=False
    )

    error_message: Mapped[str] = mapped_column(String(500))

    rpa: Mapped["RPAUiPath"] = relationship(back_populates="business_errors")


# ---------------------------------------------------------
# AGENT
# ---------------------------------------------------------
class Agent(Base):
    __tablename__ = "agent"

    id_agent: Mapped[str] = mapped_column(String(100), primary_key=True)

    id_beecker: Mapped[str] = mapped_column(String(100))
    process_name: Mapped[str] = mapped_column(String(200))

    platform: Mapped[PlatformType] = mapped_column(Enum(PlatformType))

    clients: Mapped[list["AgentClient"]] = relationship(back_populates="agent")

    state_errors: Mapped[list["AgentStateError"]] = relationship(
        back_populates="agent",
        cascade="all, delete"
    )


# ---------------------------------------------------------
# AGENT CLIENT
# ---------------------------------------------------------
class AgentClient(Base):
    __tablename__ = "agent_client"

    id_agent: Mapped[str] = mapped_column(
        ForeignKey("agent.id_agent"),
        primary_key=True
    )

    id_client: Mapped[int] = mapped_column(
        ForeignKey("client.id_client"),
        primary_key=True
    )

    monitor_type: Mapped[MonitorType] = mapped_column(Enum(MonitorType), nullable=False)

    transaction_unit: Mapped[str] = mapped_column(String(100))
    slack_channel: Mapped[str | None] = mapped_column(String(100))

    manage_flags: Mapped[dict | None] = mapped_column(JSON)
    roc_agents: Mapped[list | None] = mapped_column(JSON)

    id_scheduler_job: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=True
    )

    agent: Mapped["Agent"] = relationship(back_populates="clients")
    client: Mapped["Client"] = relationship(back_populates="agents")
    job: Mapped["Job"] = relationship()


# ---------------------------------------------------------
# AGENT STATE ERROR
# ---------------------------------------------------------
class AgentStateError(Base):
    __tablename__ = "agent_state_error"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    id_agent: Mapped[str] = mapped_column(
        ForeignKey("agent.id_agent"),
        nullable=False
    )

    state_name: Mapped[str] = mapped_column(String(100))

    agent: Mapped["Agent"] = relationship(back_populates="state_errors")