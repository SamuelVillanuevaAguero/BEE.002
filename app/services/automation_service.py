from app.models.automation import (
    Client,

    RPADashboard,
    RPADashboardClient,
    RPADashboardBusinessError,

    RPAUiPath,
    RPAUiPathClient,
    RPAUiPathBusinessError,

    Agent,
    AgentClient,
    AgentStateError
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

    rpa = RPADashboard(
        id_rpa=payload.id_rpa,
        id_beecker=payload.id_beecker,
        process_name=payload.process_name,
        platform=payload.platform
    )

    db.add(rpa)
    db.commit()
    db.refresh(rpa)

    return rpa


# ---------------------------------------------------------
# RPA DASHBOARD CLIENT CONFIG
# ---------------------------------------------------------
def link_rpa_dashboard_client(db, payload):

    relation = RPADashboardClient(
        id_rpa=payload.id_rpa,
        id_client=payload.id_client,
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
def add_rpa_dashboard_business_error(db, id_rpa: str, error_message: str):

    error = RPADashboardBusinessError(
        id_rpa=id_rpa,
        error_message=error_message
    )

    db.add(error)
    db.commit()

    return error


# ---------------------------------------------------------
# RPA UIPATH
# ---------------------------------------------------------
def create_rpa_uipath(db, payload):

    rpa = RPAUiPath(
        id_rpa=payload.id_rpa,
        id_beecker=payload.id_beecker,
        framework=payload.framework,
        robot_name=payload.robot_name,
        process_name=payload.process_name
    )

    db.add(rpa)
    db.commit()
    db.refresh(rpa)

    return rpa


# ---------------------------------------------------------
# RPA UIPATH CLIENT CONFIG
# ---------------------------------------------------------
def link_rpa_uipath_client(db, payload):

    relation = RPAUiPathClient(
        id_rpa=payload.id_rpa,
        id_client=payload.id_client,
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
# RPA UIPATH BUSINESS ERROR
# ---------------------------------------------------------
def add_rpa_uipath_business_error(db, id_rpa: str, error_message: str):

    error = RPAUiPathBusinessError(
        id_rpa=id_rpa,
        error_message=error_message
    )

    db.add(error)
    db.commit()

    return error


# ---------------------------------------------------------
# AGENT
# ---------------------------------------------------------
def create_agent(db, payload):

    agent = Agent(
        id_agent=payload.id_agent,
        id_beecker=payload.id_beecker,
        process_name=payload.process_name,
        platform=payload.platform
    )

    db.add(agent)
    db.commit()
    db.refresh(agent)

    return agent


# ---------------------------------------------------------
# AGENT CLIENT CONFIG
# ---------------------------------------------------------
def link_agent_client(db, payload):

    relation = AgentClient(
        id_agent=payload.id_agent,
        id_client=payload.id_client,
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
# AGENT STATE ERROR
# ---------------------------------------------------------
def add_agent_state_error(db, id_agent: str, state_name: str):

    error = AgentStateError(
        id_agent=id_agent,
        state_name=state_name
    )

    db.add(error)
    db.commit()

    return error