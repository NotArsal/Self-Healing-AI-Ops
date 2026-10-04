from typing import Any

from langgraph.graph import END, START, StateGraph

from kavach.graph.nodes import (
    detect_node,
    diagnose_node,
    execute_node,
    gate_node,
    outcome_node,
    plan_node,
    unwind_node,
    verify_node,
)
from kavach.graph.state import IncidentState


def build_workflow() -> Any:
    workflow = StateGraph(IncidentState)

    workflow.add_node("detect", detect_node)
    workflow.add_node("diagnose", diagnose_node)
    workflow.add_node("plan", plan_node)
    workflow.add_node("gate", gate_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("verify", verify_node)
    workflow.add_node("unwind", unwind_node)
    workflow.add_node("outcome", outcome_node)

    workflow.add_edge(START, "detect")
    workflow.add_edge("detect", "diagnose")

    def check_diagnosis(state: IncidentState) -> str:
        diag = state.get("diagnosis")
        if not diag:
            return "outcome"
        if diag.confidence < 0.8 or diag.fault_class == "INSUFFICIENT_EVIDENCE":
            # Force escalated outcome by returning outcome directly,
            # and marking a flag or just relying on the outcome node logic.
            # We'll set a temporary outcome field just to indicate it bypassed verification
            return "outcome"
        return "plan"

    workflow.add_conditional_edges("diagnose", check_diagnosis)
    workflow.add_edge("plan", "gate")
    
    def check_gate(state: IncidentState) -> str:
        if state.get("gate_verdict") == "DENY":
            return "outcome"
        return "execute"
        
    workflow.add_conditional_edges("gate", check_gate)
    workflow.add_edge("execute", "verify")

    # Conditional edge after verify
    def check_verification(state: IncidentState) -> str:
        if state.get("verification_passed"):
            return "outcome"
        return "unwind"

    workflow.add_conditional_edges("verify", check_verification)
    workflow.add_edge("unwind", "plan")
    workflow.add_edge("outcome", END)

    return workflow.compile()
