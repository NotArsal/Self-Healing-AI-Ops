import pytest

from typing import Any
from kavach.graph.workflow import build_workflow
from kavach.llm.rca import RCAResponse
from kavach.scenarios.loader import load_scenario


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


def test_f01_scenario_detected_and_mitigated() -> None:
    scenario = load_scenario("F01")
    app = build_workflow()

    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy() if scenario.state else {},
    }

    result = app.invoke(initial_state)

    assert result["fault_class"] == "F01"
    assert len(result["plan"]) > 0
    assert result["plan"][0].name == "switch_model"

    assert result["verification_passed"] is True
    assert "availability" in result["verification_deltas"]
    assert result["outcome"] == "MITIGATED"


def test_forced_verification_failure_triggers_unwind() -> None:
    scenario = load_scenario("F01")
    app = build_workflow()

    sim_state = scenario.state.copy() if scenario.state else {}
    sim_state["_force_verification_failure"] = "true"

    initial_state = {"scenario": scenario, "simulation_state": sim_state}

    result = app.invoke(initial_state)

    assert result["verification_passed"] is False
    assert result["outcome"] == "ESCALATED"

    # State should be restored to original model_primary
    assert result["simulation_state"]["active_model"] == "model_primary"


def test_forced_undo_failure_produces_unrecoverable() -> None:
    scenario = load_scenario("F01")
    app = build_workflow()

    sim_state = scenario.state.copy() if scenario.state else {}
    sim_state["_force_verification_failure"] = "true"
    sim_state["_force_undo_failure"] = "true"

    initial_state = {"scenario": scenario, "simulation_state": sim_state}

    result = app.invoke(initial_state)

    assert result["verification_passed"] is False
    assert result["outcome"] == "UNRECOVERABLE"


def test_action_without_inverse_rejected() -> None:
    # If gate drops actions not in allowed list
    scenario = load_scenario("F01")
    if scenario.permissions:
        scenario.permissions.allowed_actions = []  # clear allowed list

    app = build_workflow()

    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy() if scenario.state else {},
    }

    result = app.invoke(initial_state)

    assert len(result.get("approved_actions", [])) == 0
    assert result["gate_verdict"] == "DENY"
    assert result["outcome"] == "ESCALATED"
