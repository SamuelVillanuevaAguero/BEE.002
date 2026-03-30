"""
app/routes/rpa_dashboard.py
=============================
CRUD completo para RPADashboard, RPADashboardMonitoring, Job vinculation y BusinessErrors.
Reemplaza el endpoint atómico anterior.
"""
import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.rpa_dashboard import (
    RPADashboardCreate,
    RPADashboardUpdate,
    RPADashboardResponse,
    RPADashboardDetailResponse,
    RPADashboardMonitoringCreate,
    RPADashboardMonitoringUpdate,
    RPADashboardMonitoringResponse,
    JobLinkRequest,
    BusinessErrorCreate,
    BusinessErrorResponse,
)
from app.services import rpa_dashboard_service
from app.utils.auth import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rpa-dashboard", tags=["RPA Dashboard"])


# ── RPADashboard ──────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=RPADashboardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear bot base",
    description="Crea el registro base del bot en `rpa_dashboard`. No crea monitoring ni errores.",
)
def create_rpa_dashboard(
    payload: RPADashboardCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RPADashboardResponse:
    return rpa_dashboard_service.create_rpa_dashboard(db, payload)


@router.get(
    "/",
    response_model=list[RPADashboardResponse],
    summary="Listar bots",
    description="Devuelve todos los bots con sus campos base (sin monitorings ni errores anidados).",
)
def list_rpa_dashboards(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> list[RPADashboardResponse]:
    return rpa_dashboard_service.list_rpa_dashboards(db)


@router.get(
    "/{id_beecker}",
    response_model=RPADashboardDetailResponse,
    summary="Obtener bot con detalle",
    description="Devuelve el bot con sus monitorings y errores de negocio anidados.",
)
def get_rpa_dashboard(
    id_beecker: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RPADashboardDetailResponse:
    return rpa_dashboard_service.get_rpa_dashboard(db, id_beecker)


@router.patch(
    "/{id_beecker}",
    response_model=RPADashboardResponse,
    summary="Actualizar bot base",
)
def update_rpa_dashboard(
    id_beecker: str,
    payload: RPADashboardUpdate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RPADashboardResponse:
    return rpa_dashboard_service.update_rpa_dashboard(db, id_beecker, payload)


@router.delete(
    "/{id_beecker}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar bot",
    description="Elimina el bot y en cascade sus monitorings y errores de negocio.",
)
def delete_rpa_dashboard(
    id_beecker: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> None:
    rpa_dashboard_service.delete_rpa_dashboard(db, id_beecker)


# ── RPADashboardMonitoring ────────────────────────────────────────────────────

@router.post(
    "/{id_beecker}/monitoring",
    response_model=RPADashboardMonitoringResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear configuración de monitoring",
    description="Agrega una configuración de monitoreo (canal, tipo, agentes) al bot.",
)
def create_monitoring(
    id_beecker: str,
    payload: RPADashboardMonitoringCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RPADashboardMonitoringResponse:
    return rpa_dashboard_service.create_monitoring(db, id_beecker, payload)


@router.get(
    "/{id_beecker}/monitoring",
    response_model=list[RPADashboardMonitoringResponse],
    summary="Listar monitorings del bot",
)
def list_monitoring(
    id_beecker: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> list[RPADashboardMonitoringResponse]:
    return rpa_dashboard_service.list_monitoring(db, id_beecker)


@router.get(
    "/{id_beecker}/monitoring/{monitoring_id}",
    response_model=RPADashboardMonitoringResponse,
    summary="Obtener monitoring específico",
)
def get_monitoring(
    id_beecker: str,
    monitoring_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RPADashboardMonitoringResponse:
    return rpa_dashboard_service.get_monitoring(db, id_beecker, monitoring_id)


@router.patch(
    "/{id_beecker}/monitoring/{monitoring_id}",
    response_model=RPADashboardMonitoringResponse,
    summary="Actualizar monitoring",
)
def update_monitoring(
    id_beecker: str,
    monitoring_id: str,
    payload: RPADashboardMonitoringUpdate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RPADashboardMonitoringResponse:
    return rpa_dashboard_service.update_monitoring(db, id_beecker, monitoring_id, payload)


@router.delete(
    "/{id_beecker}/monitoring/{monitoring_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar monitoring",
    description="Elimina el monitoring. Si tiene job vinculado, lo elimina también.",
)
def delete_monitoring(
    id_beecker: str,
    monitoring_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> None:
    rpa_dashboard_service.delete_monitoring(db, id_beecker, monitoring_id)


# ── Job vinculation ───────────────────────────────────────────────────────────

@router.put(
    "/{id_beecker}/monitoring/{monitoring_id}/job",
    response_model=RPADashboardMonitoringResponse,
    summary="Vincular job al monitoring",
    description=(
        "Vincula un job existente al monitoring. "
        "Inyecta `bot_id` y `monitoring_id` en `job_kwargs` automáticamente. "
        "Si el job está activo, lo pausa."
    ),
)
def link_job(
    id_beecker: str,
    monitoring_id: str,
    payload: JobLinkRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RPADashboardMonitoringResponse:
    return rpa_dashboard_service.link_job(db, id_beecker, monitoring_id, payload)


@router.delete(
    "/{id_beecker}/monitoring/{monitoring_id}/job",
    response_model=RPADashboardMonitoringResponse,
    summary="Desvincular job del monitoring",
    description="Desvincula el job sin eliminarlo. Limpia bot_id y monitoring_id de job_kwargs.",
)
def unlink_job(
    id_beecker: str,
    monitoring_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RPADashboardMonitoringResponse:
    return rpa_dashboard_service.unlink_job(db, id_beecker, monitoring_id)


# ── BusinessErrors ────────────────────────────────────────────────────────────

@router.post(
    "/{id_beecker}/business-errors",
    response_model=BusinessErrorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar error de negocio",
)
def create_business_error(
    id_beecker: str,
    payload: BusinessErrorCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> BusinessErrorResponse:
    return rpa_dashboard_service.create_business_error(db, id_beecker, payload)


@router.get(
    "/{id_beecker}/business-errors",
    response_model=list[BusinessErrorResponse],
    summary="Listar errores de negocio del bot",
)
def list_business_errors(
    id_beecker: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> list[BusinessErrorResponse]:
    return rpa_dashboard_service.list_business_errors(db, id_beecker)


@router.delete(
    "/{id_beecker}/business-errors/{error_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar error de negocio",
)
def delete_business_error(
    id_beecker: str,
    error_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> None:
    rpa_dashboard_service.delete_business_error(db, id_beecker, error_id)