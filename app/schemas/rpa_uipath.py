"""
app/schemas/rpa_uipath.py

Schemas exclusivos de RPA UiPath.
Los subschemas compartidos (TransactionUnitSchema, ManageFlagsSchema,
MonitoringResponse, MonitoringPatch, JobSummaryResponse, etc.)
viven en rpa_dashboard.py y se importan desde ahí.
"""
from __future__ import annotations
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.rpa_dashboard import MonitorType
from app.schemas.rpa_dashboard import (
    TransactionUnitSchema,
    ManageFlagsSchema,
    ClientFragment,
    JobFragment,
    _MANAGE_FLAGS_EXAMPLE,
)


# ── Fragmento UiPath ──────────────────────────────────────────────────────────

class UiPathFragment(BaseModel):
    """
    uipath_robot_name es la referencia única para UiPath.
    """
    uipath_robot_name: str = Field(..., description="Nombre del robot UiPath. Referencia única.")
    id_beecker: Optional[str] = Field(default=None, max_length=40)
    beecker_name: Optional[str] = Field(
        default=None, max_length=200, description="Requerido solo al crear."
    )
    framework: Optional[str] = Field(
        default=None, max_length=100, description="Requerido solo al crear."
    )
    model_config = {"extra": "forbid"}


# ── Payload atómico UiPath ────────────────────────────────────────────────────

class RPAUiPathAtomicCreate(BaseModel):
    client: ClientFragment
    RPA: UiPathFragment
    monitor_type: MonitorType
    slack_channel: str = Field(..., max_length=100)
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None
    business_errors: Optional[List[str]] = None
    group_by_column: str | None = Field(default=None)
    job: Optional[JobFragment] = None

    @field_validator("monitor_type", mode="before")
    @classmethod
    def normalize_monitor_type(cls, v):
        if isinstance(v, str):
            return v.replace("_", "-")
        return v

    @field_validator("business_errors", mode="before")
    @classmethod
    def normalize_business_errors(cls, v):
        if v is None:
            return []
        return [e.strip() for e in v if e.strip()]

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "client": {"id": None, "name": "Empresa XYZ"},
                    "RPA": {
                        "uipath_robot_name": "Robot_Ventas_01",
                        "id_beecker": "VNT.001",
                        "beecker_name": "Bot Ventas",
                        "framework": "REFramework",
                    },
                    "monitor_type": "bee_informa",
                    "slack_channel": "#roc-ventas",
                    "transaction_unit": {"plural": "Órdenes", "singular": "Orden"},
                    "roc_agents": ["roc@empresa.com"],
                    "manage_flags": _MANAGE_FLAGS_EXAMPLE,
                    "business_errors": ["Business Rule Violation"],
                    "group_by_column": "columna1",
                    "job": {
                        "name": "bee-informa | Robot_Ventas_01",
                        "trigger_type": "interval",
                        "trigger_args": {"minutes": 10},
                    },
                }
            ]
        },
    }


# ── Response ──────────────────────────────────────────────────────────────────

class RPAUiPathResponse(BaseModel):
    uipath_robot_name: str = Field(
        ...,
        max_length=100,
        examples=["Robot_Ventas_01"],
        description="Nombre del robot UiPath",
    )
    id_beecker: Optional[str] = Field(
        default=None,
        max_length=40,
        examples=["VNT.001"],
        description="Identificador ROC opcional",
    )
    beecker_name: str = Field(
        ...,
        max_length=200,
        examples=["Bot Ventas"],
        description="Nombre amigable del bot",
    )
    framework: str = Field(
        ...,
        max_length=100,
        examples=["REFramework"],
        description="Framework usado (ej: REFramework)",
    )
    id_client: str = Field(
        ...,
        max_length=100,
        examples=["550e8400-e29b-41d4-a716-446655440000"],
        description="UUID del cliente propietario",
    )
    business_errors: Optional[List[str]] = Field(
        default=None,
        examples=[["Business Rule Violation"]],
        description="Errores de negocio del bot",
    )
    group_by_column: str | None = Field(default=None)
    model_config = {"from_attributes": True}