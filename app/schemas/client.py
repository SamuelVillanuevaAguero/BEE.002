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
