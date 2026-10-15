"""The human baseline PRD 11.2 asks for. Needs a person; everything else is here.

Without it, MTTR has no denominator and any speed-up factor quoted against a
human is invented. It cannot be automated -- that is the point of it -- so this
harness does the parts that can be: it shows an operator exactly the evidence
the model is given, times them, scores their answer the same way, and writes
`eval_results/human_baseline.json` for `harness/report.py` to render.

Run it:

    cd apps/control-plane && uv run python -m harness.human_baseline

Nine cases in a random order, one pass, roughly two hours. No application and no
model are needed: this measures a person against the same evidence, in the same
SIMULATION mode, which is what makes the comparison fair.

Rules for whoever sits down to it:

  * Do not open `scenarios/` or `catalogue_data/` while the clock is running.
    The fault class is in the filename.
  * Answer from the evidence shown, as you would at 3am from an alert.
  * "I cannot tell" is a legitimate answer. Type `?` for it. A human who
    declines is not a failure, and the machine's inability to decline is
    measured in docs/MEASUREMENTS.md 3.1.
  * Stop whenever you like; everything answered so far is written out.
"""

import argparse
import json
import random
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from kavach.catalogue.loader import load_catalogue
from kavach.scenarios.loader import load_scenario
from kavach.topology.graph import build_topology_graph

REPO_ROOT = Path(__file__).resolve().parents[3]
FAULTS = [f"F0{i}" for i in range(1, 10)]
DECLINE = "?"


@dataclass
class HumanCase:
    fault: str
    answered: str
    repair: str
    diagnosis_correct: bool
    repair_correct: bool
    seconds: float


def _present(fault: str) -> None:
    """Everything the RCA prompt is given, and nothing that names the answer."""
    scenario = load_scenario(fault)

    print("\n" + "=" * 72)
    print("SYSTEM TOPOLOGY")
    print(build_topology_graph(scenario.services).describe_topology())

    print("\nHEALTH")
    for name, state in (scenario.health or {}).items():
        print(f"  {name}: {state}")

    if scenario.objectives:
        print("\nOBJECTIVES (current vs threshold)")
        for name, obj in scenario.objectives.items():
            print(f"  {name}: {obj.value} (threshold {obj.threshold})")

    if scenario.signals:
        print("\nSIGNALS")
        for name, value in scenario.signals.items():
            print(f"  {name}: {value}")

    print("\nEVIDENCE")
    for ev in scenario.evidence or []:
        print(f"  {ev.id} | {ev.kind} | source={ev.source} | value={ev.value}")
        if ev.payload:
            print(f"    {ev.payload}")
    print("=" * 72)


def _ask(prompt: str, allowed: set[str] | None = None) -> str:
    while True:
        answer = input(prompt).strip()
        if not answer:
            continue
        if allowed is None or answer in allowed or answer == DECLINE:
            return answer
        print(f"  not one of: {', '.join(sorted(allowed))}, or {DECLINE}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out", type=Path, default=REPO_ROOT / "eval_results" / "human_baseline.json"
    )
    ap.add_argument("--operator", default="", help="recorded in the artifact")
    args = ap.parse_args()

    catalogue = load_catalogue()
    actions = sorted(catalogue.actions)
    order = FAULTS[:]
    random.shuffle(order)

    print(__doc__)
    print(f"\nFault classes you may answer: {', '.join(FAULTS)}, or {DECLINE}")
    print(f"Repair actions you may choose: {', '.join(actions)}")
    input("\nPress Enter to start the first case. The clock starts when it prints.")

    cases: list[HumanCase] = []
    try:
        for i, fault in enumerate(order, start=1):
            print(f"\n\n--- case {i} of {len(order)} ---")
            started = time.time()
            _present(fault)
            answered = _ask("Your diagnosis (fault class): ", set(FAULTS))
            repair = (
                DECLINE
                if answered == DECLINE
                else _ask("The repair you would run: ", set(actions))
            )
            seconds = time.time() - started

            declared = catalogue.faults.get(fault)
            expected_repair = declared.repair.action if declared and declared.repair else ""
            cases.append(
                HumanCase(
                    fault=fault,
                    answered=answered,
                    repair=repair,
                    diagnosis_correct=answered == fault,
                    repair_correct=bool(expected_repair) and repair == expected_repair,
                    seconds=round(seconds, 1),
                )
            )
            print(f"  recorded in {seconds:.0f}s")
    except (KeyboardInterrupt, EOFError):
        print("\nstopped early; writing what was answered")

    if not cases:
        print("nothing answered, nothing written")
        return 1

    correct = [c for c in cases if c.diagnosis_correct]
    declined = [c for c in cases if c.answered == DECLINE]
    summary = {
        "operator": args.operator,
        "cases": len(cases),
        "diagnosis_accuracy_pct": round(100 * len(correct) / len(cases), 1),
        "repair_accuracy_pct": round(
            100 * sum(1 for c in cases if c.repair_correct) / len(cases), 1
        ),
        "declined_pct": round(100 * len(declined) / len(cases), 1),
        "median_seconds": statistics.median(c.seconds for c in cases),
        "mean_seconds": round(statistics.fmean(c.seconds for c in cases), 1),
        "slowest_seconds": max(c.seconds for c in cases),
        "fastest_seconds": min(c.seconds for c in cases),
        "caveats": [
            (
                "One pass, not five reps: a person cannot sit through 45 cases and "
                "the later ones would measure fatigue and recall rather than "
                "diagnosis. The machine's figures are five reps per fault."
            ),
            (
                "Time to a diagnosis and a chosen repair, not to a repaired "
                "application. Executing the repair by hand is not measured, so "
                "this is a floor on human MTTR, not human MTTR."
            ),
            (
                "Same evidence, same SIMULATION mode, same catalogue of repairs as "
                "the model is offered. No application and no model are involved."
            ),
            (
                "One operator unless the artifact says otherwise. Treat it as an "
                "anecdote with a stopwatch, which is still more than an invented "
                "number."
            ),
        ],
        "per_case": [asdict(c) for c in cases],
    }

    print("\n--- Human baseline ---")
    print(f"cases                {summary['cases']}")
    print(f"diagnosis accuracy   {summary['diagnosis_accuracy_pct']}%")
    print(f"repair accuracy      {summary['repair_accuracy_pct']}%")
    print(f"declined             {summary['declined_pct']}%")
    print(f"median time          {summary['median_seconds']}s")
    print(f"mean time            {summary['mean_seconds']}s")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary}, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    print("`make bench` will render it into docs/MEASUREMENTS.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
