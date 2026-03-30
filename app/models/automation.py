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
    client_name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)

    rpa_dashboard: Mapped[list["RPADashboard"]] = relationship(back_populates="client")
    rpa_uipath: Mapped[list["RPAUiPath"]] = relationship(back_populates="client")
    agent: Mapped[list["AgentMonitoring"]] = relationship(back_populates="client")


# ---------------------------------------------------------
# RPA DASHBOARD
# ---------------------------------------------------------
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

    scheduled_monitoring: Mapped[list["RPADashboardMonitoring"]] = relationship(
        back_populates="rpa", cascade="all, delete"
    )

    client: Mapped["Client"] = relationship(back_populates="rpa_dashboard")


# ---------------------------------------------------------
# RPA DASHBOARD MONITORING
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# RPA UIPATH
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# RPA UIPATH MONITORING
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# AGENT
# ---------------------------------------------------------
class Agent(Base):
    __tablename__ = "agent"

    id_beecker: Mapped[str] = mapped_column(String(100))
    agent_name: Mapped[str] = mapped_column(
        String(200), primary_key=True, nullable=False
    )

    scheduled_monitoring: Mapped["AgentMonitoring"] = relationship(
        back_populates="agent", cascade="all, delete"
    )


# ---------------------------------------------------------
# AGENT MONITORING
# ---------------------------------------------------------
class AgentMonitoring(Base):
    __tablename__ = "agent_monitoring"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)

    agent_name: Mapped[str] = mapped_column(
        ForeignKey("agent.agent_name"), nullable=False
    )

    id_client: Mapped[str] = mapped_column(ForeignKey("client.id"), nullable=False)

    platform: Mapped[PlatformType] = mapped_column(Enum(PlatformType), nullable=False)
    id_platform: Mapped[str] = mapped_column(String(100))
    monitor_type: Mapped[MonitorType] = mapped_column(Enum(MonitorType), nullable=False)
    transaction_unit: Mapped[str] = mapped_column(String(100))
    slack_channel: Mapped[str | None] = mapped_column(String(100))
    manage_flags: Mapped[dict | None] = mapped_column(JSON)
    roc_agents: Mapped[list | None] = mapped_column(JSON)
    states_errors: Mapped[list | None] = mapped_column(JSON)
    credentials_name: Mapped[str | None] = mapped_column(String(100))

    id_scheduler_job: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id"), nullable=True
    )

    agent: Mapped["Agent"] = relationship(back_populates="scheduled_monitoring")
    client: Mapped["Client"] = relationship(back_populates="agent")
    job: Mapped["Job"] = relationship(
        cascade="all, delete", back_populates="agent_monitoring"
    )


# ---------------------------------------------------------
# RPA DASHBOARD CLIENT (Alias/Junction for configuration)
# ---------------------------------------------------------
class RPADashboardClient(Base):
    """Junction model for RPA Dashboard and Client configuration."""

    __tablename__ = "rpa_dashboard_client"

    id_rpa: Mapped[str] = mapped_column(
        ForeignKey("rpa_dashboard.id_beecker"), primary_key=True, nullable=False
    )

    id_client: Mapped[str] = mapped_column(
        ForeignKey("client.id"), primary_key=True, nullable=False
    )

    monitor_type: Mapped[MonitorType] = mapped_column(Enum(MonitorType), nullable=False)

    transaction_unit: Mapped[str] = mapped_column(String(100), nullable=False)
    slack_channel: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manage_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    roc_agents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    id_scheduler_job: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id"), nullable=True
    )

    rpa: Mapped["RPADashboard"] = relationship()
    client: Mapped["Client"] = relationship()
    job: Mapped["Job"] = relationship(
        cascade="all, delete", foreign_keys=[id_scheduler_job]
    )


# ---------------------------------------------------------
# RPA DASHBOARD BUSINESS ERROR
# ---------------------------------------------------------
class RPADashboardBusinessError(Base):
    """Business error configuration for RPA Dashboard."""

    __tablename__ = "rpa_dashboard_business_error"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)

    id_rpa: Mapped[str] = mapped_column(
        ForeignKey("rpa_dashboard.id_beecker"), nullable=False
    )

    error_code: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str] = mapped_column(String(500), nullable=False)

    rpa: Mapped["RPADashboard"] = relationship()


# ---------------------------------------------------------
# RPA UIPATH CLIENT (Alias/Junction for configuration)
# ---------------------------------------------------------
class RPAUiPathClient(Base):
    """Junction model for RPA UiPath and Client configuration."""

    __tablename__ = "rpa_uipath_client"

    id_rpa: Mapped[str] = mapped_column(
        ForeignKey("rpa_uipath.uipath_robot_name"), primary_key=True, nullable=False
    )

    id_client: Mapped[str] = mapped_column(
        ForeignKey("client.id"), primary_key=True, nullable=False
    )

    monitor_type: Mapped[MonitorType] = mapped_column(Enum(MonitorType), nullable=False)

    transaction_unit: Mapped[str] = mapped_column(String(100), nullable=False)
    slack_channel: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manage_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    roc_agents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    id_scheduler_job: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id"), nullable=True
    )

    rpa: Mapped["RPAUiPath"] = relationship()
    client: Mapped["Client"] = relationship()
    job: Mapped["Job"] = relationship(
        cascade="all, delete", foreign_keys=[id_scheduler_job]
    )


# ---------------------------------------------------------
# RPA UIPATH BUSINESS ERROR
# ---------------------------------------------------------
class RPAUiPathBusinessError(Base):
    """Business error configuration for RPA UiPath."""

    __tablename__ = "rpa_uipath_business_error"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)

    id_rpa: Mapped[str] = mapped_column(
        ForeignKey("rpa_uipath.uipath_robot_name"), nullable=False
    )

    error_code: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str] = mapped_column(String(500), nullable=False)

    rpa: Mapped["RPAUiPath"] = relationship()


# ---------------------------------------------------------
# AGENT CLIENT (Alias/Junction for configuration)
# ---------------------------------------------------------
class AgentClient(Base):
    """Junction model for Agent and Client configuration."""

    __tablename__ = "agent_client"

    id_agent: Mapped[str] = mapped_column(
        ForeignKey("agent.agent_name"), primary_key=True, nullable=False
    )

    id_client: Mapped[str] = mapped_column(
        ForeignKey("client.id"), primary_key=True, nullable=False
    )

    monitor_type: Mapped[MonitorType] = mapped_column(Enum(MonitorType), nullable=False)

    transaction_unit: Mapped[str] = mapped_column(String(100), nullable=False)
    slack_channel: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manage_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    roc_agents: Mapped[list | None] = mapped_column(JSON, nullable=True)

    agent: Mapped["Agent"] = relationship()
    client: Mapped["Client"] = relationship()


# ---------------------------------------------------------
# AGENT STATE ERROR
# ---------------------------------------------------------
class AgentStateError(Base):
    """Agent state error configuration."""

    __tablename__ = "agent_state_error"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)

    id_agent: Mapped[str] = mapped_column(
        ForeignKey("agent.agent_name"), nullable=False
    )

    state: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str] = mapped_column(String(500), nullable=False)

    agent: Mapped["Agent"] = relationship()
