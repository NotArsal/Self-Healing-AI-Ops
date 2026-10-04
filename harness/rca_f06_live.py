"""Live P3: real llama3.2 diagnosing a real F06 injection, and P2 vs P3.

Not mocked. Real target, real Toxiproxy-fronted stack, real Prometheus, real
evidence, real model on the host Ollama.

Three things it establishes:
  1. a healthy system produces no RCA incident, and RCA is not even consulted
  2. an injected F06 is diagnosed as retrieval_collapse on backend, with cited
     evidence, and the diagnosis survives deterministic validation and heals
  3. the deterministic P2 loop and the P3 RCA loop, measured on the same fault,
     so the comparison is like-for-like

Every run leaves the target healthy: the injector reverts in a finally block.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = REPO_ROOT / "apps" / "control-plane"
for _p in (REPO_ROOT, CONTROL_PLANE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from harness.faults.f06_retrieval_collapse import (  # noqa: E402
    BAD_THRESHOLD,
    F06RetrievalCollapse,
)
from kavach.detection import retrieval_collapse as rc  # noqa: E402
from kavach.llm.client import OllamaClient  # noqa: E402
from kavach.loop import IncidentStatus, run_once  # noqa: E402
from kavach.onboarding.baseline import _promql  # noqa: E402
from kavach.rca import evidence as ev  # noqa: E402
from kavach.rca.engine import diagnose  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"
HEALTHY_THRESHOLD = 0.35
SERVICES = {"backend", "db", "frontend", "toxiproxy", "prometheus"}
CONFIDENCE_THRESHOLD = 0.75


def say(m: str = "") -> None:
    print(m, flush=True)


@dataclass
class Run:
    mode: str                      # "deterministic" | "llm_rca"
    status: str = ""
    fault_class: str | None = None
    service: str | None = None
    confidence: float | None = None
    cited: list[str] = field(default_factory=list)
    rca_latency_s: float = 0.0
    total_s: float = 0.0
    resolved: bool = False
    diagnosis_correct: bool = False
    corpus_unchanged: bool = False
    detail: str = ""


def make_rca_stage(
    client: TargetClient, prometheus_url: str, llm: OllamaClient
) -> Any:
    def stage(fast_result: Any, detection: rc.Detection, baseline: float | None) -> Any:
        frame = ev.collect(
            client, prometheus_url, _promql, fast_result,
            baseline_rerank_threshold=baseline,
        )
        return diagnose(
            frame, detection, CONFIDENCE_THRESHOLD, llm=llm,
            declared_services=SERVICES,
        )
    return stage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prometheus", default="http://localhost:9091")
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--model", default="llama3.2")
    # From the environment, never a literal. The same variable compose
    # passes to the API, and the target reads the matching KAVACH_ADMIN_TOKEN.
    ap.add_argument("--admin-token",
                    default=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", ""))
    ap.add_argument("--reps", type=int, default=3,
                    help="RCA repetitions for latency and determinism")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    client = TargetClient(TargetEndpoints(admin_token=args.admin_token))
    llm = OllamaClient(args.ollama, args.model)

    def corpus() -> dict[str, float | None]:
        return {"chunks": _promql(args.prometheus, "ragapp_corpus_chunks"),
                "files": _promql(args.prometheus, "ragapp_corpus_files")}

    say("=" * 74)
    say("P3 LIVE: LLM RCA on a real F06 injection")
    say("=" * 74)
    say(f"  model              {args.model} at {args.ollama}")
    say(f"  ollama reachable   {llm.available()}")
    say(f"  confidence gate    {CONFIDENCE_THRESHOLD}")
    say(f"  healthy threshold  {client.settings()['rerank_threshold']}")
    say(f"  corpus             {corpus()}")
    say("")
    if not llm.available():
        say("Ollama is not reachable; cannot run the live RCA test.")
        return 1

    rca_stage = make_rca_stage(client, args.prometheus, llm)
    runs: list[Run] = []
    corpus_start = corpus()

    # --- 1. healthy system ---------------------------------------------------
    say("-" * 74)
    say("1. HEALTHY SYSTEM: no incident, and RCA must not be consulted")
    say("-" * 74)
    consulted = {"n": 0}

    def counting(fast_result: Any, detection: Any, baseline: Any) -> Any:
        consulted["n"] += 1
        return rca_stage(fast_result, detection, baseline)

    inc = run_once(client, args.prometheus, FAST_SET, _promql,
                   HEALTHY_THRESHOLD, rca=counting)
    say(f"  status            {inc.status}")
    say(f"  rca consulted     {consulted['n']} times (expect 0)")
    healthy_ok = inc.status is IncidentStatus.NO_FAULT and consulted["n"] == 0
    say(f"  -> {'PASS' if healthy_ok else 'FAIL'}")
    say("")

    # --- 2. RCA on the real fault, repeated ---------------------------------
    say("-" * 74)
    say(f"2. INJECT F06 (threshold -> {BAD_THRESHOLD}) and run RCA {args.reps}x")
    say("-" * 74)
    rca_results: list[Any] = []
    fault = F06RetrievalCollapse(client, corpus_probe=corpus)
    try:
        fault.inject()
        say(f"  injected; live threshold {fault.current_threshold()}")
        pre = fast.run(client, FAST_SET, check_health=False)
        say(f"  fast set under fault: {pre.pass_rate:.0%}")
        time.sleep(20)   # let the metric windows reflect the collapse

        detection = rc.evaluate(
            rc.collect(args.prometheus, _promql), pre.passed, pre.pass_rate
        )
        say(f"  deterministic detection: {detection.verdict}")
        say("")

        for i in range(1, args.reps + 1):
            frame = ev.collect(client, args.prometheus, _promql, pre,
                               baseline_rerank_threshold=HEALTHY_THRESHOLD)
            r = diagnose(frame, detection, CONFIDENCE_THRESHOLD, llm=llm,
                         declared_services=SERVICES)
            rca_results.append(r)
            d = r.diagnosis
            say(f"  rep {i}: {r.latency_s:5.1f}s  "
                f"class={d.fault_class if d else 'NONE':<22} "
                f"service={d.service if d else '-':<10} "
                f"conf={d.confidence if d else '-':<5} "
                f"approved={r.approved}")
            if d is None:
                say(f"         error: {r.error}")
            if not r.approved and r.rejection_reasons:
                say(f"         rejected: {r.rejection_reasons[0][:110]}")
        say("")
        n_items = (len(rca_results[0].evidence.items)
                   if rca_results and rca_results[0].evidence else 0)
        say(f"  evidence frame size: {n_items} items")
        if rca_results and rca_results[0].diagnosis:
            d0 = rca_results[0].diagnosis
            say(f"  cited              {d0.evidence_ids}")
            say(f"  reasoning          {d0.reasoning[:200]}")
            for alt in d0.rejected_alternatives[:3]:
                say(f"  ruled out          {alt.fault_class}: {alt.reason[:80]}")
            say("")
            say(rca_results[0].validation.render() if rca_results[0].validation else "")
    finally:
        fault.revert()
        say("")
        say(f"  reverted; threshold {fault.current_threshold()}")

    # --- 3. P2 vs P3 on the same fault --------------------------------------
    say("")
    say("-" * 74)
    say("3. P2 DETERMINISTIC vs P3 LLM-RCA, same fault, full closed loop")
    say("-" * 74)
    for mode, stage in (("deterministic", None), ("llm_rca", rca_stage)):
        f = F06RetrievalCollapse(client, corpus_probe=corpus)
        run = Run(mode=mode)
        t0 = time.perf_counter()
        try:
            f.inject()
            time.sleep(20)
            inc = run_once(client, args.prometheus, FAST_SET, _promql,
                           HEALTHY_THRESHOLD, rca=stage)
            run.total_s = time.perf_counter() - t0
            run.status = str(inc.status)
            run.resolved = inc.resolved
            run.fault_class = inc.fault_class
            run.service = inc.service
            run.corpus_unchanged = inc.corpus_before == inc.corpus_after
            if inc.rca:
                rec: dict[str, Any] = inc.rca.get("diagnosis") or {}
                run.confidence = rec.get("confidence")
                run.cited = rec.get("evidence_ids") or []
                run.rca_latency_s = inc.rca.get("latency_s") or 0.0
            run.diagnosis_correct = (inc.fault_class == "F06"
                                     and inc.service == "backend")
            run.detail = inc.escalation_reason or inc.outcome
        except Exception as exc:
            run.detail = f"{type(exc).__name__}: {exc}"
            run.total_s = time.perf_counter() - t0
        finally:
            f.revert()
        runs.append(run)
        say(f"  {mode:<14} {run.status:<10} resolved={run.resolved} "
            f"correct={run.diagnosis_correct} corpus_ok={run.corpus_unchanged} "
            f"rca={run.rca_latency_s:.1f}s loop={run.total_s:.1f}s")

    # --- summary -------------------------------------------------------------
    corpus_end = corpus()
    lat = [r.latency_s for r in rca_results]
    classes = {r.diagnosis.fault_class for r in rca_results if r.diagnosis}
    services = {r.diagnosis.service for r in rca_results if r.diagnosis}
    approved = sum(r.approved for r in rca_results)

    say("")
    say("=" * 74)
    say("SUMMARY")
    say("=" * 74)
    say(f"  healthy system clean       {healthy_ok}")
    say(f"  RCA approved               {approved}/{len(rca_results)}")
    say(f"  fault classes returned     {classes or '-'}  (want {{'F06'}})")
    say(f"  services returned          {services or '-'}  (want {{'backend'}})")
    if lat:
        say(f"  RCA latency                min {min(lat):.1f}s mean "
            f"{statistics.mean(lat):.1f}s max {max(lat):.1f}s  (PF-02 budget 45s)")
    say(f"  corpus                     {corpus_start} -> {corpus_end}")
    say(f"  final threshold            {client.settings()['rerank_threshold']}")

    final = fast.run(client, FAST_SET)
    say(f"  final fast verification    {'PASS' if final.passed else 'FAIL'} "
        f"({final.pass_rate:.0%}, {final.total_s:.1f}s)")

    ok = (
        healthy_ok
        and approved == len(rca_results) and len(rca_results) == args.reps
        and classes == {"F06"} and services == {"backend"}
        and all(r.resolved and r.diagnosis_correct and r.corpus_unchanged for r in runs)
        and corpus_start == corpus_end
        and client.settings()["rerank_threshold"] == HEALTHY_THRESHOLD
        and final.passed
        and (not lat or max(lat) < 45.0)
    )
    say("=" * 74)
    say("P3 LIVE: PASS" if ok else "P3 LIVE: FAIL")

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps({
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": args.model,
            "healthy_clean": healthy_ok,
            "rca_approved": approved, "rca_reps": len(rca_results),
            "classes": sorted(classes), "services": sorted(services),
            "latency_s": lat,
            "corpus_start": corpus_start, "corpus_end": corpus_end,
            "final_fast_set_passed": final.passed,
            "comparison": [r.__dict__ for r in runs],
            "diagnoses": [r.to_dict() for r in rca_results],
        }, indent=2, default=str) + "\n", encoding="utf-8")
        say(f"artifact: {args.json_out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
