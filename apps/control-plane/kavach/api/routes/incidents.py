import asyncio
import logging
from datetime import UTC
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


async def execute_graph_background(
    incident_id: str, initial_state: dict[str, Any]
) -> None:
    app = build_workflow()

    import time
    from datetime import datetime

    started_at = datetime.now(UTC)
    start_t = time.time()

    # Broadcast incident start
    scenario_obj = initial_state.get("scenario")
    await broadcast_event(
        {
            "type": "incident_created",
            "incident_id": incident_id,
            "scenario": scenario_obj.id if scenario_obj else "unknown",
        }
    )

    # Iterate through graph transitions
    async for event in app.astream(initial_state):
        # event is typically a dict mapping node_name -> node_output
        for node_name, node_state in event.items():
            # Merge state back to store
            update_incident(incident_id, node_state)

            # Broadcast node completion
            await broadcast_event(
                {
                    "type": "node_completed",
                    "incident_id": incident_id,
                    "node": node_name,
                    "state": get_incident(
                        incident_id
                    ),  # Send full merged state for simplicity
                }
            )

            # Add artificial delay to simulate real-world operations and make console watchable
            await asyncio.sleep(1.0)

    # End of graph execution: record MTTR metrics and Remediation Debt
    final_state = get_incident(incident_id)
    if final_state:
        outcome = final_state.get("outcome", "UNKNOWN")
        fault_class = final_state.get("fault_class", "UNKNOWN")
        duration_ms = int((time.time() - start_t) * 1000)
        resolved_at = datetime.now(UTC)

        # Check if we need to record debt
        scenario_after = final_state.get("scenario")
        if (
            scenario_after
            and hasattr(scenario_after, "active_debt_def")
            and scenario_after.active_debt_def
        ):
            from kavach.debt.ledger import record_debt_async

            # Find the params from active_debt (undo_stack inverse)
            action_params: dict[str, Any] = {}
            if scenario_after.active_debt:
                record = next(iter(scenario_after.active_debt.values()))
                action_params = (
                    record.inverse_action.params
                    if hasattr(record, "inverse_action")
                    else {}
                )

            # Use the repayment action from the debt definition
            debt_def = scenario_after.active_debt_def
            action_name = (
                debt_def.repayment_action
                if hasattr(debt_def, "repayment_action")
                else "unknown"
            )

            try:
                await record_debt_async(
                    incident_id, action_name, action_params, debt_def
                )
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "Failed to record debt for %s: %s", incident_id, e
                )

        try:
            from sqlalchemy import text

            from kavach.api.db import get_db_session

            async with get_db_session() as session:
                await session.execute(
                    text(
                        "INSERT INTO incident_metrics (incident_id, started_at, resolved_at, duration_ms, outcome, fault_class) "
                        "VALUES (:id, :start, :res, :dur, :out, :fc)"
                    ),
                    {
                        "id": incident_id,
                        "start": started_at,
                        "res": resolved_at,
                        "dur": duration_ms,
                        "out": outcome,
                        "fc": fault_class,
                    },
                )
                await session.commit()
        except Exception as e:
            logging.getLogger(__name__).warning(
                "Failed to record incident metrics to database: %s", e
            )


@router.post("/run")
async def run_scenario(
    req: RunScenarioRequest, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    try:
        scenario = load_scenario(req.scenario_name)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(e))

    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy() if scenario.state else {},
    }

    incident_id = create_incident(scenario.id, initial_state)
    initial_state["incident_id"] = incident_id
    update_incident(incident_id, initial_state)

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
            "fault_class": state.get("fault_class"),
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
        ui_state["evidence"] = (
            [e.model_dump() for e in ui_state["scenario"].evidence]
            if ui_state["scenario"].evidence
            else []
        )
        ui_state["debt"] = (
            ui_state["scenario"].active_debt.copy()
            if ui_state["scenario"].active_debt
            else {}
        )
        ui_state["services"] = (
            {k: v.model_dump() for k, v in ui_state["scenario"].services.items()}
            if ui_state["scenario"].services
            else {}
        )
        del ui_state["scenario"]

    return ui_state


@router.post("/{incident_id}/repay-debt")
async def repay_debt_endpoint(incident_id: str) -> dict[str, Any]:
    from kavach.debt.repayment import repay_debt

    state = get_incident(incident_id)
    if not state:
        raise HTTPException(status_code=404, detail="Incident not found")

    scenario = state.get("scenario")
    sim_state = state.get("simulation_state", {})

    if not scenario or not scenario.active_debt:
        raise HTTPException(status_code=400, detail="No active debt for this incident")

    # We simulate fixing the original fault by reverting the `healthy` status in sim_state to what it should be
    # For example, if it's F01, we set model_primary to healthy.
    # To be generic, let's just make the whole state "healthy" or "normal" or "clean".
    for k in list(sim_state.keys()):
        if "health" in k or k == "model_primary":
            sim_state[k] = "healthy"
        if k == "provider_latency":
            sim_state[k] = "normal"
        if k == "cache_state":
            sim_state[k] = "clean"

    debt_def = (
        scenario.debt_config.get(scenario.fault_class) if scenario.debt_config else None
    )
    # The hasattr chain here is what silently substituted "unknown" when the debt
    # arrived as a plain dict; outcome_node now parses it into DebtItemDef, so the
    # typed attribute is the normal path and the dict is the compatibility one.
    if isinstance(debt_def, dict):
        repayment_action = str(debt_def.get("repayment_action") or "restore_model")
    elif debt_def is not None and hasattr(debt_def, "repayment_action"):
        repayment_action = str(debt_def.repayment_action)
    else:
        repayment_action = "restore_model"

    success = repay_debt(scenario, sim_state, repayment_action)
    if success:
        from kavach.debt.ledger import clear_debt_async

        await clear_debt_async(incident_id)
        update_incident(
            incident_id, {"simulation_state": sim_state, "outcome": "RESOLVED"}
        )
        await broadcast_event(
            {
                "type": "debt_repaid",
                "incident_id": incident_id,
                "state": get_incident(incident_id),
            }
        )
        return {"status": "repaid"}
    else:
        raise HTTPException(
            status_code=400, detail="Debt repayment failed verification"
        )
