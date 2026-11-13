"""Fast set, serial vs parallel: what would running the three cases at once buy?

A MEASUREMENT, NOT A CHANGE. PRD FR-07 and `fast_set.yaml` lock the set to
serial execution and nothing here touches Kavach. It answers whether the owner
should consider changing that (ROADMAP, "Why detection takes 241s"): under F02
the set is three ~78s chats in a row, and Amdahl's law says parallelism can
only save the part of that wall time that really runs side by side.

WHAT IS RECORDED, AND WHY EACH ONE
1. Speed - does the target answer three chats at once, or queue them?
2. Quality - do answers stay correct (keyword, no refusal, sources) under load?
3. Detection - F02's detector needs the fast set to FAIL. The loop runs it
   with the health probe, so health, budget and quality are kept separate: a
   parallel set that finishes inside 120s under F02 still fails only if
   health does.
4. False alarms - on a healthy system any parallel failure is a deal-breaker.

SAME RULES FOR BOTH MODES
Parallel is built from Kavach's own `fast.run`: health from a zero-case copy of
the set, then one single-case copy per thread. The verdict is
`FastVerificationResult.passed` itself. Nothing about what "pass" means is
re-implemented here, so the two modes cannot drift apart.

ORDER BIAS: pairs alternate serial-first and parallel-first.

SAFETY: refuses to start while the Kavach loop is busy or any toxic is on the
primary listener (a bench may be mid-run). The F02 toxic is removed by the
injector's context manager, on an exception too, and the script asserts the
primary is clean at the end.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = ROOT / "apps" / "control-plane"
sys.path[:0] = [str(ROOT), str(CONTROL_PLANE)]

from harness.faults.f01_endpoint_outage import PRIMARY, _call  # noqa: E402
from harness.faults.f02_latency_degradation import F02LatencyDegradation  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"
TARGET = "http://127.0.0.1:8000"
API = "http://127.0.0.1:8080"


def say(m: str = "") -> None:
    print(m, flush=True)


def split_set(fast_set: Path, out_dir: Path) -> tuple[Path, list[Path]]:
    """A zero-case copy (health only) and one single-case copy per case.

    Everything but `cases` is kept, so `load_markers` and the budget read the
    same values the real set declares.
    """
    doc = yaml.safe_load(fast_set.read_text("utf-8"))
    def write(name: str, cases: list[Any]) -> Path:
        p = out_dir / name
        p.write_text(yaml.safe_dump({**doc, "cases": cases}), "utf-8")
        return p
    health_only = write("health.yaml", [])
    singles = [write(f"case-{i}.yaml", [c]) for i, c in enumerate(doc["cases"])]
    return health_only, singles


def run_parallel(client: TargetClient, health_only: Path,
                 singles: list[Path]) -> fast.FastVerificationResult:
    """Health first, then all cases at once - the serial run's order, minus the queue."""
    health = fast.run(client, health_only)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(singles)) as pool:
        parts = list(pool.map(lambda p: fast.run(client, p, check_health=False), singles))
    return fast.FastVerificationResult(
        cases=[c for part in parts for c in part.cases],
        total_s=time.perf_counter() - started,
        budget_s=health.budget_s,
        health_ok=health.health_ok,
        health_detail=health.health_detail,
    )


def row(mode: str, r: fast.FastVerificationResult) -> dict[str, Any]:
    return {"mode": mode, "passed": r.passed, "health_ok": r.health_ok,
            "within_budget": r.within_budget, "quality_ok": r.quality_ok,
            "total_s": round(r.total_s, 1),
            "case_s": [round(c.latency_s, 1) for c in r.cases],
            "case_passed": [c.passed for c in r.cases],
            "errors": [c.error for c in r.cases if c.error]}


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per mode: wall time spread and how often each probe held."""
    out: dict[str, Any] = {}
    for mode in ("serial", "parallel"):
        rs = [r for r in rows if r["mode"] == mode]
        if not rs:
            continue
        t = [r["total_s"] for r in rs]
        out[mode] = {
            "n": len(rs),
            "total_s": {"min": min(t), "median": statistics.median(t), "max": max(t)},
            **{k: sum(r[k] for r in rs) for k in
               ("passed", "health_ok", "within_budget", "quality_ok")},
        }
    if "serial" in out and "parallel" in out:
        out["speedup_median"] = round(
            out["serial"]["total_s"]["median"]
            / max(out["parallel"]["total_s"]["median"], 1e-9), 2)
    return out


def pairs(client: TargetClient, n: int, health_only: Path,
          singles: list[Path], label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(n):
        order = ("serial", "parallel") if i % 2 == 0 else ("parallel", "serial")
        for mode in order:
            r = (fast.run(client, FAST_SET) if mode == "serial"
                 else run_parallel(client, health_only, singles))
            rows.append(row(mode, r))
            say(f"  {label} pair {i + 1}/{n} {mode:8} {json.dumps(rows[-1])}")
    return rows


def refuse_reason() -> str:
    """Empty when it is safe to start; otherwise why not."""
    try:
        with urllib.request.urlopen(API + "/v1/system", timeout=30) as r:
            if json.loads(r.read()).get("loop_running"):
                return "the Kavach loop is running an incident"
    except OSError as exc:
        return f"cannot read {API}/v1/system ({exc}); cannot prove the loop is idle"
    if _call(f"/proxies/{PRIMARY}/toxics"):
        return f"{PRIMARY} already has a toxic - a fault (or a bench) is live"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--healthy-pairs", type=int, default=10)
    ap.add_argument("--f02-pairs", type=int, default=5)
    ap.add_argument("--json-out", default=str(
        ROOT / "harness" / "reports"
        / f"fastset-parallel-{datetime.now(UTC):%Y%m%d}.json"))
    args = ap.parse_args()

    if why := refuse_reason():
        say(f"REFUSING: {why}. Run this only after the bench has finished.")
        return 1
    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config"))

    with tempfile.TemporaryDirectory() as tmp:
        health_only, singles = split_set(FAST_SET, Path(tmp))
        say("healthy system (any parallel failure here is a deal-breaker)")
        healthy = pairs(client, args.healthy_pairs, health_only, singles, "healthy")
        say("F02 injected (12s latency toxic on the primary listener)")
        with F02LatencyDegradation():
            f02 = pairs(client, args.f02_pairs, health_only, singles, "f02")

    clean = not _call(f"/proxies/{PRIMARY}/toxics")
    report: dict[str, Any] = {"at": datetime.now(UTC).isoformat(timespec="seconds"),
              "primary_clean_at_end": clean,
              "healthy": {"summary": summarise(healthy), "rows": healthy},
              "f02": {"summary": summarise(f02), "rows": f02}}
    Path(args.json_out).write_text(json.dumps(report, indent=2), "utf-8")
    say(json.dumps({"healthy": report["healthy"]["summary"],
                    "f02": report["f02"]["summary"]}, indent=2))
    say(f"primary clean at end: {clean}. wrote {args.json_out}")
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
