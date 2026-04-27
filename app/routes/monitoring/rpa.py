"""
app/routes/monitoring/rpa.py
=============================
Endpoints to receive start and end notifications of RPA executions
from the Beecker platform (BAP).
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.rpa_dashboard import RPADashboard
from app.schemas.rpa import RPAExecutionPayload, RPAExecutionUpdatePayload
from app.schemas.response import ExecutionResponse
from app.services import rpa_orchestration_service
from app.utils.auth import verify_api_key
from app.utils.responses import R202, R200, R401, R404, R422, R500, COMMON

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rpa", tags=["RPA"])

_EXECUTION_EXAMPLE = {
    "success": True,
    "message": "Execution start received for 'AEC.001'.",
    "data": {
        "id": "98765",
        "bot_name": "AEC.001",
        "bot_id": "114",
        "status": "started",
    },
}

_EXECUTION_END_EXAMPLE = {
    "success": True,
    "message": "Execution end received for 'AEC.001'.",
    "data": {
        "id": "98765",
        "bot_name": "AEC.001",
        "bot_id": "114",
        "status": "completed",
    },
}


@router.post(
    "/execution",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Notifies the start of an RPA execution",
    description=(
        "Receives the start payload from the BAP. "
        "Synchronously validates that the `bot_id` (id_dashboard) exists in rpa_dashboard. "
        "If the bot is not registered it returns 404 before queuing the process. "
        "Sends a start message to Slack according to the bot configuration."
    ),
    responses={
        **R202(_EXECUTION_EXAMPLE, "Execution start accepted and queued in background"),
        **R401,
        **R404,
        **R422,
        **R500,
    },
)
async def start_execution(
    payload: RPAExecutionPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ExecutionResponse:
    """
    1. Synchronously validates that bot_id (id_dashboard) is registered in rpa_dashboard.
    2. Queues handle_execution_start in the background and responds 202 immediately.
    """
    bot_exists = (
        db.query(RPADashboard)
        .filter(RPADashboard.id_dashboard == payload.bot_id)
        .first()
    )
    if not bot_exists:
        logger.warning(
            f"⚠️ [START] bot_id='{payload.bot_id}' not found in rpa_dashboard. "
            f"Payload rejected."
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"The bot with id_dashboard='{payload.bot_id}' is not registered. "
                f"Register it first via POST /rpa-dashboard/ before sending executions."
            ),
        )

    background_tasks.add_task(
        rpa_orchestration_service.handle_execution_start,
        db=db,
        run_id=payload.id,
        bot_id=payload.bot_id,
    )

    logger.info(f"📥 [START] Received | bot_id={payload.bot_id} | run_id={payload.id}")

    return ExecutionResponse(
        success=True,
        message=f"Execution start received for '{payload.bot_name}'.",
        data={
            "id": payload.id,
            "bot_name": payload.bot_name,
            "bot_id": payload.bot_id,
            "status": "started",
        },
    )


@router.put(
    "/execution/{execution_id}",
    response_model=ExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Notifies the end of an RPA execution",
    description=(
        "Receives the completion payload from the BAP. "
        "Queries the full status in Beecker and sends an end notification to Slack."
    ),
    responses={
        **R200(_EXECUTION_END_EXAMPLE, "Execution end received and queued in background"),
        **R401,
        **R422,
        **R500,
    },
)
async def end_execution(
    execution_id: str,
    payload: RPAExecutionUpdatePayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ExecutionResponse:
    """
    Execution end → send_status_rpa()
    execution_id corresponds to the numeric run_id from Beecker.
    The process runs in the background to respond 200 immediately.
    """
    background_tasks.add_task(
        rpa_orchestration_service.handle_execution_end,
        db=db,
        run_id=execution_id,
        bot_id=payload.bot_id,
    )

    logger.info(f"📥 [END] Received | bot_id={payload.bot_id} | run_id={execution_id}")

    return ExecutionResponse(
        success=True,
        message=f"Execution end received for '{payload.bot_name}'.",
        data={
            "id": execution_id,
            "bot_name": payload.bot_name,
            "bot_id": payload.bot_id,
            "status": payload.status,
        },
    )