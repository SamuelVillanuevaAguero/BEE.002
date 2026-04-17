import logging

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone

from app.core.config import settings
from app.db.session import engine

logger = logging.getLogger(__name__)

jobstores = {
    "default": SQLAlchemyJobStore(engine=engine, tablename="apscheduler_jobs")
}

executors = {
    "default": ThreadPoolExecutor(max_workers=10),
}

job_defaults = {
    "coalesce": settings.SCHEDULER_COALESCE,
    "max_instances": settings.SCHEDULER_MAX_INSTANCES,
    "misfire_grace_time": 60,
}

scheduler = BackgroundScheduler(
    jobstores=jobstores,
    executors=executors,
    job_defaults=job_defaults,
    timezone=timezone(settings.SCHEDULER_TIMEZONE),
)


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
        logger.info("▶ APScheduler started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🛑 APScheduler stopped")
