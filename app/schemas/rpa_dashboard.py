"""
app/schemas/rpa_dashboard.py
"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from app.models.automation import MonitorType, PlatformType


# ── Subschemas compartidos ────────────────────────────────────────────────────

class TransactionUnitSchema(BaseModel):
    plural: str = Field(..., max_length=100, examples=["Facturas"])
    singular: str = Field(..., max_length=100, examples=["Factura"])


class ManageFlagsSchema(BaseModel):
    start_active: bool = Field(True)
    end_active: bool = Field(True)


# ── RPADashboard ──────────────────────────────────────────────────────────────

class RPADashboardCreate(BaseModel):
    id_beecker: str = Field(..., max_length=10, description="PK — identificador ROC (ej: 'AEC.001')", examples=["AEC.001"])
    id_dashboard: str = Field(..., max_length=40, description="ID numérico para la API de Beecker (ej: '104')", examples=["104"])
    process_name: str = Field(..., max_length=200, examples=["Proceso Aeroméxico"])
    platform: PlatformType
    id_client: str = Field(..., description="FK → client.id")

    @field_validator("id_beecker", "id_dashboard", "process_name", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class RPADashboardUpdate(BaseModel):
    id_dashboard: Optional[str] = Field(None, max_length=40)
    process_name: Optional[str] = Field(None, max_length=200)
    platform: Optional[PlatformType] = None
    id_client: Optional[str] = None


class RPADashboardResponse(BaseModel):
    id_beecker: str
    id_dashboard: str
    process_name: str
    platform: PlatformType
    id_client: str

    model_config = {"from_attributes": True}


class RPADashboardDetailResponse(RPADashboardResponse):
    """Usado en GET /{id_beecker} — incluye monitorings y errores anidados."""
    monitoring: List["RPADashboardMonitoringResponse"] = []
    business_errors: List["BusinessErrorResponse"] = []

    model_config = {"from_attributes": True}


# ── RPADashboardMonitoring ────────────────────────────────────────────────────

class RPADashboardMonitoringCreate(BaseModel):
    monitor_type: MonitorType
    slack_channel: str = Field(..., max_length=100, examples=["#roc-aeromexico-raas-test"])
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None

    @field_validator("slack_channel", mode="before")
    @classmethod
    def strip_channel(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class RPADashboardMonitoringUpdate(BaseModel):
    slack_channel: Optional[str] = Field(None, max_length=100)
    monitor_type: Optional[MonitorType] = None
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None


class RPADashboardMonitoringResponse(BaseModel):
    id: str
    id_rpa: str
    monitor_type: MonitorType
    slack_channel: Optional[str] = None
    transaction_unit: Optional[str] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[dict] = None
    id_scheduler_job: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Job vinculation ───────────────────────────────────────────────────────────

class JobLinkRequest(BaseModel):
    job_id: str = Field(..., description="ID del job a vincular al monitoring")


# ── BusinessError ─────────────────────────────────────────────────────────────

class BusinessErrorCreate(BaseModel):
    error_message: str = Field(..., max_length=500, examples=["Business Exception"])


class BusinessErrorResponse(BaseModel):
    id: str
    id_platform: str
    error_message: str

    model_config = {"from_attributes": True}


# Rebuild for forward references
RPADashboardDetailResponse.model_rebuild()