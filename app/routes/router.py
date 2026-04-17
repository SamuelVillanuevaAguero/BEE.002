"""
app/routes/router.py
====================
Main router: Responsible for routing all existing endpoints so that FastAPI displays them.
"""
from fastapi import APIRouter

from app.routes.monitoring import rpa, agent
from app.routes.jobs import jobs, executions
from app.routes import clients
from app.routes.rpa_dashboard import dashboard_router, uipath_router

router = APIRouter()

# monitoring webhooks
router.include_router(rpa.router)
router.include_router(agent.router)

# jobs
router.include_router(jobs.router)
router.include_router(executions.router)

router.include_router(clients.router)
router.include_router(dashboard_router)
router.include_router(uipath_router)

@router.get("/health", tags=["Health"])
def health():
    from app.core.scheduler import scheduler
    return {
        "status": "ok",
        "scheduler_running": scheduler.running,
        "jobs_count": len(scheduler.get_jobs()),
    }