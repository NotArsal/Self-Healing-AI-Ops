"""RCA accuracy and the conditional heal metrics (PRD 11, 11.1).

Runs the full loop over the nine scenario files with the real local model and
records, per injection, whether the diagnosis named the right class and whether
the heal succeeded. That yields the two numbers PRD 11.1 says a headline
resolution rate cannot evidence on its own:

  P(heal | diagnosis correct)  quality of the repair catalogue and executor
  P(heal | diagnosis wrong)    how much of the headline is luck

SCOPE, and it limits what these numbers mean: these scenarios are hand-authored
YAML and run against Kavach's simulated state, so verification is derived from
declared thresholds rather than measured. Only F01-against-proof2 is a live
measurement (see ablation_undo.py and the live test suite). Treat these as
RCA-engine numbers, not platform numbers.

NO RULES BASELINE. PRD 11.2 asks for Phase 3's symptom mapping against the LLM
on identical injections. That mapping no longer exists: it was replaced by the
declarative catalogue, and the catalogue retains a `detect` signal for F01 only
(the per-fault YAML files replace core.yaml's entries instead of merging). A
baseline invented here would be one this harness authored, which is worth less
than saying plainly that the comparison is unavailable.
"""

import argparse
import json
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from unittest.mock import patch

from kavach.graph.state import IncidentState
from kavach.graph.workflow import build_workflow
from kavach.remediation.tnr_gate import SafetyAssessment
from kavach.scenarios.loader import load_scenario

REPO_ROOT = Path(__file__).resolve().parents[3]
FAULTS = [f"F0{i}" for i in range(1, 10)]
HEALED = {"MITIGATED", "RESOLVED"}


@dataclass
class Injection:
    fault: str
    rep: int
    diagnosed: str
    confidence: float
    diagnosis_correct: bool
    outcome: str
    healed: bool
    duration_s: float


def _run_one(fault: str, rep: int) -> Injection:
    scenario = load_scenario(fault)
    sim_state = scenario.state.copy() if scenario.state else {}

    started = time.time()
    # Shadow Laya stubbed: advisory by construction, and a local inference per
    # gate call would dominate the runtime without affecting any outcome.
    #
    # The knowledge base is stubbed out too, and that one is load-bearing for
    # the result. Left live, each injection stores a memory whose text contains
    # the fault class and its repair, which the next rep of the same fault then
    # retrieves as evidence -- so reps stop being independent and later ones are
    # near-guaranteed correct. These are cold-memory numbers: RCA accuracy from
    # the incident evidence alone, which is what PRD 11 means by the metric.
    with (
        patch(
            "kavach.remediation.tnr_gate.evaluate_safety",
            lambda action, context: SafetyAssessment(is_safe=True, reason="stubbed"),
        ),
        patch(
            "kavach.knowledge.retrieval.retrieve_similar_incidents", return_value=[]
        ),
        patch("kavach.knowledge.store.save_incident_memory", return_value=None),
    ):
        result = build_workflow().invoke(
            IncidentState(
                incident_id=f"bench-{fault}-{rep}",
                scenario=scenario,
                mode="SIMULATION",
                simulation_state=sim_state,
            )
        )
    duration = time.time() - started

    diagnosis = result.get("diagnosis")
    diagnosed = diagnosis.fault_class if diagnosis else "NONE"
    confidence = float(diagnosis.confidence) if diagnosis else 0.0
    outcome = str(result.get("outcome"))

    return Injection(
        fault=fault,
        rep=rep,
        diagnosed=diagnosed,
        confidence=round(confidence, 3),
        diagnosis_correct=diagnosed == fault,
        outcome=outcome,
        healed=outcome in HEALED,
        duration_s=round(duration, 2),
    )


def _pct(num: int, den: int) -> float | None:
    return round(100 * num / den, 1) if den else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=5, help="reps per fault (PRD: 5)")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "eval_results" / "rca_bench.json")
    args = ap.parse_args()

    print(f"RCA bench: {len(FAULTS)} faults x {args.reps} reps, real local model")
    print("Simulated state: these are RCA-engine numbers, not platform numbers.\n")

    runs: list[Injection] = []
    for fault in FAULTS:
        for rep in range(1, args.reps + 1):
            r = _run_one(fault, rep)
            runs.append(r)
            print(
                f"  [{r.fault} rep {r.rep}] dx={r.diagnosed:<22} "
                f"conf={r.confidence:<5} {'correct' if r.diagnosis_correct else 'WRONG':<7} "
                f"outcome={r.outcome:<11} ({r.duration_s}s)",
                flush=True,
            )
        # Dumped per fault: 45 real-model injections take long enough to be
        # interrupted, and partial data beats none.
        partial = args.out.with_suffix(".partial.json")
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text(
            json.dumps([asdict(x) for x in runs], indent=2), encoding="utf-8"
        )

    correct = [r for r in runs if r.diagnosis_correct]
    wrong = [r for r in runs if not r.diagnosis_correct]
    healed = [r for r in runs if r.healed]

    summary = {
        "injections": len(runs),
        "rca_accuracy_pct": _pct(len(correct), len(runs)),
        "heal_rate_pct": _pct(len(healed), len(runs)),
        # PRD 11.1: the conditionals are the point.
        "p_heal_given_correct_dx_pct": _pct(sum(1 for r in correct if r.healed), len(correct)),
        "p_heal_given_wrong_dx_pct": _pct(sum(1 for r in wrong if r.healed), len(wrong)),
        "p_correct_dx_given_heal_pct": _pct(
            sum(1 for r in healed if r.diagnosis_correct), len(healed)
        ),
        "median_loop_s": statistics.median(r.duration_s for r in runs) if runs else None,
        "per_fault_accuracy_pct": {
            f: _pct(
                sum(1 for r in runs if r.fault == f and r.diagnosis_correct),
                sum(1 for r in runs if r.fault == f),
            )
            for f in FAULTS
        },
        "outcomes": dict(Counter(r.outcome for r in runs)),
        "misdiagnoses": dict(Counter(f"{r.fault}->{r.diagnosed}" for r in wrong)),
        "caveats": [
            "DEGENERATE EVALUATION -- do not read 100% as RCA working. The RCA prompt (llm/rca.py) contains an explicit answer key: 'If you see gen_ai_error_ratio -> output F01' and one such rule per fault class. Each scenario's evidence contains exactly the giveaway string its rule names, so the model performs a lookup the prompt spells out. This arm is a symptom matcher executed through a 7B model, which is also why PRD 11.2's LLM-vs-rules comparison is vacuous here: both arms would be the same mechanism.",
            "P(heal | wrong diagnosis) is uncomputable: there were zero wrong diagnoses, so the stratum PRD 11.1 calls the point of the exercise is empty. The headline heal rate cannot be separated from luck on this scenario set.",
            "Confidence is returned on inconsistent scales: 40 runs returned 1.0 and 5 returned 100.0. RCAResponse.confidence is an unconstrained float and the gate compares it against 0.8, so an out-of-range value passes trivially and a 0..100 reading of 50 would escalate where 0.5 would too -- by accident.",
            "Every outcome is MITIGATED because outcome_node can only emit MITIGATED or ESCALATED; RESOLVED appears nowhere in graph/nodes.py and is set only by debt repayment. The outcome distribution is structural, not measured.",
            "To get a meaningful number: remove the answer key from the prompt, and add scenarios whose evidence is ambiguous between two fault classes.",

            ("Simulated state: verification is derived from declared thresholds, "
            "not measured. Only F01-against-proof2 is a live measurement."),
            ("No rules baseline: Phase 3's symptom mapping no longer exists and the "
            "catalogue retains a detect signal for F01 only, so the LLM-vs-rules "
            "comparison PRD 11.2 asks for cannot be run."),
            "Shadow Laya stubbed; it cannot affect an outcome.",
            (
                "Cold memory: knowledge-base read and write are stubbed so reps "
                "stay independent. With memory live, a repeat of the same fault "
                "retrieves its own answer and accuracy is inflated."
            ),
        ],
    }

    print("\n--- RCA bench ---")
    print(f"RCA accuracy            {summary['rca_accuracy_pct']}%  (PRD target >= 75)")
    print(f"Heal rate               {summary['heal_rate_pct']}%")
    print(f"P(heal | correct dx)    {summary['p_heal_given_correct_dx_pct']}%")
    print(f"P(heal | wrong dx)      {summary['p_heal_given_wrong_dx_pct']}%   <- luck in the headline")
    print(f"P(correct dx | heal)    {summary['p_correct_dx_given_heal_pct']}%")
    print(f"outcomes                {summary['outcomes']}")
    if summary["misdiagnoses"]:
        print(f"misdiagnoses            {summary['misdiagnoses']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"summary": summary, "runs": [asdict(r) for r in runs]}, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
