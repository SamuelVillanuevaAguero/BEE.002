from pydantic import BaseModel
from typing import Optional


class RPAExecutionPayload(BaseModel):
    """Payload recibido en POST /rpa/execution"""
    id: str
    bot_name: str
    bot_id: str

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "id": "98765",
                    "bot_name": "AEC.001",
                    "bot_id": "114",
                }
            ]
        },
    }


class RPAExecutionUpdatePayload(BaseModel):
    """Payload recibido en PUT /rpa/execution/{id}"""
    bot_name: str
    bot_id: str
    status: str
    details: Optional[str] = None

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "bot_name": "AEC.001",
                    "bot_id": "114",
                    "status": "completed",
                    "details": None,
                }
            ]
        },
    }