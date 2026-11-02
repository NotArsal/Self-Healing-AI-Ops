"""Would majority voting over k samples have helped? Measured, not argued.

THE PROPOSAL THIS TESTS
The dominant remedy in the literature for unreliable LLM judgements is
test-time sampling: draw k answers and aggregate. CISC (arXiv 2502.06233)
reports cutting required reasoning paths by over 40% with confidence-weighted
voting; conformal aggregation (2605.14098) reports 90.1% selective accuracy on
GSM8K by abstaining on under 5% of problems; Mirror-Consistency (2410.10857)
mines the minority views for calibration. Any reviewer of this project will
ask why Kavach does not sample.

WHY THE ANSWER IS ALREADY IN THE ARTIFACTS
`rca_*_live.py` collects the evidence frame ONCE and diagnoses against that
fixed frame ten times - which is exactly a self-consistency experiment, run
long before anyone framed it as one. Each artifact is k=10 draws over one
prompt. So the question needs no new inference: replay the recorded draws and
ask what majority voting would have returned.

WHAT TO LOOK FOR
Majority voting can only help where the draws DISAGREE. If the model returns
the same class on every draw, voting returns that class, and when the class is
wrong voting returns a wrong answer with maximal apparent agreement - the worst
possible combination, because unanimity reads as confidence.

    python -I harness/self_consistency.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "harness" / "reports"

# (file, injected class, label). The F07 entries are an ablation series over
# the PromQL frame window (ADR 0013), deliberately including configurations
# known to fail - which is what makes them useful here: they supply the wrong
# answers that voting would have to rescue.
FIXED_FRAME_RUNS: list[tuple[str, str, str]] = [
    ("p6-f01-rca.json", "F01", "llama3.2"),
    ("p6-f01-rca-symmetric.json", "F01", "llama3.2, symmetric prompt"),
    ("p6-f07-rca.json", "F07", "llama3.2"),
    ("p6-f07-rca-qwen.json", "F07", "qwen, frame [10m]"),
    ("p6-f07-rca-qwen-ctx8192.json", "F07", "qwen, frame [1m], ctx 8192"),
    ("p6-f07-rca-qwen-ctx4096-ab.json", "F07", "qwen, frame [1m], ctx 4096"),
    ("p6-f07-rca-qwen-frame10m-ab.json", "F07", "qwen, frame [10m] A/B"),
    ("p6-f08-rca.json", "F08", "llama3.2"),
    ("p6-f08-rca-qwen.json", "F08", "qwen, shipped"),
]


def frames() -> list[dict[str, Any]]:
    """Every fixed-frame draw set available, as (injected, [classes])."""
    out: list[dict[str, Any]] = []
    for fname, injected, label in FIXED_FRAME_RUNS:
        path = REPORTS / fname
        if not path.is_file():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        classes = [str(r.get("fault_class")) for r in doc.get("runs", [])
                   if r.get("fault_class")]
        if classes:
            out.append({"source": fname, "injected": injected,
                        "label": label, "classes": classes})

    # The ambiguity experiment's arms are fixed-frame draw sets too, and arm B
    # is the one case where the frame itself was the variable.
    amb = REPORTS / "ambiguity-f08.json"
    if amb.is_file():
        doc = json.loads(amb.read_text(encoding="utf-8"))
        for arm in doc.get("arms", []):
            if not arm.get("valid"):
                continue
            classes = [str(r.get("fault_class")) for r in arm.get("rows", [])
                       if r.get("fault_class")]
            if classes:
                out.append({
                    "source": f"ambiguity-f08.json arm {arm['arm']}",
                    "injected": "F08", "classes": classes,
                    "label": f"frame error ratio {arm.get('frame_error_ratio')}",
                })
    return out


def main() -> int:
    data = frames()
    if not data:
        print("no fixed-frame artifacts found")
        return 1

    hdr = (f"  {'frame':46} {'inj':>4} {'draws':>6} {'majority':>9} "
           f"{'unanimous':>10}  distribution")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    draws = correct_draws = 0
    maj_correct = unanimous = unanimous_wrong = changed = 0
    rescued = broken = 0
    for f in data:
        classes: list[str] = f["classes"]
        inj: str = f["injected"]
        counts = Counter(classes)
        top, n = counts.most_common(1)[0]
        is_unanimous = n == len(classes)
        maj_ok = top == inj

        draws += len(classes)
        correct_draws += sum(1 for c in classes if c == inj)
        maj_correct += maj_ok
        unanimous += is_unanimous
        unanimous_wrong += is_unanimous and not maj_ok
        # Would voting have differed from simply taking the first draw?
        changed += top != classes[0]
        # And the only question that matters: did it change CORRECTNESS?
        first_ok = classes[0] == inj
        rescued += maj_ok and not first_ok
        broken += first_ok and not maj_ok

        print(f"  {f['source']:46} {inj:>4} {len(classes):>6} "
              f"{top + (' ok' if maj_ok else ' WRONG'):>9} "
              f"{is_unanimous!s:>10}  {dict(counts)}  {f['label']}")

    n_frames = len(data)
    print()
    print(f"  frames                          {n_frames}")
    print(f"  individual draws                {draws}")
    print(f"  single-draw accuracy            {correct_draws}/{draws} = "
          f"{correct_draws / draws:.0%}")
    print(f"  majority-vote accuracy          {maj_correct}/{n_frames} = "
          f"{maj_correct / n_frames:.0%}")
    print(f"  unanimous frames                {unanimous}/{n_frames}")
    print(f"  UNANIMOUSLY WRONG frames        {unanimous_wrong}/{n_frames}")
    print(f"  voting differed from 1st draw   {changed}/{n_frames}")
    print(f"  ... and FIXED a wrong frame     {rescued}/{n_frames}")
    print(f"  ... and BROKE a right frame     {broken}/{n_frames}")
    print()
    print("  Majority voting can only act where the draws disagree. Where it")
    print("  cannot act, it costs k times the inference and returns the same")
    print("  answer - and on a unanimously wrong frame it returns that wrong")
    print("  answer with maximal apparent agreement, which is worse than a")
    print("  split would have been, because unanimity reads as confidence.")

    (REPORTS / "self-consistency.json").write_text(json.dumps({
        "question": "would majority voting over the recorded fixed-frame "
                    "draws have changed any outcome?",
        "frames": n_frames, "draws": draws,
        "single_draw_accuracy": round(correct_draws / draws, 4),
        "majority_vote_accuracy": round(maj_correct / n_frames, 4),
        "unanimous_frames": unanimous,
        "unanimously_wrong_frames": unanimous_wrong,
        "frames_where_voting_changed_the_answer": changed,
        "frames_voting_rescued": rescued,
        "frames_voting_broke": broken,
        "detail": data,
    }, indent=2), encoding="utf-8")
    print(f"  artifact  {REPORTS / 'self-consistency.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
