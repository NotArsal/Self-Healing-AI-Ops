from kavach.graph.state import IncidentState
from kavach.llm.rca import analyze_root_cause
from kavach.simulation.executor import execute_action
from kavach.tnr.models import Action
from kavach.verification.probes import verify_state


def detect_node(state: IncidentState) -> IncidentState:
    # Future: parallel evidence gathering (e.g. telemetry)
    return {}


def diagnose_node(state: IncidentState) -> IncidentState:
    import asyncio
    from kavach.api.db import get_db_session
    from kavach.knowledge.retrieval import retrieve_similar_incidents
    from kavach.scenarios.schema import EvidenceItem

    scenario = state["scenario"]
    
    # Retrieve past incidents as evidence
    async def _fetch():
        try:
            async with get_db_session() as session:
                query_text = f"Fault: {scenario.fault_class}\nSymptoms: {scenario.trigger.condition if scenario.trigger else ''}"
                return await retrieve_similar_incidents(session, query_text)
        except Exception as e:
            import logging
            logging.warning(f"Failed to query knowledge base: {e}")
            return []

    try:
        past_incidents = asyncio.run(_fetch())
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            past_incidents = loop.run_until_complete(_fetch())
        except Exception:
            past_incidents = []

    for inc in past_incidents:
        scenario.evidence.append(EvidenceItem(
            source="kavach_memory",
            kind="log",
            content=f"Past Incident {inc.id}: {inc.summary}\nRepair Action: {inc.repair_action}\nOutcome: {inc.outcome}"
        ))

    if scenario.fault_class in ["F10", "F11"]:
        from kavach.llm.rca import RCAResponse

        diagnosis = RCAResponse(
            fault_class=scenario.fault_class,
            confidence=1.0,
            evidence_ids=[],
            rejected_alternatives=[],
        )
    else:
        app_roles = None
        if scenario.services:
            app_roles = {s.role for s in scenario.services.values()}
        diagnosis = analyze_root_cause(scenario, app_roles=app_roles)
        
    return {"diagnosis": diagnosis, "fault_class": diagnosis.fault_class}


from kavach.catalogue.loader import load_catalogue


def plan_node(state: IncidentState) -> IncidentState:
    fault_raw = state.get("fault_class", "")
    fault = fault_raw.split(":")[0].strip() if fault_raw else ""
    plan = []

    scenario = state.get("scenario")
    app_roles = None
    if scenario and scenario.services:
        app_roles = {s.role for s in scenario.services.values()}

    catalogue = load_catalogue(app_roles=app_roles)

    sandbox_required = False
    if fault and fault in catalogue.faults:
        f_def = catalogue.faults[fault]
        
        if f_def.risk == "MEDIUM":
            sandbox_required = True

        if f_def.repair:
            # Declarative execution
            plan.append(
                Action(
                    name=f_def.repair.action,
                    params=f_def.repair.params,
                )
            )
        else:
            # Legacy fallback if they still use recommended_actions
            for act_name in f_def.recommended_actions:
                plan.append(Action(name=act_name, params={}))

    return {"plan": plan, "sandbox_required": sandbox_required}


def gate_node(state: IncidentState) -> IncidentState:
    from kavach.api.store import get_all_incidents
    from kavach.remediation.tnr_gate import evaluate_safety
    from kavach.safety.engine import permit

    scenario = state["scenario"]
    loop_count = state.get("loop_count", 0) + 1

    if loop_count >= 4:
        return {
            "loop_count": loop_count,
            "gate_verdict": "DENY",
            "gate_reason": "CIRCUIT_BREAKER_TRIPPED",
            "approved_actions": [],
        }

    plan = state.get("plan", [])
    if len(plan) > 2:
        return {
            "loop_count": loop_count,
            "gate_verdict": "DENY",
            "gate_reason": "BLAST_RADIUS_EXCEEDED",
            "approved_actions": [],
        }

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

    mode = state.get("mode") or "SIMULATION"
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

    mode = state.get("mode") or "SIMULATION"
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
        elif action.name == "http_request":
            url = action.params.get("url", "")
            method = action.params.get("method", "POST")
            payload = action.params.get("payload", {})
            context = (
                f"Scenario {state['scenario'].id}" if state.get("scenario") else ""
            )

            from kavach.remediation.executor import execute_http

            if mode == "SIMULATION":
                _success = True
                output = "Simulated success"
            else:
                _success, output = execute_http(method, url, payload, context)

            sim_state["last_http_output"] = output

            from kavach.tnr.models import Action, UndoRecord

            record = UndoRecord(
                original_action=action,
                inverse_action=Action(
                    name="http_request",
                    params={
                        "url": url,
                        "method": method,
                        "payload": {"model": "primary"},
                    },
                ),  # hardcoded inverse for proof2 demo
                pre_state_witness={"output": output},
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
        passed, deltas = verify_state(state["scenario"], sim_state)
        return {"verification_passed": passed, "verification_deltas": deltas}


def sandbox_execute_node(state: IncidentState) -> IncidentState:
    # Run a dry-run/simulated execution for sandbox verification
    sim_state = state.get("simulation_state", {}).copy()
    
    # We do not append to undo_stack here because it's just a sandbox
    # and we won't unwind it in the same way. We just want to see if it passes verification.
    for action in state.get("approved_actions", []):
        if action.name == "shell_command":
            sim_state["last_shell_output"] = "Simulated success"
        elif action.name == "http_request":
            sim_state["last_http_output"] = "Simulated success"
        else:
            execute_action(action, sim_state)

    return {"simulation_state": sim_state}


def sandbox_verify_node(state: IncidentState) -> IncidentState:
    # Use the same verify logic but output to sandbox_passed
    res = verify_node(state)
    return {"sandbox_passed": res.get("verification_passed", False)}


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
    import asyncio
    
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
    
    scenario = state["scenario"]
    incident_id = state.get("incident_id", "unknown")
    outcome_str = "MITIGATED" if passed else "ESCALATED"
    
    if passed:
        # F01 usually results in MITIGATED because primary is still down, just backup is active.
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
                # Store debt_def on the scenario so we can persist it later in the async route
                scenario.active_debt_def = debt_def
    
    # --- F-MEM: Save Incident Memory ---
    async def _save():
        try:
            from kavach.api.db import get_db_session
            from kavach.knowledge.store import save_incident_memory
            
            # Determine the repairs taken
            repair_action_data = {}
            if passed and state.get("undo_stack"):
                record = state.get("undo_stack")[-1]
                if hasattr(record.original_action, "params"):
                    repair_action_data = {"name": record.original_action.name, "params": record.original_action.params}
                
            async with get_db_session() as session:
                await save_incident_memory(
                    session=session,
                    incident_id=incident_id,
                    fault_class=scenario.fault_class,
                    symptoms=scenario.trigger.condition if scenario.trigger else "",
                    summary=f"Automated RCA identified {scenario.fault_class}.",
                    repair_action=repair_action_data,
                    outcome=outcome_str
                )
        except Exception as e:
            import logging
            logging.warning(f"Failed to save incident to knowledge base: {e}")

    try:
        asyncio.run(_save())
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(_save())
        except Exception:
            pass

    return {"outcome": outcome_str}
