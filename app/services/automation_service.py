"""
app/services/automation_service.py
Service layer for automation operations using the Repository pattern.
Provides class-based services for all automation entities.
"""
import logging
import uuid
from typing import Optional, List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.automation import (
    RPADashboard,
    RPADashboardMonitoring,
    RPAUiPath,
    RPAUiPathMonitoring,
)
from app.repositories.automation_repository import (
    RPADashboardRepository,
    RPADashboardMonitoringRepository,
    RPAUiPathRepository,
    RPAUiPathMonitoringRepository,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# RPA DASHBOARD SERVICE (Repository Pattern)
# ---------------------------------------------------------
class RPADashboardService:
    """Service for RPA Dashboard operations using Repository pattern."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.repo = RPADashboardRepository(db)

    def create(self, **kwargs) -> RPADashboard:
        """
        Create a new RPA Dashboard with validation.

        Args:
            **kwargs: RPA Dashboard attributes (id_beecker, id_dashboard, process_name, etc.)

        Returns:
            The created RPADashboard instance

        Raises:
            HTTPException: If RPADashboard already exists
        """
        if self.repo.exists_by_id_beecker(kwargs.get("id_beecker")):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"RPADashboard with id_beecker '{kwargs.get('id_beecker')}' already exists.",
            )
        return self.repo.create(kwargs)

    def create_from_payload(self, payload) -> RPADashboard:
        """
        Create RPA Dashboard from payload object.
        
        Args:
            payload: Object with id_beecker, id_dashboard, process_name, platform, 
                    id_client, business_errors attributes
        
        Returns:
            The created RPADashboard instance
        """
        return self.create(
            id_beecker=payload.id_beecker,
            id_dashboard=payload.id_dashboard,
            process_name=payload.process_name,
            platform=payload.platform,
            id_client=payload.id_client,
            business_errors=payload.business_errors or None,
        )

    def get_by_id(self, id_beecker: str) -> Optional[RPADashboard]:
        """Get RPA Dashboard by ID."""
        dashboard = self.repo.get_by_id_beecker(id_beecker)
        if not dashboard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"RPADashboard '{id_beecker}' not found.",
            )
        return dashboard

    def get_by_id_with_monitoring(self, id_beecker: str) -> Optional[RPADashboard]:
        """Get RPA Dashboard by ID with monitoring configurations."""
        dashboard = self.repo.get_by_id_beecker_with_monitoring(id_beecker)
        if not dashboard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"RPADashboard '{id_beecker}' not found.",
            )
        return dashboard

    def list_all(self) -> List[RPADashboard]:
        """List all RPA Dashboards."""
        return self.repo.list_all_with_client()

    def get_by_client_id(self, id_client: str) -> List[RPADashboard]:
        """Get all RPA Dashboards for a specific client."""
        return self.repo.get_by_client_id(id_client)

    def update(self, id_beecker: str, **kwargs) -> RPADashboard:
        """Update RPA Dashboard by ID."""
        dashboard = self.get_by_id(id_beecker)
        for key, value in kwargs.items():
            if hasattr(dashboard, key):
                setattr(dashboard, key, value)
        self.db.commit()
        self.db.refresh(dashboard)
        return dashboard

    def delete(self, id_beecker: str) -> None:
        """Delete RPA Dashboard by ID."""
        dashboard = self.get_by_id(id_beecker)
        self.repo.delete(id_beecker)
        logger.info(f"✅ RPADashboard deleted | id_beecker='{id_beecker}'")

    def exists(self, id_beecker: str) -> bool:
        """Check if RPA Dashboard exists."""
        return self.repo.exists_by_id_beecker(id_beecker)


# ---------------------------------------------------------
# RPA DASHBOARD MONITORING SERVICE
# ---------------------------------------------------------
class RPADashboardMonitoringService:
    """Service for RPA Dashboard Monitoring operations."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.repo = RPADashboardMonitoringRepository(db)

    def create(self, **kwargs) -> RPADashboardMonitoring:
        """
        Create a new RPA Dashboard monitoring configuration.

        Args:
            **kwargs: Monitoring attributes

        Returns:
            The created RPADashboardMonitoring instance
        """
        return self.repo.create(kwargs)

    def create_from_payload(self, payload) -> RPADashboardMonitoring:
        """
        Create monitoring configuration from payload object.
        
        Args:
            payload: Object with id_beecker, monitor_type, transaction_unit, 
                    slack_channel, manage_flags, roc_agents, id_scheduler_job attributes
        
        Returns:
            The created RPADashboardMonitoring instance
        """
        return self.create(
            id=str(uuid.uuid4()),
            id_beecker=payload.id_beecker,
            monitor_type=payload.monitor_type,
            transaction_unit=payload.transaction_unit,
            slack_channel=payload.slack_channel,
            manage_flags=payload.manage_flags,
            roc_agents=payload.roc_agents,
            id_scheduler_job=payload.id_scheduler_job,
        )

    def get_by_id(self, monitoring_id: str) -> Optional[RPADashboardMonitoring]:
        """Get monitoring configuration by ID."""
        monitoring = self.repo.get_by_id_with_job(monitoring_id)
        if not monitoring:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring '{monitoring_id}' not found.",
            )
        return monitoring

    def list_all(self) -> List[RPADashboardMonitoring]:
        """List all monitoring configurations with jobs."""
        return self.repo.list_all_with_job()

    def get_by_id_beecker(self, id_beecker: str) -> List[RPADashboardMonitoring]:
        """Get all monitoring configurations for a specific dashboard."""
        return self.repo.get_by_id_beecker(id_beecker)

    def update(self, monitoring_id: str, **kwargs) -> RPADashboardMonitoring:
        """Update monitoring configuration by ID."""
        monitoring = self.get_by_id(monitoring_id)
        for key, value in kwargs.items():
            if hasattr(monitoring, key):
                setattr(monitoring, key, value)
        self.db.commit()
        self.db.refresh(monitoring)
        return monitoring

    def delete(self, monitoring_id: str) -> None:
        """Delete monitoring configuration by ID."""
        monitoring = self.get_by_id(monitoring_id)
        self.repo.delete(monitoring_id)
        logger.info(f"✅ RPADashboardMonitoring deleted | id='{monitoring_id}'")

    def get_by_scheduler_job_id(self, id_scheduler_job: str) -> Optional[RPADashboardMonitoring]:
        """Get monitoring configuration by scheduler job ID."""
        return self.repo.get_by_scheduler_job_id(id_scheduler_job)


# ---------------------------------------------------------
# RPA UIPATH SERVICE
# ---------------------------------------------------------
class RPAUiPathService:
    """Service for RPA UiPath operations."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.repo = RPAUiPathRepository(db)

    def create(self, **kwargs) -> RPAUiPath:
        """
        Create a new RPA UiPath bot with validation.

        Args:
            **kwargs: RPA UiPath attributes (uipath_robot_name, beecker_name, framework, etc.)

        Returns:
            The created RPAUiPath instance

        Raises:
            HTTPException: If RPA UiPath bot already exists
        """
        robot_name = kwargs.get("uipath_robot_name")
        if self.repo.exists_by_robot_name(robot_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"RPAUiPath with robot_name '{robot_name}' already exists.",
            )
        return self.repo.create(kwargs)

    def create_from_payload(self, payload) -> RPAUiPath:
        """
        Create RPA UiPath bot from payload object.
        
        Args:
            payload: Object with uipath_robot_name, id_beecker, beecker_name, 
                    framework, id_client, business_errors attributes
        
        Returns:
            The created RPAUiPath instance
        """
        return self.create(
            uipath_robot_name=payload.uipath_robot_name,
            id_beecker=payload.id_beecker,
            beecker_name=payload.beecker_name,
            framework=payload.framework,
            id_client=payload.id_client,
            business_errors=payload.business_errors or None,
        )

    def get_by_robot_name(self, uipath_robot_name: str) -> Optional[RPAUiPath]:
        """Get RPA UiPath bot by robot name."""
        uipath = self.repo.get_by_robot_name(uipath_robot_name)
        if not uipath:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"RPAUiPath '{uipath_robot_name}' not found.",
            )
        return uipath

    def get_by_robot_name_with_monitoring(
        self, uipath_robot_name: str
    ) -> Optional[RPAUiPath]:
        """Get RPA UiPath bot by robot name with monitoring configurations."""
        uipath = self.repo.get_by_robot_name_with_monitoring(uipath_robot_name)
        if not uipath:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"RPAUiPath '{uipath_robot_name}' not found.",
            )
        return uipath

    def list_all(self) -> List[RPAUiPath]:
        """List all RPA UiPath bots."""
        return self.repo.list_all_with_client()

    def get_by_client_id(self, id_client: str) -> List[RPAUiPath]:
        """Get all RPA UiPath bots for a specific client."""
        return self.repo.get_by_client_id(id_client)

    def get_by_beecker_name(self, beecker_name: str) -> Optional[RPAUiPath]:
        """Get RPA UiPath bot by Beecker name."""
        return self.repo.get_by_beecker_name(beecker_name)

    def update(self, uipath_robot_name: str, **kwargs) -> RPAUiPath:
        """Update RPA UiPath bot by robot name."""
        uipath = self.get_by_robot_name(uipath_robot_name)
        for key, value in kwargs.items():
            if hasattr(uipath, key):
                setattr(uipath, key, value)
        self.db.commit()
        self.db.refresh(uipath)
        return uipath

    def delete(self, uipath_robot_name: str) -> None:
        """Delete RPA UiPath bot by robot name."""
        uipath = self.get_by_robot_name(uipath_robot_name)
        self.repo.delete(uipath_robot_name)
        logger.info(f"✅ RPAUiPath deleted | robot_name='{uipath_robot_name}'")

    def exists(self, uipath_robot_name: str) -> bool:
        """Check if RPA UiPath bot exists."""
        return self.repo.exists_by_robot_name(uipath_robot_name)


# ---------------------------------------------------------
# RPA UIPATH MONITORING SERVICE
# ---------------------------------------------------------
class RPAUiPathMonitoringService:
    """Service for RPA UiPath Monitoring operations."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.repo = RPAUiPathMonitoringRepository(db)

    def create(self, **kwargs) -> RPAUiPathMonitoring:
        """
        Create a new RPA UiPath monitoring configuration.

        Args:
            **kwargs: Monitoring attributes

        Returns:
            The created RPAUiPathMonitoring instance
        """
        return self.repo.create(kwargs)

    def create_from_payload(self, payload) -> RPAUiPathMonitoring:
        """
        Create monitoring configuration from payload object.
        
        Args:
            payload: Object with uipath_robot_name, monitor_type, transaction_unit, 
                    slack_channel, manage_flags, roc_agents, id_scheduler_job attributes
        
        Returns:
            The created RPAUiPathMonitoring instance
        """
        return self.create(
            id=str(uuid.uuid4()),
            uipath_robot_name=payload.uipath_robot_name,
            monitor_type=payload.monitor_type,
            transaction_unit=payload.transaction_unit,
            slack_channel=payload.slack_channel,
            manage_flags=payload.manage_flags,
            roc_agents=payload.roc_agents,
            id_scheduler_job=payload.id_scheduler_job,
        )

    def get_by_id(self, monitoring_id: str) -> Optional[RPAUiPathMonitoring]:
        """Get monitoring configuration by ID."""
        monitoring = self.repo.get_by_id_with_job(monitoring_id)
        if not monitoring:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring '{monitoring_id}' not found.",
            )
        return monitoring

    def list_all(self) -> List[RPAUiPathMonitoring]:
        """List all monitoring configurations with jobs."""
        return self.repo.list_all_with_job()

    def get_by_robot_name(self, uipath_robot_name: str) -> List[RPAUiPathMonitoring]:
        """Get all monitoring configurations for a specific UiPath bot."""
        return self.repo.get_by_robot_name(uipath_robot_name)

    def update(self, monitoring_id: str, **kwargs) -> RPAUiPathMonitoring:
        """Update monitoring configuration by ID."""
        monitoring = self.get_by_id(monitoring_id)
        for key, value in kwargs.items():
            if hasattr(monitoring, key):
                setattr(monitoring, key, value)
        self.db.commit()
        self.db.refresh(monitoring)
        return monitoring

    def delete(self, monitoring_id: str) -> None:
        """Delete monitoring configuration by ID."""
        monitoring = self.get_by_id(monitoring_id)
        self.repo.delete(monitoring_id)
        logger.info(f"✅ RPAUiPathMonitoring deleted | id='{monitoring_id}'")

    def get_by_scheduler_job_id(self, id_scheduler_job: str) -> Optional[RPAUiPathMonitoring]:
        """Get monitoring configuration by scheduler job ID."""
        return self.repo.get_by_scheduler_job_id(id_scheduler_job)


# ---------------------------------------------------------
# Factory Functions
# ---------------------------------------------------------
def get_rpa_dashboard_service(db: Session) -> RPADashboardService:
    """Factory: Get RPADashboardService instance."""
    return RPADashboardService(db)


def get_rpa_dashboard_monitoring_service(db: Session) -> RPADashboardMonitoringService:
    """Factory: Get RPADashboardMonitoringService instance."""
    return RPADashboardMonitoringService(db)


def get_rpa_uipath_service(db: Session) -> RPAUiPathService:
    """Factory: Get RPAUiPathService instance."""
    return RPAUiPathService(db)


def get_rpa_uipath_monitoring_service(db: Session) -> RPAUiPathMonitoringService:
    """Factory: Get RPAUiPathMonitoringService instance."""
    return RPAUiPathMonitoringService(db)