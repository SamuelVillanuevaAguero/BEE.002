"""
app/routes/monitoring/agent.py
==============================
Endpoints invoked by the BAP to notify the start and update of agent
transactions. The routes are intentionally thin: business logic lives in
app/services/agent_transaction_service.py.
"""
import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.agent import (
    AgentTransactionPayload,
    AgentTransactionUpdatePayload,
)
from app.schemas.response import ExecutionResponse
from app.services import agent_transaction_service
from app.utils.auth import verify_api_key
from app.utils.responses import R200, R202, R401, R404, R422, R500

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])


_TX_START_EXAMPLE = {
    "success": True,
    "message": "Transaction registered successfully.",
    "data": {
        "transaction_id": "12563",
        "agent_id": "f4d2c1a0-1234-5678-90ab-cdef01234567",
        "job_id": "9b8a7c6d-1111-2222-3333-444455556666",
        "status": "registered",
        "transactions_count": 1,
    },
}

_TX_UPDATE_EXAMPLE = {
    "success": True,
    "message": "Transaction updated successfully.",
    "data": {
        "transaction_id": "12563",
        "agent_id": "f4d2c1a0-1234-5678-90ab-cdef01234567",
        "job_id": "9b8a7c6d-1111-2222-3333-444455556666",
        "status": "updated",
        "transaction_status": "pending approval",
        "transactions_count": 1,
    },
}


@router.post(
    "/transaction",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Indicates the start of an agent transaction",
    description=(
        "Called by the BAP to register a new agent transaction. The transaction "
        "is appended to the `transactions` list inside `job_kwargs` of the job "
        "linked to the AgentMonitoring identified by (agent_name, account → "
        "beecker_id). Returns 404 if no AgentMonitoring matches the pair."
    ),
    responses={
        **R202(_TX_START_EXAMPLE, "Transaction registered"),
        **R401,
        **R404,
        **R422,
        **R500,
    },
)
def start_transaction(
    payload: AgentTransactionPayload,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ExecutionResponse:
    """
    POST /agent/transaction

    Synchronous handler: resolves the AgentMonitoring, mutates job_kwargs and
    mirrors the change into APScheduler. The operation is fast (single DB
    write + in-memory mutation) so no background task is needed.
    """
    logger.info(
        f"📥 [AGENT-TX] Start received | transaction_id='{payload.id}' | "
        f"agent_name='{payload.agent_name}' | account='{payload.account}'"
    )

    result = agent_transaction_service.register_agent_transaction(
        db=db, payload=payload
    )

    return ExecutionResponse(
        success=True,
        message="Transaction registered successfully.",
        data=result,
    )


@router.put(
    "/transaction/{transaction_id}",
    response_model=ExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Indicates the update of an agent transaction",
    description=(
        "Called by the BAP to update the status and details of an existing "
        "transaction. If the transaction was never registered via POST, it is "
        "upserted (created with the data from this payload). The job is "
        "located via (agent_name, account → beecker_id); returns 404 if no "
        "AgentMonitoring matches."
    ),
    responses={
        **R200(_TX_UPDATE_EXAMPLE, "Transaction updated"),
        **R401,
        **R404,
        **R422,
        **R500,
    },
)
def update_transaction(
    transaction_id: str,
    payload: AgentTransactionUpdatePayload,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ExecutionResponse:
    """
    PUT /agent/transaction/{transaction_id}

    Synchronous handler: locates the transaction by `transaction_id` inside
    the linked job's `job_kwargs["transactions"]` and updates its status and
    details. If absent, the transaction is upserted.
    """
    logger.info(
        f"📥 [AGENT-TX] Update received | transaction_id='{transaction_id}' | "
        f"agent_name='{payload.agent_name}' | account='{payload.account}' | "
        f"status='{payload.status}'"
    )

    result = agent_transaction_service.update_agent_transaction(
        db=db, transaction_id=transaction_id, payload=payload
    )

    return ExecutionResponse(
        success=True,
        message="Transaction updated successfully.",
        data=result,
    )