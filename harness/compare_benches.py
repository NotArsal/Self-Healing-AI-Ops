"""Two bench artifacts side by side, per fault class.

Built for one question: did changing the RCA model (qwen2.5:7b -> Groq
gpt-oss-120b) change anything, and where. Every score comes from
`report.Run`'s own properties, so this cannot drift from what the bench
itself counts.

It also lists:
- who answered each diagnosis. With a backup declared, a different model may
  have diagnosed some runs, and a model change that was really a backup change
  is a different finding. `RcaResult.model` is the answering client's own, so
  the backup shows up here even where the provider field reads "?".
- runs diagnosed correctly that did not heal. These are the candidates for
  ADR 0025's overturned approval, with the escalation reason verbatim.

Offline: reads two JSON files, touches nothing.

    python -I harness/compare_benches.py OLD.json NEW.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from dataclasses import fields
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "control-plane")]

from harness.report import Run  # noqa: E402

RUN_FIELDS = {f.name for f in fields(Run)}


def load(path: Path) -> tuple[str, list[Run]]:
    doc = json.loads(path.read_text("utf-8"))
    runs = [Run(**{k: v for k, v in r.items() if k in RUN_FIELDS})
            for r in doc["runs"]]
    label = f"{path.stem} [{doc.get('rca_model') or '?'}]"
    return label, [r for r in runs if not r.error]


def med(xs: list[float | None]) -> str:
    vals = [x for x in xs if x is not None]
    return f"{statistics.median(vals):.1f}" if vals else "-"


def score(runs: list[Run]) -> dict[str, Any]:
    n = len(runs)
    return {
        "n": n,
        "rca": sum(r.diagnosis_correct for r in runs),
        "action": sum(r.action_correct for r in runs),
        "healed": sum(r.resolved for r in runs),
        "false_heal": sum(r.false_healing for r in runs),
        "mttd": med([r.mttd_s for r in runs if r.detected]),
        "mttr": med([r.mttr_s for r in runs if r.resolved]),
    }


def line(label: str, s: dict[str, Any]) -> str:
    n = s["n"]
    return (f"  {label:<46} rca {s['rca']}/{n}  action {s['action']}/{n}  "
            f"healed {s['healed']}/{n}  false_heal {s['false_heal']}  "
            f"mttd {s['mttd']}s  mttr {s['mttr']}s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    args = ap.parse_args()
    benches = [load(args.old), load(args.new)]

    classes = sorted({r.fault_class for _, runs in benches for r in runs})
    for fc in [*classes, "ALL"]:
        print(fc)
        for model, runs in benches:
            picked = runs if fc == "ALL" else [r for r in runs if r.fault_class == fc]
            print(line(model, score(picked)))

    for model, runs in benches:
        print(f"\n{model}")
        print("  answered by:", dict(Counter(r.llm_answered_by or "(not recorded)"
                                             for r in runs)))
        missed = [r for r in runs if r.diagnosis_correct and not r.resolved]
        for r in missed:
            print(f"  correct but not healed: rep {r.rep} {r.fault_class} "
                  f"{r.incident_id}: {r.escalation_reason[:160]}")
        if not missed:
            print("  correct but not healed: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
