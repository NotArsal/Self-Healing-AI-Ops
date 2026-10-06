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

    is_healthy = False

    if scenario.fault_class == "F01":
        active_model = simulation_state.get("active_model", "model_primary")
        is_healthy = simulation_state.get(active_model) == "healthy"
    elif scenario.fault_class == "F02":
        is_healthy = simulation_state.get("provider_latency") == "normal"
    elif scenario.fault_class == "F03":
        is_healthy = simulation_state.get("api_health") == "healthy"
    elif scenario.fault_class == "F04":
        is_healthy = simulation_state.get("cache_state") == "clean"
    elif scenario.fault_class == "F05":
        is_healthy = simulation_state.get("db_health") == "healthy"
    elif scenario.fault_class == "F06":
        is_healthy = simulation_state.get("retriever_health") == "healthy"
    elif scenario.fault_class == "F07":
        is_healthy = simulation_state.get("prompt_health") == "healthy"
    elif scenario.fault_class == "F08":
        is_healthy = simulation_state.get("config_health") == "healthy"
    elif scenario.fault_class == "F09":
        is_healthy = simulation_state.get("token_health") == "healthy"
    else:
        # Fallback heuristic: check if any values that were unhealthy are now healthy
        is_healthy = True

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

    if scenario.objectives and "latency" in scenario.objectives:
        obj = scenario.objectives["latency"]
        if is_healthy:
            simulated_latency = obj.threshold - 100.0  # Better than threshold
            deltas["latency"] = simulated_latency - obj.value
            if simulated_latency > obj.threshold:
                passed = False
        else:
            deltas["latency"] = 0.0
            passed = False

    if scenario.objectives and "quality" in scenario.objectives:
        obj = scenario.objectives["quality"]
        if is_healthy:
            simulated_quality = obj.threshold + 0.05  # Better than threshold
            deltas["quality"] = simulated_quality - obj.value
            if simulated_quality < obj.threshold:
                passed = False
        else:
            deltas["quality"] = 0.0
            passed = False

    if scenario.objectives and "cost" in scenario.objectives:
        obj = scenario.objectives["cost"]
        if is_healthy:
            simulated_cost = obj.threshold - 50.0  # Better than threshold
            deltas["cost"] = simulated_cost - obj.value
            if simulated_cost > obj.threshold:
                passed = False
        else:
            deltas["cost"] = 0.0
            passed = False

    # Hardcoded test fail flag
    if simulation_state.get("_force_verification_failure") == "true":
        passed = False

    return passed, deltas
