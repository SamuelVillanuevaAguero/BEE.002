from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.automation import MonitorType, PlatformType


"""Nested schemas"""

class MessageFlagsSchema(BaseModel):
    start_active: bool
    end_active: bool


"""Base schema (campos compartidos)"""

class AutomationBase(BaseModel):
    """Campos compartidos entre Create, Update y Response."""

    beecker_id: Optional[str] = Field(None, max_length=50)
    process_name: Optional[str] = Field(None, max_length=255)
    client_name: Optional[str] = Field(None, max_length=255)
    beecker_platform: Optional[PlatformType] = None
    beecker_platform_id: Optional[str] = Field(None, max_length=10)
    monitoring_type: Optional[MonitorType] = None
    id_scheduler_job: Optional[str] = Field(None, max_length=191)
    message_flags: Optional[MessageFlagsSchema] = None
    transaction_unit: Optional[str] = Field(None, max_length=255)
    slack_channel: Optional[str] = Field(None, max_length=255)
    roc_agents: Optional[dict[str, Any]] = None
    service_type: Optional[str] = Field(None, max_length=10)
    uipath_process_name: Optional[str] = Field(None, max_length=255)
    uipath_framework: Optional[str] = Field(None, max_length=50)
    calculate_average_time: Optional[bool] = None
    freshdesk_company_id: Optional[str] = Field(None, max_length=50)
    freshdesk_show_tickets: Optional[bool] = None
    maximum_messages_errors: Optional[int] = Field(None, ge=0, le=10)
    known_issues: Optional[list] = None

"""Automation Schemas"""

class AutomationCreate(AutomationBase):
    """Payload to create a new automation setting."""

    pass


class AutomationUpdate(AutomationBase):
    """Payload to partially update an existing automation setting."""
    
    pass


class AutomationResponse(AutomationBase):
    """Response schema for an automation setting."""

    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
