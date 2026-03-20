"""
app/routes/clients.py
"""
import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse
from app.services import client_service
from app.utils.auth import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED, summary="Crear cliente")
def create_client(payload: ClientCreate, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    return client_service.create_client(db, payload)


@router.get("/", response_model=list[ClientResponse], summary="Listar clientes")
def list_clients(db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    return client_service.list_clients(db)


@router.get("/{client_id}", response_model=ClientResponse, summary="Obtener cliente")
def get_client(client_id: str, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    return client_service.get_client(db, client_id)


@router.patch("/{client_id}", response_model=ClientResponse, summary="Actualizar cliente")
def update_client(client_id: str, payload: ClientUpdate, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    return client_service.update_client(db, client_id, payload)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar cliente")
def delete_client(client_id: str, db: Session = Depends(get_db), api_key: str = Depends(verify_api_key)):
    client_service.delete_client(db, client_id)