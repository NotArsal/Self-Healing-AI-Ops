"""Undo ablation: what a failed repair costs when the undo stack is removed.

PRD 11.2 calls this the strongest research output available here, and it only
became measurable once F01 ran against a live application. Before that there was
nothing to observe: the previous version of this study ran the graph with undo
*enabled* and then hardcoded "outcome_without_undo": "UNRECOVERABLE" from a
comment, so its result was asserted rather than measured.

Design. The measured variable is whether the application is returned to the
state it was in before the repair. That is purely executor and TNR behaviour, so
the diagnosis is held fixed and verification is forced to fail -- the point is
what happens *after* a repair is judged bad, not whether it is judged bad. Every
arm gets identical treatment; only the unwind step differs.

Three arms, because the first run of this study showed that "undo removed" and
"undo working" reported the same outcome, and the fix for that distinguishes two
different failures:

  undo_enabled      the unwind runs and the application is restored
  undo_ineffective  the unwind runs, the write is lost, the readback catches it
  undo_disabled     the unwind step never executes at all

undo_ineffective is the operational failure: an application, proxy or sidecar
that accepts a write and does not apply it. undo_disabled is a missing code
path, kept as the control because it is what the previous version measured.

Shadow Laya is stubbed. It cannot affect an outcome by construction (it is
advisory), and leaving it in costs a local model inference per gate call.

Requires `make target-up` and the baseline from `make onboard`.
"""

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = REPO_ROOT / "targets" / "proof2" / "kavach.yaml"
BASE = "http://127.0.0.1:8080"
PRE_INCIDENT_MODEL = "primary"
ARMS = ("undo_enabled", "undo_ineffective", "undo_disabled")


@dataclass
class Run:
    arm: str
    rep: int
    outcome: str
    final_model: str
    prior_state_restored: bool
    duration_s: float


def _reset_target() -> None:
    httpx.post(f"{BASE}/revert/F01", timeout=5)
    httpx.post(f"{BASE}/v1/admin/model", json={"model": PRE_INCIDENT_MODEL}, timeout=5)


def _current_model() -> str:
    return str(httpx.get(f"{BASE}/v1/admin/model", timeout=5).json()["model"])


def _one_run(arm: str, rep: int) -> Run:
    from kavach.detection.monitor import build_incident_scenario, detect_breach
    from kavach.graph.state import IncidentState
    from kavach.llm.rca import RCAResponse
    from kavach.remediation.tnr_gate import SafetyAssessment
    from kavach.scenarios.from_manifest import load_target

    _reset_target()
    assert _current_model() == PRE_INCIDENT_MODEL, "target did not reset"

    target = load_target(MANIFEST)
    httpx.post(f"{BASE}/inject/F01", timeout=5)
    breach = detect_breach(target)
    if breach is None:
        raise RuntimeError("injected F01 but detection saw no breach")

    scenario = build_incident_scenario(target, breach, scenario_id=f"abl-{arm}-{rep}")

    fixed_diagnosis = RCAResponse(
        fault_class="F01", confidence=0.95, evidence_ids=[], rejected_alternatives=[]
    )

    def _noop_unwind(state: IncidentState) -> IncidentState:
        return {}

    def _ineffective_revert(
        effect: Any, record: Any, rs_def: Any, mode: str
    ) -> bool:
        """The unwind runs, the write is lost, the readback is real."""
        from kavach.remediation.runtime_config import read_value

        witnessed = record.pre_state_witness.get(effect.key)
        return read_value(rs_def) == str(witnessed)

    patches = [
        patch("kavach.graph.nodes.analyze_root_cause", return_value=fixed_diagnosis),
        # The repair is judged bad in both arms. Only the response differs.
        patch("kavach.graph.nodes.verify_live", return_value=(False, {})),
        patch(
            "kavach.remediation.tnr_gate.evaluate_safety",
            lambda action, context: SafetyAssessment(is_safe=True, reason="stubbed"),
        ),
    ]
    if arm == "undo_disabled":
        patches.append(patch("kavach.graph.workflow.unwind_node", _noop_unwind))
    elif arm == "undo_ineffective":
        patches.append(patch("kavach.graph.nodes.revert_effect", _ineffective_revert))

    started = time.time()
    with _nested(patches):
        from kavach.graph.workflow import build_workflow

        result = build_workflow().invoke(
            IncidentState(
                incident_id=f"abl-{arm}-{rep}",
                scenario=scenario,
                mode="AUTONOMOUS",
                simulation_state={},
            )
        )
    duration = time.time() - started

    final_model = _current_model()
    return Run(
        arm=arm,
        rep=rep,
        outcome=str(result.get("outcome")),
        final_model=final_model,
        prior_state_restored=final_model == PRE_INCIDENT_MODEL,
        duration_s=round(duration, 2),
    )


class _nested:
    """Apply several patches for the duration of a block."""

    def __init__(self, patches: list[Any]) -> None:
        self._patches = patches

    def __enter__(self) -> None:
        for p in self._patches:
            p.start()

    def __exit__(self, *exc: object) -> None:
        for p in reversed(self._patches):
            p.stop()


def _summarise(runs: list[Run]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for arm in ARMS:
        arm_runs = [r for r in runs if r.arm == arm]
        if not arm_runs:
            continue
        restored = sum(1 for r in arm_runs if r.prior_state_restored)
        out[arm] = {
            "reps": len(arm_runs),
            "prior_state_restored": restored,
            "prior_state_restored_pct": round(100 * restored / len(arm_runs), 1),
            "left_in_mutated_state": len(arm_runs) - restored,
            "outcomes": sorted({r.outcome for r in arm_runs}),
            "median_duration_s": statistics.median(r.duration_s for r in arm_runs),
        }

    # The finding that matters as much as the headline: can an operator tell from
    # the reported outcome that the application was left mutated? The first run of
    # this study answered no for every arm, because the unwind was never checked.
    outcomes = {
        arm: {r.outcome for r in runs if r.arm == arm} for arm in ARMS
    }
    good = outcomes.get("undo_enabled") or set()
    for arm in ("undo_ineffective", "undo_disabled"):
        seen = outcomes.get(arm) or set()
        if not (good and seen):
            continue
        out[f"outcome_distinguishes_{arm}"] = good != seen
        out[f"note_{arm}"] = (
            f"{','.join(sorted(seen))} vs {','.join(sorted(good))} when the undo "
            "works: the reported outcome exposes the difference"
            if good != seen
            else "outcome is identical to a working undo; only direct inspection "
            "of the application reveals the difference"
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "eval_results" / "ablation_undo.json")
    args = ap.parse_args()

    try:
        httpx.get(f"{BASE}/healthz", timeout=3)
    except httpx.HTTPError:
        print(f"target not reachable at {BASE}. Run `make target-up` first.", file=sys.stderr)
        return 1

    print(
        f"Undo ablation: F01 against the live target, {args.reps} reps x "
        f"{len(ARMS)} arms"
    )
    print("Diagnosis fixed, verification forced to fail; only the unwind differs.\n")

    runs: list[Run] = []
    for arm in ARMS:
        for rep in range(1, args.reps + 1):
            run = _one_run(arm, rep)
            runs.append(run)
            flag = "restored" if run.prior_state_restored else "LEFT MUTATED"
            print(
                f"  [{arm:<14} rep {rep}] outcome={run.outcome:<14} "
                f"model={run.final_model:<8} {flag}  ({run.duration_s}s)"
            )

    summary = _summarise(runs)
    print("\n--- Undo ablation ---")
    for arm in ARMS:
        s = summary.get(arm)
        if not s:
            continue
        print(
            f"{arm:<17} prior state restored {s['prior_state_restored']}/{s['reps']} "
            f"({s['prior_state_restored_pct']}%)  outcomes={','.join(s['outcomes'])}"
        )

    _reset_target()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"summary": summary, "runs": [asdict(r) for r in runs]}, indent=2),
        encoding="utf-8",
    )
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
