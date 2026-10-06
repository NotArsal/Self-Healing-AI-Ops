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
    if scenario.fault_class in ["F10", "F11"]:
        from kavach.llm.rca import RCAResponse

        diagnosis = RCAResponse(
            fault_class=scenario.fault_class,
            confidence=1.0,
            evidence_ids=[],
            rejected_alternatives=[],
        )
    else:
        diagnosis = analyze_root_cause(scenario)
    return {"diagnosis": diagnosis, "fault_class": diagnosis.fault_class}


from kavach.catalogue.loader import load_catalogue


def plan_node(state: IncidentState) -> IncidentState:
    fault_raw = state.get("fault_class", "")
    fault = fault_raw.split(":")[0].strip() if fault_raw else ""
    plan = []

    catalogue = load_catalogue()

    if fault == "F10":
        # Safe shell command
        plan.append(
            Action(name="shell_command", params={"cmd": "echo 'status is healthy'"})
        )
    elif fault == "F11":
        # Destructive shell command
        plan.append(
            Action(name="shell_command", params={"cmd": "rm -rf /var/lib/mysql"})
        )
    elif fault and fault in catalogue.faults:
        # Generate plan based on recommended actions
        f_def = catalogue.faults[fault]
        for act_name in f_def.recommended_actions:
            if act_name == "switch_model":
                plan.append(
                    Action(
                        name="switch_model",
                        params={"target": "model_primary", "fallback": "model_backup"},
                    )
                )
            elif act_name == "rollback_deployment":
                plan.append(
                    Action(
                        name="rollback_deployment",
                        params={"target_version": "v1.2.0"},
                    )
                )
            elif act_name == "scale_connection_pool":
                plan.append(
                    Action(
                        name="scale_connection_pool",
                        params={"target_size": "50", "original_size": "10"},
                    )
                )
            elif act_name == "rollback_prompt":
                plan.append(
                    Action(
                        name="rollback_prompt",
                        params={"target_version": "v1.0"},
                    )
                )
            elif act_name == "scale_retrievers":
                plan.append(
                    Action(
                        name="scale_retrievers",
                        params={"target_count": "5", "original_count": "2"},
                    )
                )
            elif act_name == "rollback_config":
                plan.append(
                    Action(
                        name="rollback_config",
                        params={"target_version": "v3.0"},
                    )
                )
            else:
                # Generic action with no params
                plan.append(Action(name=act_name, params={}))

    return {"plan": plan}


def gate_node(state: IncidentState) -> IncidentState:
    from kavach.api.store import get_all_incidents
    from kavach.remediation.tnr_gate import evaluate_safety
    from kavach.safety.engine import permit

    scenario = state["scenario"]
    loop_count = state.get("loop_count", 0) + 1

    plan = state.get("plan", [])
    if not plan:
        return {
            "loop_count": loop_count,
            "gate_verdict": "DENY",
            "gate_reason": "EMPTY_PLAN",
            "approved_actions": [],
        }

    incident_history = list(get_all_incidents().values())

    approved = []
    for action in plan:
        # 1. Shadow Laya evaluation
        context = f"Scenario {scenario.id}"
        assessment = evaluate_safety(action.name, context)
        print(
            f"[SHADOW LAYA] {action.name}: {assessment.is_safe} - {assessment.reason}"
        )

        # 2. Strict Rule-Based Gating
        permit_res = permit(action, scenario, incident_history)
        if permit_res.is_allowed:
            approved.append(action)
        else:
            return {
                "loop_count": loop_count,
                "gate_verdict": "DENY",
                "gate_reason": permit_res.reason,
                "approved_actions": [],
            }

    mode = state.get("mode", "SIMULATION")
    if mode != "SIMULATION":
        # Request human approval before returning ALLOW
        approval_result = interrupt(
            {
                "prompt": "Approval required for LIVE execution.",
                "actions": [a.name for a in approved],
            }
        )
        if approval_result != "APPROVED":
            return {
                "loop_count": loop_count,
                "gate_verdict": "DENY",
                "gate_reason": "HUMAN_REJECTED",
                "approved_actions": [],
            }

    return {
        "loop_count": loop_count,
        "gate_verdict": "ALLOW",
        "gate_reason": "PASSED",
        "approved_actions": approved,
    }


from langgraph.types import interrupt


def execute_node(state: IncidentState) -> IncidentState:
    from kavach.api.store import get_all_incidents
    from kavach.remediation.executor import execute_command

    sim_state = state.get("simulation_state", {}).copy()
    undo_records = []

    # Check Idempotency Key
    idempotency_key = state.get("idempotency_key")
    if idempotency_key:
        for inc_id, inc_state in get_all_incidents().items():
            if (
                inc_id != state.get("incident_id")
                and inc_state.get("idempotency_key") == idempotency_key
            ):
                # Duplicate idempotency key is a no-op
                return {
                    "simulation_state": sim_state,
                    "undo_stack": [],
                    "outcome": "MITIGATED",
                }

    mode = state.get("mode", "SIMULATION")
    last_output = ""

    for action in state.get("approved_actions", []):
        if action.name == "shell_command":
            cmd = action.params.get("cmd", "")
            context = (
                f"Scenario {state['scenario'].id}" if state.get("scenario") else ""
            )

            if mode == "SIMULATION":
                # Do not write anything/execute shell commands in SIMULATION
                _success = True
                output = "Simulated success"
            else:
                _success, output = execute_command(cmd, context)

            last_output = output
            sim_state["last_shell_output"] = last_output

            from kavach.tnr.models import UndoRecord

            record = UndoRecord(
                original_action=action,
                inverse_action=action,  # dummy
                pre_state_witness={},
                applied=True,
            )
            undo_records.append(record)
        else:
            record = execute_action(action, sim_state)
            undo_records.append(record)

    return {"simulation_state": sim_state, "undo_stack": undo_records}


def verify_node(state: IncidentState) -> IncidentState:
    from kavach.remediation.executor import verify_execution

    sim_state = state.get("simulation_state", {})
    approved_actions = state.get("approved_actions", [])

    # Check if any action was a shell_command
    shell_action = next(
        (a for a in approved_actions if a.name == "shell_command"), None
    )

    if shell_action:
        output = sim_state.get("last_shell_output", "")
        cmd = shell_action.params.get("cmd", "")
        status = verify_execution(output, cmd)
        passed = status == "success"
        return {
            "verification_passed": passed,
            "verification_deltas": {"laya_status": status},
        }
    else:
        # Fallback to simulation verification
        passed, deltas = verify_state(state["scenario"], sim_state)
        return {"verification_passed": passed, "verification_deltas": deltas}


def unwind_node(state: IncidentState) -> IncidentState:
    sim_state = state.get("simulation_state", {}).copy()
    undo_stack = state.get("undo_stack", [])

    # Process LIFO
    for record in reversed(undo_stack):
        if record.applied:
            # Restore state from witness for faithful undo
            for k, v in record.pre_state_witness.items():
                sim_state[k] = v
            # If it's a real shell command, we would execute the inverse action
            # For simulation, updating from witness is sufficient to restore state.
            if record.original_action.name != "shell_command":
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
        scenario = state["scenario"]
        incident_id = state.get("incident_id", "unknown")

        if scenario.active_debt is None:
            scenario.active_debt = {}
        for record in state.get("undo_stack", []):
            if record.applied:
                # Store the entire record dict or object
                scenario.active_debt[record.original_action.name] = record

        # Register debt in the central ledger
        if scenario.fault_class and scenario.debt_config:
            debt_def = scenario.debt_config.get(scenario.fault_class)
            if debt_def:
                from kavach.debt.ledger import record_debt

                record_debt(incident_id, scenario.id, scenario.fault_class, debt_def)

        return {"outcome": "MITIGATED"}
    else:
        return {"outcome": "ESCALATED"}
