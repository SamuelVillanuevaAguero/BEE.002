from sqlalchemy import (
    String
)

from app.db.session import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.automation import RPADashboard, RPAUiPath


class Client(Base):
    __tablename__ = "client"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    client_name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    id_freshdesk: Mapped[str] = mapped_column(String(15), nullable=False, unique=True)
    id_beecker: Mapped[str] = mapped_column(String(4), nullable=False, unique=True)

    rpa_dashboard: Mapped[list["RPADashboard"]] = relationship(back_populates="client")
    rpa_uipath: Mapped[list["RPAUiPath"]] = relationship(back_populates="client")