from pydantic import BaseModel
from typing import Optional


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