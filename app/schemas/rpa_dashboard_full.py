"""
app/schemas/rpa_dashboard_full.py
===================================
Schema for the atomic endpoint POST /rpa-dashboard/full.

Payload design:

    {
        "client": {                      # use existing (id only) OR create new (all fields)
            "id":           null,        # null = create; UUID = use existing
            "client_name":  "Grupo Bimbo",
            "id_freshdesk": "123456",
            "id_beecker":   "BIMB"
        },
        "rpa": {
            "id_dashboard": "111",
            "id_beecker":   "CFC.003",
            "process_name": "Payment complements processing",
            "platform":     "cloud"
        },
        "monitor_type":    "bee-informa",
        "slack_channel":   "#roc-bimbo-pagos",
        "transaction_unit": { "plural": "Payments", "singular": "Payment" },
        "roc_agents":  ["samuel@beecker.ai", "alan@beecker.ai"],
        "manage_flags": { "start_active": false, "end_active": true },
        "business_errors": ["Business Exception", "Not loaded in the system"],
        "job": {                         # optional; if empty {} it is ignored
            "name":         "JOB-CFC.003",
            "task_path":    "app.tasks.rpa_tasks:send_rpa_status_task",
            "trigger_type": "cron",
            "trigger_args": { "hour": "*/1" }
        }
    }

Client logic:
- client.id has a value and exists in DB  -> that client is used; other fields are ignored.
- client.id is null or does not exist in DB -> a new client is created with the remaining fields.
- If creating a new one, client_name + id_freshdesk + id_beecker are required.

Design notes:
- business_errors is a list of strings -> JSON column in rpa_dashboard.
- job is completely optional. If omitted or sent as {} no job is created.
- Only ONE monitoring is created per atomic request.
- Full rollback if any step fails.
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.rpa_dashboard import MonitorType, PlatformType
from app.schemas.client import ClientInlineResponse
from app.schemas.rpa_dashboard import (
    TransactionUnitSchema,
    ManageFlagsSchema,
    MonitoringResponse,
)

class BaseStringValidator(BaseModel):
    """Base with a common validator for stripping strings."""
    
    @field_validator("*", mode="before")
    @classmethod
    def strip_str(cls, v: str) -> str:
        """Removes leading and trailing whitespace from strings."""
        return v.strip() if isinstance(v, str) else v


class BaseOptionalStringFields(BaseModel):
    """Base for optional string fields with max length."""
    
    @field_validator("*", mode="before")
    @classmethod
    def strip_optional_str(cls, v: str) -> str:
        """Removes leading and trailing whitespace from optional strings."""
        return v.strip() if isinstance(v, str) else v


class BaseCreatableModel(BaseModel):
    """Base for models with create vs update logic."""    
    @property
    def wants_create(self) -> bool:
        """True if the intent is to create a new record (empty/null id)."""
        return not (getattr(self, 'id', None) and getattr(self, 'id', None).strip())
    
    def _validate_required_for_create(self, required_fields: dict[str, Any]) -> None:
        """Validates that required fields are present for creation."""
        if self.wants_create:
            missing = [
                f for f, v in required_fields.items() if not v
            ]
            if missing:
                raise ValueError(
                    f"To create a new record you must include: {missing}."
                )



class ClientInline(BaseOptionalStringFields, BaseCreatableModel):
    """
    Client fragment for the atomic endpoint.

    Behavior:
    - id with an existing value in DB  -> uses that client, ignores the rest.
    - id = null or missing            -> creates a new client with the remaining fields.
    """
    id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Client UUID. null = create new; value = use existing.",
        examples=[None, "810bf42a-1645-4a51-aa5e-4ef76f2acd12"],
    )
    client_name: Optional[str] = Field(default=None, max_length=150, examples=["Grupo Bimbo"])
    id_freshdesk: Optional[str] = Field(default=None, max_length=15, examples=["123456"])
    id_beecker: Optional[str] = Field(default=None, max_length=4, examples=["BIMB"])



    @property
    def wants_create(self) -> bool:
        """True if the intent is to create a new client (empty/null id)"""
        return not (self.id and self.id.strip())

    @model_validator(mode="after")
    def validate_create_fields(self) -> "ClientInline":
        """If creating, all three data fields are required."""
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
                    f"To create a new client you must include: {missing}."
                )
        return self


class RPAInline(BaseOptionalStringFields, BaseModel):
    """Data for the base record in rpa_dashboard.

    Behavior:
    - If the bot exists by id_beecker, sending only id_beecker is enough.
    - If the bot does not exist, id_dashboard, process_name and platform are required.
    """

    id_dashboard: Optional[str] = Field(
        default=None,
        max_length=40,
        description="Numeric ID for the Beecker API (e.g., '111')",
        examples=["111"],
    )
    id_beecker: str = Field(
        ..., max_length=10,
        description="ROC identifier visible in Slack (e.g., 'CFC.003')",
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
    business_errors: Optional[List[str]] = Field(
        default=None,
        description="List of strings containing the bot's business errors.",
        examples=[["Business Exception", "No está cargada en el sistema"]],
    )



    @model_validator(mode="after")
    def validate_create_fields(self) -> "RPAInline":
        creation_fields = [self.id_dashboard, self.process_name, self.platform]
        if any(creation_fields) and not all(creation_fields):
            raise ValueError(
                "If you send RPA data for creation, you must include id_dashboard, process_name, and platform."
            )
        return self


class JobInline(BaseModel):
    """
    Data to create the APScheduler job and link it to the monitoring.
    Completely optional. If omitted or empty {}, no job is created.
    Applies only for monitor_type = bee-observa.
    """
    name: Optional[str] = Field(default=None, max_length=255)
    task_path: Optional[str] = Field(
        default=None,
        description="Python path of the function",
        examples=["app.tasks.rpa_tasks:scheduled_rpa_status"],
    )
    trigger_type: Optional[str] = Field(default=None, examples=["interval"])
    trigger_args: Optional[dict[str, Any]] = Field(default=None, examples=[{"minutes": 5}])
    job_kwargs: Optional[dict[str, Any]] = Field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """True if it has enough information to create the job."""
        return bool(self.name and self.task_path and self.trigger_type and self.trigger_args)


class RPADashboardFullCreate(BaseStringValidator, BaseModel):
    """
    Creates in a single transaction:
    1. Client (create new or use existing)
    2. rpa_dashboard (base bot + business_errors as JSON)
    3. rpa_dashboard_monitoring (a monitoring configuration)
    4. APScheduler Job (optional, only if job has all required fields)
    """

    client: ClientInline
    rpa: RPAInline

    monitor_type: MonitorType
    slack_channel: str = Field(..., max_length=100, examples=["#roc-bimbo-pagos"])
    transaction_unit: Optional[TransactionUnitSchema] = None
    roc_agents: Optional[List[str]] = Field(default=None, examples=[["samuel@beecker.ai"]])
    manage_flags: Optional[ManageFlagsSchema] = None

    job: Optional[JobInline] = Field(
        default=None,
        description=(
            "Job para bee-observa. Opcional "
        ),
    )

class RPADashboardFullResponse(BaseModel):
    """Atomic endpoint response."""

    client: ClientInlineResponse
    rpa: RPAInline
    monitoring: MonitoringResponse
    job_created: bool = Field(
        default=False,
        description="True si se creó y vinculó un job al monitoring.",
    )

    model_config = {"from_attributes": False}