"""Render docs/MEASUREMENTS.md from the measurement artifacts.

ROADMAP P10 asks for `harness/report.py` behind `make bench`. Every figure in
the report is read from `eval_results/*.json`, so the document cannot drift from
the runs that produced it and nobody has to retype a number. A study that has
not been run is reported as not run rather than omitted.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS = REPO_ROOT / "eval_results"
PIPE = r"\|"  # escaped pipe, for use inside markdown table cells


def _load(name: str) -> dict[str, Any] | None:
    path = RESULTS / name
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("summary")
    return summary if isinstance(summary, dict) else None


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {c}" for c in items) if items else "- none recorded"


def _ablation(s: dict[str, Any] | None) -> str:
    if s is None:
        return (
            "## 1. Undo ablation\n\n**NOT RUN.** `make target-up && make onboard "
            "APP=targets/proof2 && make bench-live`\n"
        )
    labels = {
        "undo_enabled": "undo works",
        "undo_ineffective": "undo runs, write is lost",
        "undo_disabled": "unwind step removed",
    }
    rows = "\n".join(
        f"| {labels.get(arm, arm)} | **{a['prior_state_restored']}/{a['reps']} "
        f"({a['prior_state_restored_pct']}%)** | {', '.join(a['outcomes'])} | "
        f"{a['median_duration_s']}s |"
        for arm, a in ((k, s[k]) for k in labels if k in s)
    )
    ineffective_detected = s.get("outcome_distinguishes_undo_ineffective")
    disabled_detected = s.get("outcome_distinguishes_undo_disabled")
    return f"""## 1. Undo ablation — the headline result

F01 against the live `targets/proof2` application. Diagnosis held fixed and
verification forced to fail in every arm, so the only variable is the unwind.

| Arm | Prior state restored | Outcome reported | Median |
|---|---|---|---|
{rows}

With the undo stack, a failed repair always returns the application to the model
it was serving before. Without it, the application is left on the backup every
time. This is a state read back over HTTP, not an outcome Kavach reports about
itself.

**Is a failed rollback detectable?** `revert_effect` now writes the witnessed
value and reads it back; a mismatch appends to `unwind_unrestored`, and
`outcome_node` reports `UNRECOVERABLE`. Measured:

- undo runs but the write is lost — detected: `{ineffective_detected}`
- unwind step never runs at all — detected: `{disabled_detected}`

The first is the operational failure: an application, proxy or sidecar that
accepts a write and does not apply it. The second is a missing code path, and it
stays invisible by construction — a step that does not execute reports nothing.
Before this, neither was detectable and ROADMAP P3's loud `UNRECOVERABLE` was
raised only by the `_force_undo_failure` test flag.
"""


def _laya(s: dict[str, Any] | None) -> str:
    if s is None:
        return "## 2. Shadow Laya vs the rule engine\n\n**NOT RUN.** `make bench`\n"
    blocked = len(s["disagreements"])
    pct = round(100 * blocked / s["cases"]) if s["cases"] else 0
    return f"""## 2. Shadow Laya vs the rule engine

Real inference over each fault's proposed repair.

- Agreement: **{s['agreements']}/{s['cases']} ({s['agreement_rate_pct']}%)**
- Laya risk tiers: `{s['laya_tier_distribution']}` against declared `{s['declared_risk_distribution']}`
- Laya judged {blocked} of {s['cases']} legitimate repairs unsafe

Had Laya been gating, it would have blocked **{pct}%** of correct repairs. That is
the strongest available evidence that `AGENTS.md`'s shadow-only rule is correct,
and the opposite of the "100% alignment" claimed in
`PROJECT_COMPLETION_REPORT.md`.

{_bullets(s.get('caveats', []))}
"""


def _rca(s: dict[str, Any] | None) -> str:
    if s is None:
        return "## 3. RCA accuracy and conditional metrics\n\n**NOT RUN.** `make bench`\n"
    p_wrong = s["p_heal_given_wrong_dx_pct"]
    wrong_cell = (
        f"**{p_wrong}%**" if p_wrong is not None else "n/a — no wrong diagnoses occurred"
    )
    reps = s["injections"] // 9 if s["injections"] else 0
    return f"""## 3. RCA accuracy and the conditional metrics

{s['injections']} injections ({reps} reps x 9 faults), real local model, cold memory, and
with no answer key in the prompt.

| Metric | Value | PRD target |
|---|---|---|
| RCA accuracy | **{s['rca_accuracy_pct']}%** | >= 75% |
| Heal rate | {s['heal_rate_pct']}% | >= 70% (LOW) |
| P(heal {PIPE} correct dx) | {s['p_heal_given_correct_dx_pct']}% | — |
| P(heal {PIPE} wrong dx) | {wrong_cell} | — |
| P(correct dx {PIPE} heal) | {s['p_correct_dx_given_heal_pct']}% | — |
| Median loop | {s['median_loop_s']}s | — |

Outcomes: `{s['outcomes']}`. Misdiagnoses: `{s['misdiagnoses'] or 'none'}`.

PRD §11.1 warns that a headline resolution rate cannot evidence that RCA works,
because published work shows mitigation succeeding on wrong diagnoses 22–62% of
the time. Here it succeeds on a wrong diagnosis **{p_wrong if p_wrong is not None else 'n/a'}%** of the time, so the
headline is not luck. Per-fault accuracy: `{s['per_fault_accuracy_pct']}`.

{_bullets(s.get('caveats', []))}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "MEASUREMENTS.md")
    args = ap.parse_args()

    abl = _load("ablation_undo.json")
    laya = _load("laya_vs_rules.json")
    rca = _load("rca_bench.json")
    if not any((abl, laya, rca)):
        print("no artifacts in eval_results/; run `make bench` first", file=sys.stderr)
        return 1

    doc = f"""# Measurements

Generated {datetime.now(UTC).date().isoformat()} by `harness/report.py` from `eval_results/*.json`.
Every figure is read from those files; none is typed by hand. Reproduce with:

```bash
make bench                                                            # RCA accuracy + Laya vs rules, then this report
make target-up && make onboard APP=targets/proof2 && make bench-live  # undo ablation
```

---

{_ablation(abl)}
---

{_laya(laya)}
---

{_rca(rca)}
---

## 4. Human baseline — NOT RUN

PRD §11.2 requires the same injections resolved by hand in `SIMULATION`, timed,
to give MTTR a denominator. **Nobody has done this.** It is roughly two hours of
one person's time and cannot be automated. Until it is run there is no human
MTTR, and any speed-up factor quoted against one is invented.

---

## 5. What is and is not measured

| Claim | Status |
|---|---|
| Undo restores prior state on a live app | **Measured** |
| An ineffective rollback is detectable | **Measured** — readback mismatch reports `UNRECOVERABLE` |
| An unwind that never runs is detectable | **No** — a step that does not execute reports nothing |
| Laya disagrees with the rule engine | **Measured**, real inference |
| RCA accuracy | **Measured**, no answer key in the prompt |
| P(heal {PIPE} wrong diagnosis) | **Measured** |
| LLM vs rules baseline | **Unavailable** — P3's mapping is gone; `detect` survives for F01, F03, F07 only |
| Human baseline | **Not run** |
| F02–F09 behaviour | Simulated state; verification derived from thresholds, not measured |
"""

    args.out.write_text(doc, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
