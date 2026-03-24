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
from app.utils.responses import R200, R200_list, R201, R204, R404, COMMON

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clients", tags=["Clients"])

# ── Reusable example ────────────────────────────────────────────────────────
_CLIENT_EXAMPLE = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "client_name": "Aeroméxico",
}

_CLIENT_LIST_EXAMPLE = [
    {"id": "550e8400-e29b-41d4-a716-446655440000", "client_name": "Aeroméxico"},
    {"id": "661f9511-f3ac-52e5-b827-557766551111", "client_name": "Empresa XYZ"},
]


@router.post(
    "/",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create client",
    responses={
        **R201(_CLIENT_EXAMPLE, "Client created successfully"),
        **COMMON,
    },
)
def create_client(
    payload: ClientCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return client_service.create_client(db, payload)


@router.get(
    "/",
    response_model=list[ClientResponse],
    summary="List clients",
    responses={
        **R200_list(_CLIENT_LIST_EXAMPLE, "List of registered clients"),
        **COMMON,
    },
)
def list_clients(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return client_service.list_clients(db)


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
    summary="Get client by ID",
    responses={
        **R200(_CLIENT_EXAMPLE, "Client found"),
        **R404,
        **COMMON,
    },
)
def get_client(
    client_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return client_service.get_client(db, client_id)


@router.patch(
    "/{client_id}",
    response_model=ClientResponse,
    summary="Update client",
    responses={
        **R200(_CLIENT_EXAMPLE, "Client updated"),
        **R404,
        **COMMON,
    },
)
def update_client(
    client_id: str,
    payload: ClientUpdate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return client_service.update_client(db, client_id, payload)


@router.delete(
    "/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete client",
    responses={
        **R204,
        **R404,
        **COMMON,
    },
)
def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    client_service.delete_client(db, client_id)