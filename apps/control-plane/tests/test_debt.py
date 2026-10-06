import pytest
from kavach.debt.ledger import record_debt, get_active_debts, clear_debt
from kavach.debt.triggers import evaluate_trigger
from kavach.scenarios.schema import Scenario, DebtDef, TriggerDef

def test_ledger_record_and_clear():
    # Setup
    incident_id = "inc-123"
    scenario_id = "f01-demo"
    fault_class = "F01"
    debt_def = DebtDef(
        repayment_action="switch_model",
        trigger=TriggerDef(condition="healthy_for_s", value=600),
        max_age_s=3600
    )
    
    # Run
    record_debt(incident_id, scenario_id, fault_class, debt_def)
    debts = get_active_debts()
    
    # Assert
    assert len(debts) == 1
    assert debts[0].incident_id == incident_id
    assert debts[0].repayment_action == "switch_model"
    
    # Clear
    clear_debt(incident_id)
    assert len(get_active_debts()) == 0

def test_trigger_healthy_for_s():
    sim_state = {"llm_proxy_health": "healthy"}
    assert evaluate_trigger("healthy_for_s", 600, sim_state) == True
    
    sim_state = {"llm_proxy_health": "unhealthy"}
    assert evaluate_trigger("healthy_for_s", 600, sim_state) == False

def test_trigger_primary_healthy_for_s():
    sim_state = {"model_primary": "healthy"}
    assert evaluate_trigger("primary_healthy_for_s", 600, sim_state) == True
    assert evaluate_trigger("primary_healthy_for_s", 600, {"model_primary": "unhealthy"}) == False

@pytest.mark.anyio
async def test_evaluate_all_debts_escalation():
    from kavach.debt.checker import evaluate_all_debts
    from kavach.api.store import get_all_incidents, create_incident, get_incident
    import time
    
    incident_id = create_incident("F01", {"simulation_state": {}, "scenario": None})
    
    debt_def = DebtDef(
        repayment_action="switch_model",
        trigger=TriggerDef(condition="primary_healthy_for_s", value=600),
        max_age_s=0  # force immediate escalation
    )
    record_debt(incident_id, "f01-demo", "F01", debt_def)
    
    # Fake time by artificially making created_at older
    debts = get_active_debts()
    debts[0].created_at = time.time() - 100
    
    await evaluate_all_debts()
    
    # Should be escalated and cleared
    assert len(get_active_debts()) == 0
    inc = get_incident(incident_id)
    assert inc["outcome"] == "UNRECOVERABLE"

@pytest.mark.anyio
async def test_evaluate_all_debts_repayment():
    from kavach.debt.checker import evaluate_all_debts
    from kavach.api.store import get_all_incidents, create_incident, get_incident
    from kavach.scenarios.loader import load_scenario
    
    scenario = load_scenario("F01")
    sim_state = scenario.state.copy() if scenario.state else {}
    sim_state["model_primary"] = "healthy"
    
    incident_id = create_incident("F01", {"simulation_state": sim_state, "scenario": scenario})
    
    debt_def = DebtDef(
        repayment_action="switch_model",
        trigger=TriggerDef(condition="primary_healthy_for_s", value=600),
        max_age_s=86400
    )
    record_debt(incident_id, scenario.id, "F01", debt_def)
    from kavach.tnr.models import UndoRecord, Action
    scenario.active_debt = {
        "switch_model": UndoRecord(
            original_action=Action(name="switch_model", params={"fallback": "model_backup"}),
            inverse_action=Action(name="switch_model", params={"fallback": "model_primary"}),
            pre_state_witness={"active_model": "model_primary"},
            applied=True
        )
    }
    
    # Trigger is met (model_primary: healthy)
    await evaluate_all_debts()
    
    # Should be repaid (cleared, outcome RESOLVED)
    assert len(get_active_debts()) == 0
    inc = get_incident(incident_id)
    assert inc["outcome"] == "RESOLVED"
