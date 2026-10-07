from pydantic import BaseModel


class SafetyAssessment(BaseModel):
    is_safe: bool
    reason: str


def evaluate_safety(proposed_action: str, incident_context: str) -> SafetyAssessment:
    """
    Evaluate safety using Laya in shadow mode.
    """
    from kavach.decision.laya import shadow_evaluate

    decision = shadow_evaluate(proposed_action, incident_context)

    # We still return SafetyAssessment to not break downstream type hints,
    # but the caller (gate_node) only uses this in shadow mode.
    return SafetyAssessment(
        is_safe=decision.is_safe,
        reason=f"{decision.reason} | Conf: {decision.confidence:.2f} | Tier: {decision.risk_tier}",
    )
