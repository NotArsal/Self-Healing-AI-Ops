"""F02 latency sweep: which Toxiproxy `latency` value makes a detectable,
non-erroring endpoint degradation?

WHY A SWEEP AND NOT A CONSTANT
F02 is detected at p95 LLM *generation* duration > SLO x 2 = 8.0s (the
target's declared `llm_latency_p95 < 4.0`, PRD section 6). The target's LLM
read timeout is 30s. A delay below the window is invisible; a delay past it
turns calls into errors, and F02 becomes F01 wearing F02's name - the
separation `harness/faults/f01_endpoint_outage.py` exists to protect. So the
injector's value is measured, the way F06's threshold was.

WHAT ONE CANDIDATE COSTS
Every LLM call in a chat - four embeddings, query expansion and generation -
goes through `llm_base_url`, i.e. the faulted primary listener. The toxic
delays each response once (per-chunk, but not cumulative: Toxiproxy sleeps
`latency - time already spent`, 1024-chunk buffer), so a chat takes ~6T plus
its healthy time.

WHY COUNTER DELTAS, NOT rate()[5m]
Each candidate runs for well under five minutes. A windowed rate would mix
candidates - the mistake PRD section 6.4's F09 entry records three times. The
histogram is read from the target's own /metrics before and after each
candidate, and the quantile is computed from the bucket deltas with
Prometheus' own interpolation.

SAFETY: only the primary listener's toxics change; the backup is asserted
untouched; the toxic is removed in a `finally`; it refuses to start if any
toxic is already present on the primary.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "control-plane")]

import yaml  # noqa: E402

from harness.faults.f01_endpoint_outage import BACKUP, PRIMARY, _call  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402

TARGET = "http://127.0.0.1:8000"
TOXIC = "f02_sweep"
CANDIDATES_MS = [0, 4000, 6000, 7500, 9000, 12000]
ASKS = 3
BUCKET_RE = re.compile(
    r'^ragapp_llm_duration_seconds_bucket\{le="([^"]+)",operation="generation"\} ([0-9.e+]+)$')
OUTCOME_RE = re.compile(
    r'^ragapp_llm_requests_total\{model="[^"]+",'
    r'operation="([^"]+)",outcome="([^"]+)"\} ([0-9.e+]+)$')


def scrape() -> tuple[dict[float, float], dict[tuple[str, str], float]]:
    text = urllib.request.urlopen(TARGET + "/metrics", timeout=10).read().decode()
    buckets: dict[float, float] = {}
    outcomes: dict[tuple[str, str], float] = {}
    for line in text.splitlines():
        if m := BUCKET_RE.match(line):
            buckets[float("inf") if m[1] == "+Inf" else float(m[1])] = float(m[2])
        elif m := OUTCOME_RE.match(line):
            key = (m[1], m[2])
            outcomes[key] = outcomes.get(key, 0.0) + float(m[3])
    return buckets, outcomes


def quantile(q: float, delta: dict[float, float]) -> float | None:
    """Prometheus histogram_quantile over cumulative bucket counts."""
    edges = sorted(delta)
    total = delta[float("inf")]
    if total <= 0:
        return None
    rank, prev_edge, prev_count = q * total, 0.0, 0.0
    for edge in edges:
        if delta[edge] >= rank:
            if edge == float("inf"):
                return prev_edge  # Prometheus returns the highest finite edge
            width = delta[edge] - prev_count
            return prev_edge + (edge - prev_edge) * ((rank - prev_count) / width if width else 0)
        prev_edge, prev_count = edge, delta[edge]
    return None


def main() -> int:
    if _call(f"/proxies/{PRIMARY}/toxics"):
        print(f"REFUSING: {PRIMARY} already has toxics; revert them first")
        return 1
    backup_before = _call(f"/proxies/{BACKUP}")
    question = yaml.safe_load(
        (ROOT / "apps/control-plane/kavach/verification/fast_set.yaml").read_text("utf-8")
    )["cases"][0]["question"]
    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))

    results: list[dict[str, Any]] = []
    for ms in CANDIDATES_MS:
        b0, o0 = scrape()
        times, errors = [], []
        try:
            if ms:
                _call(f"/proxies/{PRIMARY}/toxics", "POST", {
                    "name": TOXIC, "type": "latency", "stream": "downstream",
                    "attributes": {"latency": ms, "jitter": 0}})
            for _ in range(ASKS):
                t = time.time()
                try:
                    client.ask(question, timeout=600)
                except Exception as e:  # an erroring chat IS the measurement
                    errors.append(f"{type(e).__name__}: {str(e)[:120]}")
                times.append(round(time.time() - t, 1))
        finally:
            if ms:
                _call(f"/proxies/{PRIMARY}/toxics/{TOXIC}", "DELETE")
        b1, o1 = scrape()
        delta = {k: b1[k] - b0.get(k, 0.0) for k in b1}
        llm_err = {op: o1.get((op, "error"), 0) - o0.get((op, "error"), 0)
                   for op in ("embedding", "query_expansion", "generation")}
        row = {"latency_ms": ms, "chat_s": times, "chat_errors": errors,
               "generation_calls": delta[float("inf")],
               "generation_p95_s": quantile(0.95, delta),
               "generation_above_8s": delta[float("inf")] - delta[8.0],
               "llm_errors_by_op": llm_err}
        results.append(row)
        print(json.dumps(row), flush=True)

    assert not _call(f"/proxies/{PRIMARY}/toxics"), "a toxic was left on the primary"
    backup_after = _call(f"/proxies/{BACKUP}")
    assert backup_after == backup_before, f"backup changed: {backup_before} -> {backup_after}"
    out = ROOT / "harness" / "reports" / "f02-latency-sweep.json"
    out.write_text(json.dumps({"question": question, "asks": ASKS, "results": results},
                              indent=2), encoding="utf-8")
    print(f"clean: primary has no toxics, backup unchanged. wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
