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

    # Extract optional target path from annotations for dynamic loading
    target_path = None
    for a in payload.alerts:
        if a.annotations.description and "target=" in a.annotations.description:
            parts = a.annotations.description.split("target=")
            if len(parts) > 1:
                target_path = parts[1].split()[0]
                break

    # 2. Trigger Actionable Incidents
    if target_path:
        # Dynamic loading for Phase 9b
        from kavach.scenarios.loader import load_scenario_from_yaml

        try:
            # We mock the scenario wrapper for the graph to run
            scenario = load_scenario_from_yaml(target_path)
            scenario.id = f"dynamic-{category}"
            if not scenario.fault_class:
                scenario.fault_class = "F01"  # Default assumption
            if not scenario.evidence:
                scenario.evidence = []
            if not scenario.state:
                scenario.state = {}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to load target {target_path}: {e}"
            )
    else:
        # Fallback to hardcoded scenarios
        if category == "application":
            scenario_name = "F10"
        elif category == "database":
            scenario_name = "F11"
        else:
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
