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


def create_client(db: Session, payload: ClientCreate) -> Client:
    # Si no se envía id o viene vacío, generar UUID automáticamente
    client_id = payload.id.strip() if payload.id and payload.id.strip() else str(uuid.uuid4())

    if db.get(Client, client_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un cliente con id='{client_id}'.",
        )

    client = Client(id=client_id, client_name=payload.client_name)
    db.add(client)
    try:
        db.commit()
        db.refresh(client)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Error de integridad en BD.")

    logger.info(f"✅ Cliente creado | id='{client.id}' | nombre='{client.client_name}'")
    return client


def list_clients(db: Session) -> list[Client]:
    return db.query(Client).order_by(Client.client_name).all()


def get_client(db: Session, client_id: str) -> Client:
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente '{client_id}' no encontrado.",
        )
    return client


def update_client(db: Session, client_id: str, payload: ClientUpdate) -> Client:
    client = get_client(db, client_id)
    client.client_name = payload.client_name
    db.commit()
    db.refresh(client)
    logger.info(f"✅ Cliente actualizado | id='{client_id}'")
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
    logger.info(f"🗑️ Cliente eliminado | id='{client_id}'")