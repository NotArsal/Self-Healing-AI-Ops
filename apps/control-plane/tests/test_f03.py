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
    # F03 is MEDIUM risk, so the repair is proved in a sandbox before it is run.
    assert result["sandbox_required"] is True
    assert result["sandbox_passed"] is True


def test_f03_sandbox_failure_stops_before_execution() -> None:
    """A MEDIUM-risk repair that fails its dry run is never executed.

    This test used to assert that forcing verification to fail triggered an
    unwind. It could only do that because the catalogue loader dropped
    core.yaml's `risk: MEDIUM` for F03, so the sandbox branch was unreachable and
    the repair went straight to live execution. With the tier restored the
    sandbox catches it first: nothing is applied, so there is nothing to unwind,
    and the incident's own state is never touched.
    """
    scenario = load_scenario("F03")
    app = build_workflow()

    sim_state = scenario.state.copy() if scenario.state else {}
    sim_state["_force_verification_failure"] = "true"

    initial_state = {"scenario": scenario, "simulation_state": sim_state}
    result = app.invoke(initial_state)

    assert result["sandbox_passed"] is False
    assert result["outcome"] == "ESCALATED"
    # Not verified, because nothing ran: a dry run is not a verification.
    assert "verification_passed" not in result
    assert result.get("undo_stack", []) == []
    # The sandbox's mutations must not leak into the incident.
    assert result["simulation_state"]["api_health"] == "crash-loop"
    assert result["sandbox_state"]["api_health"] == "healthy"
