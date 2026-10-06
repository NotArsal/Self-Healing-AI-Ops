import argparse
import sys
import time

from kavach.scenarios.loader import ScenarioLoadError, load_scenario
from kavach.graph.workflow import build_workflow
from kavach.graph.state import IncidentState


def run_scenario(name: str, force_verify_fail: bool = False) -> None:
    print(f"\n{'='*60}\nRunning Scenario: {name}\n{'='*60}")
    try:
        scenario = load_scenario(name)
        print(f"[1] Loaded Scenario: {scenario.id} | Class: {scenario.fault_class}")
    except ScenarioLoadError as e:
        print(f"Error loading '{name}': {e}")
        return
    except Exception as e:
        print(f"Unexpected error loading '{name}': {e}")
        return

    sim_state = scenario.state.copy() if scenario.state else {}
    if force_verify_fail:
        sim_state["_force_verification_failure"] = "true"

    initial_state = {
        "scenario": scenario,
        "simulation_state": sim_state,
    }

    app = build_workflow()
    
    print("[2] Invoking Autonomous Healing Graph...")
    start_t = time.time()
    try:
        result = app.invoke(initial_state)
    except Exception as e:
        print(f"Graph execution failed: {e}")
        return
        
    end_t = time.time()
    
    # Extract results
    outcome = result.get("outcome", "UNKNOWN")
    fault_detected = result.get("fault_class", "None")
    actions = result.get("plan", [])
    action_names = [a.action_type for a in actions]
    
    print(f"[3] Execution Complete in {end_t - start_t:.2f}s")
    print(f"    - Diagnosed Fault : {fault_detected}")
    print(f"    - Proposed Actions: {action_names}")
    
    # Check for approval / denial
    gate_verdict = result.get("gate_verdict")
    if gate_verdict == "DENY":
        print(f"    - Gate Verdict    : DENY (Escalated to human approval)")
    else:
        print(f"    - Gate Verdict    : PERMIT")
        
    # Check unwind
    undo_stack = result.get("undo_stack", [])
    if undo_stack and not result.get("verification_passed"):
        print(f"    - Verification    : FAILED (Unwound {len(undo_stack)} actions)")
    elif result.get("verification_passed"):
        print(f"    - Verification    : PASSED")
        
    # Check debt
    active_debt = scenario.active_debt
    if active_debt:
        print(f"    - Debt Incurred   : YES")

    print(f"\n>>> FINAL OUTCOME: {outcome} <<<\n")


def demo_full() -> None:
    print("\n" + "#"*70)
    print(" KAVACH DEMO: FULL SCENARIO REHEARSAL ")
    print("#"*70)
    
    # 1. Autonomous heal with debt
    # F01 defines debt_config implicitly through its debt section
    print("\n--- [Demo 1] Autonomous Heal with Debt ---")
    run_scenario("F01")
    
    # 2. Approval heal
    # An action that violates the risk tier (e.g. max_risk_tier is LOW but action is MEDIUM)
    # F05 has max_risk_tier MEDIUM. Let's use F02 which is also MEDIUM but maybe action is HIGH?
    # F08 is max_risk_tier MEDIUM. 
    print("\n--- [Demo 2] Approval Heal (Escalated due to Risk Tier) ---")
    run_scenario("F08")
    
    # 3. Unwind (Failed verification)
    print("\n--- [Demo 3] Unwind (Failed Verification) ---")
    run_scenario("F04", force_verify_fail=True)
    
    # 4. Unknown-failure escalation
    print("\n--- [Demo 4] Unknown Failure Escalation ---")
    run_scenario("F12")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kavach Scenario Runner")
    parser.add_argument(
        "name", help="Name or prefix of the scenario to load (e.g. F01, demo-full)"
    )

    args = parser.parse_args()

    if args.name == "demo-full":
        demo_full()
    else:
        run_scenario(args.name)


if __name__ == "__main__":
    main()
