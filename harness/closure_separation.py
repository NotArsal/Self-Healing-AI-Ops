"""Does evidence closure separate a right diagnosis from a wrong one?

THE QUESTION, AND WHY IT IS WORTH ASKING
`REPORT_DRAFT.md` §4.2 measures two self-reported reliability channels -
the model's own confidence, and whether its `fault_name` agrees with the class
code it emitted - and finds neither separates a correct diagnosis from an
incorrect one. §8 notes that the literature prices risk along three axes
(2607.20005: blast radius, reversibility, epistemic uncertainty) and that
Kavach has the first two.

Evidence closure is the obvious third candidate. `Cloud-OpsBench`
(2603.00468) reports Joint RCA Accuracy 0.76 against an Evidence Closure Rate
of 0.38 and concludes that final-answer correctness substantially
overestimates evidence-grounded diagnosis. If closure separates here, it is a
cheap uncertainty signal already computable from every diagnosis Kavach makes.

This script answers it, and the answer is no. It is reported as a negative
result with its own methodology stated, because the interesting part is WHY.

WHAT THIS ADDS TO `evidence_closure.py`, WHICH IS NOT THE SAME QUESTION
That script asks how often diagnoses cite own-class evidence. This one asks
whether that citation predicts being right, which needs the two outcomes
compared within one configuration.

THE P6 ARTIFACTS CANNOT ANSWER IT, AND THAT IS THE FIRST FINDING
Pooled over the nine `p6-*-rca*.json` files, closure on the named class looks
NEGATIVELY associated with correctness: every one of the 41 wrong diagnoses
cited evidence for the class it named, against 39 of 49 correct ones.

That number is not a finding, it is an artifact, and the per-file breakdown
shows why: **every one of those files is all-correct or all-wrong.** Outcome
is perfectly confounded with artifact, so the 2x2 compares conditions rather
than diagnoses. All ten "correct but not closed" cases come from
`p6-f01-rca.json`, whose own docstring in `evidence_closure.py` already
explains them - that run reasoned from the LOGS and never cited the
error-ratio metric, which is a property of the prompt, not of grounding.

Recorded here so nobody pools those files and reports -0.20 as a result.

`diagnoses-20261020.json` is the one artifact with within-condition variation:
37 diagnoses, one model, one run, both outcomes present.

A LIMIT ON WHAT "RIGHT" CAN MEAN HERE, STATED BECAUSE IT MATTERS
That artifact records no injected class. The only reference available is
`detection_class`, the deterministic detector's verdict - so what is measured
is **agreement with the detector**, not correctness against ground truth.
`report.py` carries a long comment about exactly this substitution flattering
RCA accuracy once before, so it is named rather than glossed. The conclusion
below survives the distinction because it is about a ceiling, not a rate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.evidence_closure import (  # noqa: E402
    DISCRIMINATING,
    SOURCES,
    id_for_name,
)

REPORTS = ROOT / "harness" / "reports"
MIXED = REPORTS / "diagnoses-20261020.json"


def discriminating_ids() -> dict[str, set[str]]:
    names = id_for_name()
    return {cls: {names[s] for s in sigs if s in names}
            for cls, sigs in DISCRIMINATING.items()}


def rate(hits: int, total: int) -> str:
    return f"{hits}/{total} = {hits / total:.2f}" if total else f"{hits}/0 = n/a"


def confounding_check() -> None:
    """Show that the p6 artifacts cannot answer the question."""
    print("THE P6 ARTIFACTS: outcome is confounded with file")
    print(f"  {'artifact':34s} {'n':>3} {'correct':>8} {'wrong':>6}")
    mixed_files = 0
    for fname, injected, _label in SOURCES:
        path = REPORTS / fname
        if not path.is_file():
            continue
        doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        rows = [r for r in doc.get("runs", []) if r.get("cited")]
        if not rows:
            continue
        ok = sum(1 for r in rows if str(r.get("fault_class") or "") == injected)
        if 0 < ok < len(rows):
            mixed_files += 1
        print(f"  {fname[:33]:34s} {len(rows):>3} {ok:>8} {len(rows) - ok:>6}")
    print()
    print(f"  files containing BOTH outcomes: {mixed_files}")
    print("  With outcome constant inside almost every file, a pooled 2x2")
    print("  compares conditions, not diagnoses. Not usable for this question.")
    print()


def separation(want: dict[str, set[str]]) -> None:
    doc: dict[str, Any] = json.loads(MIXED.read_text(encoding="utf-8"))
    agree: list[tuple[bool, bool]] = []
    disagree: list[tuple[bool, bool]] = []
    models = set()
    for row in doc.get("rows", []):
        diag = row.get("diagnosis") or {}
        cited = set(diag.get("evidence_ids") or [])
        detector = str(row.get("detection_class") or "")
        named = str(diag.get("fault_class") or "")
        if not cited or not detector or not named:
            continue
        models.add(str(row.get("model") or "?"))
        pair = (bool(want.get(named, set()) & cited),
                bool(want.get(detector, set()) & cited))
        (agree if named == detector else disagree).append(pair)

    n = len(agree) + len(disagree)
    print(f"{MIXED.name}: {n} diagnoses, model(s) {sorted(models)}")
    print("  reference is the DETERMINISTIC detector's verdict, not an")
    print("  injected class - so this is agreement, not correctness.")
    print(f"  agreed {len(agree)}, disagreed {len(disagree)}")
    print()
    for idx, label in ((0, "closure on the class the MODEL NAMED"),
                       (1, "closure on the DETECTOR's class")):
        a = sum(1 for p in agree if p[idx])
        b = sum(1 for p in disagree if p[idx])
        print(f"  --- {label} ---")
        print(f"    P(closed | agreed)    = {rate(a, len(agree))}")
        print(f"    P(closed | disagreed) = {rate(b, len(disagree))}")
        if agree and disagree:
            print(f"    separation            = "
                  f"{a / len(agree) - b / len(disagree):+.2f}")
        print()


def main() -> int:
    want = discriminating_ids()
    confounding_check()
    if not MIXED.is_file():
        print(f"MISSING: {MIXED}")
        return 1
    separation(want)
    print("THE CONCLUSION")
    print("  Closure on the reference class is at CEILING: every diagnosis,")
    print("  including every one that named a different class, had already")
    print("  cited the evidence that discriminates the detector's class.")
    print("  A metric pinned at 1.00 cannot separate anything, so evidence")
    print("  closure joins confidence and fault-name coherence as a channel")
    print("  that carries no usable uncertainty signal here.")
    print()
    print("  The reason is architectural rather than a property of the model.")
    print("  Cloud-OpsBench measures 0.38 closure because its agents must find")
    print("  their own evidence in raw telemetry and often do not. Kavach hands")
    print("  the model a bounded frame built by a deterministic extractor, so")
    print("  the relevant evidence is already in front of it and citing it is")
    print("  nearly free. The bounded frame - the design decision section 8.1 defends")
    print("  - is what saturates the metric.")
    print()
    print("  So the model's errors here are not ungrounded in the sense that")
    print("  metric was built to detect. It looked at the right evidence and")
    print("  drew the wrong conclusion, which is a harder failure to catch and")
    print("  the reason the deterministic cross-check in section 4.4 exists.")
    print()
    print("  NOT CLAIMED: that named-class closure is a signal. It differs")
    print("  between the arms, but the minority arm is n=5, which is an")
    print("  observation and not a result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
