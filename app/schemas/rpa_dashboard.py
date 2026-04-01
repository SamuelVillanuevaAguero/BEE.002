"""
app/schemas/rpa_dashboard.py

Todos los schemas de REQUEST tienen extra="forbid":
    → Campos desconocidos en el payload devuelven 422 automáticamente.

Fragmento RPA usa id_beecker como referencia única:
    - Si id_beecker tiene valor y el bot existe → reutiliza
    - Si id_beecker tiene valor y el bot NO existe → crea uno nuevo
Fragmento UiPath usa uipath_robot_name como referencia única, misma lógica.

ManageFlagsSchema agrupa dos categorías de flags:
    - Flags de flujo (start_active / end_active): controlan si se envían
      mensajes en el inicio y fin de ejecución.
    - Flags de comportamiento del monitor (enable_*): controlan qué
      funcionalidades se activan en los mensajes de estado.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from app.models.automation import MonitorType, PlatformType


# ── Subschemas compartidos ────────────────────────────────────────────────────

class TransactionUnitSchema(BaseModel):
    plural: str = Field(..., max_length=100, examples=["Transacciones"])
    singular: str = Field(..., max_length=100, examples=["Transacción"])
    model_config = {"extra": "forbid"}


class ManageFlagsSchema(BaseModel):
    """
    Flags de configuración del monitoring. Se persisten como JSON en BD.

    Flags de flujo:
        start_active  : Si True, envía mensaje de inicio al recibir el webhook de START.
        end_active    : Si True, envía mensaje de fin con el estado de la ejecución.

    Flags de comportamiento del monitor:
        enable_overtime_check : Si True, detecta ejecuciones que superan el tiempo
                                histórico promedio y añade alerta en el mensaje.
        enable_freshdesk_link : Si True, incluye el link de tickets FreshDesk del cliente
                                en mensajes de CRITICAL_FAILURE y PARTIAL_FAILURE.
        enable_chart          : Si True, genera y envía la gráfica PNG de la ejecución
                                como attachment en Slack al finalizar.
        show_error_groups     : Si True, incluye el desglose de grupos de error en el
                                mensaje de PARTIAL_FAILURE.
    """
    # ── Flujo ─────────────────────────────────────────────────────────────────
    start_active: bool = Field(
        default=True,
        description="Envía mensaje de inicio al recibir webhook START.",
    )
    end_active: bool = Field(
        default=True,
        description="Envía mensaje de fin con el estado de la ejecución.",
    )

    # ── Comportamiento del monitor ────────────────────────────────────────────
    enable_overtime_check: bool = Field(
        default=False,
        description="Detecta ejecuciones que superan el tiempo histórico promedio.",
    )
    enable_freshdesk_link: bool = Field(
        default=True,
        description="Incluye link de tickets FreshDesk en mensajes de fallo.",
    )
    enable_chart: bool = Field(
        default=True,
        description="Genera y envía gráfica PNG al finalizar la ejecución.",
    )
    show_error_groups: bool = Field(
        default=True,
        description="Incluye desglose de grupos de error en mensajes de fallo parcial.",
    )

    model_config = {"extra": "forbid"}


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
    model_config = {"extra": "forbid"}


class ClientFragment(BaseModel):
    """
    Si id tiene valor → reutiliza el cliente existente.
    Si id es null/omitido → crea uno nuevo con name.
    """
    id: Optional[str] = Field(default=None, description="ID del cliente. Omitir o null = crear nuevo.")
    name: Optional[str] = Field(default=None, max_length=150, description="Nombre (requerido si id es null).")
    model_config = {"extra": "forbid"}


# ── Fragmento RPA Dashboard ───────────────────────────────────────────────────

class RPAFragment(BaseModel):
    """
    id_beecker es la referencia única para Dashboard:
        - Si el bot con ese id_beecker ya existe → se reutiliza
        - Si no existe → se crea con los demás campos (id_rpa, process_name, platform obligatorios)
    """
    id_beecker: str = Field(..., description="Identificador ROC del bot (ej: 'AEC.001'). Referencia única.")
    id_rpa: Optional[str] = Field(default=None, max_length=40, description="ID numérico de plataforma (ej: '114'). Requerido solo al crear.")
    process_name: Optional[str] = Field(default=None, max_length=200, description="Requerido solo al crear.")
    platform: Optional[PlatformType] = Field(default=None, description="Requerido solo al crear.")
    model_config = {"extra": "forbid"}


# ── Fragmento UiPath ──────────────────────────────────────────────────────────

class UiPathFragment(BaseModel):
    """
    uipath_robot_name es la referencia única para UiPath.
    """
    uipath_robot_name: str = Field(..., description="Nombre del robot UiPath. Referencia única.")
    id_beecker: Optional[str] = Field(default=None, max_length=40)
    beecker_name: Optional[str] = Field(default=None, max_length=200, description="Requerido solo al crear.")
    framework: Optional[str] = Field(default=None, max_length=100, description="Requerido solo al crear.")
    model_config = {"extra": "forbid"}


# ── Payloads atómicos ─────────────────────────────────────────────────────────

_MANAGE_FLAGS_EXAMPLE = {
    "start_active": True,
    "end_active": True,
    "enable_overtime_check": False,
    "enable_freshdesk_link": True,
    "enable_chart": True,
    "show_error_groups": True,
}


class RPADashboardAtomicCreate(BaseModel):
    client: ClientFragment
    RPA: RPAFragment
    monitor_type: MonitorType
    slack_channel: str = Field(..., max_length=100)
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None
    business_errors: Optional[List[str]] = None
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
                    "client": {"id": None, "name": "Empresa ABC"},
                    "RPA": {
                        "id_beecker": "AEC.001",
                        "id_rpa": "114",
                        "process_name": "Automatización Cuentas por Cobrar",
                        "platform": "cloud",
                    },
                    "monitor_type": "bee_informa",
                    "slack_channel": "#roc-notificaciones",
                    "transaction_unit": {"plural": "Facturas", "singular": "Factura"},
                    "roc_agents": ["agente@empresa.com"],
                    "manage_flags": _MANAGE_FLAGS_EXAMPLE,
                    "business_errors": ["Business Exception", "Application Exception"],
                    "job": {
                        "name": "bee-informa | AEC.001",
                        "trigger_type": "interval",
                        "trigger_args": {"minutes": 5},
                    },
                }
            ]
        },
    }


class RPAUiPathAtomicCreate(BaseModel):
    client: ClientFragment
    RPA: UiPathFragment
    monitor_type: MonitorType
    slack_channel: str = Field(..., max_length=100)
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None
    business_errors: Optional[List[str]] = None
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
                    "job": {
                        "name": "bee-informa | Robot_Ventas_01",
                        "trigger_type": "interval",
                        "trigger_args": {"minutes": 10},
                    },
                }
            ]
        },
    }


# ── Patch monitoring ──────────────────────────────────────────────────────────

class MonitoringPatch(BaseModel):
    slack_channel: Optional[str] = Field(None, max_length=100)
    monitor_type: Optional[MonitorType] = None
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None

    @field_validator("monitor_type", mode="before")
    @classmethod
    def normalize_monitor_type(cls, v):
        if isinstance(v, str):
            return v.replace("_", "-")
        return v

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "slack_channel": "#roc-ops",
                    "monitor_type": "bee_observa",
                    "transaction_unit": {"plural": "Facturas", "singular": "Factura"},
                    "roc_agents": ["agente1@empresa.com", "agente2@empresa.com"],
                    "manage_flags": _MANAGE_FLAGS_EXAMPLE,
                }
            ]
        },
    }


# ── Response schemas (from_attributes=True, SIN extra=forbid) ────────────────

class ClientResponse(BaseModel):
    id: str
    client_name: str
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "client_name": "Empresa ABC",
                }
            ]
        },
    }


class JobSummaryResponse(BaseModel):
    id: str
    name: str
    status: str
    trigger_type: str
    trigger_args: Dict[str, Any]
    next_run_time: Optional[str] = None
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "name": "bee-informa | AEC.001",
                    "status": "paused",
                    "trigger_type": "interval",
                    "trigger_args": {"minutes": 5},
                    "next_run_time": None,
                }
            ]
        },
    }


class MonitoringResponse(BaseModel):
    id: str
    monitor_type: MonitorType
    slack_channel: Optional[str] = None
    transaction_unit: Optional[str] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[dict] = None
    id_scheduler_job: Optional[str] = None
    job: Optional[JobSummaryResponse] = None
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "a1b2c3d4-0000-0000-0000-000000000001",
                    "monitor_type": "bee_informa",
                    "slack_channel": "#roc-notificaciones",
                    "transaction_unit": "Facturas|Factura",
                    "roc_agents": ["agente@empresa.com"],
                    "manage_flags": _MANAGE_FLAGS_EXAMPLE,
                    "id_scheduler_job": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "job": {
                        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "name": "bee-informa | AEC.001",
                        "status": "paused",
                        "trigger_type": "interval",
                        "trigger_args": {"minutes": 5},
                        "next_run_time": None,
                    },
                }
            ]
        },
    }


class RPADashboardResponse(BaseModel):
    id_beecker: str
    id_dashboard: str
    process_name: str
    platform: PlatformType
    id_client: str
    business_errors: Optional[List[str]] = None
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id_beecker": "AEC.001",
                    "id_dashboard": "114",
                    "process_name": "Automatización Cuentas por Cobrar",
                    "platform": "cloud",
                    "id_client": "550e8400-e29b-41d4-a716-446655440000",
                    "business_errors": ["Business Exception", "Application Exception"],
                }
            ]
        },
    }


class RPAUiPathResponse(BaseModel):
    uipath_robot_name: str
    id_beecker: Optional[str] = None
    beecker_name: str
    framework: str
    id_client: str
    business_errors: Optional[List[str]] = None
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "uipath_robot_name": "Robot_Ventas_01",
                    "id_beecker": "VNT.001",
                    "beecker_name": "Bot Ventas",
                    "framework": "REFramework",
                    "id_client": "550e8400-e29b-41d4-a716-446655440000",
                    "business_errors": ["Business Rule Violation"],
                }
            ]
        },
    }


class AtomicCreateResponse(BaseModel):
    client: ClientResponse
    rpa: RPADashboardResponse | RPAUiPathResponse
    monitoring: MonitoringResponse
    job: Optional[JobSummaryResponse] = None

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "client": {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "client_name": "Empresa ABC",
                    },
                    "rpa": {
                        "id_beecker": "AEC.001",
                        "id_dashboard": "114",
                        "process_name": "Automatización Cuentas por Cobrar",
                        "platform": "cloud",
                        "id_client": "550e8400-e29b-41d4-a716-446655440000",
                        "business_errors": ["Business Exception"],
                    },
                    "monitoring": {
                        "id": "a1b2c3d4-0000-0000-0000-000000000001",
                        "monitor_type": "bee_informa",
                        "slack_channel": "#roc-notificaciones",
                        "transaction_unit": "Facturas|Factura",
                        "roc_agents": ["agente@empresa.com"],
                        "manage_flags": _MANAGE_FLAGS_EXAMPLE,
                        "id_scheduler_job": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "job": {
                            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                            "name": "bee-informa | AEC.001",
                            "status": "paused",
                            "trigger_type": "interval",
                            "trigger_args": {"minutes": 5},
                            "next_run_time": None,
                        },
                    },
                    "job": {
                        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "name": "bee-informa | AEC.001",
                        "status": "paused",
                        "trigger_type": "interval",
                        "trigger_args": {"minutes": 5},
                        "next_run_time": None,
                    },
                }
            ]
        }
    }


# ── Schemas del endpoint CRUD /rpa-dashboard ──────────────────────────────────

class RPADashboardCreate(BaseModel):
    id_beecker: str = Field(..., max_length=10)
    id_dashboard: str = Field(..., max_length=40)
    process_name: str = Field(..., max_length=200)
    platform: PlatformType
    id_client: str = Field(..., max_length=100)
    business_errors: Optional[List[str]] = None
    model_config = {"extra": "forbid"}


class RPADashboardUpdate(BaseModel):
    process_name: Optional[str] = Field(None, max_length=200)
    platform: Optional[PlatformType] = None
    id_client: Optional[str] = Field(None, max_length=100)
    business_errors: Optional[List[str]] = None
    model_config = {"extra": "forbid"}


class RPADashboardDetailResponse(RPADashboardResponse):
    monitorings: List[MonitoringResponse] = []


class RPADashboardMonitoringCreate(BaseModel):
    monitor_type: MonitorType
    slack_channel: str = Field(..., max_length=100)
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None
    id_scheduler_job: Optional[str] = None

    @field_validator("monitor_type", mode="before")
    @classmethod
    def normalize_monitor_type(cls, v):
        if isinstance(v, str):
            return v.replace("_", "-")
        return v

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "monitor_type": "bee_informa",
                    "slack_channel": "#roc-notificaciones",
                    "transaction_unit": {"plural": "Facturas", "singular": "Factura"},
                    "roc_agents": ["agente@empresa.com"],
                    "manage_flags": _MANAGE_FLAGS_EXAMPLE,
                }
            ]
        },
    }


class RPADashboardMonitoringUpdate(BaseModel):
    slack_channel: Optional[str] = Field(None, max_length=100)
    monitor_type: Optional[MonitorType] = None
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None

    @field_validator("monitor_type", mode="before")
    @classmethod
    def normalize_monitor_type(cls, v):
        if isinstance(v, str):
            return v.replace("_", "-")
        return v

    model_config = {"extra": "forbid"}


class RPADashboardMonitoringResponse(MonitoringResponse):
    pass


class JobLinkRequest(BaseModel):
    job_id: str = Field(..., description="ID del job a vincular.")
    model_config = {"extra": "forbid"}


class BusinessErrorCreate(BaseModel):
    errors: List[str] = Field(..., description="Lista de errores de negocio a agregar.")
    model_config = {"extra": "forbid"}


class BusinessErrorResponse(BaseModel):
    id_beecker: str
    business_errors: List[str]
    model_config = {"from_attributes": True}