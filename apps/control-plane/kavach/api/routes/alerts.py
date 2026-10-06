from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from kavach.api.routes.incidents import execute_graph_background
from kavach.api.store import create_incident
from kavach.scenarios.loader import load_scenario
from kavach.triage.router import classify_alert

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertAnnotation(BaseModel):
    description: str | None = None


class AlertItem(BaseModel):
    labels: dict[str, str] = {}
    annotations: AlertAnnotation = AlertAnnotation()


class WebhookPayload(BaseModel):
    status: str
    alerts: list[AlertItem] = []


@router.post("/webhook")
async def receive_alert(
    payload: WebhookPayload, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    if payload.status != "firing":
        return {"status": "ignored", "reason": "not firing"}

    # Combine alert descriptions
    descriptions = [
        a.annotations.description for a in payload.alerts if a.annotations.description
    ]
    if not descriptions:
        return {"status": "ignored", "reason": "no descriptions provided"}

    combined_text = " | ".join(descriptions)

    # 1. Laya Triage
    category = classify_alert(combined_text)

    # 2. Trigger Actionable Incidents
    # We use F10 to simulate a safe remediation for application alerts
    if category == "application":
        scenario_name = "F10"
    elif category == "database":
        # We use F11 to simulate an unsafe destructive attempt
        scenario_name = "F11"
    else:
        # Ignore network or unknown noise for this test
        return {"status": "triaged", "category": category, "action": "ignored"}

    try:
        scenario = load_scenario(scenario_name)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load scenario {scenario_name}: {e}"
        )

    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy() if scenario.state else {},
    }

    incident_id = create_incident(scenario.id, initial_state)
    background_tasks.add_task(execute_graph_background, incident_id, initial_state)

    return {"status": "triggered", "category": category, "incident_id": incident_id}
