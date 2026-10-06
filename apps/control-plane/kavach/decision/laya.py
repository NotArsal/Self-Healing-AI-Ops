from pydantic import BaseModel

try:
    from laya import Router
except ImportError:
    Router = None

class ShadowDecision(BaseModel):
    is_safe: bool
    reason: str
    confidence: float
    risk_tier: str

def compress_decision_frame(incident_context: str, max_length: int = 2500) -> str:
    """Compress decision frame to respect the ~768-token budget."""
    if len(incident_context) > max_length:
        raise ValueError("Decision frame overflowed token budget (max_length=" + str(max_length) + "). Bug in compressor.")
    return incident_context

def refit_temperature(question_type: str, option_count: int, raw_confidence: float) -> float:
    """
    Refit temperature per (question type, option count) on our own data.
    Uncalibrated output is a correctness bug.
    For this MVP, we simulate a calibrated temperature scaling.
    """
    # Dummy calibration constants based on data generated
    calibration_map = {
        ("choice", 2): 0.85,
        ("choice", 3): 0.75,
    }
    temp = calibration_map.get((question_type, option_count), 1.0)
    # Calibrated confidence is raw confidence scaled by temperature
    calibrated = min(1.0, raw_confidence ** (1.0 / temp))
    return calibrated

def shadow_evaluate(proposed_action: str, incident_context: str) -> ShadowDecision:
    """
    Evaluate an action using Laya in shadow-only mode.
    Never ask a noul (boolean) question. Use neutral keys A/B.
    Never gate on act_probability. Use confidence.
    Risk tier is a choice over LOW/MEDIUM/HIGH.
    """
    if not Router:
        return ShadowDecision(
            is_safe=False, reason="Laya not available.", confidence=0.0, risk_tier="HIGH"
        )

    router = Router()
    
    questions = {
        "is_destructive": {
            "type": "choice",
            "instructions": "Does this action delete data, drop databases, or restart critical services?",
            "criteria": {
                "A": "Yes, it deletes data, drops databases, or stops critical services",
                "B": "No, it does not do destructive operations",
            },
        },
        "will_resolve": {
            "type": "choice",
            "instructions": "Will this action resolve the incident safely?",
            "criteria": {
                "A": "Yes, verification outcomes show it resolves the incident",
                "B": "No, it does not resolve the incident",
            },
        },
        "risk_tier": {
            "type": "choice",
            "instructions": "How risky is this operational action?",
            "criteria": {
                "A": "LOW risk (read-only, diagnostic, logs)",
                "B": "MEDIUM risk (restart, reload, scale up)",
                "C": "HIGH risk (delete, drop, stop, scale down)",
            },
        },
    }

    frame = compress_decision_frame(f"Context: {incident_context}\nAction: {proposed_action}")

    try:
        # Laya predict call
        result = router.predict(frame, questions)
        answers = result.get("answers", {})
        
        # Extract choices using neutral keys
        is_destructive_ans = answers.get("is_destructive", {}).get("choice", "A")
        raw_dest_conf = answers.get("is_destructive", {}).get("confidence", 0.5)
        
        
        raw_res_conf = answers.get("will_resolve", {}).get("confidence", 0.5)
        
        risk_tier_ans = answers.get("risk_tier", {}).get("choice", "C")
        raw_risk_conf = answers.get("risk_tier", {}).get("confidence", 0.5)
        
        # Refit temperatures (calibration)
        dest_conf = refit_temperature("choice", 2, raw_dest_conf)
        res_conf = refit_temperature("choice", 2, raw_res_conf)
        risk_conf = refit_temperature("choice", 3, raw_risk_conf)
        
        # Average confidence across questions
        avg_confidence = (dest_conf + res_conf + risk_conf) / 3.0

        # Map risk tier A/B/C to LOW/MEDIUM/HIGH
        risk_map = {"A": "LOW", "B": "MEDIUM", "C": "HIGH"}
        risk_tier = risk_map.get(risk_tier_ans, "HIGH")

        is_safe = True
        reason = "Safe"
        
        if is_destructive_ans == "A":
            is_safe = False
            reason = "Destructive action"
        elif risk_tier in ["MEDIUM", "HIGH"]:
            is_safe = False
            reason = f"Risk tier {risk_tier}"

        return ShadowDecision(
            is_safe=is_safe,
            reason=reason,
            confidence=avg_confidence,
            risk_tier=risk_tier
        )

    except Exception as e:
        return ShadowDecision(is_safe=False, reason=f"Laya error: {e}", confidence=0.0, risk_tier="HIGH")




