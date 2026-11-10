"""Does the detector reach the same verdict twice on the same injected fault?

WHY THIS EXISTS. The closure ablation drops an incident when the detector
names something other than the injected class, and across three full runs it
dropped a completely different set each time: F07#11, F07#14, F08#4, F08#8;
then F08#15; then F08#2, F08#8, F08#11. The detector is upstream of the model
and nothing about those runs differed on its side, so the drop set should have
been stable. `EXPERIMENT_CLOSURE_ABLATION.md` §21.5 records the pattern and
says, correctly, that three drop sets are an inference and not a measurement.

This is the measurement. Same fault, injected and reverted N times, counting
how often detection concludes with the injected class. It calls no model, so
it is cheap, and it is deliberately a SEPARATE script from the ablation:
re-measuring detection must not require re-running 855 diagnoses.

WHAT IT BEARS ON. `REPORT_DRAFT` §4.1's MTTD figures are means over detections
that concluded. If detection concludes only some of the time, a mean over the
successes is a conditional number reported as an unconditional one, and the
denominator belongs in the report.

NOT MEASURED HERE: why. A non-deterministic detector could be a timing
phenomenon in the windowed PromQL (the suspected cause, since the two classes
that ever fail are the two whose detectors read windows), a warm-up effect, or
a genuine threshold sitting on top of the signal. This script says how often,
not why - and the how-often has to exist before the why is worth chasing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = ROOT / "apps" / "control-plane"
sys.path[:0] = [str(ROOT), str(CONTROL_PLANE)]

from harness.closure_ablation import newest_baseline, promql, say  # noqa: E402
from harness.kavach_baseline import (  # noqa: E402
    FAST_SET,
    PROM,
    TARGET,
    build,
    drive_until_detectable,
    warm_up_f01,
)
from kavach.config import get_settings  # noqa: E402
from kavach.detection import base as det  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

ALL_CLASSES = ("F01", "F06", "F07", "F08")


def detect_once(
    fault_class: str,
    client: TargetClient,
    baseline: dict[str, Any],
) -> tuple[str, float, float, str]:
    """Inject, detect, revert. Returns (verdict, pass_rate, seconds, reason).

    The verdict is the detector's fault class when it named one, otherwise
    its bare verdict string - which is what the ablation's drop rule reads.
    `revert` is in a `finally` for the same reason it is there: a trial that
    raises must not leave the target faulted for the next one.

    THE REASON IS WHY THIS FUNCTION RETURNS FOUR THINGS. Three runs of this
    script found F07 missing on its first two trials and F06 naming `F01`,
    and both were then explained by guesswork - the detectors have several
    distinct paths to `INSUFFICIENT_EVIDENCE` (an unreachable control
    interface, a baseline holding digests without text, too few changed
    files) and a bare verdict cannot tell them apart. Recording the
    detector's own first reason costs nothing and replaces a hypothesis
    with a reading.
    """
    fault = build(fault_class, client)
    started = time.monotonic()
    try:
        fault.inject()
        if fault_class == "F06":
            drive_until_detectable(client)
        elif fault_class == "F01":
            warm_up_f01(client)

        pre = fast.run(client, FAST_SET, check_health=False)
        detection = det.run_all(
            det.registry.specs(),
            det.Signals(prometheus_url=PROM, promql=promql, client=client,
                        baseline=baseline),
            pre.passed, pre.pass_rate,
        )
        elapsed = time.monotonic() - started
        reasons = list(getattr(detection, "reasons", None) or [])
        return (detection.fault_class or detection.verdict,
                pre.pass_rate, elapsed, reasons[0] if reasons else "")
    finally:
        fault.revert()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--classes", default="F07,F08",
                    help="comma-separated; default is the two that have ever "
                         "failed to detect")
    ap.add_argument("--trials", type=int, default=20,
                    help="injections per class")
    ap.add_argument("--json-out", default="",
                    help="write the per-trial record here")
    args = ap.parse_args()

    classes = [c.strip().upper() for c in args.classes.split(",") if c.strip()]
    bad = [c for c in classes if c not in ALL_CLASSES]
    if bad:
        raise SystemExit(f"no injector for {', '.join(bad)}; "
                         f"have {', '.join(ALL_CLASSES)}")
    if args.trials < 2:
        raise SystemExit("REFUSING: --trials must be at least 2. One trial "
                         "cannot measure reproducibility, and reporting it as "
                         "though it could is the error this script exists to "
                         "correct.")

    settings = get_settings()
    client = TargetClient(TargetEndpoints(
        health=f"{TARGET}/healthz", chat=f"{TARGET}/v1/chat",
        config=f"{TARGET}/v1/admin/config",
        admin_token=settings.target_admin_token))

    baseline, source = newest_baseline()
    if not baseline:
        raise SystemExit("no usable baseline; F07 and F08 would be undetectable")

    # Same guard, same reason as the ablation: a killed run cannot revert
    # itself, and starting dirty measures the leftover and the new injection
    # together with nothing downstream able to tell them apart.
    dirty = [c for c in ALL_CLASSES if build(c, client).is_active()]
    if dirty:
        raise SystemExit(
            f"REFUSING: {', '.join(dirty)} already active on the target. "
            f"Nothing has been injected. `inject.py revert --all` clears it.")

    say("=" * 78)
    say("DETECTOR REPRODUCIBILITY - EXPERIMENT_CLOSURE_ABLATION.md section 21.5")
    say("=" * 78)
    say(f"  baseline     {source}")
    say(f"  classes      {', '.join(classes)}")
    say(f"  trials       {args.trials} per class")
    say("")

    rows: list[dict[str, Any]] = []
    for fault_class in classes:
        say(f"  {fault_class}")
        for trial in range(1, args.trials + 1):
            try:
                verdict, pass_rate, elapsed, reason = detect_once(
                    fault_class, client, baseline)
                err = ""
            except Exception as exc:   # broad on purpose: recorded, not hidden
                verdict, pass_rate, elapsed, err, reason = "", 0.0, 0.0, str(exc), ""
            rows.append({"fault_class": fault_class, "trial": trial,
                         "verdict": verdict, "pass_rate": round(pass_rate, 3),
                         "seconds": round(elapsed, 2), "error": err,
                         "reason": reason})
            hit = "OK " if verdict == fault_class else "MISS"
            say(f"    trial {trial:>3}: {hit} verdict={verdict or '-'} "
                f"pass_rate={pass_rate:.2f} {elapsed:.1f}s"
                + (f"  {err}" if err else ""))
            # Only on a miss: on a hit the reason restates the claim and
            # would bury the one line that matters in a wall of prose.
            if verdict != fault_class and reason:
                say(f"             why: {reason[:160]}")

    say("")
    say("  " + "-" * 74)
    say(f"  {'class':6} {'detected':>10} {'rate':>7}   other verdicts")
    for fault_class in classes:
        mine = [r for r in rows if r["fault_class"] == fault_class]
        hits = sum(r["verdict"] == fault_class for r in mine)
        others = Counter(r["verdict"] or "ERROR" for r in mine
                         if r["verdict"] != fault_class)
        say(f"  {fault_class:6} {hits:>4}/{len(mine):<5} {hits / len(mine):>7.2f}   "
            + (", ".join(f"{k}x{v}" for k, v in others.most_common()) or "-"))

    say("")
    say("  A rate below 1.00 means every MTTD figure measured on that class is")
    say("  conditional on detection concluding, and REPORT_DRAFT section 4.1")
    say("  must say so. A rate of 1.00 here does not clear the class - it")
    say(f"  bounds the miss rate at roughly 1-in-{args.trials}, which is the")
    say("  resolution this many trials buys.")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "at": datetime.now(UTC).isoformat(),
            "baseline": source,
            "trials": args.trials,
            "rows": rows,
        }, indent=2), encoding="utf-8")
        say(f"  artifact {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
