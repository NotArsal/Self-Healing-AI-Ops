from pydantic import BaseModel

# Optional try-except if laya fails to import initially
try:
    from laya import Router
except ImportError:
    Router = None


class SafetyAssessment(BaseModel):
    is_safe: bool
    reason: str


def evaluate_safety(proposed_action: str, incident_context: str) -> SafetyAssessment:
    if not Router:
        return SafetyAssessment(
            is_safe=False, reason="Laya is not available. Defaulting to block."
        )

    router = Router()
    questions = {
        "is_destructive": {
            "type": "choice",
            "instructions": "Does this action delete data, drop databases, or restart critical services?",
            "criteria": {
                "destructive": "Yes, it deletes data, drops databases, or stops critical services",
                "safe": "No, it does not do destructive operations",
            },
        },
        "will_resolve": {
            "type": "choice",
            "instructions": "Will this action resolve the incident safely?",
            "criteria": {
                "yes": "Yes, verification outcomes show it resolves the incident",
                "no": "No, it does not resolve the incident",
            },
        },
        "risk_level": {
            "type": "choice",
            "instructions": "How risky is this operational action?",
            "criteria": {
                "low_risk": "read-only, diagnostic, ping, curl, status, info, logs",
                "medium_risk": "restart, reload, edit configuration, scale up",
                "high_risk": "delete, drop, stop, kill, reset, scale down",
            },
        },
    }

    prompt = f"Context: {incident_context}\nAction: {proposed_action}"

    # Check if we have a fine-tuned model available
    import os

    finetuned_path = "models/laya_finetuned/finetune_metadata.json"
    is_finetuned = os.path.exists(finetuned_path)

    try:
        result = router.predict(prompt, questions)

        is_destructive_ans = result["answers"]["is_destructive"].get(
            "choice", "destructive"
        )
        risk_level = result["answers"]["risk_level"].get("choice", "high_risk")
        will_resolve = result["answers"]["will_resolve"].get("choice", "no")

        model_name = "Fine-tuned Laya" if is_finetuned else "Laya"

        if is_destructive_ans == "destructive":
            return SafetyAssessment(
                is_safe=False, reason=f"Action flagged as destructive by {model_name}"
            )

        if risk_level in ["medium_risk", "high_risk"]:
            return SafetyAssessment(
                is_safe=False, reason=f"Action flagged as {risk_level} by {model_name}."
            )

        return SafetyAssessment(
            is_safe=True, reason=f"Action is safe to execute ({model_name} verified)."
        )

    except Exception as e:
        return SafetyAssessment(is_safe=False, reason=f"TNR Gate Exception: {e!s}")
