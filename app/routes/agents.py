"""
app/routes/agents.py
CRUD endpoints for AgentMonitoring.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.utils.auth import verify_api_key
from app.schemas.agent import (
    AgentMonitoringCreate,
    AgentMonitoringResponse,
    AgentMonitoringUpdate,
    AgentMonitoringUpdateResponse,
)
from app.services.agent_service import AgentMonitoringService

router = APIRouter(
    prefix="/agents",
    tags=["Agent Monitoring"],
    dependencies=[Depends(verify_api_key)],
)

@router.post(
    "/",
    response_model=AgentMonitoringResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create agent monitoring",
    description="Creates a new AgentMonitoring configuration.",
)
def create_agent(
    payload: AgentMonitoringCreate,
    db: Session = Depends(get_db),
) -> AgentMonitoringResponse:
    svc = AgentMonitoringService(db)
    return svc.create(payload)

@router.get(
    "/",
    response_model=list[AgentMonitoringResponse],
    summary="List all agent monitoring configurations",
)
def list_agents(
    db: Session = Depends(get_db),
) -> list[AgentMonitoringResponse]:
    svc = AgentMonitoringService(db)
    return svc.list_all()


@router.get(
    "/by-client/{beecker_id}",
    response_model=list[AgentMonitoringResponse],
    summary="List agent monitoring by Beecker client ID",
    description=(
        "Returns all AgentMonitoring configurations associated with a given "
        "Beecker client ID (e.g., 'PML.001')."
    ),
)
def get_agents_by_client(
    beecker_id: str,
    db: Session = Depends(get_db),
) -> list[AgentMonitoringResponse]:
    svc = AgentMonitoringService(db)
    return svc.get_by_beecker_id(beecker_id)

@router.get(
    "/by-name/{agent_name}",
    response_model=list[AgentMonitoringResponse],
    summary="List agent monitoring by agent name",
    description=(
        "Returns all AgentMonitoring configurations whose agent_name matches "
        "the given value (case-insensitive)."
    ),
)
def get_agents_by_name(
    agent_name: str,
    db: Session = Depends(get_db),
) -> list[AgentMonitoringResponse]:
    svc = AgentMonitoringService(db)
    return svc.get_by_agent_name(agent_name)


@router.get(
    "/{agent_id}",
    response_model=AgentMonitoringResponse,
    summary="Get agent monitoring by ID",
)
def get_agent(
    agent_id: str,
    db: Session = Depends(get_db),
) -> AgentMonitoringResponse:
    svc = AgentMonitoringService(db)
    return svc.get_by_id(agent_id)

@router.patch(
    "/{agent_id}",
    response_model=AgentMonitoringUpdateResponse,
    summary="Partially update an agent monitoring configuration",
    description=(
        "Applies partial updates to an AgentMonitoring record. "
        "Only explicitly provided fields are modified. "
        "Immutable fields (beecker_id, platform_id, platform, job_id) "
        "are not accepted in this payload."
    ),
)
def update_agent(
    agent_id: str,
    payload: AgentMonitoringUpdate,
    db: Session = Depends(get_db),
) -> AgentMonitoringUpdateResponse:
    svc = AgentMonitoringService(db)
    return svc.update(agent_id, payload)


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an agent monitoring configuration",
)
def delete_agent(
    agent_id: str,
    db: Session = Depends(get_db),
) -> None:
    svc = AgentMonitoringService(db)
    svc.delete(agent_id)

@router.post(
    "/enable/{agent_id}",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Enable or disable an agent monitoring configuration",
    description="Not yet implemented.",
    include_in_schema=True,
)
def enable_monitor(agent_id: str) -> dict:
    return {"detail": "Not implemented yet."}