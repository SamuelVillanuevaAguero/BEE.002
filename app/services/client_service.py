"""
app/services/client_service.py
"""
from __future__ import annotations
import logging
import uuid
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.automation import Client
from app.schemas.client import ClientCreate, ClientUpdate

logger = logging.getLogger(__name__)


def get_or_create_client(db: Session, client_id: str | None, client_name: str | None) -> Client:
    """
    Lógica del fragmento client en el payload atómico:
      - Si client_id tiene valor → buscar y retornar ese cliente (404 si no existe)
      - Si client_id es None/vacío → crear nuevo cliente con client_name
    """
    cid = client_id.strip() if client_id and client_id.strip() else None

    if cid:
        client = db.get(Client, cid)
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cliente '{cid}' no encontrado.",
            )
        return client

    if not client_name or not client_name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Si client.id es null, client.name es obligatorio para crear el cliente.",
        )

    new_id = str(uuid.uuid4())
    client = Client(id=new_id, client_name=client_name.strip())
    db.add(client)
    db.flush()
    logger.info(f"✅ Cliente creado | id='{new_id}' | nombre='{client_name}'")
    return client


def create_client(db: Session, payload: ClientCreate) -> Client:
    client_id = payload.id.strip() if payload.id and payload.id.strip() else str(uuid.uuid4())
    if db.get(Client, client_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe un cliente con id='{client_id}'.")
    client = Client(id=client_id, client_name=payload.client_name)
    db.add(client)
    try:
        db.commit()
        db.refresh(client)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Error de integridad en BD.")
    logger.info(f"✅ Cliente creado | id='{client.id}'")
    return client


def list_clients(db: Session) -> list[Client]:
    return db.query(Client).order_by(Client.client_name).all()


def get_client(db: Session, client_id: str) -> Client:
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Cliente '{client_id}' no encontrado.")
    return client


def update_client(db: Session, client_id: str, payload: ClientUpdate) -> Client:
    client = get_client(db, client_id)
    client.client_name = payload.client_name
    db.commit()
    db.refresh(client)
    return client


def delete_client(db: Session, client_id: str) -> None:
    client = get_client(db, client_id)
    db.delete(client)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar el cliente porque tiene bots asociados.",
        )