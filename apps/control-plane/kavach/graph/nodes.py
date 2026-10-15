from collections.abc import Callable
from typing import Any

from kavach.catalogue.schema import EffectDef
from kavach.graph.state import IncidentState
from kavach.knowledge.summary import describe_incident, describe_symptoms
from kavach.llm.rca import analyze_root_cause
from kavach.preflight.schema import DebtItemDef, ReversibleStateDef
from kavach.remediation.runtime_config import apply_effect, revert_effect
from kavach.scenarios.schema import Scenario
from kavach.simulation.executor import ExecutorError, execute_action
from kavach.tnr.models import Action, UndoRecord
from kavach.verification.live import verify_live
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
    query_text = describe_incident(scenario, scenario.fault_class)

    async def _fetch() -> list[Any]:
        try:
            async with get_db_session() as session:
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

    if past_incidents and scenario.evidence is None:
        scenario.evidence = []
    for inc in past_incidents:
        # A cited ID has to resolve to a stored row, so the memory's own id is
        # carried in the evidence id rather than buried in free text.
        scenario.evidence.append(  # type: ignore[union-attr]
            EvidenceItem(
                id=f"ev-memory-{inc.id}",
                kind="similar_incident",
                source="kavach_memory",
                payload={
                    "incident_id": inc.id,
                    "fault_class": inc.fault_class,
                    "summary": inc.summary,
                    "repair_action": inc.repair_action,
                    "outcome": inc.outcome,
                },
            )
        )

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
    risk_tier = None
    if fault and fault in catalogue.faults:
        f_def = catalogue.faults[fault]
        risk_tier = f_def.risk

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

    return {
        "plan": plan,
        "sandbox_required": sandbox_required,
        "risk_tier": risk_tier,
    }


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

    # Mode policy (ARCHITECTURE.md 8, PRD F-MODE). This runs only after the
    # allow-list, forbidden-services, breaker and blast-radius checks above have
    # all passed: a mode can never buy permission those checks refused.
    mode = state.get("mode") or "SIMULATION"
    # An unrecognised risk tier is treated as HIGH. Absent information is not
    # permission.
    risk_tier = state.get("risk_tier") or "HIGH"
    allow: IncidentState = {
        "loop_count": loop_count,
        "gate_verdict": "ALLOW",
        "gate_reason": "PASSED",
        "approved_actions": approved,
    }

    def deny(reason: str) -> IncidentState:
        return {
            "loop_count": loop_count,
            "gate_verdict": "DENY",
            "gate_reason": reason,
            "approved_actions": [],
        }

    match mode:
        case "SIMULATION":
            # Plans and dry-runs only; execute_node writes nothing in this mode.
            return allow
        case "AUTONOMOUS":
            if risk_tier == "LOW":
                return allow
            if risk_tier == "MEDIUM":
                # plan_node set sandbox_required; approval is requested after the
                # sandbox run proves the repair, in sandbox_verify_node.
                return allow
            return deny("HIGH_RISK_REQUIRES_HUMAN")
        case _:
            # APPROVAL, and any unknown mode, routes everything to a human.
            return _request_approval(approved, loop_count, allow, deny)


def _request_approval(
    approved: list[Action],
    loop_count: int,
    allow: IncidentState,
    deny: "Callable[[str], IncidentState]",
) -> IncidentState:
    approval_result = interrupt(
        {
            "prompt": "Approval required before execution.",
            "actions": [a.name for a in approved],
        }
    )
    if approval_result != "APPROVED":
        return deny("HUMAN_REJECTED")
    return allow


from langgraph.types import interrupt


def _live_effect_binding(
    action: Action, scenario: Scenario | None
) -> tuple[EffectDef, ReversibleStateDef] | None:
    """Resolve an action to a live application effect, or None if it has none.

    Returns a binding only when the catalogue declares how the action is realised
    *and* the incident concerns a real application that declares the state it
    touches. Both are data, so adding an action or a target needs no change here.
    """
    if scenario is None or scenario.target is None:
        return None

    catalogue = load_catalogue()
    act_def = catalogue.actions.get(action.name)
    if act_def is None or act_def.effect is None:
        return None

    rs_def = (scenario.target.manifest.reversible_state or {}).get(act_def.effect.key)
    if rs_def is None:
        raise ExecutorError(
            f"action {action.name} needs reversible_state '{act_def.effect.key}', "
            f"which {scenario.target.manifest_path} does not declare"
        )
    return act_def.effect, rs_def


def _apply_live_effect(
    action: Action, scenario: Scenario | None, mode: str
) -> UndoRecord | None:
    binding = _live_effect_binding(action, scenario)
    if binding is None:
        return None
    effect, rs_def = binding
    return apply_effect(effect, action, rs_def, mode)


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
        effect_record = _apply_live_effect(action, state.get("scenario"), mode)
        if effect_record is not None:
            undo_records.append(effect_record)
            continue

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
        elif action.name in ["rollback_prompt", "rollforward_prompt"]:
            from kavach.remediation.git_ops import GitOpsAdapter
            
            git_adapter = GitOpsAdapter()
            if mode != "SIMULATION":
                git_adapter.checkout_ops_branch()
                
                # Mock file modification for F07
                prompt_file = "prompts.yaml"
                version = action.params.get("target_version") or action.params.get("version") or "unknown"
                with open(prompt_file, "w") as f:
                    f.write(f"version: {version}\n")
                    
                git_adapter.commit_changes(prompt_file, f"Execute {action.name} to {version}")

            # Still mutate simulation state
            record = execute_action(action, sim_state)
            undo_records.append(record)
        else:
            record = execute_action(action, sim_state)
            undo_records.append(record)

    return {"simulation_state": sim_state, "undo_stack": undo_records}


def verify_node(state: IncidentState) -> IncidentState:
    from kavach.remediation.executor import verify_execution

    sim_state = state.get("simulation_state", {})
    approved_actions = state.get("approved_actions", [])

    scenario = state.get("scenario")
    if scenario is not None and scenario.target is not None:
        # Real application: measure it. Nothing below this point is reachable for
        # a live target, so no simulated number can leak into a live verdict.
        passed, deltas = verify_live(scenario)
        return {"verification_passed": passed, "verification_deltas": deltas}

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
    # A dry run, published under its own key. Returning it as simulation_state
    # merged the sandbox's mutations into the incident, so an incident whose
    # sandbox *failed* still carried a half-repaired state -- with no undo record
    # for it, because nothing had been applied.
    sandbox_state = state.get("simulation_state", {}).copy()

    for action in state.get("approved_actions", []):
        if action.name == "shell_command":
            sandbox_state["last_shell_output"] = "Simulated success"
        elif action.name == "http_request":
            sandbox_state["last_http_output"] = "Simulated success"
        else:
            execute_action(action, sandbox_state)

    return {"sandbox_state": sandbox_state}


def sandbox_verify_node(state: IncidentState) -> IncidentState:
    # Verifies the sandbox's state, never the incident's, and deliberately does
    # not publish verification_passed: a repair that passed a dry run has not
    # been verified.
    res = verify_node({**state, "simulation_state": state.get("sandbox_state", {})})
    passed = res.get("verification_passed", False)

    # MEDIUM risk under AUTONOMOUS is "sandbox, then approval": a human approves
    # on the evidence of a sandbox run rather than on a proposal.
    mode = state.get("mode") or "SIMULATION"
    if passed and mode == "AUTONOMOUS" and state.get("risk_tier") == "MEDIUM":
        approval_result = interrupt(
            {
                "prompt": "Sandbox run passed. Approval required for live execution.",
                "actions": [a.name for a in state.get("approved_actions", [])],
            }
        )
        if approval_result != "APPROVED":
            return {
                "sandbox_passed": False,
                "gate_verdict": "DENY",
                "gate_reason": "HUMAN_REJECTED",
            }

    return {"sandbox_passed": passed}


def unwind_node(state: IncidentState) -> IncidentState:
    sim_state = state.get("simulation_state", {}).copy()
    undo_stack = state.get("undo_stack", [])
    mode = state.get("mode") or "SIMULATION"

    scenario = state.get("scenario")
    unrestored: list[str] = []

    # Process LIFO
    for record in reversed(undo_stack):
        if record.applied:
            binding = _live_effect_binding(record.original_action, scenario)
            if binding is not None:
                effect, rs_def = binding
                if not revert_effect(effect, record, rs_def, mode):
                    unrestored.append(effect.key)
                continue
            
            if record.original_action.name in ["rollback_prompt", "rollforward_prompt"] and mode != "SIMULATION":
                from kavach.remediation.git_ops import GitOpsAdapter
                git_adapter = GitOpsAdapter()
                git_adapter.checkout_ops_branch()
                
                # Undo file modification
                prompt_file = "prompts.yaml"
                version = record.pre_state_witness.get("prompt_version", "unknown")
                with open(prompt_file, "w") as f:
                    f.write(f"version: {version}\n")
                    
                git_adapter.commit_changes(prompt_file, f"Undo {record.original_action.name} (Restored to {version})")

            # The inverse runs first and the witness goes on top of it. The
            # witness is the prior state captured as data, so it has the last
            # word (AGENTS.md 4a). The previous order -- witness first, inverse
            # second -- let the inverse overwrite the restored value with
            # "unknown" or with the forward target for five of the nine faults.
            #
            # Nothing is read back here: this state is Kavach's own dict, so a
            # readback would compare the witness against a copy of itself. The
            # live path does read back (remediation/runtime_config.revert_effect)
            # and the catalogue's inverses are covered by tests/test_unwind.py.
            if record.original_action.name != "shell_command":
                execute_action(record.inverse_action, sim_state)
            for k, v in record.pre_state_witness.items():
                sim_state[k] = v

    # A deliberately broken undo, routed through the same reporting path as a real
    # one so the test exercises the mechanism rather than a shortcut in outcome.
    if sim_state.get("_force_undo_failure") == "true":
        unrestored.append("_force_undo_failure")

    return {"simulation_state": sim_state, "unwind_unrestored": unrestored}


def outcome_node(state: IncidentState) -> IncidentState:
    import asyncio
    
    # Check if we bypassed planning due to low confidence
    diag = state.get("diagnosis")
    if diag and (diag.confidence < 0.8 or diag.fault_class == "INSUFFICIENT_EVIDENCE"):
        return {"outcome": "ESCALATED"}

    # An unwind that did not put the state back is the one failure this system
    # must never report quietly (ROADMAP P3).
    unrestored = state.get("unwind_unrestored") or []
    if unrestored:
        import logging

        logging.getLogger(__name__).error(
            "unwind did not restore %s for incident %s; state left mutated",
            unrestored,
            state.get("incident_id", "unknown"),
        )
        return {"outcome": "UNRECOVERABLE"}

    # Check if gate blocked execution
    if state.get("gate_verdict") == "DENY":
        return {"outcome": "ESCALATED"}

    passed = state.get("verification_passed", False)

    scenario = state["scenario"]
    incident_id = state.get("incident_id", "unknown")
    outcome_str = "MITIGATED" if passed else "ESCALATED"

    # The diagnosis is authoritative. A detection-created incident arrives as
    # UNKNOWN and is only classified by the diagnose node, so reading the
    # scenario's own field here resolved debt against "UNKNOWN" and never found
    # any. Record the diagnosed class on the scenario so the API routes that read
    # it later agree with the graph.
    fault_class = state.get("fault_class") or scenario.fault_class
    scenario.fault_class = fault_class

    if passed:
        # F01 usually results in MITIGATED because primary is still down, just backup is active.
        if scenario.active_debt is None:
            scenario.active_debt = {}
        for record in state.get("undo_stack", []):
            if record.applied:
                # Store the entire record dict or object
                scenario.active_debt[record.original_action.name] = record

        # Register debt in the central ledger. debt_config is keyed by fault
        # class (CONTRACT.md 10.1).
        if fault_class and scenario.debt_config:
            raw_debt = scenario.debt_config.get(fault_class)
            if raw_debt is not None:
                # Parsed into the typed model, because the ledger and the API
                # route both reach for .repayment_action / .trigger.condition via
                # hasattr and silently substitute "unknown" on a plain dict --
                # which is how a recorded debt ended up with a trigger that could
                # never fire.
                scenario.active_debt_def = (
                    raw_debt
                    if isinstance(raw_debt, DebtItemDef)
                    else DebtItemDef(**raw_debt)
                )
    
    # --- F-MEM: Save Incident Memory ---
    # Built outside the coroutine so a failure here surfaces rather than being
    # swallowed by the except below, which is what hid this path for so long.
    symptoms = describe_symptoms(scenario)
    repair_action_data: dict[str, Any] = {}
    undo_stack = state.get("undo_stack") or []
    if passed and undo_stack:
        record = undo_stack[-1]
        repair_action_data = {
            "name": record.original_action.name,
            "params": record.original_action.params,
        }

    async def _save() -> None:
        try:
            from kavach.api.db import get_db_session
            from kavach.knowledge.store import save_incident_memory

            async with get_db_session() as session:
                await save_incident_memory(
                    session=session,
                    incident_id=incident_id,
                    fault_class=fault_class,
                    symptoms=symptoms,
                    summary=f"Automated RCA identified {fault_class}. Outcome {outcome_str}.",
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
