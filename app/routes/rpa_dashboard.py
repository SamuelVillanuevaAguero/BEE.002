"""
app/routes/rpa_dashboard.py
=============================
Endpoints para administración de RPA Dashboards en la BD.

Rutas disponibles:
    POST /rpa-dashboard/   → Crea un RPA Dashboard completo (atómico)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.rpa_dashboard import RPADashboardCreate, RPADashboardResponse
from app.services import rpa_dashboard_service
from app.utils.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rpa-dashboard", tags=["RPA Dashboard"])


@router.post(
    "/",
    response_model=RPADashboardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un RPA Dashboard",
    description=(
        "Crea un RPA Dashboard completo en una sola transacción atómica. "
        "Registra el bot en `rpa_dashboard`, su configuración operativa en "
        "`rpa_dashboard_client` y los errores de negocio en "
        "`rpa_dashboard_business_error` (si se proporcionan). "
        "**No asigna job** — usa el endpoint de vinculación para eso "
        "(solo aplica a bots con tipo `bee-observa`)."
    ),
)
def create_rpa_dashboard(
    payload: RPADashboardCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> RPADashboardResponse:
    """
    POST /rpa-dashboard/

    Crea en una sola transacción:
        1. rpa_dashboard
        2. rpa_dashboard_client
        3. rpa_dashboard_business_error (uno por cada string en business_errors)

    Errores posibles:
        - 409 Conflict   → id_rpa ya existe en la BD.
        - 404 Not Found  → id_client no existe en la tabla client.
        - 500            → Error inesperado de BD.
    """
    rpa = rpa_dashboard_service.create_rpa_dashboard_full(db, payload)

    # Construir respuesta manualmente para incluir la relación client
    # (evita múltiples queries lazy y acopla solo lo necesario)
    client_rel = next(
        (c for c in rpa.clients if c.id_client == payload.id_client),
        None,
    )
    if client_rel is None:
        logger.error(
            f"No se encontró rpa_dashboard_client tras el commit para id_rpa='{rpa.id_rpa}'"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar la configuración del cliente tras la creación.",
        )

    return RPADashboardResponse(
        id_rpa=rpa.id_rpa,
        id_beecker=rpa.id_beecker,
        process_name=rpa.process_name,
        platform=rpa.platform,
        client={
            "id_client": client_rel.id_client,
            "monitor_type": client_rel.monitor_type,
            "transaction_unit": client_rel.transaction_unit,
            "slack_channel": client_rel.slack_channel,
            "roc_agents": client_rel.roc_agents,
        },
        business_errors=rpa.business_errors,
    )