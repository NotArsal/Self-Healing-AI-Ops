import pytest

from kavach.graph.workflow import build_workflow
from kavach.llm.rca import analyze_root_cause
from kavach.scenarios.loader import load_scenario


# We mark these as LLM tests so they can be skipped in quick CI runs if needed
@pytest.mark.llm
def test_f01_llm_classification() -> None:
    scenario = load_scenario("F01")

    # Direct LLM check
    result = analyze_root_cause(scenario)
    assert result.fault_class.startswith("F01")
    assert result.confidence >= 0.8
    assert len(result.evidence_ids) > 0

    # Graph check
    app = build_workflow()
    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy() if scenario.state else {},
    }
    graph_result = app.invoke(initial_state)
    assert graph_result["outcome"] == "MITIGATED"


@pytest.mark.llm
def test_insufficient_evidence_escalates() -> None:
    scenario = load_scenario("F01")
    # Strip evidence to confuse LLM
    scenario.evidence = []

    app = build_workflow()
    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy() if scenario.state else {},
    }
    graph_result = app.invoke(initial_state)

    # With no evidence, LLM should lack confidence or choose INSUFFICIENT_EVIDENCE
    assert graph_result["outcome"] == "ESCALATED"
    assert "plan" not in graph_result or len(graph_result.get("plan", [])) == 0
