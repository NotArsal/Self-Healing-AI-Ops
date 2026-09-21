"""
LangGraph Orchestration State — the shared typed dict passed between all nodes.
"""

from typing import TypedDict, List, Optional, Dict, Any


class OrchestratorState(TypedDict):
    # Core incident context
    incident_id: str
    affected_service: str
    failure_type: str
    severity: str
    timestamp: str

    # Evidence gathered during investigation
    metrics_summary: Optional[str]
    logs_summary: Optional[str]
    k8s_events: Optional[str]

    # RCA output
    hypotheses: Optional[List[Dict[str, Any]]]   # [{hypothesis, confidence, evidence}]
    top_hypothesis: Optional[str]

    # Memory retrieval
    similar_incidents: Optional[List[Dict[str, Any]]]

    # Repair plan
    repair_candidates: Optional[List[Dict[str, Any]]]  # [{action, risk, rollback}]
    selected_action: Optional[Dict[str, Any]]

    # Safety decision
    safety_decision: Optional[str]  # "auto" | "sandbox" | "approval_required"

    # Execution
    execution_result: Optional[str]

    # Verification
    verification_passed: Optional[bool]
    verification_details: Optional[str]

    # Terminal outcome
    final_status: Optional[str]  # "RESOLVED" | "ROLLED_BACK" | "ESCALATED"
