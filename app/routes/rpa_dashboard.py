"""
app/routes/rpa_dashboard.py

Endpoints:
    POST   /rpa-dashboard/                              → Create dashboard bot (atomic)
    GET    /rpa-dashboard/                              → List dashboard bots
    GET    /rpa-dashboard/monitoring                    → List all dashboard monitorings (+ job)
    GET    /rpa-dashboard/{id_beecker}/errors           → List bot business errors
    GET    /rpa-dashboard/{id_beecker}/monitoring       → List bot monitorings by id_beecker
    PATCH  /rpa-dashboard/monitoring/{monitoring_id}    → Update monitoring
    DELETE /rpa-dashboard/monitoring/{monitoring_id}    → Delete monitoring (+ job if linked)

    POST   /rpa-uipath/                                 → Create UiPath bot (atomic)
    GET    /rpa-uipath/                                 → List UiPath bots
    GET    /rpa-uipath/monitoring                       → List all UiPath monitorings (+ job)
    GET    /rpa-uipath/{robot_name}/errors              → List bot errors
    PATCH  /rpa-uipath/monitoring/{monitoring_id}       → Update monitoring
    DELETE /rpa-uipath/monitoring/{monitoring_id}       → Delete monitoring (+ job if linked)

NOTE: Routes with a literal segment (/monitoring) must be declared BEFORE routes
with a path parameter (/{id_beecker}/...) so that FastAPI resolves them correctly.
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

dashboard_router = APIRouter(prefix="/rpa-dashboard", tags=["RPA Dashboard"])
uipath_router = APIRouter(prefix="/rpa-uipath", tags=["RPA UiPath"])

# ── Common reusable responses ─────────────────────────────────────────────────
_R401 = {401: {"description": "Invalid or missing API Key"}}
_R404 = {404: {"description": "Resource not found"}}
_R422 = {422: {"description": "Payload validation error"}}
_R500 = {500: {"description": "Internal server error"}}
_COMMON = {**_R401, **_R422, **_R500}


# ═══════════════════════════════════════════════════════════════════════════════
# RPA DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@dashboard_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Create Dashboard bot (atomic)",
    description=(
        "Creates in a single transaction: client (or reuses existing), Dashboard bot, "
        "monitoring and job (paused). If the bot already exists by id_beecker, it is reused."
    ),
    responses={
        201: {"description": "Bot and monitoring created successfully"},
        **_COMMON,
    },
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
    summary="List Dashboard bots",
    responses={
        200: {"description": "List of registered bots"},
        **_COMMON,
    },
)
def list_rpa_dashboards(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_rpa_dashboards(db)


@dashboard_router.get(
    "/monitoring",
    summary="List all Dashboard monitorings with job info",
    description="Returns all rpa_dashboard_monitoring records with the nested job.",
    responses={
        200: {"description": "List of monitorings with jobs"},
        **_COMMON,
    },
)
def list_dashboard_monitoring(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_dashboard_monitoring(db)


@dashboard_router.get(
    "/{id_beecker}/errors",
    response_model=list[str],
    summary="List Dashboard bot business errors",
    responses={
        200: {"description": "List of configured business errors"},
        **_R404,
        **_COMMON,
    },
)
def list_dashboard_errors(
    id_beecker: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_dashboard_errors(db, id_beecker)


@dashboard_router.get(
    "/{id_beecker}/monitoring",
    summary="List Dashboard bot monitorings by id_beecker",
    description=(
        "Returns all rpa_dashboard_monitoring records linked to the bot. "
        "A single bot can have N configurations (different channels, jobs, and agents)."
    ),
    responses={
        200: {"description": "List of bot monitorings with jobs"},
        **_R404,
        **_COMMON,
    },
)
def list_monitoring_by_id_beecker(
    id_beecker: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_monitoring_by_id_beecker(db, id_beecker)


@dashboard_router.patch(
    "/monitoring/{monitoring_id}",
    summary="Update Dashboard monitoring",
    description="Updates the channel, flags, agents, and transactional unit of the monitoring.",
    responses={
        200: {"description": "Monitoring updated"},
        **_R404,
        **_COMMON,
    },
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
    summary="Delete Dashboard monitoring",
    description=(
        "Deletes the monitoring. If it has a linked job, "
        "it removes it from APScheduler and deletes it in cascade."
    ),
    responses={
        204: {"description": "Monitoring deleted successfully"},
        **_R404,
        **_COMMON,
    },
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
    summary="Create UiPath bot (atomic)",
    description=(
        "Creates in a single transaction: client (or reuses existing), UiPath bot, "
        "monitoring and job (paused). If the bot already exists by uipath_robot_name, it is reused."
    ),
    responses={
        201: {"description": "Bot and monitoring created successfully"},
        **_COMMON,
    },
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
    summary="List UiPath bots",
    responses={
        200: {"description": "List of registered UiPath bots"},
        **_COMMON,
    },
)
def list_rpa_uipath(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_rpa_uipath(db)


@uipath_router.get(
    "/monitoring",
    summary="List all UiPath monitorings with job info",
    description="Returns all rpa_uipath_monitoring records with the nested job.",
    responses={
        200: {"description": "List of monitorings with jobs"},
        **_COMMON,
    },
)
def list_uipath_monitoring(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_uipath_monitoring(db)


@uipath_router.get(
    "/{robot_name}/errors",
    response_model=list[str],
    summary="List UiPath bot business errors",
    responses={
        200: {"description": "List of configured business errors"},
        **_R404,
        **_COMMON,
    },
)
def list_uipath_errors(
    robot_name: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_uipath_errors(db, robot_name)


@uipath_router.patch(
    "/monitoring/{monitoring_id}",
    summary="Update UiPath monitoring",
    description="Updates the channel, flags, agents, and transactional unit of the monitoring.",
    responses={
        200: {"description": "Monitoring updated"},
        **_R404,
        **_COMMON,
    },
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
    summary="Delete UiPath monitoring",
    description=(
        "Deletes the monitoring. If it has a linked job, "
        "it removes it from APScheduler and deletes it in cascade."
    ),
    responses={
        204: {"description": "Monitoring deleted successfully"},
        **_R404,
        **_COMMON,
    },
)
def delete_uipath_monitoring(
    monitoring_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    rpa_dashboard_service.delete_uipath_monitoring(db, monitoring_id)