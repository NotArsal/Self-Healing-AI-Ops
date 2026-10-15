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
declarative catalogue, which carries a `detect` signal for F01, F03 and F07 only
-- three of nine, so a rules arm would have to answer INSUFFICIENT_EVIDENCE for
two thirds of the set by construction. (Until the loader was fixed to overlay
per-fault files onto core.yaml rather than replace its entries, only F01's
survived.) A baseline invented here would be one this harness authored, which is
worth less than saying plainly that the comparison is unavailable.
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

# A scenario built to be undiagnosable, scored separately from the nine so the
# headline accuracy stays comparable with earlier runs. Answering
# INSUFFICIENT_EVIDENCE and taking no action is the correct result, and every
# other scenario in the set points at exactly one catalogue entry -- so a model
# that always guessed something scored well and nothing caught it.
AMBIGUOUS = "FAMB"
NO_DIAGNOSIS = "INSUFFICIENT_EVIDENCE"


@dataclass
class Injection:
    fault: str
    rep: int
    diagnosed: str
    diagnosed_raw: str
    confidence: float
    diagnosis_correct: bool
    outcome: str
    healed: bool
    duration_s: float


def _run_one(fault: str, rep: int, expected: str | None = None) -> Injection:
    expected = expected or fault
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
        patch("kavach.knowledge.retrieval.retrieve_similar_incidents", return_value=[]),
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
    raw = diagnosis.fault_class if diagnosis else "NONE"
    # The model sometimes answers "F05: connection pool exhaustion". plan_node
    # already normalises this way; scoring the raw string marked correct
    # diagnoses as wrong.
    diagnosed = raw.split(":")[0].split("(")[0].strip()
    confidence = float(diagnosis.confidence) if diagnosis else 0.0
    outcome = str(result.get("outcome"))

    return Injection(
        fault=fault,
        rep=rep,
        diagnosed=diagnosed,
        diagnosed_raw=raw,
        confidence=round(confidence, 3),
        diagnosis_correct=diagnosed == expected,
        outcome=outcome,
        healed=outcome in HEALED,
        duration_s=round(duration, 2),
    )


def _pct(num: int, den: int) -> float | None:
    return round(100 * num / den, 1) if den else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=5, help="reps per fault (PRD: 5)")
    ap.add_argument(
        "--out", type=Path, default=REPO_ROOT / "eval_results" / "rca_bench.json"
    )
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

    # The fails-closed study. Reported on its own: a case whose correct answer
    # is "I cannot tell" does not belong in an accuracy denominator, and its
    # outcome is correct precisely when nothing healed.
    print(f"\nFails-closed: {args.reps} reps of an undiagnosable scenario")
    closed: list[Injection] = []
    for rep in range(1, args.reps + 1):
        r = _run_one(AMBIGUOUS, rep, expected=NO_DIAGNOSIS)
        closed.append(r)
        print(
            f"  [{AMBIGUOUS} rep {r.rep}] dx={r.diagnosed:<22} conf={r.confidence:<5} "
            f"{'correct' if r.diagnosis_correct else 'GUESSED':<7} "
            f"outcome={r.outcome:<11} ({r.duration_s}s)",
            flush=True,
        )

    correct = [r for r in runs if r.diagnosis_correct]
    wrong = [r for r in runs if not r.diagnosis_correct]
    healed = [r for r in runs if r.healed]

    summary = {
        "injections": len(runs),
        "rca_accuracy_pct": _pct(len(correct), len(runs)),
        "heal_rate_pct": _pct(len(healed), len(runs)),
        # PRD 11.1: the conditionals are the point.
        "p_heal_given_correct_dx_pct": _pct(
            sum(1 for r in correct if r.healed), len(correct)
        ),
        "p_heal_given_wrong_dx_pct": _pct(
            sum(1 for r in wrong if r.healed), len(wrong)
        ),
        "p_correct_dx_given_heal_pct": _pct(
            sum(1 for r in healed if r.diagnosis_correct), len(healed)
        ),
        "median_loop_s": statistics.median(r.duration_s for r in runs)
        if runs
        else None,
        "fails_closed": {
            "reps": len(closed),
            "answered_insufficient_evidence": sum(
                1 for r in closed if r.diagnosed == NO_DIAGNOSIS
            ),
            "took_no_action": sum(1 for r in closed if not r.healed),
            "guesses": dict(
                Counter(r.diagnosed for r in closed if r.diagnosed != NO_DIAGNOSIS)
            ),
            "outcomes": dict(Counter(r.outcome for r in closed)),
        },
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
            (
                "Simulated state: these scenarios are hand-authored YAML and run "
                "against Kavach's simulated state, so verification is derived from "
                "declared thresholds rather than measured. Only F01-against-proof2 "
                "is a live measurement. Treat these as RCA-engine numbers, not "
                "platform numbers."
            ),
            (
                "No rules baseline: Phase 3's symptom mapping no longer exists and "
                "the catalogue carries a detect signal for F01, F03 and F07 only, "
                "so the LLM-vs-rules comparison PRD 11.2 asks for cannot be run."
            ),
            (
                "F08's evidence was changed between runs. It previously carried one "
                "log line and no indication that the configuration had changed, so "
                "every rep answered INSUFFICIENT_EVIDENCE -- correctly, on evidence "
                "that distinguished nothing. It now surfaces the config_errors "
                "signal it already declared and the version change that preceded "
                "the errors. The instrument changed, so this run is not directly "
                "comparable with the 88.9% recorded before it; both are in git."
            ),
            (
                "The fails-closed block is scored separately, against a scenario "
                "built to be undiagnosable. It is not in the accuracy denominator: "
                "a case whose correct answer is INSUFFICIENT_EVIDENCE would reward "
                "a model for refusing to answer anywhere."
            ),
            (
                "Every heal reports MITIGATED because outcome_node can only emit "
                "MITIGATED or ESCALATED; RESOLVED appears nowhere in graph/nodes.py "
                "and is set only by debt repayment. The outcome distribution is "
                "partly structural."
            ),
            (
                "Confidence is coerced: the model has been observed returning this "
                "field as both 1.0 and 100.0, so RCAResponse now treats a value in "
                "(1, 100] as a percentage and refuses anything further out of "
                "range. Raw values are not preserved here."
            ),
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
    print(
        f"P(heal | wrong dx)      {summary['p_heal_given_wrong_dx_pct']}%   <- luck in the headline"
    )
    print(f"P(correct dx | heal)    {summary['p_correct_dx_given_heal_pct']}%")
    print(f"outcomes                {summary['outcomes']}")
    if summary["misdiagnoses"]:
        print(f"misdiagnoses            {summary['misdiagnoses']}")
    fc = summary["fails_closed"]
    print(
        f"fails closed            {fc['answered_insufficient_evidence']}/{fc['reps']} "
        f"said INSUFFICIENT_EVIDENCE, {fc['took_no_action']}/{fc['reps']} took no action"
    )
    if fc["guesses"]:
        print(f"  guessed instead       {fc['guesses']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "summary": summary,
                "runs": [asdict(r) for r in runs],
                "fails_closed_runs": [asdict(r) for r in closed],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
