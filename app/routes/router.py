from fastapi import APIRouter

from app.routes import hello
from app.routes.monitoring import rpa, agent
from app.routes.jobs import jobs, executions
from app.routes import automations
from app.routes import rpa_dashboard


router = APIRouter()

#home
router.include_router(hello.router)

#monitoring
router.include_router(rpa.router)
router.include_router(agent.router)

#jobs
router.include_router(jobs.router)
router.include_router(executions.router)

#automations
router.include_router(automations.router)

router.include_router(rpa_dashboard.router)


#health
@router.get("/health", tags=["Health"])
def health():
    from app.core.scheduler import scheduler
    return {
        "status": "ok",
        "scheduler_running": scheduler.running,
        "jobs_count": len(scheduler.get_jobs()),
    }
