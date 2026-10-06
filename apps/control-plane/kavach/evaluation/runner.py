import json
import statistics
import time
from pathlib import Path

from kavach.evaluation.extractor import build_scenario_from_case
from kavach.evaluation.schema import CaseResult, EvaluationCase, EvaluationReport
from kavach.llm.rca import analyze_root_cause


def evaluate_cases(cases: list[EvaluationCase], output_file: str) -> EvaluationReport:
    results = []
    failed_invalid = 0
    mapped_count = 0
    unmapped_count = 0
    mapped_correct = 0
    latencies = []
    confusion_matrix = {}

    audit_log = []

    for i, case in enumerate(cases):
        try:
            scenario = build_scenario_from_case(case)

            print(f"\n--- [CASE {i + 1}/{len(cases)}: {case.case_id}] ---")

            audit_log.append(
                {
                    "case_id": case.case_id,
                    "dataset_fault": case.dataset_fault,
                    "normalized_fault": case.normalized_fault,
                    "inject_time": case.inject_time,
                    "extracted_scenario": scenario.model_dump(),
                }
            )

            start_t = time.time()
            diagnosis = analyze_root_cause(scenario)
            latency = (time.time() - start_t) * 1000
            latencies.append(latency)

            predicted_fault = diagnosis.fault_class

            is_unmapped = case.normalized_fault == "UNMAPPED"
            passed = predicted_fault == case.normalized_fault

            if is_unmapped:
                unmapped_count += 1
            else:
                mapped_count += 1
                if passed:
                    mapped_correct += 1

                # Update confusion matrix
                if case.normalized_fault not in confusion_matrix:
                    confusion_matrix[case.normalized_fault] = {}
                if predicted_fault not in confusion_matrix[case.normalized_fault]:
                    confusion_matrix[case.normalized_fault][predicted_fault] = 0
                confusion_matrix[case.normalized_fault][predicted_fault] += 1

            results.append(
                CaseResult(
                    case_id=case.case_id,
                    dataset_fault=case.dataset_fault,
                    normalized_fault=case.normalized_fault,
                    predicted_fault=predicted_fault,
                    expected_result=case.normalized_fault,
                    passed=passed,
                    latency_ms=latency,
                    is_unmapped=is_unmapped,
                    scenario_dump=scenario.model_dump(),
                )
            )

            print(
                f"Actual: {case.dataset_fault} -> {case.normalized_fault} | Pred: {predicted_fault} | Pass: {passed} | {latency:.0f}ms"
            )

        except Exception as e:
            import traceback

            print(f"Error evaluating case {case.case_id}: {e}")
            traceback.print_exc()
            failed_invalid += 1

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    latencies.sort()
    median_latency = statistics.median(latencies) if latencies else 0.0
    p95_latency = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

    mapped_top1_accuracy = mapped_correct / mapped_count if mapped_count > 0 else 0.0
    unmapped_rate = unmapped_count / len(cases) if cases else 0.0

    report = EvaluationReport(
        total_cases=len(cases),
        mapped_cases=mapped_count,
        unmapped_cases=unmapped_count,
        mapped_top1_accuracy=mapped_top1_accuracy,
        unmapped_rate=unmapped_rate,
        failed_invalid_cases=failed_invalid,
        avg_latency_ms=avg_latency,
        median_latency_ms=median_latency,
        p95_latency_ms=p95_latency,
        confusion_matrix=confusion_matrix,
        results=results,
    )

    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))

    audit_path = out_path.parent / f"audit_{out_path.name}"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit_log, f, indent=2)

    # Generate Markdown Report
    md_path = out_path.parent / f"{out_path.stem}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# RCAEval-RE2 Baseline Evaluation\n\n")
        f.write("## Summary Metrics\n")
        f.write(f"- **Total Cases**: {report.total_cases}\n")
        f.write(f"- **Mapped Cases**: {report.mapped_cases}\n")
        f.write(
            f"- **Unmapped Cases**: {report.unmapped_cases} ({report.unmapped_rate:.2%})\n"
        )
        f.write(f"- **Mapped Top-1 Accuracy**: {report.mapped_top1_accuracy:.2%}\n")
        f.write(f"- **Failed/Invalid Execution**: {report.failed_invalid_cases}\n\n")
        f.write("## Latency Metrics\n")
        f.write(f"- **Average**: {report.avg_latency_ms:.0f} ms\n")
        f.write(f"- **Median**: {report.median_latency_ms:.0f} ms\n")
        f.write(f"- **P95**: {report.p95_latency_ms:.0f} ms\n\n")
        f.write("## Confusion Matrix (Mapped Cases Only)\n")
        f.write("`Actual \\ Predicted`\n\n")
        for actual, preds in confusion_matrix.items():
            f.write(f"- **{actual}**: ")
            f.write(", ".join(f"{k}: {v}" for k, v in preds.items()))
            f.write("\n")

    return report
