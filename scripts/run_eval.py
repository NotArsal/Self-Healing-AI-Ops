import argparse
import sys
from pathlib import Path

# Add control-plane to sys.path so we can import kavach
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "control-plane"))

from kavach.evaluation.loaders.re2_loader import load_re2_cases
from kavach.evaluation.runner import evaluate_cases

def select_representative_subset(cases):
    """
    Selects 5 cases covering different fault types and different services if possible.
    """
    import random
    
    selected = []
    selected_services = set()
    faults_needed = ["delay", "socket", "cpu", "mem", "loss", "disk"]
    
    for fault in faults_needed:
        if len(selected) >= 5:
            break
        # Shuffle cases of this fault to ensure we try different services
        fault_cases = [c for c in cases if c.dataset_fault == fault]
        random.shuffle(fault_cases)
        
        for case in fault_cases:
            if case.root_cause_service not in selected_services:
                selected.append(case)
                selected_services.add(case.root_cause_service)
                break
                
    # Fallback to pad to 5 if needed
    for case in cases:
        if len(selected) >= 5:
            break
        if case not in selected:
            selected.append(case)
            
    return selected

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", type=int, default=0, help="Number of cases to run")
    parser.add_argument("--dataset", type=str, default="../datasets", help="Path to datasets dir")
    parser.add_argument("--out", type=str, default="../apps/control-plane/eval_results/re2_validation.json", help="Output JSON path")
    args = parser.parse_args()

    # Base path is the datasets dir relative to scripts/
    base_path = Path(__file__).parent / args.dataset
    cases = load_re2_cases(str(base_path.resolve()))
    print(f"Loaded {len(cases)} RE2-TT cases in total.")

    if args.subset == 5:
        print("Selecting 5 representative validation cases...")
        cases = select_representative_subset(cases)
        for c in cases:
            print(f" - {c.case_id} (Fault: {c.dataset_fault})")
    elif args.subset > 0:
        cases = cases[:args.subset]

    report = evaluate_cases(cases, str((Path(__file__).parent / args.out).resolve()))
    
    print("\n--- EVALUATION COMPLETE ---")
    print(f"Total Cases: {report.total_cases}")
    print(f"Mapped Cases: {report.mapped_cases}")
    print(f"Unmapped Cases: {report.unmapped_cases}")
    print(f"Mapped Top-1 Accuracy: {report.mapped_top1_accuracy:.2%}")
    print(f"Unmapped Rate: {report.unmapped_rate:.2%}")
    print(f"Avg RCA Latency: {report.avg_latency_ms:.0f}ms")
    print(f"Failed/Invalid: {report.failed_invalid_cases}")
    print(f"Results saved to: {args.out}")
