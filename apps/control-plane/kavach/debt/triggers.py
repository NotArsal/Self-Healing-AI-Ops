from typing import Any


def evaluate_trigger(
    condition: str, value: float, current_signals: dict[str, Any]
) -> bool:
    """
    Evaluate if a debt repayment trigger has been met.
    For simulation, current_signals is the simulation_state of the incident.
    """
    if condition == "primary_healthy_for_s":
        signal_val = current_signals.get("model_primary")
        return signal_val == "healthy"

    if condition == "healthy_for_s":
        signal_val = current_signals.get("llm_proxy_health")
        return signal_val == "healthy"

    if condition.startswith("<"):
        # Not used in F01, but keeping for completeness
        pass

    return False
