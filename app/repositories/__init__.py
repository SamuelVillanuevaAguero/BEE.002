"""
app/repositories/__init__.py
Repository pattern implementations for data access abstraction.
"""
from .base_repository import BaseRepository
from .job_repository import JobRepository
from .client_repository import ClientRepository
from .automation_repository import (
    RPADashboardRepository,
    RPADashboardMonitoringRepository,
    RPAUiPathRepository,
    RPAUiPathMonitoringRepository,
)

__all__ = [
    "BaseRepository",
    "JobRepository",
    "ClientRepository",
    "RPADashboardRepository",
    "RPADashboardMonitoringRepository",
    "RPAUiPathRepository",
    "RPAUiPathMonitoringRepository",
]
