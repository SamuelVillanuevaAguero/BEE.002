import uuid

from app.models.automation import (
    Client,
    RPADashboard,
    RPADashboardMonitoring,
    RPAUiPath,
    RPAUiPathMonitoring,
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
    id_dashboard = ID numérico para la API de Beecker (ej: "104").
    business_errors = lista JSON opcional (ej: ["Business Exception"]).
    """
    rpa = RPADashboard(
        id_beecker=payload.id_beecker,
        id_dashboard=payload.id_dashboard,
        process_name=payload.process_name,
        platform=payload.platform,
        id_client=payload.id_client,
        business_errors=payload.business_errors or None,
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
    id_beecker → rpa_dashboard.id_beecker (ej: "AEC.001")
    """
    relation = RPADashboardMonitoring(
        id=str(uuid.uuid4()),
        id_beecker=payload.id_beecker,
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
# RPA UIPATH
# ---------------------------------------------------------
def create_rpa_uipath(db, payload):

    rpa = RPAUiPath(
        uipath_robot_name=payload.uipath_robot_name,
        id_beecker=payload.id_beecker,
        beecker_name=payload.beecker_name,
        framework=payload.framework,
        id_client=payload.id_client,
        business_errors=payload.business_errors or None,
    )

    db.add(rpa)
    db.commit()
    db.refresh(rpa)

    return rpa


# ---------------------------------------------------------
# RPA UIPATH MONITORING CONFIG
# ---------------------------------------------------------
def link_rpa_uipath_monitoring(db, payload):

    relation = RPAUiPathMonitoring(
        id=str(uuid.uuid4()),
        uipath_robot_name=payload.uipath_robot_name,
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