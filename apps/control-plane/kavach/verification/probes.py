from kavach.scenarios.schema import Scenario


def verify_state(
    scenario: Scenario, simulation_state: dict[str, str]
) -> tuple[bool, dict[str, float]]:
    """
    Verifies the mutated simulated state.
    Returns (passed, deltas).
    """
    deltas = {}
    passed = True

    # In F01 scenario: "switch_model" changes active_model to "model_backup"
    # If active_model is healthy (e.g. model_backup is healthy), availability delta recovers.
    active_model = simulation_state.get("active_model", "model_primary")
    is_healthy = simulation_state.get(active_model) == "healthy"

    if scenario.objectives and "availability" in scenario.objectives:
        obj = scenario.objectives["availability"]
        # Fake calculation: if healthy, it meets threshold, otherwise it stays at original value
        if is_healthy:
            simulated_availability = obj.threshold + 0.001
            deltas["availability"] = simulated_availability - obj.value
            if simulated_availability < obj.threshold:
                passed = False
        else:
            deltas["availability"] = 0.0
            passed = False

    # Hardcoded test fail flag
    if simulation_state.get("_force_verification_failure") == "true":
        passed = False

    return passed, deltas
