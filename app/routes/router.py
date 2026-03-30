"""
app/routes/router.py
"""
from fastapi import APIRouter

from app.routes import hello
from app.routes.monitoring import rpa, agent
from app.routes.jobs import jobs, executions
from app.routes import automations
from app.routes import rpa_dashboard
from app.routes import clients

router = APIRouter()

# home / debug
router.include_router(hello.router)

# monitoring webhooks
router.include_router(rpa.router)
router.include_router(agent.router)

# jobs
router.include_router(jobs.router)
router.include_router(executions.router)

# automations (legacy)
router.include_router(automations.router)

# CRUD
router.include_router(clients.router)
router.include_router(rpa_dashboard.router)

@router.get("/health", tags=["Health"])
def health():
    from app.core.scheduler import scheduler
    return {
        "status": "ok",
        "scheduler_running": scheduler.running,
        "jobs_count": len(scheduler.get_jobs()),
    }