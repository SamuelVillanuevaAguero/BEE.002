"""
app/services/client_service.py
Client service with Repository pattern for clean data access abstraction.
"""
from __future__ import annotations
import logging
import uuid
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.automation import Client
from app.schemas.client import ClientCreate, ClientUpdate
from app.repositories import ClientRepository

logger = logging.getLogger(__name__)


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


def create_client(db: Session, payload: ClientCreate) -> Client:
    """
    Create a new client using the Repository pattern.
    
    Args:
        db: Database session
        payload: Client creation payload
        
    Returns:
        The created Client instance
        
    Raises:
        HTTPException: If there's an integrity error
    """
    try:
        repo = ClientRepository(db)
        client_id = str(uuid.uuid4())
        
        data = payload.model_dump()
        data["id"] = client_id
        client = repo.create(data)
        
        logger.info(
            f"✅ Cliente creado | id='{client.id}' | nombre='{client.client_name}' "
            f"| id_freshdesk='{client.id_freshdesk}' | id_beecker='{client.id_beecker}'"
        )
        return client
    except HTTPException:
        raise
    except IntegrityError as exc:
        _handle_integrity_error(exc)
    except Exception as e:
        logger.error(f"Error creating client: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


def list_clients(db: Session) -> list[Client]:
    """
    List all clients ordered by name using Repository pattern.
    
    Args:
        db: Database session
        
    Returns:
        List of Client instances
    """
    try:
        repo = ClientRepository(db)
        return repo.list_all()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing clients: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


def get_client(db: Session, client_id: str) -> Client:
    """
    Get a client by ID using Repository pattern.
    
    Args:
        db: Database session
        client_id: The client ID
        
    Returns:
        The Client instance
        
    Raises:
        HTTPException: If client not found
    """
    try:
        repo = ClientRepository(db)
        client = repo.get_by_id(client_id)
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cliente '{client_id}' no encontrado."
            )
        return client
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting client {client_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


def update_client(db: Session, client_id: str, payload: ClientUpdate) -> Client:
    """
    Update a client using Repository pattern with dynamic field mapping.
    
    Args:
        db: Database session
        client_id: The client ID
        payload: Client update payload
        
    Returns:
        The updated Client instance
        
    Raises:
        HTTPException: If client not found or update fails
    """
    try:
        repo = ClientRepository(db)
        client = repo.get_by_id(client_id)
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cliente '{client_id}' no encontrado."
            )
        
        # Update only provided fields
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            if value is not None:
                setattr(client, field, value)
        
        repo.commit()
        repo.refresh(client)
        
        logger.info(f"✅ Cliente actualizado | id='{client_id}'")
        return client
    except HTTPException:
        raise
    except IntegrityError as exc:
        _handle_integrity_error(exc)
    except Exception as e:
        logger.error(f"Error updating client {client_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


def delete_client(db: Session, client_id: str) -> None:
    """
    Delete a client using Repository pattern.
    
    Args:
        db: Database session
        client_id: The client ID
        
    Raises:
        HTTPException: If client not found or cannot be deleted due to references
    """
    try:
        repo = ClientRepository(db)
        client = repo.get_by_id(client_id)
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cliente '{client_id}' no encontrado."
            )
        
        repo.delete(client_id)
        logger.info(f"🗑️ Cliente eliminado | id='{client_id}'")
    except HTTPException:
        raise
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar el cliente porque tiene bots asociados.",
        )
    except Exception as e:
        logger.error(f"Error deleting client {client_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")


def get_or_create_client(db: Session, client_id: str | None, client_name: str | None) -> Client:
    """
    Logic for the client fragment in the atomic payload:
      - If client_id has a value → look up and return that client (404 if missing)
      - If client_id is None/empty → create a new client with client_name
      
    Args:
        db: Database session
        client_id: The client ID (optional)
        client_name: The client name (optional, required if client_id is None)
        
    Returns:
        The Client instance
        
    Raises:
        HTTPException: If validation fails or client not found
    """
    try:
        repo = ClientRepository(db)
        cid = client_id.strip() if client_id and client_id.strip() else None

        if cid:
            client = repo.get_by_id(cid)
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

        new_client = repo.create({
            "id": str(uuid.uuid4()),
            "client_name": client_name.strip(),
        })
        
        logger.info(f"✅ Cliente creado automáticamente | id='{new_client.id}' | nombre='{new_client.client_name}'")
        return new_client
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_or_create_client: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error")
