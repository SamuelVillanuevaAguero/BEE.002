"""
app/repositories/automation_repository.py
Repository pattern implementations for Automation models.
Centralizes all database operations for automation-related entities.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.automation import (
    RPADashboard,
    RPADashboardMonitoring,
    RPAUiPath,
    RPAUiPathMonitoring,
)
from .base_repository import BaseRepository

class RPADashboardRepository(BaseRepository[RPADashboard]):
    """
    Repository for RPADashboard model.
    Provides specialized query methods for RPA Dashboard operations.
    """

    def __init__(self, db: Session):
        """Initialize RPADashboardRepository with RPADashboard model."""
        super().__init__(db, RPADashboard)

    def list_all_with_client(self) -> List[RPADashboard]:
        """
        List all RPA dashboards with their client information eagerly loaded.

        Returns:
            List of RPADashboard instances with client data preloaded
        """
        stmt = select(RPADashboard).options(
            joinedload(RPADashboard.client)
        ).order_by(RPADashboard.id_beecker)
        return self.db.execute(stmt).scalars().unique().all()

    def get_by_id_beecker(self, id_beecker: str) -> Optional[RPADashboard]:
        """
        Get an RPA dashboard by its Beecker ID.

        Args:
            id_beecker: The Beecker ID (e.g., "AEC.001")

        Returns:
            The RPADashboard instance or None if not found
        """
        return self.db.get(RPADashboard, id_beecker)

    def get_by_id_beecker_with_monitoring(
        self, id_beecker: str
    ) -> Optional[RPADashboard]:
        """
        Get an RPA dashboard by its Beecker ID with monitoring configurations.

        Args:
            id_beecker: The Beecker ID (e.g., "AEC.001")

        Returns:
            The RPADashboard instance with monitoring data or None if not found
        """
        stmt = select(RPADashboard).where(
            RPADashboard.id_beecker == id_beecker
        ).options(joinedload(RPADashboard.scheduled_monitoring))
        return self.db.execute(stmt).scalars().unique().first()

    def get_by_client_id(self, id_client: str) -> List[RPADashboard]:
        """
        Get all RPA dashboards for a specific client.

        Args:
            id_client: The client ID

        Returns:
            List of RPADashboard instances for the client
        """
        stmt = select(RPADashboard).where(
            RPADashboard.id_client == id_client
        ).order_by(RPADashboard.id_beecker)
        return self.db.execute(stmt).scalars().all()

    def exists_by_id_beecker(self, id_beecker: str) -> bool:
        """
        Check if an RPA dashboard exists by its Beecker ID.

        Args:
            id_beecker: The Beecker ID (e.g., "AEC.001")

        Returns:
            True if exists, False otherwise
        """
        stmt = select(1).select_from(RPADashboard).where(
            RPADashboard.id_beecker == id_beecker
        ).limit(1)
        return self.db.execute(stmt).scalar() is not None


class RPADashboardMonitoringRepository(BaseRepository[RPADashboardMonitoring]):
    """
    Repository for RPADashboardMonitoring model.
    Provides specialized query methods for RPA Dashboard monitoring operations.
    """

    def __init__(self, db: Session):
        """Initialize RPADashboardMonitoringRepository with RPADashboardMonitoring model."""
        super().__init__(db, RPADashboardMonitoring)

    def list_all_with_job(self) -> List[RPADashboardMonitoring]:
        """
        List all monitoring configurations with their job information eagerly loaded.

        Returns:
            List of RPADashboardMonitoring instances with job data preloaded
        """
        stmt = select(RPADashboardMonitoring).options(
            joinedload(RPADashboardMonitoring.job)
        ).order_by(RPADashboardMonitoring.id)
        return self.db.execute(stmt).scalars().unique().all()

    def get_by_id_with_job(self, monitoring_id: str) -> Optional[RPADashboardMonitoring]:
        """
        Get a monitoring configuration by ID with its job information.

        Args:
            monitoring_id: The monitoring configuration ID

        Returns:
            The RPADashboardMonitoring instance with job data or None if not found
        """
        stmt = select(RPADashboardMonitoring).where(
            RPADashboardMonitoring.id == monitoring_id
        ).options(joinedload(RPADashboardMonitoring.job))
        return self.db.execute(stmt).scalars().unique().first()

    def get_by_id_beecker(self, id_beecker: str) -> List[RPADashboardMonitoring]:
        """
        Get all monitoring configurations for a specific RPA dashboard.

        Args:
            id_beecker: The Beecker ID (e.g., "AEC.001")

        Returns:
            List of RPADashboardMonitoring instances for the dashboard
        """
        stmt = select(RPADashboardMonitoring).where(
            RPADashboardMonitoring.id_beecker == id_beecker
        ).options(joinedload(RPADashboardMonitoring.job))
        return self.db.execute(stmt).scalars().unique().all()

    def get_by_scheduler_job_id(
        self, id_scheduler_job: str
    ) -> Optional[RPADashboardMonitoring]:
        """
        Get a monitoring configuration by its scheduler job ID.

        Args:
            id_scheduler_job: The scheduler job ID

        Returns:
            The RPADashboardMonitoring instance or None if not found
        """
        stmt = select(RPADashboardMonitoring).where(
            RPADashboardMonitoring.id_scheduler_job == id_scheduler_job
        )
        return self.db.execute(stmt).scalars().first()


class RPAUiPathRepository(BaseRepository[RPAUiPath]):
    """
    Repository for RPAUiPath model.
    Provides specialized query methods for RPA UiPath operations.
    """

    def __init__(self, db: Session):
        """Initialize RPAUiPathRepository with RPAUiPath model."""
        super().__init__(db, RPAUiPath)

    def list_all_with_client(self) -> List[RPAUiPath]:
        """
        List all RPA UiPath bots with their client information eagerly loaded.

        Returns:
            List of RPAUiPath instances with client data preloaded
        """
        stmt = select(RPAUiPath).options(
            joinedload(RPAUiPath.client)
        ).order_by(RPAUiPath.uipath_robot_name)
        return self.db.execute(stmt).scalars().unique().all()

    def get_by_robot_name(self, uipath_robot_name: str) -> Optional[RPAUiPath]:
        """
        Get an RPA UiPath bot by its robot name.

        Args:
            uipath_robot_name: The UiPath robot name

        Returns:
            The RPAUiPath instance or None if not found
        """
        return self.db.get(RPAUiPath, uipath_robot_name)

    def get_by_robot_name_with_monitoring(
        self, uipath_robot_name: str
    ) -> Optional[RPAUiPath]:
        """
        Get an RPA UiPath bot by its robot name with monitoring configurations.

        Args:
            uipath_robot_name: The UiPath robot name

        Returns:
            The RPAUiPath instance with monitoring data or None if not found
        """
        stmt = select(RPAUiPath).where(
            RPAUiPath.uipath_robot_name == uipath_robot_name
        ).options(joinedload(RPAUiPath.scheduled_monitoring))
        return self.db.execute(stmt).scalars().unique().first()

    def get_by_client_id(self, id_client: str) -> List[RPAUiPath]:
        """
        Get all RPA UiPath bots for a specific client.

        Args:
            id_client: The client ID

        Returns:
            List of RPAUiPath instances for the client
        """
        stmt = select(RPAUiPath).where(
            RPAUiPath.id_client == id_client
        ).order_by(RPAUiPath.uipath_robot_name)
        return self.db.execute(stmt).scalars().all()

    def get_by_beecker_name(self, beecker_name: str) -> Optional[RPAUiPath]:
        """
        Get an RPA UiPath bot by its Beecker name.

        Args:
            beecker_name: The Beecker name

        Returns:
            The RPAUiPath instance or None if not found
        """
        stmt = select(RPAUiPath).where(RPAUiPath.beecker_name == beecker_name)
        return self.db.execute(stmt).scalars().first()

    def exists_by_robot_name(self, uipath_robot_name: str) -> bool:
        """
        Check if an RPA UiPath bot exists by its robot name.

        Args:
            uipath_robot_name: The UiPath robot name

        Returns:
            True if exists, False otherwise
        """
        stmt = select(1).select_from(RPAUiPath).where(
            RPAUiPath.uipath_robot_name == uipath_robot_name
        ).limit(1)
        return self.db.execute(stmt).scalar() is not None


class RPAUiPathMonitoringRepository(BaseRepository[RPAUiPathMonitoring]):
    """
    Repository for RPAUiPathMonitoring model.
    Provides specialized query methods for RPA UiPath monitoring operations.
    """

    def __init__(self, db: Session):
        """Initialize RPAUiPathMonitoringRepository with RPAUiPathMonitoring model."""
        super().__init__(db, RPAUiPathMonitoring)

    def list_all_with_job(self) -> List[RPAUiPathMonitoring]:
        """
        List all monitoring configurations with their job information eagerly loaded.

        Returns:
            List of RPAUiPathMonitoring instances with job data preloaded
        """
        stmt = select(RPAUiPathMonitoring).options(
            joinedload(RPAUiPathMonitoring.job)
        ).order_by(RPAUiPathMonitoring.id)
        return self.db.execute(stmt).scalars().unique().all()

    def get_by_id_with_job(self, monitoring_id: str) -> Optional[RPAUiPathMonitoring]:
        """
        Get a monitoring configuration by ID with its job information.

        Args:
            monitoring_id: The monitoring configuration ID

        Returns:
            The RPAUiPathMonitoring instance with job data or None if not found
        """
        stmt = select(RPAUiPathMonitoring).where(
            RPAUiPathMonitoring.id == monitoring_id
        ).options(joinedload(RPAUiPathMonitoring.job))
        return self.db.execute(stmt).scalars().unique().first()

    def get_by_robot_name(self, uipath_robot_name: str) -> List[RPAUiPathMonitoring]:
        """
        Get all monitoring configurations for a specific RPA UiPath bot.

        Args:
            uipath_robot_name: The UiPath robot name

        Returns:
            List of RPAUiPathMonitoring instances for the bot
        """
        stmt = select(RPAUiPathMonitoring).where(
            RPAUiPathMonitoring.uipath_robot_name == uipath_robot_name
        ).options(joinedload(RPAUiPathMonitoring.job))
        return self.db.execute(stmt).scalars().unique().all()

    def get_by_scheduler_job_id(
        self, id_scheduler_job: str
    ) -> Optional[RPAUiPathMonitoring]:
        """
        Get a monitoring configuration by its scheduler job ID.

        Args:
            id_scheduler_job: The scheduler job ID

        Returns:
            The RPAUiPathMonitoring instance or None if not found
        """
        stmt = select(RPAUiPathMonitoring).where(
            RPAUiPathMonitoring.id_scheduler_job == id_scheduler_job
        )
        return self.db.execute(stmt).scalars().first()
