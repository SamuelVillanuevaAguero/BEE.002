from pydantic import BaseModel
from typing import Optional


class RPAExecutionPayload(BaseModel):
    """Payload recibido en POST /rpa/execution"""
    id: str
    bot_name: str
    bot_id: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Inicio de ejecución estándar",
                    "value": {
                        "id": "98765",
                        "bot_name": "AEC.001",
                        "bot_id": "114",
                    },
                }
            ]
        }
    }


class RPAExecutionUpdatePayload(BaseModel):
    """Payload recibido en PUT /rpa/execution/{id}"""
    bot_name: str
    bot_id: str
    status: str
    details: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Fin de ejecución exitosa",
                    "value": {
                        "bot_name": "AEC.001",
                        "bot_id": "114",
                        "status": "completed",
                        "details": None,
                    },
                },
                {
                    "summary": "Fin de ejecución con error",
                    "value": {
                        "bot_name": "AEC.001",
                        "bot_id": "114",
                        "status": "failed",
                        "details": "Timeout al conectar con el sistema origen.",
                    },
                },
            ]
        }
    }