"""
app/services/agent_transaction_service.py
=========================================
Business logic for agent transaction lifecycle webhooks.

Handles persistence of agent transactions inside the `transactions` list
of the job's `job_kwargs`, following the same canonical pattern used by
`activate_observa_job` / `pause_observa_job`:

    1. Read current job_kwargs from DB (single source of truth).
    2. Mutate the in-memory copy.
    3. Persist via JobRepository.update_job_kwargs (DB commit).
    4. Mirror the change into APScheduler in-memory kwargs via
       aps_job.modify(kwargs=...), so the next tick sees the updated data.

job_kwargs shape after the first transaction is registered:

    {
        "monitoring_id": "c06275dc-643a-4725-82be-d1b6ad79886a",
        "transactions": [
            {
                "id": "12563",
                "agent_name": "Santiago",
                "agent_id": "20",
                "account": "SLC",
                "status": "in progress",
                "details": ""
            },
            ...
        ]
    }
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.scheduler import scheduler
from app.models.agent_monitoring import AgentMonitoring
from app.repositories.agent_repository import AgentMonitoringRepository
from app.repositories.job_repository import JobRepository
from app.schemas.agent import (
    AgentTransactionPayload,
    AgentTransactionUpdatePayload,
)

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────────────

_TRANSACTIONS_KEY = "transactions"
_INITIAL_STATUS = "in progress"
_INITIAL_DETAILS = ""


# ── Internal helpers ───────────────────────────────────────────────────────────

def _resolve_agent_or_404(
    db: Session,
    agent_name: str,
    account: str,
) -> AgentMonitoring:
    """
    Look up the AgentMonitoring record by (agent_name, account → beecker_id).

    Raises:
        HTTPException 404: When no record matches the pair.
    """
    repo = AgentMonitoringRepository(db)
    agent = repo.get_by_name_and_beecker_id(
        agent_name=agent_name, beecker_id=account
    )
    if not agent:
        logger.warning(
            f"⚠️ [AGENT-TX] AgentMonitoring not found | "
            f"agent_name='{agent_name}' | account='{account}'"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No AgentMonitoring registered for agent_name='{agent_name}' "
                f"and account='{account}'."
            ),
        )
    return agent


def _require_job_id(agent: AgentMonitoring) -> str:
    """
    Return the job_id linked to the agent. Raises 500 if missing — the schema
    requires every AgentMonitoring to be linked to a job (job_id is NOT NULL).
    """
    if not agent.job_id:
        logger.error(
            f"❌ [AGENT-TX] AgentMonitoring '{agent.id}' has no linked job_id"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"AgentMonitoring '{agent.id}' is not linked to any job. "
                f"Cannot persist transaction."
            ),
        )
    return agent.job_id


def _persist_job_kwargs(
    db: Session,
    job_id: str,
    new_kwargs: Dict[str, Any],
) -> None:
    """
    Persist `new_kwargs` in the `jobs` table and mirror them into APScheduler
    in-memory kwargs (so the next scheduled tick observes the change).

    Pattern is identical to the one used in activate_observa_job /
    pause_observa_job. If the APScheduler in-memory job is missing
    (e.g. after a container restart before recover_all_jobs runs), the DB
    write is still committed and the mirror is skipped silently.
    """
    job_repo = JobRepository(db)
    db_job = job_repo.update_job_kwargs(job_id, new_kwargs)
    if not db_job:
        # Should be unreachable: agent.job_id is FK-constrained to jobs.id
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job '{job_id}' not found while updating job_kwargs.",
        )

    aps_job = scheduler.get_job(job_id)
    if aps_job:
        aps_job.modify(kwargs={
            "job_id": job_id,
            "task_path": db_job.task_path,
            **new_kwargs,
        })
    else:
        logger.warning(
            f"⚠️ [AGENT-TX] APScheduler job not found in memory | job_id={job_id}. "
            f"DB updated; in-memory mirror skipped."
        )


def _find_transaction_index(
    transactions: List[Dict[str, Any]], transaction_id: str
) -> Optional[int]:
    """Return the index of the transaction whose 'id' matches, or None."""
    for idx, tx in enumerate(transactions):
        if str(tx.get("id")) == str(transaction_id):
            return idx
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

def register_agent_transaction(
    db: Session,
    payload: AgentTransactionPayload,
) -> Dict[str, Any]:
    """
    Handle POST /agent/transaction.

    1. Resolve the AgentMonitoring by (agent_name, account) — 404 if missing.
    2. Read the linked job's current job_kwargs.
    3. Append a new transaction with status="in progress" and details="".
       Idempotent: if a transaction with the same `id` already exists in the
       list, it is left untouched (no duplicate, no overwrite).
    4. Persist via JobRepository.update_job_kwargs + aps_job.modify.

    Returns:
        Dict suitable for ExecutionResponse.data with the persisted transaction
        and metadata for observability.
    """
    agent = _resolve_agent_or_404(db, payload.agent_name, payload.account)
    job_id = _require_job_id(agent)

    job_repo = JobRepository(db)
    db_job = job_repo.get_by_id(job_id)
    # Defensive: FK should guarantee existence
    if not db_job:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job '{job_id}' linked to agent '{agent.id}' not found.",
        )

    current_kwargs: Dict[str, Any] = dict(db_job.job_kwargs or {})
    transactions: List[Dict[str, Any]] = list(
        current_kwargs.get(_TRANSACTIONS_KEY, [])
    )

    existing_idx = _find_transaction_index(transactions, payload.id)
    if existing_idx is not None:
        logger.warning(
            f"⚠️ [AGENT-TX] Duplicate transaction ignored | "
            f"transaction_id='{payload.id}' | agent='{agent.agent_name}' | "
            f"account='{agent.beecker_id}' | job_id={job_id}"
        )
        return {
            "transaction_id": payload.id,
            "agent_id": agent.id,
            "job_id": job_id,
            "status": "duplicate_ignored",
            "transactions_count": len(transactions),
        }

    new_transaction: Dict[str, Any] = {
        "id": payload.id,
        "agent_name": payload.agent_name,
        "agent_id": payload.agent_id,
        "account": payload.account,
        "status": _INITIAL_STATUS,
        "details": _INITIAL_DETAILS,
    }
    transactions.append(new_transaction)

    new_kwargs = {**current_kwargs, _TRANSACTIONS_KEY: transactions}
    _persist_job_kwargs(db, job_id, new_kwargs)

    logger.info(
        f"🟢 [AGENT-TX] Transaction registered | "
        f"transaction_id='{payload.id}' | agent='{agent.agent_name}' | "
        f"account='{agent.beecker_id}' | job_id={job_id} | "
        f"total_transactions={len(transactions)}"
    )

    return {
        "transaction_id": payload.id,
        "agent_id": agent.id,
        "job_id": job_id,
        "status": "registered",
        "transactions_count": len(transactions),
    }


def update_agent_transaction(
    db: Session,
    transaction_id: str,
    payload: AgentTransactionUpdatePayload,
) -> Dict[str, Any]:
    """
    Handle PUT /agent/transaction/{transaction_id}.

    1. Resolve the AgentMonitoring by (agent_name, account) — 404 if missing.
    2. Read the linked job's current job_kwargs.
    3. If a transaction with the given `transaction_id` exists in the list:
         → update its `status` and `details`.
       Otherwise:
         → upsert: append a new transaction entry built from the update payload.
    4. Persist via JobRepository.update_job_kwargs + aps_job.modify.

    Returns:
        Dict suitable for ExecutionResponse.data with operation metadata.
    """
    agent = _resolve_agent_or_404(db, payload.agent_name, payload.account)
    job_id = _require_job_id(agent)

    job_repo = JobRepository(db)
    db_job = job_repo.get_by_id(job_id)
    if not db_job:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job '{job_id}' linked to agent '{agent.id}' not found.",
        )

    current_kwargs: Dict[str, Any] = dict(db_job.job_kwargs or {})
    transactions: List[Dict[str, Any]] = list(
        current_kwargs.get(_TRANSACTIONS_KEY, [])
    )

    details_value = payload.details if payload.details is not None else ""
    existing_idx = _find_transaction_index(transactions, transaction_id)

    if existing_idx is not None:
        # Update in place — preserve any field already stored that isn't
        # explicitly overwritten (forward compatibility).
        updated_tx = {
            **transactions[existing_idx],
            "id": transaction_id,
            "agent_name": payload.agent_name,
            "agent_id": payload.agent_id,
            "account": payload.account,
            "status": payload.status,
            "details": details_value,
        }
        transactions[existing_idx] = updated_tx
        operation = "updated"
    else:
        # Upsert: transaction was never registered via POST. Create it with the
        # full data from the update payload (no "in progress" default — the
        # current status from the payload is the source of truth).
        new_tx = {
            "id": transaction_id,
            "agent_name": payload.agent_name,
            "agent_id": payload.agent_id,
            "account": payload.account,
            "status": payload.status,
            "details": details_value,
        }
        transactions.append(new_tx)
        operation = "upserted"

    new_kwargs = {**current_kwargs, _TRANSACTIONS_KEY: transactions}
    _persist_job_kwargs(db, job_id, new_kwargs)

    logger.info(
        f"✏️  [AGENT-TX] Transaction {operation} | "
        f"transaction_id='{transaction_id}' | status='{payload.status}' | "
        f"agent='{agent.agent_name}' | account='{agent.beecker_id}' | "
        f"job_id={job_id} | total_transactions={len(transactions)}"
    )

    return {
        "transaction_id": transaction_id,
        "agent_id": agent.id,
        "job_id": job_id,
        "status": operation,
        "transaction_status": payload.status,
        "transactions_count": len(transactions),
    }