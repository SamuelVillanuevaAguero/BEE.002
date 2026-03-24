"""
app/routes/rpa_dashboard.py

Endpoints:
    POST   /rpa-dashboard/                              → Create dashboard bot (atomic)
    GET    /rpa-dashboard/                              → List dashboard bots
    GET    /rpa-dashboard/monitoring                    → List all monitorings (+ job)
    GET    /rpa-dashboard/{id_beecker}/errors           → List business errors of the bot
    GET    /rpa-dashboard/{id_beecker}/monitoring       → List monitorings of the bot by id_beecker
    PATCH  /rpa-dashboard/monitoring/{monitoring_id}    → Update monitoring
    DELETE /rpa-dashboard/monitoring/{monitoring_id}    → Delete monitoring (+ job if linked)

    POST   /rpa-uipath/                                 → Create UiPath bot (atomic)
    GET    /rpa-uipath/                                 → List UiPath bots
    GET    /rpa-uipath/monitoring                       → List all UiPath monitorings (+ job)
    GET    /rpa-uipath/{robot_name}/errors              → List bot errors
    PATCH  /rpa-uipath/monitoring/{monitoring_id}       → Update monitoring
    DELETE /rpa-uipath/monitoring/{monitoring_id}       → Delete monitoring (+ job if linked)

NOTE: Routes with a literal segment (/monitoring) must be declared BEFORE routes
with a parameter (/{id_beecker}/...) so that FastAPI resolves them correctly.
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
    MonitoringResponse,
)
from app.services import rpa_dashboard_service
from app.utils.auth import verify_api_key
from app.utils.responses import (
    R200, R200_list, R200_str_list, R201, R204,
    R404, COMMON,
)

logger = logging.getLogger(__name__)

dashboard_router = APIRouter(prefix="/rpa-dashboard", tags=["RPA Dashboard"])
uipath_router = APIRouter(prefix="/rpa-uipath", tags=["RPA UiPath"])


# ── Reusable examples ────────────────────────────────────────────────────────

_MONITORING_EXAMPLE = {
    "id": "a1b2c3d4-0000-0000-0000-000000000001",
    "monitor_type": "bee_informa",
    "slack_channel": "#roc-notificaciones",
    "transaction_unit": "Facturas|Factura",
    "roc_agents": ["agente@empresa.com"],
    "manage_flags": {"start_active": True, "end_active": True},
    "id_scheduler_job": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "job": {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "name": "bee-informa | AEC.001",
        "status": "paused",
        "trigger_type": "interval",
        "trigger_args": {"minutes": 5},
        "next_run_time": None,
    },
}

_ATOMIC_CREATE_EXAMPLE = {
    "client": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "client_name": "Empresa ABC",
    },
    "rpa": {
        "id_beecker": "AEC.001",
        "id_dashboard": "114",
        "process_name": "Accounts Receivable Automation",
        "platform": "beecker",
        "id_client": "550e8400-e29b-41d4-a716-446655440000",
        "business_errors": ["Business Exception"],
    },
    "monitoring": _MONITORING_EXAMPLE,
    "job": {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "name": "bee-informa | AEC.001",
        "status": "paused",
        "trigger_type": "interval",
        "trigger_args": {"minutes": 5},
        "next_run_time": None,
    },
}

_DASHBOARD_BOT_EXAMPLE = {
    "id_beecker": "AEC.001",
    "id_dashboard": "114",
    "process_name": "Accounts Receivable Automation",
    "platform": "beecker",
    "id_client": "550e8400-e29b-41d4-a716-446655440000",
    "business_errors": ["Business Exception", "Application Exception"],
}

_UIPATH_BOT_EXAMPLE = {
    "uipath_robot_name": "Robot_Ventas_01",
    "id_beecker": "VNT.001",
    "beecker_name": "Bot Ventas",
    "framework": "REFramework",
    "id_client": "550e8400-e29b-41d4-a716-446655440000",
    "business_errors": ["Business Rule Violation"],
}


# ═══════════════════════════════════════════════════════════════════════════════
# RPA DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@dashboard_router.post(
    "/",
    response_model=AtomicCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Dashboard bot (atomic)",
    description=(
        "Creates in a single transaction: client (or reuses existing), Dashboard bot, "
        "monitoring and job (paused). If the bot already exists by id_beecker, it is reused."
    ),
    responses={
        **R201(_ATOMIC_CREATE_EXAMPLE, "Bot and monitoring created successfully"),
        **COMMON,
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
        **R200_list([_DASHBOARD_BOT_EXAMPLE], "List of registered bots"),
        **COMMON,
    },
)
def list_rpa_dashboards(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_rpa_dashboards(db)


@dashboard_router.get(
    "/monitoring",
    response_model=list[MonitoringResponse],
    summary="List all Dashboard monitorings with job info",
    description="Returns all rpa_dashboard_monitoring records with the nested job.",
    responses={
        **R200_list([_MONITORING_EXAMPLE], "List of monitorings with jobs"),
        **COMMON,
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
    summary="List business errors of the Dashboard bot",
    responses={
        **R200_str_list(
            ["Business Exception", "Application Exception"],
            "List of configured business errors",
        ),
        **R404,
        **COMMON,
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
    response_model=list[MonitoringResponse],
    summary="List monitorings of a Dashboard bot by id_beecker",
    description=(
        "Returns all rpa_dashboard_monitoring records associated with the bot. "
        "A single bot can have N configurations (different channels, jobs and agents)."
    ),
    responses={
        **R200_list([_MONITORING_EXAMPLE], "List of bot monitorings with jobs"),
        **R404,
        **COMMON,
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
    response_model=MonitoringResponse,
    summary="Update Dashboard monitoring",
    description="Updates the channel, flags, agents and transactional unit of the monitoring.",
    responses={
        **R200(_MONITORING_EXAMPLE, "Monitoring updated"),
        **R404,
        **COMMON,
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
        **R204,
        **R404,
        **COMMON,
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
    response_model=AtomicCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create UiPath bot (atomic)",
    description=(
        "Creates in a single transaction: client (or reuses existing), UiPath bot, "
        "monitoring and job (paused). If the bot already exists by uipath_robot_name, it is reused."
    ),
    responses={
        **R201(_ATOMIC_CREATE_EXAMPLE, "Bot and monitoring created successfully"),
        **COMMON,
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
        **R200_list([_UIPATH_BOT_EXAMPLE], "List of registered UiPath bots"),
        **COMMON,
    },
)
def list_rpa_uipath(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    return rpa_dashboard_service.list_rpa_uipath(db)


@uipath_router.get(
    "/monitoring",
    response_model=list[MonitoringResponse],
    summary="List all UiPath monitorings with job info",
    description="Returns all rpa_uipath_monitoring records with the nested job.",
    responses={
        **R200_list([_MONITORING_EXAMPLE], "List of monitorings with jobs"),
        **COMMON,
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
    summary="List business errors of the UiPath bot",
    responses={
        **R200_str_list(
            ["Business Rule Violation"],
            "List of configured business errors",
        ),
        **R404,
        **COMMON,
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
    response_model=MonitoringResponse,
    summary="Update UiPath monitoring",
    description="Updates the channel, flags, agents and transactional unit of the monitoring.",
    responses={
        **R200(_MONITORING_EXAMPLE, "Monitoring updated"),
        **R404,
        **COMMON,
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
        **R204,
        **R404,
        **COMMON,
    },
)
def delete_uipath_monitoring(
    monitoring_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    rpa_dashboard_service.delete_uipath_monitoring(db, monitoring_id)