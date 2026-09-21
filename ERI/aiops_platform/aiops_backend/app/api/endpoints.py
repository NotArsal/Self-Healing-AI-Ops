from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from app.managers.incident import incident_manager
from app.core.detector import failure_detector

router = APIRouter()


# ─── Incident Endpoints ───────────────────────────────────────────────────────

@router.get("/incidents")
def get_incidents():
    return {"incidents": incident_manager.list_incidents()}


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str):
    inc = incident_manager.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc


@router.post("/trigger_detection")
def trigger_detection():
    failure_detector.check_for_failures()
    return {"status": "Detection cycle completed"}


# ─── Orchestration Endpoints ──────────────────────────────────────────────────

class OrchestrateRequest(BaseModel):
    incident_id: str


def _run_orchestration(incident_id: str):
    """Background task: invoke the LangGraph workflow for a given incident."""
    # Import here to avoid circular imports at module load
    from app.orchestrator.graph import orchestrator_graph

    inc = incident_manager.get_incident(incident_id)
    if not inc:
        return

    incident_manager.update_incident_status(incident_id, "INVESTIGATING")

    initial_state = {
        "incident_id": inc.id,
        "affected_service": inc.affected_service,
        "failure_type": inc.failure_type,
        "severity": inc.severity,
        "timestamp": inc.timestamp,
    }

    final_state = orchestrator_graph.invoke(initial_state)

    # Persist key results back to the incident record
    incident_manager.update_incident_status(
        incident_id,
        final_state.get("final_status", "ESCALATED"),
        hypothesis=final_state.get("top_hypothesis"),
        action=final_state.get("execution_result"),
    )


@router.post("/orchestrate")
async def orchestrate_incident(req: OrchestrateRequest, background_tasks: BackgroundTasks):
    """
    Kick off the full LangGraph heal-loop asynchronously.
    The incident status is updated in real-time as each node completes.
    """
    inc = incident_manager.get_incident(req.incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    background_tasks.add_task(_run_orchestration, req.incident_id)
    return {"status": "Orchestration started", "incident_id": req.incident_id}
