"""How short can F06's detection window be, and what does shortening it cost?

THE PROBLEM THIS MEASURES
`PRD.md` §12 records the ten-minute window biting three separate times, the
last of which needed ~5 minutes of driven load to make one fault detectable.
That is not a demo and it is not a measurement protocol. The entry says the
window "cannot be shortened in the detector alone without diverging from the
manifest contract", and that is true of two of the three signals and NOT of
the one that actually gates the claim.

WHICH SIGNAL GATES F06, AND WHAT IS ACTUALLY DECLARED
`retrieval_collapse.py` reads three retrieval signals at `[10m]`:

    similarity_p50        mirrors kavach.yaml retrieval_similarity_p50 (600s)
    empty_context_ratio   mirrors kavach.yaml empty_context_ratio      (600s)
    kept_chunks_mean      NOT AN SLO IN kavach.yaml AT ALL

`kept_chunks` appears in the manifest exactly once, as the denominator inside
`empty_context_ratio`'s expression. There is no `kept_chunks` SLO, no declared
`window_s` for it, and therefore no contract to diverge from. It is also the
signal that blocked detection every time: the measured failures were
`kept_chunks` sitting at a ten-minute mean of 2.0 and 2.61 against a 1.0
floor.

`similarity_p50` is the DISCRIMINATOR rather than the trigger - during a real
F06 it must stay HEALTHY, because that is what separates a bad rerank filter
from broken embeddings - so a long window on it is harmless and arguably
correct. The same argument does not apply to `kept_chunks_mean`, which has to
fall.

So the question this script answers is not "should we break the manifest
contract". It is the same question the F01 `[5m] -> [2m]` fix answered, for
the one signal that has no contract:

  1. FALSE POSITIVES. On a healthy target, does a short window ever read
     below the 1.0 floor? If a 30s window is noisy at rest, it is unusable
     however fast it is.
  2. DETECTION LATENCY. Under a real injection, how many seconds until each
     window crosses the floor? That is the number the demo actually cares
     about.

Both are measured against the live stack. Nothing here changes the detector;
it reports what each candidate window WOULD have seen, so the decision is
made on numbers rather than on three options and a shrug.

    uv run --project apps/control-plane python -I harness/window_sweep_f06.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = ROOT / "apps" / "control-plane"
sys.path[:0] = [str(ROOT), str(CONTROL_PLANE)]

from harness.faults.f06_retrieval_collapse import F06RetrievalCollapse  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"
TARGET = "http://127.0.0.1:8000"
PROM = "http://127.0.0.1:9091"

# The candidate windows, shortest first. 10m is the status quo and is included
# so the table carries its own control.
WINDOWS = ["30s", "1m", "2m", "5m", "10m"]

# From `retrieval_collapse.Thresholds`. Not re-declared loosely: a sweep that
# used a different floor than the detector would measure nothing useful.
KEPT_CHUNKS_FLOOR = 1.0


def kept_chunks_query(window: str) -> str:
    """Exactly `retrieval_collapse.QUERIES["kept_chunks_mean"]`, parametrised."""
    return (f"rate(ragapp_retrieval_kept_chunks_sum[{window}]) "
            f"/ clamp_min(rate(ragapp_retrieval_kept_chunks_count[{window}]), 1e-9)")


def empty_ratio_query(window: str) -> str:
    return (f"(sum(rate(ragapp_retrieval_empty_context_total[{window}])) "
            f"or vector(0)) / clamp_min(sum(rate("
            f"ragapp_retrieval_kept_chunks_count[{window}])), 1e-9)")


def say(m: str = "") -> None:
    print(m, flush=True)


def promql(query: str) -> float | None:
    url = PROM + "/api/v1/query?query=" + urllib.parse.quote(query)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            res = json.loads(r.read())["data"]["result"]
        return float(res[0]["value"][1]) if res else None
    except Exception:
        return None


def read_all() -> dict[str, dict[str, float | None]]:
    """Every candidate window for both signals, read at one instant."""
    return {
        "kept_chunks_mean": {w: promql(kept_chunks_query(w)) for w in WINDOWS},
        "empty_context_ratio": {w: promql(empty_ratio_query(w)) for w in WINDOWS},
    }


def fmt(v: float | None) -> str:
    return "none" if v is None else f"{v:.3f}"


def row(label: str, vals: dict[str, float | None]) -> str:
    cells = "  ".join(f"{fmt(vals[w]):>7}" for w in WINDOWS)
    return f"  {label:<26} {cells}"


def header() -> str:
    return "  " + " " * 26 + " " + "  ".join(f"{w:>7}" for w in WINDOWS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-drain-rounds", type=int, default=20,
                    help="healthy rounds allowed to flush a prior fault")
    ap.add_argument("--settle-rounds", type=int, default=3,
                    help="healthy fast-set rounds before measuring at rest")
    ap.add_argument("--fault-rounds", type=int, default=8,
                    help="max driven rounds under injection")
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports" / "window-sweep-f06.json"))
    args = ap.parse_args()

    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))

    say("=" * 78)
    say("F06 DETECTION WINDOW SWEEP")
    say("=" * 78)
    say(f"  kept_chunks floor  {KEPT_CHUNKS_FLOOR} (from retrieval_collapse.Thresholds)")
    say("  kept_chunks has NO SLO in kavach.yaml, so its window is detector-local")
    say("")

    report: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "windows": WINDOWS,
        "kept_chunks_floor": KEPT_CHUNKS_FLOOR,
    }

    # --- 0. DRAIN. Residue is not noise, and conflating them is a bug -------
    #
    # The first version of this script went straight to "at rest" and reported
    # a false positive at EVERY window, including 30s. It was measuring the
    # residue of the injection from the previous run: the fast set passed
    # 100% while kept_chunks read 0.000 at 30s/1m/2m, because Prometheus still
    # held the collapsed samples. That is contamination, not a false positive,
    # and folding the two into one verdict is the same error as F08's harness
    # folding `broke` into its pass condition.
    #
    # So the residue gets its own measurement, and it is the more useful one:
    # HOW LONG DOES EACH WINDOW TAKE TO FORGET A FAULT. That is the number
    # behind all three occurrences in PRD section 12 - a prior fault's samples
    # sitting in the next fault's window - and it is what decides whether two
    # demos can run back to back.
    say("-" * 78)
    say("0. DRAIN. Healthy traffic until every window has forgotten whatever")
    say("   ran before this. Residue from a prior fault is not a false")
    say("   positive, and measuring them together reports neither.")
    say("-" * 78)
    drain_t0 = time.time()
    recovered_at: dict[str, float | None] = dict.fromkeys(WINDOWS)
    drain_rounds = 0
    for i in range(1, args.max_drain_rounds + 1):
        drain_rounds = i
        r = fast.run(client, FAST_SET, check_health=False)
        elapsed = round(time.time() - drain_t0, 1)
        vals = read_all()
        for w in WINDOWS:
            v = vals["kept_chunks_mean"][w]
            if recovered_at[w] is None and v is not None and v >= KEPT_CHUNKS_FLOOR:
                recovered_at[w] = elapsed
        say(f"  round {i} at {elapsed:6.1f}s (fast set {r.pass_rate:.0%})")
        say(header())
        say(row("kept_chunks_mean", vals["kept_chunks_mean"]))
        if all(recovered_at[w] is not None for w in WINDOWS):
            say("  every window is back above the floor")
            break
    report["recovered_at_s"] = recovered_at
    report["drain_rounds"] = drain_rounds
    say("")
    say(f"  time to forget the previous fault: "
        f"{ {w: ('never' if v is None else f'{v}s') for w, v in recovered_at.items()} }")
    say("")

    # --- 1. FALSE POSITIVES AT REST -----------------------------------------
    say("-" * 78)
    say("1. AT REST, after draining. Healthy traffic only. A window reading")
    say("   below the floor HERE would claim a fault on a working system.")
    say("-" * 78)
    healthy_samples: list[dict[str, Any]] = []
    for i in range(1, args.settle_rounds + 1):
        r = fast.run(client, FAST_SET, check_health=False)
        vals = read_all()
        healthy_samples.append({"round": i, "pass_rate": r.pass_rate, **vals})
        say(f"  round {i} (fast set {r.pass_rate:.0%})")
        say(header())
        say(row("kept_chunks_mean", vals["kept_chunks_mean"]))
        say(row("empty_context_ratio", vals["empty_context_ratio"]))
    report["healthy"] = healthy_samples

    false_positive: dict[str, bool] = {}
    for w in WINDOWS:
        # NOT `vals`: that name holds the window->value mapping above, and
        # reusing it here hid the real type from mypy.
        series: list[float | None] = [
            sample["kept_chunks_mean"][w] for sample in healthy_samples
        ]
        below = [v for v in series if v is not None and v < KEPT_CHUNKS_FLOOR]
        false_positive[w] = bool(below)
    report["false_positive_at_rest"] = false_positive
    say("")
    say(f"  below the floor while healthy:  "
        f"{ {w: ('YES' if b else 'no') for w, b in false_positive.items()} }")

    # --- 2. DETECTION LATENCY UNDER A REAL INJECTION ------------------------
    say("")
    say("-" * 78)
    say("2. UNDER INJECTION. Seconds from the first faulted request until each")
    say("   window crosses the floor. This is the number the demo cares about.")
    say("-" * 78)
    fault = F06RetrievalCollapse(client)
    crossed_at: dict[str, float | None] = dict.fromkeys(WINDOWS)
    timeline: list[dict[str, Any]] = []

    try:
        fault.inject()
        say(f"  injected: rerank_threshold = {fault.current_threshold()}")
        t0 = time.time()
        for i in range(1, args.fault_rounds + 1):
            r = fast.run(client, FAST_SET, check_health=False)
            elapsed = round(time.time() - t0, 1)
            vals = read_all()
            timeline.append({"round": i, "elapsed_s": elapsed,
                             "pass_rate": r.pass_rate, **vals})
            for w in WINDOWS:
                v = vals["kept_chunks_mean"][w]
                if crossed_at[w] is None and v is not None and v < KEPT_CHUNKS_FLOOR:
                    crossed_at[w] = elapsed
            say(f"  round {i} at {elapsed:6.1f}s (fast set {r.pass_rate:.0%})")
            say(header())
            say(row("kept_chunks_mean", vals["kept_chunks_mean"]))
            if all(crossed_at[w] is not None for w in WINDOWS):
                say("  every window has crossed; stopping early")
                break
    finally:
        say("")
        fault.revert()
        say(f"  reverted: rerank_threshold = {fault.current_threshold()}")

    report["under_fault"] = timeline
    report["crossed_at_s"] = crossed_at

    # --- the decision table --------------------------------------------------
    say("")
    say("=" * 78)
    say("DECISION TABLE")
    say("=" * 78)
    say(f"  {'window':<10} {'false positive at rest':<24} {'detected after':<16} verdict")
    for w in WINDOWS:
        fp = false_positive[w]
        at = crossed_at[w]
        detected = "never" if at is None else f"{at:.1f}s"
        if fp:
            verdict = "UNUSABLE - claims on a healthy system"
        elif at is None:
            verdict = f"too slow - no claim within {args.fault_rounds} rounds"
        else:
            verdict = "usable"
        say(f"  {w:<10} {('YES' if fp else 'no'):<24} {detected:<16} {verdict}")

    usable = [w for w in WINDOWS
              if not false_positive[w] and crossed_at[w] is not None]
    say("")
    if usable:
        best = min(usable, key=lambda w: crossed_at[w] or 1e9)
        say(f"  SHORTEST USABLE WINDOW: {best} "
            f"(detects in {crossed_at[best]:.1f}s, no false positive at rest)")
        now = crossed_at["10m"]
        say(f"  current: 10m, detecting in "
            f"{'never' if now is None else f'{now:.1f}s'}")
        report["shortest_usable"] = best
    else:
        say("  NO USABLE WINDOW among the candidates. The problem is not the "
            "window length and this measurement has ruled that out, which is "
            "itself the result.")
        report["shortest_usable"] = None

    say("")
    say("  NOTE: this changes kept_chunks_mean ONLY. similarity_p50 and")
    say("  empty_context_ratio mirror declared window_s values in kavach.yaml")
    say("  and are left alone - similarity must stay HEALTHY during an F06, so")
    say("  a long window on it is correct rather than merely tolerable.")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str) + "\n",
                   encoding="utf-8")
    say(f"  artifact {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
