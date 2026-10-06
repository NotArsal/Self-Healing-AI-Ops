import pytest
import os
from kavach.preflight.checker import PreflightChecker
from kavach.graph.workflow import build_workflow
from kavach.scenarios.schema import Scenario, ServiceDef, QualityDef, ObjectiveDef, PermissionDef, EvidenceItem, TriggerDef, DebtDef

def test_proof2_preflight_and_heal(monkeypatch: pytest.MonkeyPatch):
    # 1. Read kavach.yaml
    kavach_path = os.path.join(os.path.dirname(__file__), "../../../targets/proof2/kavach.yaml")
    with open(kavach_path, "r", encoding="utf-8") as f:
        manifest_yaml = f.read()
    
    # 2. Run Preflight
    checker = PreflightChecker(manifest_yaml)
    report = checker.run_all()
    
    # Verify preflight passes
    failed_checks = [c for c in report.checks if not c.passed]
    assert len(failed_checks) == 0, f"Preflight failed: {failed_checks}"
    
    # 3. Create a synthetic scenario to simulate an F01 fault on proof2
    # The scenario must match the schema expected by the graph
    scenario = Scenario(
        id="proof2-f01-test",
        fault_class="F01",
        services={
            "api": ServiceDef(role="application", depends_on=["model_primary"]),
            "llm-proxy": ServiceDef(role="model_primary")
        },
        health={
            "api": "healthy",
            "llm-proxy": "unhealthy"
        },
        quality=QualityDef(
            golden_set="./golden_set.yaml",
            min_cases=20,
            scorers=["groundedness"]
        ),
        objectives={
            "availability": ObjectiveDef(value=0.05, threshold=0.01, weight=1.0),
            "quality": ObjectiveDef(value=0.90, threshold=0.85, weight=1.0)
        },
        tolerance={"quality_drop_pct": 15.0},
        permissions=PermissionDef(
            allowed_actions=["switch_model", "restart_container"],
            max_risk_tier="MEDIUM"
        ),
        evidence=[
            EvidenceItem(
                id="ev-proof2-1",
                kind="metric",
                source="llm_proxy_health",
                value=0.0
            )
        ],
        signals={"llm_proxy_health": 0.0},
        state={
            "llm-proxy": "unhealthy",
            "model_primary": "unhealthy",
            "model_backup": "healthy",
            "active_model": "model_primary"
        },
        debt={
            "f01_provider_outage": {
                "repayment_action": "switch_model",
                "trigger": {
                    "metric": "llm_proxy_health",
                    "condition": "healthy_for_s",
                    "value": 600
                },
                "max_age_s": 86400
            }
        }
    )
    
    
    from kavach.llm.rca import RCAResponse
    
    def fake_analyze(*args, **kwargs):
        return RCAResponse(
            fault_class="F01",
            confidence=0.95,
            evidence_ids=["ev-proof2-1"],
            reasoning="Provider is down",
            rejected_alternatives=[]
        )
    
    import kavach.graph.nodes
    monkeypatch.setattr(kavach.graph.nodes, "analyze_root_cause", fake_analyze)

    # 4. Run the graph to heal it
    app = build_workflow()
    initial_state = {
        "scenario": scenario,
        "simulation_state": scenario.state.copy()
    }
    
    result = app.invoke(initial_state)
    import json
    # we can't print easily with pytest without -s, but we can put it in the assert message
    assert result["outcome"] in ["RESOLVED", "MITIGATED"], f"Escalated with gate verdict: {result.get('gate_verdict')}, reason: {result.get('gate_reason')}, plan: {result.get('plan')}"



