import logging
from fastapi import APIRouter, Depends, status, HTTPException
from app.schemas.rpa import RPAExecutionPayload, RPAExecutionUpdatePayload
from app.schemas.response import ExecutionResponse
from app.utils.auth import verify_api_key
from app.services.monitoring_service import MonitoringAgent
from app.services.config.rpa_config import RPAConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rpa", tags=["RPA"])


# routes/debug.py (solo para pruebas)
@router.get("/debug/session")
async def session_status():
    from app.utils.session_manager import beecker_session
    s = beecker_session
    s._init_state()
    return {
        "has_token":   s._access_token is not None,
        "expires_at":  s._expires_at.isoformat() if s._expires_at else None,
        "is_valid":    s._is_valid(),
        "minutes_left": int(
            (s._expires_at - __import__('datetime').datetime.now(
                tz=__import__('datetime').timezone.utc
            )).total_seconds() / 60
        ) if s._expires_at else None,
    }

@router.post(
    "/test",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Indicates the start of an RPA execution",
)
async def start_execution(
    payload: RPAExecutionPayload,
) -> ExecutionResponse:
    config = RPAConfig(
        bot_name=payload.bot_name,
        process_name="Proceso de prueba",
    )

    try:
        monitoring = MonitoringAgent()
        await monitoring.load_config(config)
        await monitoring.send_initial_rpa(bot_id=payload.bot_id)
    except Exception as e:
        logger.error(f"Error al iniciar monitoreo RPA: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    return ExecutionResponse(
        success=True,
        message=f"Monitoreo iniciado para '{payload.bot_name}'.",
        data={
            "id": payload.id,
            "bot_name": payload.bot_name,
            "bot_id": payload.bot_id,
            "status": "started",
        },
    )


@router.put(
    "/test/{execution_id}",
    response_model=ExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Indicates the update of an RPA execution",
)
def update_execution(
    execution_id: str,
    payload: RPAExecutionUpdatePayload,
    api_key: str = Depends(verify_api_key),
) -> ExecutionResponse:
    return ExecutionResponse(
        success=True,
        message=f"Execution of process '{payload.bot_name}' updated successfully.",
        data={
            "id": execution_id,
            "bot_name": payload.bot_name,
            "bot_id": payload.bot_id,
            "status": "updated",
        },
    )