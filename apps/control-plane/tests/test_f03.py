from typing import Any

import pytest

from kavach.graph.workflow import build_workflow
from kavach.llm.rca import RCAResponse
from kavach.scenarios.loader import load_scenario


@pytest.fixture(autouse=True)
def mock_rca(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_analyze(*args: Any, **kwargs: Any) -> RCAResponse:
        return RCAResponse(
            fault_class="F03", confidence=0.9, evidence_ids=[], rejected_alternatives=[]
        )

    monkeypatch.setattr("kavach.graph.nodes.analyze_root_cause", fake_analyze)


def test_f03_loop() -> None:
    scenario = load_scenario("F03")
    app = build_workflow()

    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy() if scenario.state else {},
    }

    result = app.invoke(initial_state)

    assert result["verification_passed"] is True
    assert result["outcome"] == "MITIGATED"
    assert len(result["approved_actions"]) == 1
    assert result["approved_actions"][0].name == "rollback_deployment"
    assert result["approved_actions"][0].params["target_version"] == "last_known_good"


def test_f03_forced_verification_failure_triggers_unwind() -> None:
    scenario = load_scenario("F03")
    app = build_workflow()

    sim_state = scenario.state.copy() if scenario.state else {}
    sim_state["_force_verification_failure"] = "true"

    initial_state = {"scenario": scenario, "simulation_state": sim_state}
    result = app.invoke(initial_state)

    assert result["verification_passed"] is False
    assert result["outcome"] == "ESCALATED"
    # Unwind should have run, so state should be back to crash-loop
    assert result["simulation_state"]["api_health"] == "crash-loop"
