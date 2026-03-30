"""
app/services/rpa_dashboard_service.py
========================================
CRUD completo para RPADashboard, RPADashboardMonitoring y BusinessError.
Reemplaza el endpoint atómico anterior.
"""
from __future__ import annotations
import logging
import uuid
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.automation import (
    Client,
    RPADashboard,
    RPADashboardMonitoring,
    RPADashboardBusinessError,
)
from app.models.job import Job, JobStatus
from app.schemas.rpa_dashboard import (
    RPADashboardCreate,
    RPADashboardUpdate,
    RPADashboardMonitoringCreate,
    RPADashboardMonitoringUpdate,
    BusinessErrorCreate,
    JobLinkRequest,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_rpa_or_404(db: Session, id_beecker: str) -> RPADashboard:
    rpa = db.get(RPADashboard, id_beecker)
    if not rpa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bot '{id_beecker}' no encontrado en rpa_dashboard.",
        )
    return rpa


def _get_monitoring_or_404(db: Session, id_beecker: str, monitoring_id: str) -> RPADashboardMonitoring:
    mon = (
        db.query(RPADashboardMonitoring)
        .filter(
            RPADashboardMonitoring.id == monitoring_id,
            RPADashboardMonitoring.id_beecker == id_beecker,
        )
        .first()
    )
    if not mon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring '{monitoring_id}' no encontrado para bot '{id_beecker}'.",
        )
    return mon


def _transaction_unit_str(tu) -> str | None:
    if tu is None:
        return None
    return f"{tu.plural}|{tu.singular}"


# ── RPADashboard CRUD ─────────────────────────────────────────────────────────

def create_rpa_dashboard(db: Session, payload: RPADashboardCreate) -> RPADashboard:
    if db.get(RPADashboard, payload.id_beecker):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un bot con id_beecker='{payload.id_beecker}'.",
        )
    if not db.get(Client, payload.id_client):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente '{payload.id_client}' no encontrado.",
        )
    rpa = RPADashboard(
        id_beecker=payload.id_beecker,
        id_dashboard=payload.id_dashboard,
        process_name=payload.process_name,
        platform=payload.platform,
        id_client=payload.id_client,
    )
    db.add(rpa)
    try:
        db.commit()
        db.refresh(rpa)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Error de integridad en BD.")
    logger.info(f"✅ RPADashboard creado | id_beecker='{rpa.id_beecker}'")
    return rpa


def list_rpa_dashboards(db: Session) -> list[RPADashboard]:
    return db.query(RPADashboard).order_by(RPADashboard.id_beecker).all()


def get_rpa_dashboard(db: Session, id_beecker: str) -> RPADashboard:
    rpa = (
        db.query(RPADashboard)
        .options(
            joinedload(RPADashboard.scheduled_monitoring),
            joinedload(RPADashboard.business_errors),
        )
        .filter(RPADashboard.id_beecker == id_beecker)
        .first()
    )
    if not rpa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bot '{id_beecker}' no encontrado.",
        )
    return rpa


def update_rpa_dashboard(db: Session, id_beecker: str, payload: RPADashboardUpdate) -> RPADashboard:
    rpa = _get_rpa_or_404(db, id_beecker)
    if payload.id_dashboard is not None:
        rpa.id_dashboard = payload.id_dashboard
    if payload.process_name is not None:
        rpa.process_name = payload.process_name
    if payload.platform is not None:
        rpa.platform = payload.platform
    if payload.id_client is not None:
        if not db.get(Client, payload.id_client):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Cliente '{payload.id_client}' no encontrado.")
        rpa.id_client = payload.id_client
    db.commit()
    db.refresh(rpa)
    logger.info(f"✅ RPADashboard actualizado | id_beecker='{id_beecker}'")
    return rpa


def delete_rpa_dashboard(db: Session, id_beecker: str) -> None:
    rpa = _get_rpa_or_404(db, id_beecker)
    db.delete(rpa)
    db.commit()
    logger.info(f"🗑️ RPADashboard eliminado | id_beecker='{id_beecker}'")


# ── RPADashboardMonitoring CRUD ───────────────────────────────────────────────

def create_monitoring(db: Session, id_beecker: str, payload: RPADashboardMonitoringCreate) -> RPADashboardMonitoring:
    _get_rpa_or_404(db, id_beecker)
    mon = RPADashboardMonitoring(
        id=str(uuid.uuid4()),
        id_beecker=id_beecker,
        monitor_type=payload.monitor_type,
        slack_channel=payload.slack_channel,
        transaction_unit=_transaction_unit_str(payload.transaction_unit),
        roc_agents=payload.roc_agents,
        manage_flags=payload.manage_flags.model_dump() if payload.manage_flags else None,
        id_scheduler_job=None,
    )
    db.add(mon)
    db.commit()
    db.refresh(mon)
    logger.info(f"✅ Monitoring creado | id='{mon.id}' | bot='{id_beecker}' | canal='{mon.slack_channel}'")
    return mon


def list_monitoring(db: Session, id_beecker: str) -> list[RPADashboardMonitoring]:
    _get_rpa_or_404(db, id_beecker)
    return (
        db.query(RPADashboardMonitoring)
        .filter(RPADashboardMonitoring.id_beecker == id_beecker)
        .all()
    )


def get_monitoring(db: Session, id_beecker: str, monitoring_id: str) -> RPADashboardMonitoring:
    return _get_monitoring_or_404(db, id_beecker, monitoring_id)


def update_monitoring(
    db: Session, id_beecker: str, monitoring_id: str, payload: RPADashboardMonitoringUpdate
) -> RPADashboardMonitoring:
    mon = _get_monitoring_or_404(db, id_beecker, monitoring_id)
    if payload.slack_channel is not None:
        mon.slack_channel = payload.slack_channel
    if payload.monitor_type is not None:
        mon.monitor_type = payload.monitor_type
    if payload.transaction_unit is not None:
        mon.transaction_unit = _transaction_unit_str(payload.transaction_unit)
    if payload.roc_agents is not None:
        mon.roc_agents = payload.roc_agents
    if payload.manage_flags is not None:
        mon.manage_flags = payload.manage_flags.model_dump()
    db.commit()
    db.refresh(mon)
    logger.info(f"✅ Monitoring actualizado | id='{monitoring_id}'")
    return mon


def delete_monitoring(db: Session, id_beecker: str, monitoring_id: str) -> None:
    """
    Elimina el monitoring. Si tiene job vinculado, elimina el job también
    (cascade automático por la FK con ondelete en job_service o directo aquí).
    """
    from app.services import job_service

    mon = _get_monitoring_or_404(db, id_beecker, monitoring_id)

    # Eliminar job vinculado si existe
    if mon.id_scheduler_job:
        job_id = mon.id_scheduler_job
        mon.id_scheduler_job = None
        db.flush()
        job_service.delete_job(db, job_id)
        logger.info(f"🗑️ Job '{job_id}' eliminado por cascade desde monitoring")

    db.delete(mon)
    db.commit()
    logger.info(f"🗑️ Monitoring eliminado | id='{monitoring_id}' | bot='{id_beecker}'")


# ── Job vinculation ───────────────────────────────────────────────────────────

def link_job(db: Session, id_beecker: str, monitoring_id: str, payload: JobLinkRequest) -> RPADashboardMonitoring:
    """
    Vincula un job existente a un monitoring.
    - Pausa el job si está activo.
    - Inyecta bot_id y monitoring_id en job_kwargs automáticamente.
    - Actualiza id_scheduler_job en el monitoring.
    """
    from app.core.scheduler import scheduler

    mon = _get_monitoring_or_404(db, id_beecker, monitoring_id)
    job = db.get(Job, payload.job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{payload.job_id}' no encontrado.",
        )

    # Pausar si está activo
    if job.status == JobStatus.active:
        aps_job = scheduler.get_job(payload.job_id)
        if aps_job:
            scheduler.pause_job(payload.job_id)
        job.status = JobStatus.paused
        job.next_run_time = None
        logger.info(f"⏸ Job '{payload.job_id}' pausado automáticamente al vincular")

    # Inyectar bot_id y monitoring_id en job_kwargs
    new_kwargs = {
        **{k: v for k, v in job.job_kwargs.items() if k not in ("bot_id", "monitoring_id")},
        "bot_id": id_beecker,
        "monitoring_id": monitoring_id,
    }
    job.job_kwargs = new_kwargs

    # Actualizar kwargs en APScheduler también
    aps_job = scheduler.get_job(payload.job_id)
    if aps_job:
        aps_job.modify(kwargs={"job_id": payload.job_id, "task_path": job.task_path, **new_kwargs})

    # Vincular
    mon.id_scheduler_job = payload.job_id
    db.commit()
    db.refresh(mon)

    logger.info(
        f"🔗 Job vinculado | job_id='{payload.job_id}' | monitoring_id='{monitoring_id}' | "
        f"bot='{id_beecker}' | job_kwargs={new_kwargs}"
    )
    return mon


def unlink_job(db: Session, id_beecker: str, monitoring_id: str) -> RPADashboardMonitoring:
    """
    Desvincula el job del monitoring: limpia job_kwargs y pone id_scheduler_job = NULL.
    No elimina el job.
    """
    from app.core.scheduler import scheduler

    mon = _get_monitoring_or_404(db, id_beecker, monitoring_id)

    if not mon.id_scheduler_job:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este monitoring no tiene ningún job vinculado.",
        )

    job = db.get(Job, mon.id_scheduler_job)
    if job:
        # Limpiar bot_id y monitoring_id de job_kwargs
        clean_kwargs = {k: v for k, v in job.job_kwargs.items() if k not in ("bot_id", "monitoring_id", "run_id")}
        job.job_kwargs = clean_kwargs
        aps_job = scheduler.get_job(mon.id_scheduler_job)
        if aps_job:
            aps_job.modify(kwargs={"job_id": job.id, "task_path": job.task_path, **clean_kwargs})

    mon.id_scheduler_job = None
    db.commit()
    db.refresh(mon)
    logger.info(f"🔓 Job desvinculado | monitoring_id='{monitoring_id}' | bot='{id_beecker}'")
    return mon


# ── BusinessError CRUD ────────────────────────────────────────────────────────

def create_business_error(db: Session, id_beecker: str, payload: BusinessErrorCreate) -> RPADashboardBusinessError:
    _get_rpa_or_404(db, id_beecker)
    error = RPADashboardBusinessError(
        id=str(uuid.uuid4()),
        id_platform=id_beecker,
        error_message=payload.error_message.strip(),
    )
    db.add(error)
    db.commit()
    db.refresh(error)
    logger.info(f"✅ BusinessError creado | id='{error.id}' | bot='{id_beecker}'")
    return error


def list_business_errors(db: Session, id_beecker: str) -> list[RPADashboardBusinessError]:
    _get_rpa_or_404(db, id_beecker)
    return (
        db.query(RPADashboardBusinessError)
        .filter(RPADashboardBusinessError.id_platform == id_beecker)
        .all()
    )


def delete_business_error(db: Session, id_beecker: str, error_id: str) -> None:
    error = (
        db.query(RPADashboardBusinessError)
        .filter(
            RPADashboardBusinessError.id == error_id,
            RPADashboardBusinessError.id_platform == id_beecker,
        )
        .first()
    )
    if not error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Error '{error_id}' no encontrado para bot '{id_beecker}'.",
        )
    db.delete(error)
    db.commit()
    logger.info(f"🗑️ BusinessError eliminado | id='{error_id}'")