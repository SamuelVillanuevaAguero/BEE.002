"""
app/repositories/agent_repository.py
Repository pattern implementation for AgentMonitoring model.
Centralizes all database operations for agent monitoring entities.
"""
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.agent_monitoring import AgentMonitoring
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class AgentMonitoringRepository(BaseRepository[AgentMonitoring]):
    """
    Repository for AgentMonitoring model.
    Provides specialized query methods for agent monitoring operations.
    """

    def __init__(self, db: Session):
        """Initialize AgentMonitoringRepository with AgentMonitoring model."""
        super().__init__(db, AgentMonitoring)


    def list_all(self) -> List[AgentMonitoring]:
        """
        List all agent monitoring configurations ordered by agent_name.

        Returns:
            List of AgentMonitoring instances
        """
        stmt = select(AgentMonitoring).order_by(AgentMonitoring.agent_name)
        return self.db.execute(stmt).scalars().all()

    def list_all_with_job(self) -> List[AgentMonitoring]:
        """
        List all agent monitoring configurations with their job eagerly loaded.

        Returns:
            List of AgentMonitoring instances with job data preloaded
        """
        stmt = (
            select(AgentMonitoring)
            .options(joinedload(AgentMonitoring.job))
            .order_by(AgentMonitoring.agent_name)
        )
        return self.db.execute(stmt).scalars().unique().all()

    def get_by_id_with_job(self, agent_id: str) -> Optional[AgentMonitoring]:
        """
        Get an agent monitoring by its ID with job eagerly loaded.

        Args:
            agent_id: The agent monitoring UUID

        Returns:
            The AgentMonitoring instance with job data or None if not found
        """
        stmt = (
            select(AgentMonitoring)
            .where(AgentMonitoring.id == agent_id)
            .options(joinedload(AgentMonitoring.job))
        )
        return self.db.execute(stmt).scalars().unique().first()

    def get_by_beecker_id(self, beecker_id: str) -> List[AgentMonitoring]:
        """
        Get all agent monitoring configurations for a specific Beecker client.

        Args:
            beecker_id: The Beecker client ID (e.g., "PML.001")

        Returns:
            List of AgentMonitoring instances for that client
        """
        stmt = (
            select(AgentMonitoring)
            .where(AgentMonitoring.beecker_id == beecker_id)
            .order_by(AgentMonitoring.agent_name)
        )
        return self.db.execute(stmt).scalars().all()

    def get_by_agent_name(self, agent_name: str) -> List[AgentMonitoring]:
        """
        Get all agent monitoring configurations matching a given agent name.
        Comparison is case-insensitive.

        Args:
            agent_name: The agent name (e.g., "Pedro")

        Returns:
            List of AgentMonitoring instances with that name
        """
        stmt = (
            select(AgentMonitoring)
            .where(AgentMonitoring.agent_name.ilike(agent_name))
            .order_by(AgentMonitoring.beecker_id)
        )
        return self.db.execute(stmt).scalars().all()

    def get_by_job_id(self, job_id: str) -> Optional[AgentMonitoring]:
        """
        Get an agent monitoring configuration by its associated job ID.

        Args:
            job_id: The scheduler job ID

        Returns:
            The AgentMonitoring instance or None if not found
        """
        stmt = select(AgentMonitoring).where(AgentMonitoring.job_id == job_id)
        return self.db.execute(stmt).scalars().first()

    def exists_by_id(self, agent_id: str) -> bool:
        """
        Check if an agent monitoring record exists by its UUID.

        Args:
            agent_id: The agent monitoring UUID

        Returns:
            True if exists, False otherwise
        """
        return self.exists(agent_id)