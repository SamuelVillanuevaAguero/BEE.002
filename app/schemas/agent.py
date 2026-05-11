from pydantic import BaseModel, Field
from typing import Optional
from datetime import time


class AgentTransactionPayload(BaseModel):
    """Payload received in POST /agent/transaction"""
    id: str
    agent_name: str
    agent_id: str
    account: str
    platform: str

class AgentTransactionUpdatePayload(BaseModel):
    """Payload received in PUT /agent/transaction"""
    agent_name: str
    agent_id: str
    account: str
    platform: str
    status: str
    details: Optional[str] = None

#Agent Monitoring Schemas

#Body Schemas

class TransactionUnit(BaseModel):
    plural: str = Field(..., examples=["Transacciones"])
    singular: str = Field(..., examples=["Transacción"])

class AgentMonitoring(BaseModel):
    agent_name: str = Field(..., examples=["Pedro"])
    beecker_id: str = Field(..., examples=["PML.001"])
    platform_id: str = Field(..., examples=["18"])
    platform: str = Field(..., examples=["cloud"])

    transaction_unit: TransactionUnit
    manage_flags: dict = Field(..., examples=[{"sla_active" : True, "tag_agents" : True}])
    roc_agents: list = Field(..., examples=[["agente.soporte@beecker.ai", "monitor.soporte@beecker.ai"]])

    SLA_time: int = Field(examples=[30])
    error_status: dict = Field(examples=[{"status": "^[error|system]$"}])
    completed_status: dict = Field(examples=[{"status": "completed"}])
    cut_off_time: time = Field(..., examples=["00:00:00"])

    slack_channel_id: str = Field(..., examples=["454as54as-84sa5sae-5a4sa8sa-5a1s5a1s5a1"])

class AgentMonitoringUpdate(BaseModel):
    pass

#Response Schemas
class AgentMonitoringResponse(AgentMonitoring):
    id: str = Field(..., examples=["5a4s51as-d5sa4wdawd-da451w5d-d8w1d5"])

class AgentMonitoringUpdateResponse(BaseModel):
    pass