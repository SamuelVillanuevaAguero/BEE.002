from fastapi import APIRouter, Depends, status
from app.schemas.response import ExecutionResponse
from app.utils.auth import verify_api_key
from app.schemas.agent import AgentTransactionPayload, AgentTransactionUpdatePayload

router = APIRouter(prefix="/agent", tags=["Agent"])

@router.post(
    "/transaction",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Indicates the start of an agent transaction",
    description=(
        "This endpoint is called by the BAP to indicate the start of a new transaction."
    ),
)
def start_transaction(
    payload: AgentTransactionPayload,
    api_key: str = Depends(verify_api_key),
) -> ExecutionResponse:
    """
    POST /agent/transaction
    Indicates the start of an agent transaction.
    """
    return ExecutionResponse(
        success=True,
        message="Transaction registered successfully.",
        data={
            "status": "registered",
        },
    )

@router.put(
    "/transaction/{transaction_id}",
    response_model=ExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Indicates the update of an agent transaction",
    description=(
        "This endpoint is called by the BAP to indicate the update of a transaction."
    ),
)
def update_transaction(
    transaction_id: str,
    payload: AgentTransactionUpdatePayload,
    api_key: str = Depends(verify_api_key),
) -> ExecutionResponse:
    """
    PUT /agent/transaction/{transaction_id}
    Indicates the update of an agent transaction.
    """
    return ExecutionResponse(
        success=True,
        message="Transaction updated successfully.",
        data={
            "status": "updated",
        },
    )