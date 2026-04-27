"""
app/services/rpa_dashboard_full_service.py
===========================================
Servicio para el endpoint atómico POST /rpa-dashboard/full.

Crea en UNA sola transacción de BD:
  1. Client     (usa existente si client.id existe en BD, sino lo crea)
  2. rpa_dashboard  (bot base + business_errors como columna JSON)
  3. rpa_dashboard_monitoring (una config de monitoreo)
  4. Job en APScheduler + jobs table (solo si job.is_complete)

Rollback total si cualquier paso falla.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.rpa_dashboard import RPADashboard, RPADashboardMonitoring
from app.models.job import JobStatus, TriggerType
from app.schemas.client import ClientInlineResponse
from app.schemas.rpa_dashboard_full import (
    ClientInline,
    RPADashboardFullCreate,
    RPADashboardFullResponse,
    RPAInline
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _transaction_unit_str(tu) -> str | None:
    if tu is None:
        return None
    return f"{tu.plural}|{tu.singular}"


def _resolve_client(db: Session, client_payload: ClientInline) -> tuple[Client, bool]:
    """
    Resuelve el cliente a usar en la transacción.

    Lógica:
    - Si client.id tiene valor y existe en BD → retorna ese cliente (created=False).
    - Si client.id tiene valor pero NO existe → crea uno nuevo con ese id.
    - Si client.id es null/vacío             → crea uno nuevo con UUID auto-generado.

    Returns
    -------
    (client_obj, created)
        created = True si se creó en esta request.
    """
    client_id = client_payload.id.strip() if client_payload.id and client_payload.id.strip() else None

    # Caso 1: id proporcionado y existe en BD → reutilizar
    if client_id:
        existing = db.get(Client, client_id)
        if existing:
            logger.info(f"♻️ Usando cliente existente | id='{client_id}' | nombre='{existing.client_name}'")
            return existing, False

    # Caso 2: crear nuevo cliente
    new_id = client_id or str(uuid.uuid4())
    client = Client(
        id=new_id,
        client_name=client_payload.client_name,
        id_freshdesk=client_payload.id_freshdesk,
        id_beecker=client_payload.id_beecker,
    )
    db.add(client)
    logger.info(f"🆕 Cliente nuevo encolado | id='{new_id}' | nombre='{client_payload.client_name}'")
    return client, True


def _resolve_rpa(db: Session, rpa_payload) -> tuple[RPADashboard, bool]:
    """Resuelve el bot a usar en la transacción."""
    existing = db.get(RPADashboard, rpa_payload.id_beecker)
    if existing:
        if rpa_payload.id_dashboard and rpa_payload.id_dashboard != existing.id_dashboard:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "El bot ya existe, pero id_dashboard no coincide con el registro existente. "
                    "Envía solo id_beecker o los mismos datos completos."
                ),
            )
        if rpa_payload.process_name and rpa_payload.process_name != existing.process_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "El bot ya existe, pero process_name no coincide con el registro existente. "
                    "Envía solo id_beecker o los mismos datos completos."
                ),
            )
        if rpa_payload.platform and rpa_payload.platform != existing.platform:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "El bot ya existe, pero platform no coincide con el registro existente. "
                    "Envía solo id_beecker o los mismos datos completos."
                ),
            )

        logger.info(f"♻️ Usando bot existente | id_beecker='{rpa_payload.id_beecker}'")
        return existing, False

    missing = [
        name for name, value in {
            "id_dashboard": rpa_payload.id_dashboard,
            "process_name": rpa_payload.process_name,
            "platform": rpa_payload.platform,
        }.items() if not value
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No existe un bot con id_beecker='{rpa_payload.id_beecker}'. "
                f"Para crearlo debes enviar: {missing}."
            ),
        )

    rpa = RPADashboard(
        id_beecker=rpa_payload.id_beecker,
        id_dashboard=rpa_payload.id_dashboard,
        process_name=rpa_payload.process_name,
        platform=rpa_payload.platform,
        id_client="",
        business_errors=None,
        group_by_column=rpa_payload.group_by_column
    )
    logger.info(f"🆕 Bot nuevo encolado | id_beecker='{rpa_payload.id_beecker}'")
    return rpa, True


# ── Función principal ─────────────────────────────────────────────────────────

def create_rpa_dashboard_full(
    db: Session,
    payload: RPADashboardFullCreate,
) -> RPADashboardFullResponse:
    """
    Crea el bot completo en una única transacción atómica.

    Flujo:
        1. Validar duplicado de id_beecker.
        2. Validar job (si viene parcial → error inmediato).
        3. Resolver cliente (reutilizar o crear).
        4. Crear RPADashboard (con business_errors JSON).
        5. Crear RPADashboardMonitoring.
        6. Si job.is_complete → crear Job en APScheduler y vincularlo.
        7. db.commit() único — rollback total en fallo.

    Raises
    ------
    HTTP 400  Si job tiene campos parciales.
    HTTP 409  Si id_beecker ya existe, o colisión de unique en cliente.
    """
    from app.core.scheduler import scheduler
    from app.services.job_service import _build_trigger, _wrapped_task

    id_beecker = payload.rpa.id_beecker

    # ── 1. Validar job parcial ────────────────────────────────────────────────
    job_payload = payload.job
    has_any_job_field = job_payload and any([
        job_payload.name, job_payload.task_path,
        job_payload.trigger_type, job_payload.trigger_args,
    ])
    if has_any_job_field and not job_payload.is_complete:
        missing = [
            f for f, v in {
                "name": job_payload.name,
                "task_path": job_payload.task_path,
                "trigger_type": job_payload.trigger_type,
                "trigger_args": job_payload.trigger_args,
            }.items() if not v
        ]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El job tiene campos incompletos: {missing}. "
                   "Envía todos los campos o deja job vacío/nulo.",
        )

    # ── 3. Resolver cliente ───────────────────────────────────────────────────
    client, client_created = _resolve_client(db, payload.client)

    # ── 4. Resolver o crear el bot ─────────────────────────────────────────────
    rpa, rpa_created = _resolve_rpa(db, payload.rpa)
    if rpa_created:
        rpa.id_client = client.id
        rpa.business_errors = payload.rpa.business_errors or None
        db.add(rpa)

    # ── 5. Construir monitoring ───────────────────────────────────────────────
    monitoring_id = str(uuid.uuid4())
    mon = RPADashboardMonitoring(
        id=monitoring_id,
        id_beecker=id_beecker,
        monitor_type=payload.monitor_type,
        slack_channel=payload.slack_channel,
        transaction_unit=_transaction_unit_str(payload.transaction_unit),
        roc_agents=payload.roc_agents,
        manage_flags=payload.manage_flags.model_dump() if payload.manage_flags else None,
        id_scheduler_job=None,
    )
    db.add(mon)

    # ── 6. Crear Job (opcional) ───────────────────────────────────────────────
    job_created = False
    aps_job_id = None

    if job_payload and job_payload.is_complete:
        from app.models.job import Job

        job_id = str(uuid.uuid4())
        trigger_type = TriggerType(job_payload.trigger_type)
        trigger = _build_trigger(trigger_type, job_payload.trigger_args)

        job_kwargs = {
            **(job_payload.job_kwargs or {}),
            "bot_id": id_beecker,
            "monitoring_id": monitoring_id,
        }

        try:
            scheduler.add_job(
                func=_wrapped_task,
                trigger=trigger,
                id=job_id,
                name=job_payload.name,
                kwargs={"job_id": job_id, "task_path": job_payload.task_path, **job_kwargs},
                replace_existing=True,
            )
            scheduler.pause_job(job_id)
            aps_job_id = job_id
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error al registrar el job en APScheduler: {exc}",
            )

        db_job = Job(
            id=job_id,
            name=job_payload.name,
            description=f"Job auto-creado para {id_beecker}",
            task_path=job_payload.task_path,
            trigger_type=trigger_type,
            trigger_args=job_payload.trigger_args,
            job_kwargs=job_kwargs,
            status=JobStatus.paused,
            next_run_time=None,
        )
        db.add(db_job)
        mon.id_scheduler_job = job_id
        job_created = True

        logger.info(
            f"📅 Job creado y vinculado | job_id='{job_id}' | "
            f"monitoring_id='{monitoring_id}' | bot='{id_beecker}'"
        )

    # ── 7. Commit único ───────────────────────────────────────────────────────
    try:
        db.commit()
        db.refresh(client)
        db.refresh(rpa)
        db.refresh(mon)
    except IntegrityError as exc:
        db.rollback()
        if aps_job_id:
            try:
                scheduler.remove_job(aps_job_id)
            except Exception:
                pass
        msg = str(exc.orig).lower() if exc.orig else ""
        if "id_freshdesk" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Ya existe un cliente con ese id_freshdesk.")
        if "id_beecker" in msg and "client" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Ya existe un cliente con ese id_beecker.")
        if "id_beecker" in msg or "primary" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"Ya existe un bot con id_beecker='{id_beecker}'.")
        if "client_name" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Ya existe un cliente con ese nombre.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Error de integridad en BD: {exc.orig}")

    logger.info(
        f"✅ Bot creado de forma atómica | id_beecker='{id_beecker}' | "
        f"client_id='{client.id}' | client_created={client_created} | "
        f"job_created={job_created}"
    )

    # ── 8. Construir respuesta ────────────────────────────────────────────────
    return RPADashboardFullResponse(
        client=ClientInlineResponse(
            id=client.id,
            client_name=client.client_name,
            id_freshdesk=client.id_freshdesk,
            id_beecker=client.id_beecker,
            created=client_created,
        ),
        rpa=RPAInline(
            id_beecker=rpa.id_beecker,
            id_dashboard=rpa.id_dashboard,
            process_name=rpa.process_name,
            platform=rpa.platform,
            group_by_column=rpa.group_by_column,
            business_errors=rpa.business_errors,
        ),
        monitoring={
            "id": mon.id,
            "id_rpa": mon.id_beecker,
            "monitor_type": mon.monitor_type,
            "slack_channel": mon.slack_channel,
            "transaction_unit": mon.transaction_unit,
            "roc_agents": mon.roc_agents,
            "manage_flags": mon.manage_flags,
            "id_scheduler_job": mon.id_scheduler_job,
        },
        job_created=job_created,
    )
