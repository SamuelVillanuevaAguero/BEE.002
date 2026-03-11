"""
app/routes/monitoring/rpa.py
=============================
Endpoints para recibir notificaciones de inicio y fin de ejecuciones RPA
desde la plataforma Beecker (BAP).
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.rpa import RPAExecutionPayload, RPAExecutionUpdatePayload
from app.schemas.response import ExecutionResponse
from app.services import rpa_orchestration_service
from app.utils.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rpa", tags=["RPA"])


# ── POST /rpa/execution ───────────────────────────────────────────────────────

@router.post(
    "/execution",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Notifica el inicio de una ejecución RPA",
    description=(
        "Recibe el payload de inicio desde el BAP. "
        "Envía un mensaje de inicio a Slack según la configuración del bot en la DB."
    ),
)
async def start_execution(
    payload: RPAExecutionPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ExecutionResponse:
    """
    Inicio de ejecución → send_initial_rpa()

    El proceso corre en background para responder 202 inmediatamente.
    """
    background_tasks.add_task(
        rpa_orchestration_service.handle_execution_start,
        db=db,
        run_id=payload.id,
        bot_id=payload.bot_id,
    )

    logger.info(f"📥 [START] Recibido | bot_id={payload.bot_id} | run_id={payload.id}")

    return ExecutionResponse(
        success=True,
        message=f"Inicio de ejecución recibido para '{payload.bot_name}'.",
        data={
            "id": payload.id,
            "bot_name": payload.bot_name,
            "bot_id": payload.bot_id,
            "status": "started",
        },
    )


# ── PUT /rpa/execution/{execution_id} ────────────────────────────────────────

@router.put(
    "/execution/{execution_id}",
    response_model=ExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Notifica el fin de una ejecución RPA",
    description=(
        "Recibe el payload de finalización desde el BAP. "
        "Consulta el status completo en Beecker y envía notificación de fin a Slack."
    ),
)
async def end_execution(
    execution_id: str,
    payload: RPAExecutionUpdatePayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ExecutionResponse:
    """
    Fin de ejecución → send_status_rpa()

    execution_id corresponde al run_id numérico de Beecker.
    El proceso corre en background para responder 200 inmediatamente.
    """
    background_tasks.add_task(
        rpa_orchestration_service.handle_execution_end,
        db=db,
        run_id=execution_id,
        bot_id=payload.bot_id,
    )

    logger.info(
        f"📥 [END] Recibido | bot_id={payload.bot_id} | "
        f"run_id={execution_id} | status={payload.status}"
    )

    return ExecutionResponse(
        success=True,
        message=f"Fin de ejecución recibido para '{payload.bot_name}'.",
        data={
            "id": execution_id,
            "bot_name": payload.bot_name,
            "bot_id": payload.bot_id,
            "status": payload.status,
        },
    )