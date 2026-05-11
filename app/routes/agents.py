from fastapi import APIRouter, Depends
from app.utils.auth import verify_api_key
from app.schemas.agent import AgentMonitoring, AgentMonitoringResponse

router = APIRouter(
    prefix="/agents",
    tags=["Agent Monitoring"]
)

@router.post(
    path="/",
    name="Create Agent Monitoring",
    response_model=AgentMonitoringResponse
)
def create_agent(payload: AgentMonitoring, api_key: str = Depends(verify_api_key)):
    pass

@router.patch(
    path="/",
    name="Update Agent Monitoring"
)
def update_agent():
    pass

@router.get(
    path="/",
    name="List all agent monitoring"
)
def list_agents():
    pass

@router.get(
    path="/{beecker_client}",
    name="List agent monitoring by beecker client"
)
def get_agent(beecker_client: str):
    pass

@router.get(
    path="/{agent_name}",
    name="List agent monitoring by agent name"
)
def get_agent(agent_name: str):
    pass

@router.post(
    path="/enable/{id_monitoring}",
    name="Enable or Disable monitoring"
)
def enable_monitor(id_monitoring: str):
    pass