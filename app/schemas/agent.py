"""
app/schemas/agent.py
Pydantic schemas for Agent Monitoring CRUD and webhook endpoints.
"""
from datetime import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.job import TriggerType
from app.models.rpa_dashboard import PlatformType


class AgentTransactionPayload(BaseModel):
    """Payload received in POST /agent/transaction"""
    id: str
    agent_name: str
    agent_id: str
    account: str
    platform: str
 
    model_config = {"extra": "forbid"}
 
    @field_validator("id", "agent_name", "agent_id", "account", "platform", mode="before")
    @classmethod
    def strip_str(cls, v):
        return v.strip() if isinstance(v, str) else v


class AgentTransactionUpdatePayload(BaseModel):
    """Payload received in PUT /agent/transaction/{transaction_id}"""
    agent_name: str
    agent_id: str
    account: str
    platform: str
    status: str
    details: Optional[str] = None
 
    model_config = {"extra": "forbid"}
 
    @field_validator(
        "agent_name", "agent_id", "account", "platform", "status", "details",
        mode="before",
    )
    @classmethod
    def strip_str(cls, v):
        return v.strip() if isinstance(v, str) else v


class TransactionUnit(BaseModel):
    """Plural / singular labels for the execution unit."""
    plural: str = Field(..., examples=["Transacciones"])
    singular: str = Field(..., examples=["Transacción"])

    @field_validator("plural", "singular", mode="before")
    @classmethod
    def strip_str(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class AgentJobCreate(BaseModel):
    """
    Inline job definition embedded in the agent creation payload.

    If omitted entirely from the request, a default interval job
    (every 1 hour) is created automatically.

    The job is always registered in APScheduler in PAUSED state —
    it must be resumed explicitly via POST /jobs/{job_id}/resume.
    """
    name: str = Field(..., max_length=255, examples=["JOB-PML.001-Pedro"])
    task_path: str = Field(
        ...,
        max_length=500,
        examples=["app.tasks.agent_tasks:scheduled_agent_status"],
    )
    trigger_type: TriggerType = Field(..., examples=["interval"])
    trigger_args: Dict[str, Any] = Field(..., examples=[{"hours": 1}])
    job_kwargs: Dict[str, Any] = Field(default_factory=dict, examples=[{}])

    model_config = {"extra": "forbid"}

    @field_validator("name", "task_path", mode="before")
    @classmethod
    def strip_str(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class AgentMonitoringCreate(BaseModel):
    """
    Payload to create a new AgentMonitoring record.

    The `job` field is optional. When omitted, a default interval job
    running every 1 hour is created and linked to the agent automatically.

    The job is always created in PAUSED state.
    """
    agent_name: str = Field(..., max_length=100, examples=["Pedro"])
    beecker_id: str = Field(..., max_length=10, examples=["PML.001"])
    platform_id: str = Field(..., max_length=10, examples=["18"])
    platform: PlatformType = Field(..., examples=["cloud"])

    transaction_unit: TransactionUnit
    manage_flags: Dict[str, Any] = Field(
        ..., examples=[{"sla_active": True, "tag_agents": True}]
    )
    roc_agents: List[str] = Field(
        ...,
        examples=[["agente.soporte@beecker.ai", "monitor.soporte@beecker.ai"]],
    )

    SLA_time: int = Field(..., ge=1, examples=[30])
    error_status: Dict[str, Any] = Field(..., examples=[{"status": "^[error|system]$"}])
    completed_status: Dict[str, Any] = Field(..., examples=[{"status": "completed"}])
    cut_off_time: time = Field(..., examples=["00:00:00"])
    slack_channel_id: str = Field(..., max_length=100, examples=["C04XXXXXXX"])

    # Optional inline job — defaults to hourly interval when omitted
    job: Optional[AgentJobCreate] = None

    model_config = {"extra": "forbid"}

    @field_validator("agent_name", "beecker_id", "platform_id", "slack_channel_id", mode="before")
    @classmethod
    def strip_str(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class AgentMonitoringUpdate(BaseModel):
    """
    Payload for partial updates to an AgentMonitoring record.
    Only explicitly provided fields are applied.

    Immutable fields (beecker_id, platform_id, platform, job_id) are
    intentionally excluded.
    """
    transaction_unit: Optional[TransactionUnit] = None
    manage_flags: Optional[Dict[str, Any]] = Field(
        None, examples=[{"sla_active": True, "tag_agents": False}]
    )
    roc_agents: Optional[List[str]] = Field(None, examples=[["agente.soporte@beecker.ai"]])
    SLA_time: Optional[int] = Field(None, ge=1, examples=[60])
    error_status: Optional[Dict[str, Any]] = Field(None, examples=[{"status": "error"}])
    completed_status: Optional[Dict[str, Any]] = Field(None, examples=[{"status": "completed"}])
    cut_off_time: Optional[time] = Field(None, examples=["23:59:00"])
    slack_channel_id: Optional[str] = Field(None, max_length=100)
    transactions_with_errors: Optional[List[Any]] = None

    model_config = {"extra": "forbid"}

    @field_validator("slack_channel_id", mode="before")
    @classmethod
    def strip_str(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class JobSummary(BaseModel):
    """Minimal job info embedded in the agent monitoring response."""
    id: str
    name: str
    task_path: str
    trigger_type: TriggerType
    trigger_args: Dict[str, Any]
    job_kwargs: Dict[str, Any]
    status: str
    next_run_time: Optional[Any] = None

    model_config = {"from_attributes": True}


class AgentMonitoringResponse(BaseModel):
    """Response schema for a single AgentMonitoring record."""
    id: str
    agent_name: str
    beecker_id: str
    platform_id: str
    platform: PlatformType

    transaction_unit: Any
    manage_flags: Dict[str, Any]
    roc_agents: Optional[List[str]]

    SLA_time: int
    error_status: Optional[Dict[str, Any]]
    completed_status: Optional[Dict[str, Any]]
    cut_off_time: time
    slack_channel_id: str

    transactions_exceeded_sla: Optional[List[Any]] = None
    transactions_with_errors: Optional[List[Any]] = None
    slack_message_id: Optional[str] = None
    job_id: Optional[str] = None

    job: Optional[JobSummary] = None

    model_config = {"from_attributes": True}


class AgentMonitoringUpdateResponse(AgentMonitoringResponse):
    """
    Response schema after a PATCH update.
    Identical to AgentMonitoringResponse — kept as separate symbol
    so the route signature is explicit.
    """
    pass