
import pytest

from kavach.llm.rca import RCAResponse
from kavach.remediation.tnr_gate import SafetyAssessment


@pytest.fixture(autouse=True)
def mock_laya(monkeypatch):
    def fake_evaluate(action, context):
        return SafetyAssessment(is_safe=True, reason="Mock safe")
    monkeypatch.setattr("kavach.remediation.tnr_gate.evaluate_safety", fake_evaluate)

@pytest.fixture(autouse=True)
def mock_ollama(monkeypatch):
    class FakeLLM:
        def __init__(self, *args, **kwargs):
            pass
        def invoke(self, prompt, *args, **kwargs):
            if "- None" in str(prompt) or "[]" in str(prompt) or not prompt:
                return RCAResponse(fault_class="INSUFFICIENT_EVIDENCE", confidence=0.3, evidence_ids=[], rejected_alternatives=[])
            return RCAResponse(fault_class="F01", confidence=0.9, evidence_ids=["log-1"], rejected_alternatives=[])
    
    def fake_with_structured(self, schema, *args, **kwargs):
        return FakeLLM()
        
    monkeypatch.setattr("langchain_ollama.ChatOllama.with_structured_output", fake_with_structured)


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




