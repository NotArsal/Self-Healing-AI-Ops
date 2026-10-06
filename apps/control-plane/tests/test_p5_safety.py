from typing import Any

import pytest

from kavach.graph.workflow import build_workflow
from kavach.llm.rca import RCAResponse
from kavach.scenarios.loader import load_scenario
from kavach.tnr.models import Action


@pytest.fixture(autouse=True)
def mock_rca(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_analyze(*args: Any, **kwargs: Any) -> RCAResponse:
        return RCAResponse(
            fault_class="F01",
            confidence=0.9,
            evidence_ids=[],
            rejected_alternatives=[]
        )
    monkeypatch.setattr("kavach.graph.nodes.analyze_root_cause", fake_analyze)


def test_circuit_breaker_trips() -> None:
    scenario = load_scenario("F01")
    app = build_workflow()

    sim_state = scenario.state.copy() if scenario.state else {}
    # Force verification failure so it loops
    sim_state["_force_verification_failure"] = "true"

    initial_state = {"scenario": scenario, "simulation_state": sim_state}
    result = app.invoke(initial_state)

    # Should have looped 3 times and then gate blocked it with CIRCUIT_BREAKER_TRIPPED
    assert result["loop_count"] == 4  # (3 failed retries + 1 trip)
    assert result["gate_verdict"] == "DENY"
    assert result["gate_reason"] == "CIRCUIT_BREAKER_TRIPPED"
    assert result["outcome"] == "ESCALATED"


def test_unapproved_action_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = load_scenario("F01")
    
    # Mock the plan node to return an unapproved action (e.g. drop_database)
    def malicious_plan(state: Any) -> dict[str, Any]:
        return {"plan": [Action(name="drop_database", params={})]}
    
    monkeypatch.setattr("kavach.graph.workflow.plan_node", malicious_plan)
    
    app = build_workflow()
    initial_state = {"scenario": scenario, "simulation_state": scenario.state.copy() if scenario.state else {}}
    result = app.invoke(initial_state)
    
    assert result["gate_verdict"] == "DENY"
    assert result["gate_reason"] == "UNAPPROVED_ACTION_DROP_DATABASE"
    assert result["outcome"] == "ESCALATED"
    assert len(result["approved_actions"]) == 0


def test_blast_radius_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = load_scenario("F01")
    
    # Mock the plan node to return too many actions
    def overeager_plan(state: Any) -> dict[str, Any]:
        return {"plan": [
            Action(name="switch_model", params={}),
            Action(name="switch_model", params={}),
            Action(name="switch_model", params={})
        ]}
    
    monkeypatch.setattr("kavach.graph.workflow.plan_node", overeager_plan)
    
    app = build_workflow()
    initial_state = {"scenario": scenario, "simulation_state": scenario.state.copy() if scenario.state else {}}
    result = app.invoke(initial_state)
    
    assert result["gate_verdict"] == "DENY"
    assert result["gate_reason"] == "BLAST_RADIUS_EXCEEDED"
    assert result["outcome"] == "ESCALATED"
