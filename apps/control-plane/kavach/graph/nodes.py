from kavach.graph.state import IncidentState
from kavach.llm.rca import analyze_root_cause
from kavach.simulation.executor import execute_action
from kavach.tnr.models import Action
from kavach.verification.probes import verify_state


def detect_node(state: IncidentState) -> IncidentState:
    # Just transitions to diagnose
    return {}


def diagnose_node(state: IncidentState) -> IncidentState:
    scenario = state["scenario"]
    diagnosis = analyze_root_cause(scenario)
    return {"diagnosis": diagnosis, "fault_class": diagnosis.fault_class}


from kavach.catalogue.loader import load_catalogue

def plan_node(state: IncidentState) -> IncidentState:
    fault = state.get("fault_class")
    plan = []
    
    catalogue = load_catalogue()
    
    if fault and fault in catalogue.faults:
        # Generate plan based on recommended actions
        f_def = catalogue.faults[fault]
        for act_name in f_def.recommended_actions:
            if act_name == "switch_model":
                # For now, hardcode parameter injection logic for specific actions 
                # (A full templating engine is out of scope for MVP, but the pipeline logic is declarative)
                plan.append(
                    Action(
                        name="switch_model",
                        params={"target": "model_primary", "fallback": "model_backup"},
                    )
                )
            else:
                # Generic action with no params
                plan.append(Action(name=act_name, params={}))

    return {"plan": plan}


def gate_node(state: IncidentState) -> IncidentState:
    scenario = state["scenario"]
    loop_count = state.get("loop_count", 0) + 1
    
    # 1. Circuit Breaker
    if loop_count > 3:
        return {
            "loop_count": loop_count,
            "gate_verdict": "DENY",
            "gate_reason": "CIRCUIT_BREAKER_TRIPPED",
            "approved_actions": []
        }

    allowed = scenario.permissions.allowed_actions if scenario.permissions else []
    plan = state.get("plan", [])
    
    if not plan:
        return {
            "loop_count": loop_count,
            "gate_verdict": "DENY",
            "gate_reason": "EMPTY_PLAN",
            "approved_actions": []
        }
        
    # 2. Blast Radius Check
    # For now, simplistic rule: max 2 actions allowed concurrently
    if len(plan) > 2:
        return {
            "loop_count": loop_count,
            "gate_verdict": "DENY",
            "gate_reason": "BLAST_RADIUS_EXCEEDED",
            "approved_actions": []
        }

    # 3. Allow-list Check
    approved = []
    for action in plan:
        if action.name in allowed:
            approved.append(action)
        else:
            return {
                "loop_count": loop_count,
                "gate_verdict": "DENY",
                "gate_reason": f"UNAPPROVED_ACTION_{action.name.upper()}",
                "approved_actions": []
            }

    return {
        "loop_count": loop_count,
        "gate_verdict": "ALLOW",
        "gate_reason": "PASSED",
        "approved_actions": approved
    }


def execute_node(state: IncidentState) -> IncidentState:
    sim_state = state.get("simulation_state", {}).copy()
    undo_records = []

    for action in state.get("approved_actions", []):
        record = execute_action(action, sim_state)
        undo_records.append(record)

    return {"simulation_state": sim_state, "undo_stack": undo_records}


def verify_node(state: IncidentState) -> IncidentState:
    passed, deltas = verify_state(state["scenario"], state.get("simulation_state", {}))
    return {"verification_passed": passed, "verification_deltas": deltas}


def unwind_node(state: IncidentState) -> IncidentState:
    sim_state = state.get("simulation_state", {}).copy()
    undo_stack = state.get("undo_stack", [])

    # Process LIFO
    for record in reversed(undo_stack):
        if record.applied:
            execute_action(record.inverse_action, sim_state)

    # Clear the stack since it's unwound (in real system we append to audit, here we just return state change)
    return {"simulation_state": sim_state}


def outcome_node(state: IncidentState) -> IncidentState:
    # Check if we bypassed planning due to low confidence
    diag = state.get("diagnosis")
    if diag and (diag.confidence < 0.8 or diag.fault_class == "INSUFFICIENT_EVIDENCE"):
        return {"outcome": "ESCALATED"}
        
    force_undo_fail = (
        state.get("simulation_state", {}).get("_force_undo_failure") == "true"
    )
    if force_undo_fail:
        return {"outcome": "UNRECOVERABLE"}

    # Check if gate blocked execution
    if state.get("gate_verdict") == "DENY":
        return {"outcome": "ESCALATED"}

    passed = state.get("verification_passed", False)
    if passed:
        # F01 usually results in MITIGATED because primary is still down, just backup is active.
        return {"outcome": "MITIGATED"}
    else:
        return {"outcome": "ESCALATED"}
