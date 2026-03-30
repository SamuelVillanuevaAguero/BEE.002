from pydantic import BaseModel
from typing import Optional


class RPAExecutionPayload(BaseModel):
    """Payload received in POST /rpa/execution"""
    id: str
    bot_name: str
    bot_id: str

class RPAExecutionUpdatePayload(BaseModel):
    """Payload received in PUT /rpa/execution"""
    bot_name: str
    bot_id: str
    status: str
    details: Optional[str] = None