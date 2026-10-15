"""Shadow Laya against the rule engine, on the actions the catalogue proposes.

PRD 11.2 asks for agreement rate, the disagreement cases, and which was right.
The previous version of this study never invoked Laya: it derived "Laya's
answer" from the dataset's own ground-truth labels with a hand-written
expression and compared it to another hand-written expression, so its agreement
rate described two constants. This one runs the model.

permit() is the authority by construction -- Laya is shadow and cannot gate
(AGENTS.md) -- so a disagreement is a Laya error, not a tie to adjudicate. The
interesting output is therefore the disagreement cases themselves.

Caveat recorded in the output: Laya's risk tier cannot be scored against the
catalogue, because every fault currently loads as LOW (the per-fault YAML files
replace core.yaml's entries instead of merging, dropping their declared tiers).
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from kavach.catalogue.loader import load_catalogue
from kavach.decision.laya import shadow_evaluate
from kavach.safety.engine import permit
from kavach.scenarios.loader import load_scenario
from kavach.tnr.models import Action

REPO_ROOT = Path(__file__).resolve().parents[3]
FAULTS = [f"F0{i}" for i in range(1, 10)]


def _planned_action(fault_def: Any) -> Action | None:
    if fault_def.repair:
        return Action(name=fault_def.repair.action, params=fault_def.repair.params)
    if fault_def.recommended_actions:
        return Action(name=fault_def.recommended_actions[0], params={})
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "eval_results" / "laya_vs_rules.json")
    args = ap.parse_args()

    catalogue = load_catalogue()
    rows: list[dict[str, Any]] = []

    print("Shadow Laya vs the rule engine, on each fault's proposed repair\n")
    for fault in FAULTS:
        fault_def = catalogue.faults.get(fault)
        if fault_def is None:
            continue
        action = _planned_action(fault_def)
        if action is None:
            continue

        scenario = load_scenario(fault)
        rule = permit(action, scenario, [])
        laya = shadow_evaluate(action.name, f"Fault {fault} on scenario {scenario.id}")

        agree = rule.is_allowed == laya.is_safe
        rows.append(
            {
                "fault": fault,
                "action": action.name,
                "declared_risk": fault_def.risk,
                "rule_allowed": rule.is_allowed,
                "rule_reason": rule.reason,
                "laya_is_safe": laya.is_safe,
                "laya_risk_tier": laya.risk_tier,
                "laya_reason": laya.reason,
                "laya_confidence": round(laya.confidence, 4),
                "agree": agree,
            }
        )
        mark = "agree" if agree else "DISAGREE"
        print(
            f"  {fault} {action.name:<24} rule={'ALLOW' if rule.is_allowed else 'DENY':<5} "
            f"laya={'safe' if laya.is_safe else 'unsafe':<6} tier={laya.risk_tier:<6} "
            f"conf={laya.confidence:.2f}  {mark}"
        )

    agreements = sum(1 for r in rows if r["agree"])
    tiers = Counter(r["laya_risk_tier"] for r in rows)
    declared = Counter(r["declared_risk"] for r in rows)

    summary = {
        "cases": len(rows),
        "agreements": agreements,
        "agreement_rate_pct": round(100 * agreements / len(rows), 1) if rows else None,
        "laya_tier_distribution": dict(tiers),
        "declared_risk_distribution": dict(declared),
        "disagreements": [r for r in rows if not r["agree"]],
        "caveats": [
            ("permit() is the authority: Laya is shadow-only and cannot gate, so "
            "every disagreement is a Laya error rather than a tie."),
            ("Laya's risk tier is reported, not scored. The declared tiers are "
            "LOW for seven faults and MEDIUM for two, and nine cases over two "
            "classes is too thin to call it agreement or disagreement."),
            ("Laya confidence is reported as returned. The checkpoint ships "
            "invalid temperatures (runtime warning on load), so treat it as "
            "uncalibrated."),
        ],
    }

    print("\n--- Laya vs rules ---")
    print(f"agreement {agreements}/{len(rows)} ({summary['agreement_rate_pct']}%)")
    print(f"laya tiers: {dict(tiers)}   declared: {dict(declared)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
