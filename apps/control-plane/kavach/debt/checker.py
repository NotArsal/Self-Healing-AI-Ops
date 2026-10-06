import asyncio
import logging
import time

from kavach.api.store import broadcast_event, get_all_incidents, update_incident
from kavach.debt.ledger import clear_debt, get_active_debts
from kavach.debt.repayment import repay_debt
from kavach.debt.triggers import evaluate_trigger

logger = logging.getLogger(__name__)

async def check_debts_loop():
    """Background task that ticks every 60 seconds to check active debts."""
    while True:
        try:
            await asyncio.sleep(60)
            await evaluate_all_debts()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in debt checker loop: {e}")


async def evaluate_all_debts():
    debts = get_active_debts()
    if not debts:
        return
        
    incidents = get_all_incidents()
    now = time.time()
    
    for debt in debts:
        incident_id = debt.incident_id
        state = incidents.get(incident_id)
        if not state:
            continue
            
        # 1. Check Max Age Escalation
        if (now - debt.created_at) > debt.max_age_s:
            logger.warning(f"Debt for {incident_id} exceeded max_age_s ({debt.max_age_s}). Escalating.")
            update_incident(incident_id, {"outcome": "UNRECOVERABLE"})
            clear_debt(incident_id)
            await broadcast_event({
                "type": "debt_escalated",
                "incident_id": incident_id,
                "reason": "max_age_exceeded"
            })
            continue
            
        # 2. Evaluate Trigger
        sim_state = state.get("simulation_state", {})
        triggered = evaluate_trigger(
            condition=debt.trigger_condition,
            value=debt.trigger_value,
            current_signals=sim_state
        )
        
        if triggered:
            logger.info(f"Trigger met for debt in {incident_id}. Initiating repayment...")
            scenario = state.get("scenario")
            success = repay_debt(scenario, sim_state, debt.repayment_action)
            if success:
                update_incident(incident_id, {"simulation_state": sim_state, "outcome": "RESOLVED"})
                clear_debt(incident_id)
                await broadcast_event({
                    "type": "debt_repaid",
                    "incident_id": incident_id,
                    "state": state
                })
            else:
                logger.warning(f"Debt repayment failed or blocked by gate for {incident_id}.")
                
