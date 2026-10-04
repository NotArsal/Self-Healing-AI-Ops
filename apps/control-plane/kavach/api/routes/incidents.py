import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from kavach.api.store import (
    broadcast_event,
    create_incident,
    get_all_incidents,
    get_incident,
    update_incident,
)
from kavach.graph.workflow import build_workflow
from kavach.scenarios.loader import load_scenario

router = APIRouter(prefix="/incidents", tags=["incidents"])

class RunScenarioRequest(BaseModel):
    scenario_name: str

async def execute_graph_background(incident_id: str, initial_state: dict[str, Any]) -> None:
    app = build_workflow()
    
    # Broadcast incident start
    scenario_obj = initial_state.get("scenario")
    await broadcast_event({
        "type": "incident_created",
        "incident_id": incident_id,
        "scenario": scenario_obj.id if scenario_obj else "unknown"
    })
    
    # Iterate through graph transitions
    async for event in app.astream(initial_state):
        # event is typically a dict mapping node_name -> node_output
        for node_name, node_state in event.items():
            # Merge state back to store
            update_incident(incident_id, node_state)
            
            # Broadcast node completion
            await broadcast_event({
                "type": "node_completed",
                "incident_id": incident_id,
                "node": node_name,
                "state": get_incident(incident_id) # Send full merged state for simplicity
            })
            
            # Add artificial delay to simulate real-world operations and make console watchable
            await asyncio.sleep(1.0)


@router.post("/run")
async def run_scenario(req: RunScenarioRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    try:
        scenario = load_scenario(req.scenario_name)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(e))
        
    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy() if scenario.state else {}
    }
    
    incident_id = create_incident(scenario.id, initial_state)
    
    background_tasks.add_task(execute_graph_background, incident_id, initial_state)
    
    return {"incident_id": incident_id, "status": "started"}

@router.get("")
async def list_incidents() -> dict[str, Any]:
    # Return light version
    incidents = {}
    for i_id, state in get_all_incidents().items():
        scenario_obj = state.get("scenario")
        incidents[i_id] = {
            "scenario": scenario_obj.id if scenario_obj else None,
            "outcome": state.get("outcome", "IN_PROGRESS"),
            "fault_class": state.get("fault_class")
        }
    return incidents

@router.get("/{incident_id}")
async def get_incident_detail(incident_id: str) -> dict[str, Any]:
    state = get_incident(incident_id)
    if not state:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    # Remove scenario object from state payload for UI, keep needed fields
    ui_state = state.copy()
    if "scenario" in ui_state:
        ui_state["scenario_id"] = ui_state["scenario"].id
        ui_state["evidence"] = [e.model_dump() for e in ui_state["scenario"].evidence] if ui_state["scenario"].evidence else []
        del ui_state["scenario"]
        
    return ui_state
