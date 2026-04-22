"""
app/schemas/rpa_dashboard_full.py
===================================
Schema para el endpoint atómico POST /rpa-dashboard/full.

Diseño del payload:

    {
        "client": {                      ← usar existente (solo id) O crear nuevo (todos los campos)
            "id":           null,        ← null = crear; UUID = usar existente
            "client_name":  "Grupo Bimbo",
            "id_freshdesk": "123456",
            "id_beecker":   "BIMB"
        },
        "rpa": {
            "id_dashboard": "111",
            "id_beecker":   "CFC.003",
            "process_name": "Procesamiento de complementos de pago",
            "platform":     "cloud"
        },
        "monitor_type":    "bee-informa",
        "slack_channel":   "#roc-bimbo-pagos",
        "transaction_unit": { "plural": "Pagos", "singular": "Pago" },
        "roc_agents":  ["samuel@beecker.ai", "alan@beecker.ai"],
        "manage_flags": { "start_active": false, "end_active": true },
        "business_errors": ["Business Exception", "No está cargada en el sistema"],
        "job": {                         ← opcional; si viene vacío {} se ignora
            "name":         "JOB-CFC.003",
            "task_path":    "app.tasks.rpa_tasks:send_rpa_status_task",
            "trigger_type": "cron",
            "trigger_args": { "hour": "*/1" }
        }
    }

Lógica del cliente:
- client.id tiene valor y existe en BD  → se usa ese cliente; resto de campos ignorados.
- client.id es null o no existe en BD   → se crea un cliente nuevo con los demás campos.
- Si se va a crear, client_name + id_freshdesk + id_beecker son obligatorios.

Notas de diseño:
- business_errors es una lista de strings → columna JSON en rpa_dashboard.
- job es completamente opcional. Si se omite o viene como {} no se crea job.
- Se crea UN solo monitoring por request atómica.
- Rollback total si cualquier paso falla.
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.automation import MonitorType, PlatformType
from app.schemas.client import ClientInlineResponse
from app.schemas.rpa_dashboard import (
    TransactionUnitSchema,
    ManageFlagsSchema,
    MonitoringResponse,
)


# ── Sub-schema: cliente inline ────────────────────────────────────────────────

class ClientInline(BaseModel):
    """
    Fragmento de cliente para el endpoint atómico.

    Comportamiento:
    - id con valor existente en BD  → usa ese cliente, ignora el resto.
    - id = null o ausente           → crea cliente nuevo con los demás campos.
    """
    id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="UUID del cliente. null = crear nuevo; valor = usar existente.",
        examples=[None, "810bf42a-1645-4a51-aa5e-4ef76f2acd12"],
    )
    client_name: Optional[str] = Field(default=None, max_length=150, examples=["Grupo Bimbo"])
    id_freshdesk: Optional[str] = Field(default=None, max_length=15, examples=["123456"])
    id_beecker: Optional[str] = Field(default=None, max_length=4, examples=["BIMB"])

    @field_validator("client_name", "id_freshdesk", "id_beecker", mode="before")
    @classmethod
    def strip_str(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @property
    def wants_create(self) -> bool:
        """True si el intent es crear un cliente nuevo (id vacío/null)."""
        return not (self.id and self.id.strip())

    @model_validator(mode="after")
    def validate_create_fields(self) -> "ClientInline":
        """Si se va a crear, los tres campos de datos son obligatorios."""
        if self.wants_create:
            missing = [
                f for f, v in {
                    "client_name": self.client_name,
                    "id_freshdesk": self.id_freshdesk,
                    "id_beecker": self.id_beecker,
                }.items() if not v
            ]
            if missing:
                raise ValueError(
                    f"Para crear un cliente nuevo debes incluir: {missing}."
                )
        return self


# ── Sub-schema: datos del bot ─────────────────────────────────────────────────

class RPAInline(BaseModel):
    """Datos del registro base en rpa_dashboard.

    Comportamiento:
    - Si el bot existe por id_beecker, basta con enviar solo id_beecker.
    - Si el bot no existe, es obligatorio enviar id_dashboard, process_name y platform.
    """

    id_dashboard: Optional[str] = Field(
        default=None,
        max_length=40,
        description="ID numérico para la API de Beecker (ej: '111')",
        examples=["111"],
    )
    id_beecker: str = Field(
        ..., max_length=10,
        description="Identificador ROC visible en Slack (ej: 'CFC.003')",
        examples=["CFC.003"],
    )
    process_name: Optional[str] = Field(
        default=None,
        max_length=200,
        examples=["Procesamiento de complementos de pago"],
    )
    platform: Optional[PlatformType] = None
    group_by_column: str | None = Field(
        default=None
    )

    @field_validator("id_dashboard", "id_beecker", "process_name", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def validate_create_fields(self) -> "RPAInline":
        creation_fields = [self.id_dashboard, self.process_name, self.platform]
        if any(creation_fields) and not all(creation_fields):
            raise ValueError(
                "Si envías datos de RPA para crear, debes incluir id_dashboard, process_name y platform."
            )
        return self


# ── Sub-schema: job opcional ──────────────────────────────────────────────────

class JobInline(BaseModel):
    """
    Datos para crear el APScheduler job y vincularlo al monitoring.
    Completamente opcional. Si se omite o viene vacío {}, no se crea job.
    Solo aplica para monitor_type = bee-observa.
    """
    name: Optional[str] = Field(default=None, max_length=255)
    task_path: Optional[str] = Field(
        default=None,
        description="Python path de la función",
        examples=["app.tasks.rpa_tasks:scheduled_rpa_status"],
    )
    trigger_type: Optional[str] = Field(default=None, examples=["interval"])
    trigger_args: Optional[dict[str, Any]] = Field(default=None, examples=[{"minutes": 5}])
    job_kwargs: Optional[dict[str, Any]] = Field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """True si tiene suficiente información para crear el job."""
        return bool(self.name and self.task_path and self.trigger_type and self.trigger_args)


# ── Payload principal ─────────────────────────────────────────────────────────

class RPADashboardFullCreate(BaseModel):
    """
    Crea en una sola transacción:
      1. Client (crea nuevo o usa existente)
      2. rpa_dashboard (bot base + business_errors como JSON)
      3. rpa_dashboard_monitoring (una config de monitoreo)
      4. Job en APScheduler (opcional, solo si job tiene todos sus campos)
    """

    # ── Cliente (crear o reutilizar) ──────────────────────────────────────────
    client: ClientInline

    # ── Bot ───────────────────────────────────────────────────────────────────
    rpa: RPAInline

    # ── Monitoring (aplanado en el root) ──────────────────────────────────────
    monitor_type: MonitorType
    slack_channel: str = Field(..., max_length=100, examples=["#roc-bimbo-pagos"])
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = Field(default=None, examples=[["samuel@beecker.ai"]])
    manage_flags: Optional[ManageFlagsSchema] = None

    # ── Errores de negocio (JSON en rpa_dashboard.business_errors) ───────────
    business_errors: Optional[List[str]] = Field(
        default=None,
        description="Lista de strings con los errores de negocio del bot.",
        examples=[["Business Exception", "No está cargada en el sistema"]],
    )

    # ── Job (opcional) ────────────────────────────────────────────────────────
    job: Optional[JobInline] = Field(
        default=None,
        description=(
            "Job para bee-observa. Opcional — si se omite o viene vacío {}, "
            "el monitoring se crea sin job vinculado."
        ),
    )

    @field_validator("slack_channel", mode="before")
    @classmethod
    def strip_channel(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


# ── Response ──────────────────────────────────────────────────────────────────

class RPADashboardFullResponse(BaseModel):
    """Respuesta del endpoint atómico."""

    client: ClientInlineResponse
    id_beecker: str
    id_dashboard: str
    process_name: str
    platform: PlatformType
    business_errors: Optional[List[str]] = None
    group_by_column: str | None = Field(
        default=None
    )
    monitoring: MonitoringResponse
    job_created: bool = Field(
        default=False,
        description="True si se creó y vinculó un job al monitoring.",
    )

    model_config = {"from_attributes": False}