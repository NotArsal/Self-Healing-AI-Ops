from kavach.llm.rca import RCAResponse, analyze_root_cause
from kavach.scenarios.loader import load_scenario


def test_llm_degradation(monkeypatch):
    scenario = load_scenario("F01")
    call_counts = {"primary": 0, "fallback": 0}
    
    class FakeFailingLLM:
        def __init__(self, model, *args, **kwargs):
            self.model = model
            
        def with_structured_output(self, schema, *args, **kwargs):
            return self
            
        def invoke(self, prompt, *args, **kwargs):
            if "7b" in self.model:
                call_counts["primary"] += 1
                raise ValueError("Primary LLM Timeout")
            else:
                call_counts["fallback"] += 1
                return RCAResponse(
                    fault_class="F01",
                    confidence=0.85,
                    evidence_ids=["fallback_evidence"],
                    rejected_alternatives=[]
                )

    # We need to mock ChatOllama class entirely so we can track the model_name
    monkeypatch.setattr("kavach.llm.rca.ChatOllama", FakeFailingLLM)
    
    result = analyze_root_cause(scenario, model_name="qwen2.5:7b-instruct")
    
    assert call_counts["primary"] == 1
    assert call_counts["fallback"] == 1
    assert result.fault_class == "F01"
    assert result.confidence == 0.85
    assert result.evidence_ids == ["fallback_evidence"]
