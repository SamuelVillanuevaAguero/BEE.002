import uuid

from app.models.automation import (
    Client,
    RPADashboard,
    RPADashboardMonitoring,
    RPADashboardBusinessError
)


# ---------------------------------------------------------
# CLIENT
# ---------------------------------------------------------
def create_client(db, client_name: str):

    client = Client(client_name=client_name)

    db.add(client)
    db.commit()
    db.refresh(client)

    return client


# ---------------------------------------------------------
# RPA DASHBOARD
# ---------------------------------------------------------
def create_rpa_dashboard(db, payload):
    """
    Crea el registro base en rpa_dashboard.
    PK = id_beecker (ej: "AEC.001").
    id_dashboard = ID numérico para la API de Beecker (ej: "114").
    """
    rpa = RPADashboard(
        id_beecker=payload.id_beecker,
        id_dashboard=payload.id_dashboard,
        process_name=payload.process_name,
        platform=payload.platform,
        id_client=payload.id_client,
    )

    db.add(rpa)
    db.commit()
    db.refresh(rpa)

    return rpa


# ---------------------------------------------------------
# RPA DASHBOARD MONITORING CONFIG
# ---------------------------------------------------------
def link_rpa_dashboard_monitoring(db, payload):
    """
    Crea el registro de configuración en rpa_dashboard_monitoring.
    id_rpa → rpa_dashboard.id_beecker (ej: "AEC.001")
    """
    relation = RPADashboardMonitoring(
        id=str(uuid.uuid4()),
        id_rpa=payload.id_beecker,
        monitor_type=payload.monitor_type,
        transaction_unit=payload.transaction_unit,
        slack_channel=payload.slack_channel,
        manage_flags=payload.manage_flags,
        roc_agents=payload.roc_agents,
        id_scheduler_job=payload.id_scheduler_job,
    )

    db.add(relation)
    db.commit()

    return relation


# ---------------------------------------------------------
# RPA DASHBOARD BUSINESS ERROR
# ---------------------------------------------------------
def add_rpa_dashboard_business_error(db, id_beecker: str, error_message: str):
    """
    Registra un error de negocio para el RPA indicado.
    id_platform → rpa_dashboard.id_beecker (ej: "AEC.001")
    """
    error = RPADashboardBusinessError(
        id=str(uuid.uuid4()),
        id_platform=id_beecker,
        error_message=error_message,
    )

    db.add(error)
    db.commit()

    return error