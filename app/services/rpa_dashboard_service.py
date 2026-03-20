"""
app/services/rpa_dashboard_service.py
"""
from __future__ import annotations
import logging
import uuid
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.automation import (
    Client, RPADashboard, RPADashboardMonitoring, RPAUiPath, RPAUiPathMonitoring,
)
from app.models.job import Job, JobStatus, TriggerType
from app.schemas.rpa_dashboard import (
    RPADashboardAtomicCreate, RPAUiPathAtomicCreate,
    MonitoringPatch, JobFragment,
)
from app.services.client_service import get_or_create_client

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _transaction_unit_str(tu) -> str | None:
    return f"{tu.plural}|{tu.singular}" if tu else None


def _build_job_response(job: Job | None) -> dict | None:
    if not job:
        return None
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status.value,
        "trigger_type": job.trigger_type.value,
        "trigger_args": job.trigger_args,
        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
    }


def _build_monitoring_response(mon, job: Job | None) -> dict:
    return {
        "id": mon.id,
        "monitor_type": mon.monitor_type,
        "slack_channel": mon.slack_channel,
        "transaction_unit": mon.transaction_unit,
        "roc_agents": mon.roc_agents,
        "manage_flags": mon.manage_flags,
        "id_scheduler_job": mon.id_scheduler_job,
        "job": _build_job_response(job),
    }


def _create_and_pause_job(
    db: Session,
    job_fragment: JobFragment,
    bot_id: str,
    monitoring_id: str,
) -> Job:
    """
    Crea el job usando el mismo patrón que job_service.create_job:
      - APScheduler ejecuta _wrapped_task(job_id, task_path, **kwargs)
      - task_path va en kwargs de APScheduler (lo consume _wrapped_task internamente)
      - job_kwargs en BD solo guarda bot_id y monitoring_id (no task_path)
      - Se pausa inmediatamente en APScheduler y en BD
    """
    from app.services.job_service import _wrapped_task, _build_trigger
    from app.core.scheduler import scheduler

    job_id = str(uuid.uuid4())
    job_name = job_fragment.name or f"bee-observa | {bot_id}"
    task_path = job_fragment.task_path or "app.tasks.rpa_tasks:scheduled_rpa_status"
    trigger_type_str = job_fragment.trigger_type or "interval"
    trigger_args = job_fragment.trigger_args or {"minutes": 5}

    try:
        trigger_type_enum = TriggerType(trigger_type_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"trigger_type inválido: '{trigger_type_str}'. Válidos: cron, interval, date.",
        )

    # job_kwargs que se guardan en BD (lo que recibe scheduled_rpa_status)
    job_kwargs = {
        "bot_id": bot_id,
        "monitoring_id": monitoring_id,
    }

    # APScheduler recibe _wrapped_task con task_path + job_kwargs
    # _wrapped_task(job_id, task_path, **kwargs) → llama a scheduled_rpa_status(job_id, **kwargs)
    trigger = _build_trigger(trigger_type_enum, trigger_args)
    scheduler.add_job(
        func=_wrapped_task,
        trigger=trigger,
        id=job_id,
        name=job_name,
        kwargs={
            "job_id": job_id,
            "task_path": task_path,
            **job_kwargs,
        },
        replace_existing=True,
    )

    # Pausar inmediatamente en APScheduler
    scheduler.pause_job(job_id)
    logger.info(f"⏸ Job '{job_id}' pausado en APScheduler tras creación")

    # Crear en BD ya como paused (next_run_time=None)
    db_job = Job(
        id=job_id,
        name=job_name,
        description=job_fragment.description,
        task_path=task_path,
        trigger_type=trigger_type_enum,
        trigger_args=trigger_args,
        job_kwargs=job_kwargs,
        status=JobStatus.paused,
        next_run_time=None,
    )
    db.add(db_job)
    db.flush()

    logger.info(
        f"✅ Job creado y pausado | id='{job_id}' | bot='{bot_id}' | monitoring='{monitoring_id}'"
    )
    return db_job


def _get_monitoring_or_404(db: Session, monitoring_id: str, table) -> object:
    mon = db.query(table).filter(table.id == monitoring_id).first()
    if not mon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring '{monitoring_id}' no encontrado.",
        )
    return mon


# ── RPADashboard — Atómico ────────────────────────────────────────────────────

def create_rpa_dashboard_atomic(db: Session, payload: RPADashboardAtomicCreate) -> dict:
    # 1. Cliente
    client = get_or_create_client(db, payload.client.id, payload.client.name)

    # 2. Bot
    rpa_fragment = payload.RPA
    id_beecker = (rpa_fragment.id_beecker or "").strip()
    if not id_beecker:
        raise HTTPException(status_code=422, detail="RPA.id_beecker es obligatorio.")

    rpa = db.get(RPADashboard, id_beecker)
    if not rpa:
        if not rpa_fragment.process_name or not rpa_fragment.platform:
            raise HTTPException(
                status_code=422,
                detail="RPA.process_name y RPA.platform son obligatorios al crear un bot nuevo.",
            )
        rpa = RPADashboard(
            id_beecker=id_beecker,
            id_dashboard=(rpa_fragment.id_rpa or "").strip(),
            process_name=rpa_fragment.process_name.strip(),
            platform=rpa_fragment.platform,
            id_client=client.id,
            business_errors=[e.strip() for e in payload.business_errors if e.strip()] if payload.business_errors else None,
        )
        db.add(rpa)
        db.flush()
        logger.info(f"✅ RPADashboard creado | id_beecker='{id_beecker}'")
    else:
        logger.info(f"ℹ️ RPADashboard existente reutilizado | id_beecker='{id_beecker}'")

    # 3. Monitoring
    monitoring_id = str(uuid.uuid4())
    mon = RPADashboardMonitoring(
        id=monitoring_id,
        id_beecker=id_beecker,
        monitor_type=payload.monitor_type,
        slack_channel=payload.slack_channel.strip(),
        transaction_unit=_transaction_unit_str(payload.transaction_unit),
        roc_agents=payload.roc_agents,
        manage_flags=payload.manage_flags.model_dump() if payload.manage_flags else None,
        id_scheduler_job=None,
    )
    db.add(mon)
    db.flush()

    # 4. Job (opcional)
    db_job = None
    if payload.job is not None:
        db_job = _create_and_pause_job(
            db=db,
            job_fragment=payload.job,
            bot_id=id_beecker,
            monitoring_id=monitoring_id,
        )
        mon.id_scheduler_job = db_job.id
        db.flush()

    db.commit()
    db.refresh(mon)
    if db_job:
        db.refresh(db_job)

    return {
        "client": client,
        "rpa": rpa,
        "monitoring": _build_monitoring_response(mon, db_job),
        "job": _build_job_response(db_job),
    }


# ── RPAUiPath — Atómico ───────────────────────────────────────────────────────

def create_rpa_uipath_atomic(db: Session, payload: RPAUiPathAtomicCreate) -> dict:
    # 1. Cliente
    client = get_or_create_client(db, payload.client.id, payload.client.name)

    # 2. Bot
    rpa_fragment = payload.RPA
    robot_name = (rpa_fragment.uipath_robot_name or "").strip()
    if not robot_name:
        raise HTTPException(status_code=422, detail="RPA.uipath_robot_name es obligatorio.")

    rpa = db.get(RPAUiPath, robot_name)
    if not rpa:
        if not rpa_fragment.beecker_name or not rpa_fragment.framework:
            raise HTTPException(
                status_code=422,
                detail="RPA.beecker_name y RPA.framework son obligatorios al crear un bot nuevo.",
            )
        rpa = RPAUiPath(
            uipath_robot_name=robot_name,
            id_beecker=(rpa_fragment.id_beecker or "").strip(),
            beecker_name=rpa_fragment.beecker_name.strip(),
            framework=rpa_fragment.framework.strip(),
            id_client=client.id,
            business_errors=[e.strip() for e in payload.business_errors if e.strip()] if payload.business_errors else None,
        )
        db.add(rpa)
        db.flush()
        logger.info(f"✅ RPAUiPath creado | robot_name='{robot_name}'")
    else:
        logger.info(f"ℹ️ RPAUiPath existente reutilizado | robot_name='{robot_name}'")

    # 3. Monitoring
    monitoring_id = str(uuid.uuid4())
    mon = RPAUiPathMonitoring(
        id=monitoring_id,
        uipath_robot_name=robot_name,
        monitor_type=payload.monitor_type,
        slack_channel=payload.slack_channel.strip(),
        transaction_unit=_transaction_unit_str(payload.transaction_unit),
        roc_agents=payload.roc_agents,
        manage_flags=payload.manage_flags.model_dump() if payload.manage_flags else None,
        id_scheduler_job=None,
    )
    db.add(mon)
    db.flush()

    # 4. Job (opcional)
    db_job = None
    if payload.job is not None:
        db_job = _create_and_pause_job(
            db=db,
            job_fragment=payload.job,
            bot_id=robot_name,
            monitoring_id=monitoring_id,
        )
        mon.id_scheduler_job = db_job.id
        db.flush()

    db.commit()
    db.refresh(mon)
    if db_job:
        db.refresh(db_job)

    return {
        "client": client,
        "rpa": rpa,
        "monitoring": _build_monitoring_response(mon, db_job),
        "job": _build_job_response(db_job),
    }


# ── GET: Listados ─────────────────────────────────────────────────────────────

def list_rpa_dashboards(db: Session) -> list:
    return db.query(RPADashboard).order_by(RPADashboard.id_beecker).all()


def list_rpa_uipath(db: Session) -> list:
    return db.query(RPAUiPath).order_by(RPAUiPath.uipath_robot_name).all()


def list_clients(db: Session) -> list:
    return db.query(Client).order_by(Client.client_name).all()


def list_dashboard_errors(db: Session, id_beecker: str) -> list[str]:
    rpa = db.get(RPADashboard, id_beecker)
    if not rpa:
        raise HTTPException(status_code=404, detail=f"Bot '{id_beecker}' no encontrado.")
    return rpa.business_errors or []


def list_uipath_errors(db: Session, robot_name: str) -> list[str]:
    rpa = db.get(RPAUiPath, robot_name)
    if not rpa:
        raise HTTPException(status_code=404, detail=f"Bot UiPath '{robot_name}' no encontrado.")
    return rpa.business_errors or []


def list_dashboard_monitoring(db: Session) -> list[dict]:
    mons = (
        db.query(RPADashboardMonitoring)
        .options(joinedload(RPADashboardMonitoring.job))
        .all()
    )
    return [_build_monitoring_response(m, m.job) for m in mons]


def list_uipath_monitoring(db: Session) -> list[dict]:
    mons = (
        db.query(RPAUiPathMonitoring)
        .options(joinedload(RPAUiPathMonitoring.job))
        .all()
    )
    return [_build_monitoring_response(m, m.job) for m in mons]


# ── PATCH monitoring ──────────────────────────────────────────────────────────

def patch_dashboard_monitoring(db: Session, monitoring_id: str, payload: MonitoringPatch) -> dict:
    mon = _get_monitoring_or_404(db, monitoring_id, RPADashboardMonitoring)
    _apply_monitoring_patch(mon, payload)
    db.commit()
    db.refresh(mon)
    job = db.get(Job, mon.id_scheduler_job) if mon.id_scheduler_job else None
    return _build_monitoring_response(mon, job)


def patch_uipath_monitoring(db: Session, monitoring_id: str, payload: MonitoringPatch) -> dict:
    mon = _get_monitoring_or_404(db, monitoring_id, RPAUiPathMonitoring)
    _apply_monitoring_patch(mon, payload)
    db.commit()
    db.refresh(mon)
    job = db.get(Job, mon.id_scheduler_job) if mon.id_scheduler_job else None
    return _build_monitoring_response(mon, job)


def _apply_monitoring_patch(mon, payload: MonitoringPatch) -> None:
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


# ── DELETE monitoring ─────────────────────────────────────────────────────────

def delete_dashboard_monitoring(db: Session, monitoring_id: str) -> None:
    mon = _get_monitoring_or_404(db, monitoring_id, RPADashboardMonitoring)
    _delete_monitoring_with_job(db, mon)


def delete_uipath_monitoring(db: Session, monitoring_id: str) -> None:
    mon = _get_monitoring_or_404(db, monitoring_id, RPAUiPathMonitoring)
    _delete_monitoring_with_job(db, mon)


def _delete_monitoring_with_job(db: Session, mon) -> None:
    from app.core.scheduler import scheduler

    if mon.id_scheduler_job:
        try:
            scheduler.remove_job(mon.id_scheduler_job)
            logger.info(f"🗑️ Job '{mon.id_scheduler_job}' removido de APScheduler")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo remover job de APScheduler: {e}")

    db.delete(mon)
    db.commit()
    logger.info(f"🗑️ Monitoring eliminado | id='{mon.id}'")