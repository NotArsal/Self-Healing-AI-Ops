import pytest
from kavach.scenarios.schema import Scenario, TriggerDef, ServiceDef
from kavach.graph.state import IncidentState
from kavach.graph.workflow import build_workflow

def test_unknown_failure_loop():
    workflow = build_workflow()
    
    scenario = Scenario(
        id="test-unknown",
        fault_class="UNKNOWN_FAULT",
        services={"web": ServiceDef(role="application")},
        health={},
        evidence=[]
    )
    
    initial_state = IncidentState(
        incident_id="test-123",
        scenario=scenario,
        mode="SIMULATION",
        simulation_state={}
    )
    
    result = workflow.invoke(initial_state)
    
    # Assert we escalated and took zero repair actions
    assert result["outcome"] == "ESCALATED"
    assert len(result.get("undo_stack", [])) == 0

