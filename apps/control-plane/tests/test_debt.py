import pytest

from kavach.remediation.tnr_gate import SafetyAssessment


@pytest.fixture(autouse=True)
def mock_laya(monkeypatch):
    def fake_evaluate(action, context):
        return SafetyAssessment(is_safe=True, reason="Mock safe")

    monkeypatch.setattr("kavach.remediation.tnr_gate.evaluate_safety", fake_evaluate)


from kavach.debt.triggers import evaluate_trigger
from kavach.scenarios.schema import DebtDef, TriggerDef

# Mock the ledger functions to avoid needing a real Postgres DB in tests
_MOCK_LEDGER = []

async def fake_record_debt_async(incident_id, action_name, action_params, debt_def):
    from kavach.debt.ledger import ActiveDebt
    import time
    trigger_cond = debt_def.trigger.condition if hasattr(debt_def, "trigger") else "unknown"
    max_age_s = debt_def.max_age_s if hasattr(debt_def, "max_age_s") else 86400
    _MOCK_LEDGER.append(
        ActiveDebt(
            id="test-debt",
            incident_id=incident_id,
            action_name=action_name,
            action_params=action_params,
            trigger_type="promql",
            trigger_condition=trigger_cond,
            created_at=time.time(),
            max_age_s=max_age_s,
            status="PENDING"
        )
    )

async def fake_get_active_debts_async():
    return [d for d in _MOCK_LEDGER if d.status == "PENDING"]

async def fake_clear_debt_async(incident_id):
    for d in _MOCK_LEDGER:
        if d.incident_id == incident_id:
            d.status = "REPAID"

async def fake_escalate_debt_async(incident_id):
    for d in _MOCK_LEDGER:
        if d.incident_id == incident_id:
            d.status = "ESCALATED"

@pytest.fixture(autouse=True)
def mock_ledger(monkeypatch):
    _MOCK_LEDGER.clear()
    monkeypatch.setattr("kavach.debt.ledger.record_debt_async", fake_record_debt_async)
    monkeypatch.setattr("kavach.debt.ledger.get_active_debts_async", fake_get_active_debts_async)
    monkeypatch.setattr("kavach.debt.ledger.clear_debt_async", fake_clear_debt_async)
    monkeypatch.setattr("kavach.debt.ledger.escalate_debt_async", fake_escalate_debt_async)
    monkeypatch.setattr("kavach.debt.checker.get_active_debts_async", fake_get_active_debts_async)
    monkeypatch.setattr("kavach.debt.checker.clear_debt_async", fake_clear_debt_async)
    monkeypatch.setattr("kavach.debt.checker.escalate_debt_async", fake_escalate_debt_async)

# Use the real functions for imports but they will be mocked at runtime
from kavach.debt.ledger import clear_debt_async, get_active_debts_async, record_debt_async


@pytest.mark.anyio
async def test_ledger_record_and_clear():
    # Setup
    incident_id = "inc-123"
    action_name = "switch_model"
    action_params = {"target": "model_backup"}
    debt_def = DebtDef(
        repayment_action="switch_model",
        trigger=TriggerDef(condition="healthy_for_s", value=600),
        max_age_s=3600,
    )

    # Run
    import kavach.debt.ledger as ledger
    await ledger.record_debt_async(incident_id, action_name, action_params, debt_def)
    debts = await ledger.get_active_debts_async()

    # Assert
    assert len(debts) >= 1
    
    # We might have remnants from other tests in DB, find ours
    my_debt = next((d for d in debts if d.incident_id == incident_id), None)
    assert my_debt is not None
    assert my_debt.action_name == "switch_model"

    # Clear
    await ledger.clear_debt_async(incident_id)
    new_debts = await ledger.get_active_debts_async()
    assert not any(d.incident_id == incident_id for d in new_debts)


def test_trigger_healthy_for_s():
    sim_state = {"llm_proxy_health": "healthy"}
    assert evaluate_trigger("healthy_for_s", 600, sim_state) == True

    sim_state = {"llm_proxy_health": "unhealthy"}
    assert evaluate_trigger("healthy_for_s", 600, sim_state) == False


def test_trigger_primary_healthy_for_s():
    sim_state = {"model_primary": "healthy"}
    assert evaluate_trigger("primary_healthy_for_s", 600, sim_state) == True
    assert (
        evaluate_trigger("primary_healthy_for_s", 600, {"model_primary": "unhealthy"})
        == False
    )


@pytest.mark.anyio
async def test_evaluate_all_debts_escalation():
    from kavach.api.store import create_incident, get_incident
    from kavach.debt.checker import evaluate_all_debts

    incident_id = create_incident("F01", {"simulation_state": {}, "scenario": None})

    debt_def = DebtDef(
        repayment_action="switch_model",
        trigger=TriggerDef(condition="primary_healthy_for_s", value=600),
        max_age_s=0,  # force immediate escalation
    )
    import kavach.debt.ledger as ledger
    await ledger.record_debt_async(incident_id, "switch_model", {"fallback": "model_primary"}, debt_def)

    # In database, the age is compared to created_at
    # We force max_age_s = 0, so it will instantly escalate
    await evaluate_all_debts()

    # Should be escalated and cleared
    debts = await ledger.get_active_debts_async()
    assert not any(d.incident_id == incident_id for d in debts)
    
    inc = get_incident(incident_id)
    assert inc["outcome"] == "UNRECOVERABLE"


@pytest.mark.anyio
async def test_evaluate_all_debts_repayment(monkeypatch):
    from kavach.api.store import create_incident, get_incident
    from kavach.debt.checker import evaluate_all_debts
    from kavach.scenarios.loader import load_scenario

    def fake_verify(scenario, sim_state):
        return True, {}

    monkeypatch.setattr("kavach.verification.probes.verify_state", fake_verify)

    scenario = load_scenario("F01")
    sim_state = scenario.state.copy() if scenario.state else {}
    sim_state["model_primary"] = "healthy"

    incident_id = create_incident(
        "F01", {"simulation_state": sim_state, "scenario": scenario}
    )

    debt_def = DebtDef(
        repayment_action="switch_model",
        trigger=TriggerDef(condition="primary_healthy_for_s", value=600),
        max_age_s=86400,
    )
    import kavach.debt.ledger as ledger
    await ledger.record_debt_async(incident_id, "switch_model", {"fallback": "model_primary"}, debt_def)
    from kavach.tnr.models import Action, UndoRecord

    scenario.active_debt = {
        "switch_model": UndoRecord(
            original_action=Action(
                name="switch_model", params={"target": "model_backup", "fallback": "model_primary"}
            ),
            inverse_action=Action(
                name="switch_model", params={"target": "model_primary", "fallback": "model_backup"}
            ),
            pre_state_witness={"active_model": "model_primary"},
            applied=True,
        )
    }

    # Trigger is met (model_primary: healthy)
    await evaluate_all_debts()

    # Should be repaid (cleared, outcome RESOLVED)
    debts = await ledger.get_active_debts_async()
    assert not any(d.incident_id == incident_id for d in debts)
    
    inc = get_incident(incident_id)
    assert inc["outcome"] == "RESOLVED"
