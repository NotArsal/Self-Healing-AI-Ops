import logging
from typing import Any

from kavach.catalogue.loader import load_catalogue
from kavach.graph.nodes import _apply_live_effect, gate_node
from kavach.graph.state import IncidentState
from kavach.scenarios.schema import Scenario
from kavach.simulation.executor import execute_action
from kavach.tnr.models import Action
from kavach.verification.live import verify_live
from kavach.verification.probes import verify_state

logger = logging.getLogger(__name__)


def _risk_tier_for(scenario: Scenario) -> str | None:
    """Risk tier of the fault being repaid, from the catalogue. None if unknown."""
    fault = load_catalogue().faults.get(scenario.fault_class)
    return fault.risk if fault else None


def repay_debt(
    scenario: Scenario,
    simulation_state: dict[str, Any],
    repayment_action_name: str,
    repayment_action_params: dict[str, Any] | None = None,
    mode: str = "SIMULATION",
) -> bool:
    """
    Attempts to repay debt for a mitigated incident by routing the repayment action through the safety gate.
    """
    if repayment_action_params is None:
        repayment_action_params = {}

    action = None
    if scenario.active_debt:
        record = scenario.active_debt.get(repayment_action_name)
        if record and hasattr(record, "inverse_action"):
            action = record.inverse_action
            logger.info(f"Using inverse action from UndoRecord: {action}")

    if not action:
        # Fallback to DB params
        action = Action(name=repayment_action_name, params=repayment_action_params)

    # 1. Gate Check. Repayment is not privileged (AGENTS.md 4d): it goes through
    # permit() exactly like any other action, in the same mode, carrying the risk
    # tier of the fault it repays. Without the tier the gate would read it as
    # HIGH and refuse every autonomous repayment.
    risk_tier = _risk_tier_for(scenario)
    if mode == "AUTONOMOUS" and risk_tier != "LOW":
        # The AUTONOMOUS policy sandboxes MEDIUM before executing, and repayment
        # has no sandbox step. Rather than let it through unsandboxed, hand it to
        # a human. v1 only defines debt for F01, which is LOW.
        logger.warning(
            "Debt repayment for a %s risk action needs approval; not repaying "
            "autonomously",
            risk_tier,
        )
        return False

    gate_result = gate_node(
        IncidentState(
            scenario=scenario,
            plan=[action],
            loop_count=0,
            mode=mode,
            risk_tier=risk_tier,
        )
    )
    if gate_result.get("gate_verdict") == "DENY":
        logger.warning(
            f"Debt repayment denied by gate: {gate_result.get('gate_reason')}"
        )
        return False

    # 2. Execute. A live application is written to through the same effect
    # binding the original repair used; only a simulated scenario mutates a dict.
    logger.info(f"Repaying debt: executing {action.name}")
    live_record = _apply_live_effect(action, scenario, mode)
    if live_record is None:
        execute_action(action, simulation_state)

    # 3. Verify
    if scenario.target is not None:
        passed, _deltas = verify_live(scenario)
    else:
        passed, _deltas = verify_state(scenario, simulation_state)

    if passed:
        # Guarded: active_debt is only populated when this process also handled
        # the original mitigation. Reached with None, this raised *after* the
        # live write had already landed, leaving the application repaid and the
        # debt still outstanding.
        if scenario.active_debt is not None:
            scenario.active_debt.clear()
        logger.info("Debt successfully repaid. System fully restored.")
        return True
    else:
        logger.warning(
            "Debt repayment verification failed. The underlying fault is likely not resolved."
        )
        # We don't rollback simulation state in this demo if it fails (it's simulated).
        # But normally we'd unwind the debt repayment.
        return False
