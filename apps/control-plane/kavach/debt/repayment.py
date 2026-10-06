import logging

from kavach.graph.nodes import gate_node
from kavach.scenarios.schema import Scenario
from kavach.simulation.executor import execute_action
from kavach.tnr.models import Action
from kavach.verification.probes import verify_state

logger = logging.getLogger(__name__)

def repay_debt(scenario: Scenario, simulation_state: dict, repayment_action_name: str) -> bool:
    """
    Attempts to repay debt for a mitigated incident by routing the repayment action through the safety gate.
    """
    if not scenario.active_debt:
        return False
        
    record = scenario.active_debt.get(repayment_action_name)
    if record and hasattr(record, 'inverse_action'):
        action = record.inverse_action
        logger.info(f"Using inverse action from UndoRecord: {action}")
    else:
        # Fallback
        action = Action(name=repayment_action_name, params={})
    
    # 1. Gate Check
    test_state = {
        "scenario": scenario,
        "plan": [action],
        "loop_count": 0
    }
    
    gate_result = gate_node(test_state)
    if gate_result.get("gate_verdict") == "DENY":
        logger.warning(f"Debt repayment denied by gate: {gate_result.get('gate_reason')}")
        return False

    # 2. Execute
    logger.info(f"Repaying debt: executing {action.name}")
    execute_action(action, simulation_state)
            
    # 3. Verify
    passed, _deltas = verify_state(scenario, simulation_state)
    
    if passed:
        scenario.active_debt.clear()
        logger.info("Debt successfully repaid. System fully restored.")
        return True
    else:
        logger.warning("Debt repayment verification failed. The underlying fault is likely not resolved.")
        # We don't rollback simulation state in this demo if it fails (it's simulated). 
        # But normally we'd unwind the debt repayment.
        return False
