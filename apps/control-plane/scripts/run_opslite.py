import json
import time
from pathlib import Path

from kavach.evaluation.loaders.opslite_loader import load_opslite_cases
from kavach.evaluation.opslite_extractor import build_scenario_from_opslite
from kavach.llm.rca import analyze_root_cause


def run():
    target_cases = {
        "hs1-frontend-delay-24srn4",
        "ts0-ts-travel-plan-service-response-delay-pfwcqk",
        "hs0-attractions-pod-failure-s8fsgm",
        "hs1-geo-cpu-exhaustion-q8nln6",
        "ts0-ts-travel-plan-service-response-replace-code-7ps8tm"
    }
    
    all_cases = load_opslite_cases("../../datasets/datasets--anon-ops--ops-lite")
    cases = [c for c in all_cases if c.case_id in target_cases]
    
    print(f"Found {len(cases)} target cases for ops-lite validation.")
    
    audit_log = []
    mapped_count = 0
    mapped_correct = 0
    unmapped_count = 0
    latencies = []
    
    md_content = "# OpenRCA ops-lite 5-Case Validation\n\n"
    
    for c in cases:
        print(f"\n--- [CASE: {c.case_id}] ---")
        try:
            scenario = build_scenario_from_opslite(c)
            
            # Print extraction
            print(f"Dataset Fault: {c.dataset_fault} | Mapped: {c.normalized_fault}")
            print("Extracted Evidence:")
            for ev in scenario.evidence or []:
                if ev.kind == "metric":
                    print(f" - [metric] {ev.source}: {ev.value} (score: {ev.payload.get('anomaly_score', 0):.2f})")
                else:
                    print(f" - [log] {ev.source}: {ev.payload.get('message', '')}")
                    
            start_t = time.time()
            diagnosis = analyze_root_cause(scenario)
            latency = (time.time() - start_t) * 1000
            latencies.append(latency)
            
            predicted = diagnosis.fault_class
            passed = (predicted == c.normalized_fault)
            
            if c.normalized_fault == "UNMAPPED":
                unmapped_count += 1
            else:
                mapped_count += 1
                if passed:
                    mapped_correct += 1
                    
            print(f"Actual: {c.dataset_fault} -> {c.normalized_fault} | Pred: {predicted} | Pass: {passed}")
            
            md_content += f"### Case: {c.case_id}\n"
            md_content += f"- **Actual Chaos Type**: {c.dataset_fault}\n"
            md_content += f"- **Mapped Status**: {c.normalized_fault}\n"
            md_content += f"- **Affected Service**: {c.root_cause_service}\n"
            md_content += f"- **Predicted Fault**: {predicted}\n"
            md_content += f"- **Pass/Fail**: {'PASS' if passed else 'FAIL'}\n"
            md_content += f"- **Latency**: {latency:.0f}ms\n"
            md_content += f"- **Extracted Metrics**: {', '.join([m.source for m in scenario.evidence if m.kind == 'metric'])}\n"
            md_content += f"- **Extracted Logs**: {len([l for l in scenario.evidence if l.kind == 'log'])}\n\n"
            
            audit_log.append({
                "case_id": c.case_id,
                "dataset_fault": c.dataset_fault,
                "normalized_fault": c.normalized_fault,
                "predicted": predicted,
                "passed": passed,
                "scenario": scenario.model_dump()
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error evaluating {c.case_id}: {e}")
            
    # Metrics
    avg_latency = sum(latencies)/len(latencies) if latencies else 0
    accuracy = (mapped_correct / mapped_count * 100) if mapped_count > 0 else 0
    
    md_content = f"""# OpenRCA ops-lite 5-Case Validation Report

## Summary
- **F02 Top-1 Accuracy**: {accuracy:.1f}% ({mapped_correct}/{mapped_count})
- **Mapped/Unmapped Coverage**: {mapped_count} Mapped / {unmapped_count} Unmapped
- **Average RCA Latency**: {avg_latency:.0f}ms

## Case Breakdown
""" + md_content[37:] # append rest
    
    out_dir = Path("../eval_results")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_dir / "ops_lite_validation.md", "w", encoding="utf-8") as f:
        f.write(md_content)
        
    with open(out_dir / "audit_ops_lite_validation.json", "w", encoding="utf-8") as f:
        json.dump(audit_log, f, indent=2)
        
    print("\nValidation complete. Results saved to eval_results/ops_lite_validation.md")

if __name__ == "__main__":
    run()
