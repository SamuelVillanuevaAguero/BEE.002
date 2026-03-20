"""
app/routes/rpa_dashboard.py

Endpoints:
    POST   /rpa-dashboard/                              → Crear bot dashboard (atómico)
    GET    /rpa-dashboard/                              → Listar bots dashboard
    GET    /rpa-dashboard/{id_beecker}/errors           → Listar errores del bot
    GET    /rpa-dashboard/monitoring                    → Listar todos los monitoreos dashboard (+ job)
    PATCH  /rpa-dashboard/monitoring/{monitoring_id}    → Actualizar monitoring
    DELETE /rpa-dashboard/monitoring/{monitoring_id}    → Eliminar monitoring (+ job si tiene)

    POST   /rpa-uipath/                                 → Crear bot uipath (atómico)
    GET    /rpa-uipath/                                 → Listar bots uipath
    GET    /rpa-uipath/{robot_name}/errors              → Listar errores del bot
    GET    /rpa-uipath/monitoring                       → Listar todos los monitoreos uipath (+ job)
    PATCH  /rpa-uipath/monitoring/{monitoring_id}       → Actualizar monitoring
    DELETE /rpa-uipath/monitoring/{monitoring_id}       → Eliminar monitoring (+ job si tiene)
"""
import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.rpa_dashboard import (
    RPADashboardAtomicCreate,
    RPAUiPathAtomicCreate,
    MonitoringPatch,
    RPADashboardResponse,
    RPAUiPathResponse,
    AtomicCreateResponse,
)
from app.services import rpa_dashboard_service
from app.utils.auth import verify_api_key

logger = logging.getLogger(__name__)

# Dos routers separados para mantener prefijos distintos
dashboard_router = APIRouter(prefix="/rpa-dashboard", tags=["RPA Dashboard"])
uipath_router = APIRouter(prefix="/rpa-uipath", tags=["RPA UiPath"])


# ═══════════════════════════════════════════════════════════════════════════════
# RPA DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@dashboard_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Crear bot Dashboard (atómico)",
    description=(
        "Crea en una sola transacción"
    ),
)
def create_rpa_dashboard(
    payload: RPADashboardAtomicCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.create_rpa_dashboard_atomic(db, payload)


@dashboard_router.get(
    "/",
    response_model=list[RPADashboardResponse],
    summary="Listar bots Dashboard",
)
def list_rpa_dashboards(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_rpa_dashboards(db)


@dashboard_router.get(
    "/monitoring",
    summary="Listar monitoreos Dashboard con info del job",
    description="Devuelve todos los registros de rpa_dashboard_monitoring con el job anidado.",
)
def list_dashboard_monitoring(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_dashboard_monitoring(db)


@dashboard_router.get(
    "/{id_beecker}/errors",
    response_model=list[str],
    summary="Listar errores de negocio del bot Dashboard",
)
def list_dashboard_errors(
    id_beecker: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_dashboard_errors(db, id_beecker)


@dashboard_router.patch(
    "/monitoring/{monitoring_id}",
    summary="Actualizar monitoring Dashboard",
    description="Actualiza canal, flags, agentes y unidad transaccional del monitoring.",
)
def patch_dashboard_monitoring(
    monitoring_id: str,
    payload: MonitoringPatch,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.patch_dashboard_monitoring(db, monitoring_id, payload)


@dashboard_router.delete(
    "/monitoring/{monitoring_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar monitoring Dashboard",
    description="Elimina el monitoring. Si tiene job vinculado, lo remueve de APScheduler y lo elimina en cascade.",
)
def delete_dashboard_monitoring(
    monitoring_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    rpa_dashboard_service.delete_dashboard_monitoring(db, monitoring_id)


# ═══════════════════════════════════════════════════════════════════════════════
# RPA UIPATH
# ═══════════════════════════════════════════════════════════════════════════════

@uipath_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Crear bot UiPath (atómico)",
    description=(
        "Crea en una sola transacción: cliente (o reutiliza), bot UiPath, monitoring y job (pausado). "
        "Misma lógica de reutilización que el endpoint Dashboard."
    ),
)
def create_rpa_uipath(
    payload: RPAUiPathAtomicCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.create_rpa_uipath_atomic(db, payload)


@uipath_router.get(
    "/",
    response_model=list[RPAUiPathResponse],
    summary="Listar bots UiPath",
)
def list_rpa_uipath(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_rpa_uipath(db)


@uipath_router.get(
    "/monitoring",
    summary="Listar monitoreos UiPath con info del job",
    description="Devuelve todos los registros de rpa_uipath_monitoring con el job anidado.",
)
def list_uipath_monitoring(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_uipath_monitoring(db)


@uipath_router.get(
    "/{robot_name}/errors",
    response_model=list[str],
    summary="Listar errores de negocio del bot UiPath",
)
def list_uipath_errors(
    robot_name: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_uipath_errors(db, robot_name)


@uipath_router.patch(
    "/monitoring/{monitoring_id}",
    summary="Actualizar monitoring UiPath",
)
def patch_uipath_monitoring(
    monitoring_id: str,
    payload: MonitoringPatch,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.patch_uipath_monitoring(db, monitoring_id, payload)


@uipath_router.delete(
    "/monitoring/{monitoring_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar monitoring UiPath",
    description="Elimina el monitoring. Si tiene job vinculado, lo remueve de APScheduler y lo elimina en cascade.",
)
def delete_uipath_monitoring(
    monitoring_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    rpa_dashboard_service.delete_uipath_monitoring(db, monitoring_id)