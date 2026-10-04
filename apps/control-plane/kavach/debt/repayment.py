import logging
from kavach.scenarios.schema import Scenario
from kavach.simulation.executor import execute_action
from kavach.verification.probes import verify_state

logger = logging.getLogger(__name__)

def repay_debt(scenario: Scenario, simulation_state: dict) -> bool:
    """
    Attempts to repay debt for a mitigated incident.
    Returns True if debt was successfully repaid and cleared, False otherwise.
    """
    if not scenario.debt:
        return False
        
    # Process LIFO for safe rollback of stacked actions
    records = list(scenario.debt.values())
    records.reverse()
    
    # We create a scratch state to test if repayment succeeds
    test_state = simulation_state.copy()
    
    for record in records:
        if record.applied:
            logger.info(f"Repaying debt: executing inverse {record.inverse_action.name}")
            execute_action(record.inverse_action, test_state)
            
    # After repaying, we must verify the system is still healthy (meaning the original fault was indeed fixed)
    passed, deltas = verify_state(scenario, test_state)
    
    if passed:
        # Commit the state
        simulation_state.update(test_state)
        # Clear the debt
        scenario.debt.clear()
        logger.info("Debt successfully repaid. System fully restored.")
        return True
    else:
        logger.warning("Debt repayment verification failed. The underlying fault is likely not resolved.")
        return False
