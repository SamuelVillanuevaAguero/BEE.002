from fastapi import APIRouter, Depends, status
from app.schemas.rpa import RPAExecutionPayload, RPAExecutionUpdatePayload
from app.schemas.response import ExecutionResponse
from app.utils.auth import verify_api_key

router = APIRouter(prefix="/rpa", tags=["RPA"])

@router.post(
    "/execution",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Indicates the start of an RPA execution",
    description=(
        "This endpoint is called by the BAP to indicate the start of a new RPA execution."
    ),
)
def start_execution(
    payload: RPAExecutionPayload,
    api_key: str = Depends(verify_api_key),
) -> ExecutionResponse:
    """
    POST /rpa/execution
    Indicates the start of an RPA execution.
    """
    # TODO: integrate with RPA orchestration service
    print(payload)
    return ExecutionResponse(
        success=True,
        message=f"Execution of process '{payload.bot_name}' started successfully.",
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
    summary="Indicates the update of an RPA execution",
    description=(
        "This endpoint is called by the BAP to indicate the update of an RPA execution."
    ),
)
def update_execution(
    execution_id: str,
    payload: RPAExecutionUpdatePayload,
    api_key: str = Depends(verify_api_key),
) -> ExecutionResponse:
    """
    PUT /rpa/execution
    Indicates the update of an RPA execution.
    """
    # TODO: integrate with RPA orchestration service
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