"""
app/schemas/rpa_dashboard.py

Fragmento RPA usa id_beecker como referencia única:
    - Si id_beecker tiene valor y el bot existe → reutiliza
    - Si id_beecker tiene valor y el bot NO existe → crea uno nuevo
Fragmento UiPath usa uipath_robot_name como referencia única, misma lógica.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from app.models.automation import MonitorType, PlatformType


# ── Subschemas compartidos ────────────────────────────────────────────────────

class TransactionUnitSchema(BaseModel):
    plural: str = Field(..., max_length=100, examples=["Facturas"])
    singular: str = Field(..., max_length=100, examples=["Factura"])


class ManageFlagsSchema(BaseModel):
    start_active: bool = Field(True)
    end_active: bool = Field(True)


class JobFragment(BaseModel):
    """
    Fragmento de job en el payload atómico.
    Si viene vacío ({}) se usa trigger_type=interval con minutes=5 por defecto.
    """
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    task_path: Optional[str] = Field(default="app.tasks.rpa_tasks:scheduled_rpa_status")
    trigger_type: Optional[str] = Field(default="interval")
    trigger_args: Optional[Dict[str, Any]] = Field(default_factory=lambda: {"minutes": 5})


class ClientFragment(BaseModel):
    """
    Si id tiene valor → reutiliza el cliente existente.
    Si id es null/omitido → crea uno nuevo con name.
    """
    id: Optional[str] = Field(default=None, description="ID del cliente. Omitir o null = crear nuevo.")
    name: Optional[str] = Field(default=None, max_length=150, description="Nombre (requerido si id es null).")


# ── Fragmento RPA Dashboard ───────────────────────────────────────────────────

class RPAFragment(BaseModel):
    """
    id_beecker es la referencia única para Dashboard:
        - Si el bot con ese id_beecker ya existe → se reutiliza
        - Si no existe → se crea con los demás campos (id_rpa, process_name, platform obligatorios)
    """
    id_beecker: str = Field(..., description="Identificador ROC del bot (ej: 'AEC.001'). Referencia única.")
    id_rpa: Optional[str] = Field(default=None, max_length=40, description="ID numérico de plataforma (ej: '104'). Requerido solo al crear.")
    process_name: Optional[str] = Field(default=None, max_length=200, description="Requerido solo al crear.")
    platform: Optional[PlatformType] = Field(default=None, description="Requerido solo al crear.")


# ── Fragmento UiPath ──────────────────────────────────────────────────────────

class UiPathFragment(BaseModel):
    """
    uipath_robot_name es la referencia única para UiPath:
        - Si el bot con ese nombre ya existe → se reutiliza
        - Si no existe → se crea con los demás campos (beecker_name, framework obligatorios)
    """
    uipath_robot_name: str = Field(..., description="Nombre del robot UiPath. Referencia única.")
    id_beecker: Optional[str] = Field(default=None, max_length=100)
    beecker_name: Optional[str] = Field(default=None, max_length=200, description="Requerido solo al crear.")
    framework: Optional[str] = Field(default=None, max_length=100, description="Requerido solo al crear.")


# ── Payload atómico RPADashboard ──────────────────────────────────────────────

class RPADashboardAtomicCreate(BaseModel):
    client: ClientFragment
    RPA: RPAFragment
    slack_channel: str = Field(..., max_length=100, examples=["#roc-aeromexico-raas-test"])
    monitor_type: MonitorType
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None
    business_errors: Optional[List[str]] = None
    job: Optional[JobFragment] = Field(default=None, description="Si se envía, crea y vincula el job automáticamente.")

    @field_validator("business_errors", mode="before")
    @classmethod
    def validate_business_errors(cls, v):
        if v is not None:
            if not all(isinstance(e, str) and e.strip() for e in v):
                raise ValueError("Cada error de negocio debe ser un string no vacío.")
        return v


# ── Payload atómico RPAUiPath ─────────────────────────────────────────────────

class RPAUiPathAtomicCreate(BaseModel):
    client: ClientFragment
    RPA: UiPathFragment
    slack_channel: str = Field(..., max_length=100)
    monitor_type: MonitorType
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None
    business_errors: Optional[List[str]] = None
    job: Optional[JobFragment] = None

    @field_validator("business_errors", mode="before")
    @classmethod
    def validate_business_errors(cls, v):
        if v is not None:
            if not all(isinstance(e, str) and e.strip() for e in v):
                raise ValueError("Cada error de negocio debe ser un string no vacío.")
        return v


# ── Patch monitoring ──────────────────────────────────────────────────────────

class MonitoringPatch(BaseModel):
    slack_channel: Optional[str] = Field(None, max_length=100)
    monitor_type: Optional[MonitorType] = None
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None


# ── Response schemas ──────────────────────────────────────────────────────────

class ClientResponse(BaseModel):
    id: str
    client_name: str
    model_config = {"from_attributes": True}


class JobSummaryResponse(BaseModel):
    id: str
    name: str
    status: str
    trigger_type: str
    trigger_args: Dict[str, Any]
    next_run_time: Optional[str] = None
    model_config = {"from_attributes": True}


class MonitoringResponse(BaseModel):
    id: str
    monitor_type: MonitorType
    slack_channel: Optional[str] = None
    transaction_unit: Optional[str] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[dict] = None
    id_scheduler_job: Optional[str] = None
    job: Optional[JobSummaryResponse] = None
    model_config = {"from_attributes": True}


class RPADashboardResponse(BaseModel):
    id_beecker: str
    id_dashboard: str
    process_name: str
    platform: PlatformType
    id_client: str
    business_errors: Optional[List[str]] = None
    model_config = {"from_attributes": True}


class RPAUiPathResponse(BaseModel):
    uipath_robot_name: str
    id_beecker: Optional[str] = None
    beecker_name: str
    framework: str
    id_client: str
    business_errors: Optional[List[str]] = None
    model_config = {"from_attributes": True}


class AtomicCreateResponse(BaseModel):
    client: ClientResponse
    rpa: dict
    monitoring: MonitoringResponse
    job: Optional[JobSummaryResponse] = None