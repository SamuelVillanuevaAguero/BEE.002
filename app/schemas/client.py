"""
app/schemas/client.py
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class ClientFragment(BaseModel):
    """
    Fragmento de cliente en el payload atómico.
    Si id es null o vacío → se crea un cliente nuevo con name.
    Si id tiene valor → se usa el cliente existente.
    """
    id: Optional[str] = Field(default=None, description="ID del cliente. Null = crear nuevo.")
    name: Optional[str] = Field(default=None, max_length=150, description="Nombre del cliente (requerido si id es null).")
    model_config = {"extra": "forbid"}


class ClientCreate(BaseModel):
    id: Optional[str] = Field(default=None, max_length=100, description="Si no se envía o está vacío, se genera un UUID.")
    client_name: str = Field(..., max_length=150, examples=["Aeroméxico"])
    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "id": None,
                    "client_name": "Aeroméxico",
                }
            ]
        },
    }


class ClientUpdate(BaseModel):
    client_name: str = Field(..., max_length=150)
    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "client_name": "Aeroméxico Internacional",
                }
            ]
        },
    }


class ClientResponse(BaseModel):
    id: str
    client_name: str
    model_config = {"from_attributes": True}