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
    Logic for the client fragment in the atomic payload:
      - If client_id has a value → look up and return that client (404 if missing)
      - If client_id is None/empty → create a new client with client_name
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

    client = Client(
        id=client_id,
        client_name=payload.client_name,
        id_freshdesk=payload.id_freshdesk,
        id_beecker=payload.id_beecker,
    )
    db.add(client)
    try:
        db.commit()
        db.refresh(client)
    except IntegrityError as exc:
        db.rollback()
        _handle_integrity_error(exc)

    logger.info(
        f"✅ Cliente creado | id='{client.id}' | nombre='{client.client_name}' "
        f"| id_freshdesk='{client.id_freshdesk}' | id_beecker='{client.id_beecker}'"
    )
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

    if payload.client_name is not None:
        client.client_name = payload.client_name
    if payload.id_freshdesk is not None:
        client.id_freshdesk = payload.id_freshdesk
    if payload.id_beecker is not None:
        client.id_beecker = payload.id_beecker

    try:
        db.commit()
        db.refresh(client)
    except IntegrityError as exc:
        db.rollback()
        _handle_integrity_error(exc)

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _handle_integrity_error(exc: IntegrityError) -> None:
    """Translate uniqueness errors into human-readable HTTP responses."""
    msg = str(exc.orig).lower() if exc.orig else ""
    if "id_freshdesk" in msg:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un cliente con ese id_freshdesk.",
        )
    if "id_beecker" in msg:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un cliente con ese id_beecker.",
        )
    if "client_name" in msg:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un cliente con ese nombre.",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Error de integridad en BD.",
    )
