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
    id_freshdesk: str = Field(
        ...,
        max_length=15,
        description="ID de la empresa en FreshDesk.",
        examples=["123456"],
    )
    id_beecker: str = Field(
        ...,
        max_length=4,
        description="ID del cliente en la plataforma Beecker (máx. 4 caracteres).",
        examples=["AERO"],
    )


class ClientUpdate(BaseModel):
    client_name: Optional[str] = Field(default=None, max_length=150)
    id_freshdesk: Optional[str] = Field(default=None, max_length=15)
    id_beecker: Optional[str] = Field(default=None, max_length=4)


class ClientResponse(BaseModel):
    id: str
    client_name: str
    id_freshdesk: str
    id_beecker: str

    model_config = {"from_attributes": True}


class ClientInlineResponse(ClientResponse):
    """Igual que ClientResponse pero indica si fue creado en la request actual."""
    created: bool = Field(description="True si el cliente fue creado en esta request.")