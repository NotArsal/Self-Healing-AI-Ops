import pytest
from kavach.scenarios.schema import Scenario, TriggerDef, ServiceDef
from kavach.graph.state import IncidentState
from kavach.graph.workflow import build_workflow
from kavach.llm.rca import RCAResponse
from kavach.catalogue.schema import Catalogue, FaultDef, RepairDef
from unittest.mock import patch

@patch("kavach.graph.nodes.load_catalogue")
@patch("kavach.graph.nodes.analyze_root_cause")
def test_sandbox_medium_risk(mock_rca, mock_loader):
    mock_rca.return_value = RCAResponse(
        fault_class="F03",
        confidence=0.9,
        evidence_ids=[],
        rejected_alternatives=[]
    )
    mock_loader.return_value = Catalogue(
        faults={"F03": FaultDef(
            fault_class="F03",
            risk="MEDIUM",
            repair=RepairDef(action="noop", params={})
        )}
    )
    workflow = build_workflow()
    
    # F03 is MEDIUM risk
    scenario = Scenario(
        id="test-sbx",
        fault_class="F03",
        services={"web": ServiceDef(role="application")},
        health={},
        evidence=[],
        permissions=None  # We should mock permissions or let it bypass
    )
    
    from kavach.scenarios.schema import PermissionDef
    scenario.permissions = PermissionDef(allowed_actions=["noop"], max_risk_tier="HIGH")
    
    initial_state = IncidentState(
        incident_id="test-sbx-123",
        scenario=scenario,
        mode="SIMULATION",
        simulation_state={}
    )
    
    result = workflow.invoke(initial_state)
    
    # Assert sandbox was required and passed
    assert result.get("sandbox_required") is True
    assert result.get("sandbox_passed") is True
    
    # Assert execution completed
    assert result["outcome"] == "MITIGATED"
