"""
app/schemas/rpa_dashboard.py
=============================
Schemas Pydantic para el endpoint de creación atómica de un RPA Dashboard.

Cubre las tres tablas involucradas en una sola llamada:
    - rpa_dashboard
    - rpa_dashboard_client
    - rpa_dashboard_business_error (opcionales)
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.automation import MonitorType, PlatformType


# ── Subschemas ────────────────────────────────────────────────────────────────

class TransactionUnitSchema(BaseModel):
    """
    Unidad transaccional en formato plural|singular.

    Ejemplos:
        plural="Facturas", singular="Factura"
        plural="Archivos", singular="Archivo"
    """
    plural: str = Field(..., max_length=100, examples=["Facturas"])
    singular: str = Field(..., max_length=100, examples=["Factura"])


class ManageFlagsSchema(BaseModel):
    """
    Controla qué mensajes Slack se envían para este RPA.

        start_active → envía mensaje de inicio de ejecución
        end_active   → envía mensaje de fin de ejecución
    """
    start_active: bool = Field(True, description="Enviar mensaje de inicio a Slack.")
    end_active: bool = Field(True, description="Enviar mensaje de fin a Slack.")


# ── Payload principal ─────────────────────────────────────────────────────────

class RPADashboardCreate(BaseModel):
    """
    Payload para crear un RPA Dashboard de forma atómica.

    Crea en una sola transacción:
        1. rpa_dashboard          (datos base del bot)
        2. rpa_dashboard_client   (configuración operativa)
        3. rpa_dashboard_business_error (uno por cada error en business_errors)

    Campos obligatorios (columna "Obligatorios"):
        - id_rpa          → ID de plataforma del bot (PK, lo define el usuario)
        - id_beecker      → ID del proceso en Beecker (ej: "SAC.003")
        - process_name    → Nombre del proceso (ej: "Procesador de facturas")
        - platform        → Plataforma Beecker ("cloud" | "hub")
        - id_client       → ID del cliente en la BD
        - slack_channel   → Canal de Slack destino (ej: "#roc-sigma-raas")
        - monitor_type    → Tipo de monitoreo ("bee_informa" | "bee_observa" | "bee_comunica")
                            También acepta con guión medio: "bee-informa", "bee-observa"

    Campos opcionales (columna "Opcionales"):
        - transaction_unit   → Unidad transaccional con plural y singular
        - roc_agents         → Lista de emails de agentes ROC
        - business_errors    → Lista de mensajes de error de negocio
        - manage_flags       → Control de mensajes de inicio/fin a Slack
    """

    # ── Obligatorios: rpa_dashboard ───────────────────────────────────────────
    id_rpa: str = Field(
        ...,
        max_length=100,
        description="ID de plataforma del bot. Funciona como PK (ej: '114').",
        examples=["114"],
    )
    id_beecker: str = Field(
        ...,
        max_length=100,
        description="ID del proceso en Beecker (ej: 'SAC.003').",
        examples=["SAC.003"],
    )
    process_name: str = Field(
        ...,
        max_length=200,
        description="Nombre del proceso RPA.",
        examples=["Procesador de facturas"],
    )
    platform: PlatformType = Field(
        ...,
        description="Plataforma Beecker donde corre el bot.",
        examples=["cloud"],
    )

    # ── Obligatorios: rpa_dashboard_client ───────────────────────────────────
    id_client: int = Field(
        ...,
        gt=0,
        description="ID del cliente en la tabla 'client'.",
        examples=[1],
    )
    slack_channel: str = Field(
        ...,
        max_length=100,
        description="Canal de Slack donde se envían las notificaciones (ej: '#roc-sigma-raas').",
        examples=["#roc-sigma-raas"],
    )
    monitor_type: MonitorType = Field(
        ...,
        description=(
            "Tipo de monitoreo. Acepta guión bajo o guión medio. "
            "Solo 'bee_observa' puede tener job asociado."
        ),
        examples=["bee_informa"],
    )

    # ── Opcionales: rpa_dashboard_client ─────────────────────────────────────
    transaction_unit: Optional[TransactionUnitSchema] = Field(
        default=None,
        description=(
            "Unidad transaccional en plural y singular. "
            "Se almacena como 'plural|singular' (ej: 'Facturas|Factura')."
        ),
    )
    roc_agents: Optional[List[str]] = Field(
        default=None,
        description="Lista de emails de agentes ROC que recibirán menciones en Slack.",
        examples=[["samuel.villanueva@beecker.ai", "otro@beecker.ai"]],
    )
    manage_flags: Optional[ManageFlagsSchema] = Field(
        default=None,
        description=(
            "Controla qué mensajes se envían a Slack. "
            "Si no se envía, ambos flags quedan como NULL en BD."
        ),
        examples=[{"start_active": True, "end_active": True}],
    )

    # ── Opcionales: rpa_dashboard_business_error ──────────────────────────────
    business_errors: Optional[List[str]] = Field(
        default=None,
        description="Lista de mensajes de error de negocio a registrar para este RPA.",
        examples=[["Business Exception", "Error Factura"]],
    )

    @field_validator("id_rpa", "id_beecker", "process_name", "slack_channel", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("business_errors", mode="before")
    @classmethod
    def validate_business_errors(cls, v):
        if v is not None:
            if not all(isinstance(e, str) and e.strip() for e in v):
                raise ValueError("Cada error de negocio debe ser un string no vacío.")
        return v


# ── Response ──────────────────────────────────────────────────────────────────

class BusinessErrorResponse(BaseModel):
    id: int
    error_message: str

    model_config = {"from_attributes": True}


class RPADashboardClientResponse(BaseModel):
    id_client: int
    monitor_type: MonitorType
    transaction_unit: Optional[str] = None
    slack_channel: Optional[str] = None
    roc_agents: Optional[List[str]] = None
    manage_flags: Optional[ManageFlagsSchema] = None

    model_config = {"from_attributes": True}


class RPADashboardResponse(BaseModel):
    id_rpa: str
    id_beecker: str
    process_name: str
    platform: PlatformType
    client: RPADashboardClientResponse
    business_errors: List[BusinessErrorResponse]

    model_config = {"from_attributes": True}