"""
app/services/rpa_dashboard_service.py
=======================================
Lógica de negocio para la creación atómica de un RPA Dashboard.

Opera en una sola transacción de BD que abarca:
    1. rpa_dashboard
    2. rpa_dashboard_client
    3. rpa_dashboard_business_error  (N registros, si se proporcionan)

Si cualquier paso falla, se hace rollback completo.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.automation import (
    Client,
    RPADashboard,
    RPADashboardBusinessError,
    RPADashboardClient,
)
from app.schemas.rpa_dashboard import RPADashboardCreate

logger = logging.getLogger(__name__)


def create_rpa_dashboard_full(
    db: Session,
    payload: RPADashboardCreate,
) -> RPADashboard:
    """
    Crea un RPA Dashboard completo en una sola transacción atómica.

    Pasos:
        1. Valida que id_rpa no exista ya en rpa_dashboard.
        2. Valida que id_client exista en la tabla client.
        3. Crea el registro en rpa_dashboard.
        4. Crea el registro en rpa_dashboard_client.
        5. Crea N registros en rpa_dashboard_business_error (si aplica).
        6. Commit único — si algo falla, rollback total.

    Args:
        db:      Sesión de SQLAlchemy inyectada por FastAPI.
        payload: Datos validados por RPADashboardCreate.

    Returns:
        El objeto RPADashboard recién creado con sus relaciones cargadas.

    Raises:
        HTTPException 409: Si id_rpa ya existe.
        HTTPException 404: Si id_client no existe.
        HTTPException 500: Error inesperado de BD.
    """

    # ── 1. Verificar duplicado ────────────────────────────────────────────────
    existing = db.query(RPADashboard).filter(
        RPADashboard.id_rpa == payload.id_rpa
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un RPA Dashboard con id_rpa='{payload.id_rpa}'.",
        )

    # ── 2. Verificar que el cliente existe ────────────────────────────────────
    client = db.query(Client).filter(Client.id_client == payload.id_client).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró un cliente con id_client={payload.id_client}.",
        )

    try:
        # ── 3. Crear rpa_dashboard ────────────────────────────────────────────
        rpa = RPADashboard(
            id_rpa=payload.id_rpa,
            id_beecker=payload.id_beecker,
            process_name=payload.process_name,
            platform=payload.platform,
        )
        db.add(rpa)
        db.flush()  # Obtiene el id_rpa en la sesión sin commit todavía

        # ── 4. Crear rpa_dashboard_client ─────────────────────────────────────
        # transaction_unit se almacena como "plural|singular"
        transaction_unit_str: str | None = None
        if payload.transaction_unit:
            transaction_unit_str = (
                f"{payload.transaction_unit.plural}|{payload.transaction_unit.singular}"
            )

        client_config = RPADashboardClient(
            id_rpa=rpa.id_rpa,
            id_client=payload.id_client,
            monitor_type=payload.monitor_type,
            slack_channel=payload.slack_channel,
            transaction_unit=transaction_unit_str,
            roc_agents=payload.roc_agents,
            manage_flags=payload.manage_flags.model_dump() if payload.manage_flags else None,
            id_scheduler_job=None,               # Sin job en este endpoint
        )
        db.add(client_config)

        # ── 5. Crear errores de negocio ───────────────────────────────────────
        if payload.business_errors:
            for error_msg in payload.business_errors:
                db.add(RPADashboardBusinessError(
                    id_rpa=rpa.id_rpa,
                    error_message=error_msg.strip(),
                ))

        # ── 6. Commit único ───────────────────────────────────────────────────
        db.commit()
        db.refresh(rpa)

        logger.info(
            f"✅ RPA Dashboard creado | id_rpa='{rpa.id_rpa}' | "
            f"proceso='{rpa.process_name}' | cliente={payload.id_client} | "
            f"monitor={payload.monitor_type.value}"
        )
        return rpa

    except IntegrityError as e:
        db.rollback()
        logger.error(f"IntegrityError al crear RPA Dashboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Error de integridad en BD. Verifica que los IDs sean únicos y las FKs existan.",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error inesperado al crear RPA Dashboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear el RPA Dashboard.",
        )