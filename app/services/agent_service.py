"""
app/services/agent_service.py
Service layer for AgentMonitoring CRUD operations using the Repository pattern.
"""
import logging
import uuid
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.scheduler import scheduler
from app.models.agent_monitoring import AgentMonitoring
from app.models.job import Job, JobStatus, TriggerType
from app.repositories.agent_repository import AgentMonitoringRepository
from app.repositories.job_repository import JobRepository
from app.schemas.agent import AgentMonitoringCreate, AgentMonitoringUpdate
from app.services.job_service import _build_trigger, _wrapped_task

logger = logging.getLogger(__name__)

_DEFAULT_TRIGGER_TYPE = TriggerType.interval
_DEFAULT_TRIGGER_ARGS = {"hours": 1}


def _transaction_unit_str(tu) -> str:
    """
    Serialize TransactionUnit to 'plural|singular' format.
    Matches the convention used across RPA dashboard services.

    Example: TransactionUnit(plural="Transacciones", singular="Transacción")
             → "Transacciones|Transacción"
    """
    if hasattr(tu, "plural"):
        return f"{tu.plural}|{tu.singular}"
    # Already a dict (e.g. coming from model_dump in update)
    return f"{tu['plural']}|{tu['singular']}"


def _create_paused_job(
    job_repo: JobRepository,
    job_id: str,
    name: str,
    task_path: str,
    trigger_type: TriggerType,
    trigger_args: dict,
    job_kwargs: dict,
) -> Job:
    """
    Register a job in APScheduler (paused immediately) and persist it
    in the jobs table with status=paused.

    Raises:
        ValueError: If trigger_args are invalid (propagated from APScheduler).
    """
    trigger = _build_trigger(trigger_type, trigger_args)

    scheduler.add_job(
        func=_wrapped_task,
        trigger=trigger,
        id=job_id,
        name=name,
        kwargs={
            "job_id": job_id,
            "task_path": task_path,
            **job_kwargs,
        },
        replace_existing=True,
    )
    scheduler.pause_job(job_id)

    db_job = job_repo.create({
        "id": job_id,
        "name": name,
        "task_path": task_path,
        "trigger_type": trigger_type,
        "trigger_args": trigger_args,
        "job_kwargs": job_kwargs,
        "status": JobStatus.paused,
        "next_run_time": None,
        "description": "Job - Auto create",
    })

    logger.info(
        f"⏸  Job created (paused) | id='{job_id}' | name='{name}' | "
        f"trigger={trigger_type}({trigger_args})"
    )
    return db_job


class AgentMonitoringService:
    """
    Service for AgentMonitoring CRUD operations.
    Encapsulates business logic and delegates persistence to
    AgentMonitoringRepository and JobRepository.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = AgentMonitoringRepository(db)
        self.job_repo = JobRepository(db)

    # ------------------------------------------------------------------
    # Create  (atomic: job + agent in a single transaction)
    # ------------------------------------------------------------------

    def create(self, payload: AgentMonitoringCreate) -> AgentMonitoring:
        """
        Atomically create a Job and an AgentMonitoring record.

        Steps:
          1. Validate no duplicate (beecker_id + agent_name).
          2. Resolve job definition from payload or apply hourly default.
          3. Register job in APScheduler (paused) + persist in jobs table.
          4. Persist AgentMonitoring linked to the new job_id.
          5. Return the record with job eagerly loaded.

        Raises:
            HTTPException 409: Duplicate agent for the same beecker_id.
            HTTPException 400: Invalid trigger_args.
            HTTPException 500: Unexpected error.
        """
        # 1. Duplicate check
        existing = self.repo.get_by_agent_name(payload.agent_name)
        if any(a.beecker_id == payload.beecker_id for a in existing):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"AgentMonitoring '{payload.agent_name}' already exists "
                    f"for beecker_id '{payload.beecker_id}'."
                ),
            )

        # 2. Resolve job definition
        job_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())

        if payload.job is not None:
            job_name = payload.job.name
            task_path = payload.job.task_path
            trigger_type = payload.job.trigger_type
            trigger_args = payload.job.trigger_args
            job_kwargs = {"monitoring_id": agent_id}
        else:
            job_name = f"JOB-{payload.beecker_id}-{payload.agent_name}"
            task_path = "app.tasks.agent_tasks:scheduled_agent_status"
            trigger_type = _DEFAULT_TRIGGER_TYPE
            trigger_args = _DEFAULT_TRIGGER_ARGS
            job_kwargs = {"monitoring_id": agent_id}

        try:
            # 3. Register + persist job
            _create_paused_job(
                job_repo=self.job_repo,
                job_id=job_id,
                name=job_name,
                task_path=task_path,
                trigger_type=trigger_type,
                trigger_args=trigger_args,
                job_kwargs=job_kwargs,
            )

            # 4. Persist agent monitoring
            self.repo.create({
                "id": agent_id,
                "agent_name": payload.agent_name,
                "beecker_id": payload.beecker_id,
                "platform_id": payload.platform_id,
                "platform": payload.platform,
                "transaction_unit": _transaction_unit_str(payload.transaction_unit),
                "manage_flags": payload.manage_flags,
                "roc_agents": payload.roc_agents,
                "SLA_time": payload.SLA_time,
                "error_status": payload.error_status,
                "completed_status": payload.completed_status,
                "cut_off_time": payload.cut_off_time,
                "slack_channel_id": payload.slack_channel_id,
                "transactions_exceeded_sla": None,
                "transactions_with_errors": None,
                "slack_message_id": None,
                "job_id": job_id,
            })

            logger.info(
                f"✅ AgentMonitoring created | id='{agent_id}' | "
                f"agent='{payload.agent_name}' | beecker_id='{payload.beecker_id}' | "
                f"job_id='{job_id}'"
            )

            # 5. Return with job eagerly loaded
            return self.repo.get_by_id_with_job(agent_id)

        except HTTPException:
            raise
        except ValueError as e:
            self._cleanup_aps_job(job_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            self._cleanup_aps_job(job_id)
            logger.error(f"Error creating AgentMonitoring: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unexpected error while creating agent monitoring.",
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_id(self, agent_id: str) -> AgentMonitoring:
        """
        Get an agent monitoring record by its UUID (with job loaded).

        Raises:
            HTTPException 404: If not found.
        """
        agent = self.repo.get_by_id_with_job(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AgentMonitoring '{agent_id}' not found.",
            )
        return agent

    def list_all(self) -> List[AgentMonitoring]:
        """List all agent monitoring configurations (job eagerly loaded)."""
        return self.repo.list_all_with_job()

    def get_by_beecker_id(self, beecker_id: str) -> List[AgentMonitoring]:
        """
        Get all agents for a Beecker client ID.
        Returns empty list if none found (not a 404).
        """
        return self.repo.get_by_beecker_id(beecker_id)

    def get_by_agent_name(self, agent_name: str) -> List[AgentMonitoring]:
        """
        Get all agents matching a name (case-insensitive).
        Returns empty list if none found (not a 404).
        """
        return self.repo.get_by_agent_name(agent_name)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, agent_id: str, payload: AgentMonitoringUpdate) -> AgentMonitoring:
        """
        Partially update an agent monitoring configuration.

        transaction_unit is serialized to 'plural|singular' when provided.
        Only explicitly set fields are applied (exclude_unset=True).

        Raises:
            HTTPException 404: Record not found.
            HTTPException 500: Unexpected DB error.
        """
        agent = self.get_by_id(agent_id)

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return agent  # No-op

        try:
            if "transaction_unit" in updates and updates["transaction_unit"] is not None:
                updates["transaction_unit"] = _transaction_unit_str(
                    updates["transaction_unit"]
                )

            for field, value in updates.items():
                setattr(agent, field, value)

            self.db.commit()
            self.db.refresh(agent)

            logger.info(
                f"✏️  AgentMonitoring updated | id='{agent_id}' | "
                f"fields={list(updates.keys())}"
            )
            return agent
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating AgentMonitoring '{agent_id}': {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unexpected error while updating agent monitoring.",
            )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, agent_id: str) -> None:
        """
        Delete an agent monitoring configuration by its UUID.

        The APScheduler job is removed first (best-effort), then the DB
        cascade handles the jobs table row via the relationship.

        Raises:
            HTTPException 404: Record not found.
            HTTPException 500: Unexpected error.
        """
        agent = self.get_by_id(agent_id)
        job_id = agent.job_id

        try:
            self._cleanup_aps_job(job_id)
            self.repo.delete(agent_id)
            logger.info(
                f"🗑️  AgentMonitoring deleted | id='{agent_id}' | job_id='{job_id}'"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting AgentMonitoring '{agent_id}': {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unexpected error while deleting agent monitoring.",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cleanup_aps_job(self, job_id: Optional[str]) -> None:
        """Remove a job from APScheduler silently (used on rollback / delete)."""
        if not job_id:
            return
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass