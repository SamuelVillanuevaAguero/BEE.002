"""
app/schemas/client.py
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="ID del cliente. Si no se envía o está vacío, se genera un UUID automáticamente.",
        examples=["810bf42a-1645-4a51-aa5e-4ef76f2acd12"],
    )
    client_name: str = Field(..., max_length=150, examples=["Aeroméxico"])


class ClientUpdate(BaseModel):
    client_name: str = Field(..., max_length=150)


class ClientResponse(BaseModel):
    id: str
    client_name: str

    model_config = {"from_attributes": True}