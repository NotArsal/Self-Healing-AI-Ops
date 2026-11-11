"""P6 LIVE: F02 latency degradation, through the HTTP API, both modes.

Derived from `p6_f01_live.py`; only what F02 changes is changed. The injector
adds a 12s latency toxic to `ollama-primary` (it does not disable it); the
repair is the same switch to the clean `:21435` backup.

WHAT THIS ALSO MEASURES: DETECTION TIME ON F01'S CLOCK
F01's "detection within 30s" was 15.1s from POST /v1/loop/run to the parked
incident. The loop runs the fast set before deciding, and under F02 every chat
takes ~78s (measured), so this records the same interval for F02 and reports
it whatever it is.

Requires both stacks up and the real admin token in the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "control-plane")]

from harness.faults.f01_endpoint_outage import BACKUP, PRIMARY  # noqa: E402
from harness.faults.f02_latency_degradation import F02LatencyDegradation  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = ROOT / "apps" / "control-plane" / "kavach" / "verification" / "fast_set.yaml"

API = "http://127.0.0.1:8080"
TARGET = "http://127.0.0.1:8000"
PROM = "http://127.0.0.1:9091"

# The detector's own discriminator and floor, so this waits on exactly what
# the loop will read rather than on a guessed sleep - the same lesson
# `p5_gate_live.py` learned the hard way.
ERROR_RATIO = (
    '(sum(rate(ragapp_llm_requests_total{outcome!="ok"}[2m])) or vector(0)) '
    "/ clamp_min(sum(rate(ragapp_llm_requests_total[2m])), 1e-9)"
)
ERROR_RATIO_FLOOR = 0.50
# The F02 detector's own query and floor (detection/latency_degradation.py).
GEN_P95 = (
    "histogram_quantile(0.95, sum by (le) (rate("
    'ragapp_llm_duration_seconds_bucket{operation="generation"}[2m])))'
)
GEN_P95_FLOOR = 8.0


def api(
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: int = 60,
) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def promql(query: str) -> float | None:
    url = PROM + "/api/v1/query?query=" + urllib.parse.quote(query)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            res = json.loads(r.read())["data"]["result"]
        return float(res[0]["value"][1]) if res else None
    except Exception:
        return None


def say(m: str = "") -> None:
    print(m, flush=True)


def corpus() -> dict[str, float | None]:
    return {"chunks": promql("ragapp_corpus_chunks"),
            "files": promql("ragapp_corpus_files")}


def wait_terminal(incident_id: str, limit_s: int = 900) -> dict[str, Any]:
    terminal = {"NO_FAULT", "AWAITING_APPROVAL", "RESOLVED", "ESCALATED"}
    t0 = time.time()
    last = ""
    while time.time() - t0 < limit_s:
        code, inc = api("/v1/incidents/" + incident_id)
        if code != 200:
            say(f"    [poll {code}] {inc}")
            time.sleep(5)
            continue
        status = inc.get("status", "")
        if status != last:
            say(f"    [{time.time() - t0:6.1f}s] {status}")
            last = status
        if status in terminal:
            return dict(inc)
        time.sleep(5)
    raise TimeoutError(incident_id + " never reached a terminal status")


def drive_until_detectable(
    client: TargetClient, max_rounds: int = 6
) -> tuple[bool, float | None]:
    """Put load on the faulted system until the 2m generation p95 crosses 8s
    while the error ratio stays below F01's floor - exactly what the F02
    detector will read. One round of ~3 x 78s fills the 2m window with slow
    calls."""
    for round_no in range(1, max_rounds + 1):
        r = fast.run(client, FAST_SET, check_health=False)
        p95, ratio = promql(GEN_P95), promql(ERROR_RATIO)
        say(f"    round {round_no}: fast set {r.pass_rate:.0%} in {r.total_s:.1f}s, "
            f"generation p95 2m = {p95}, llm error ratio 2m = {ratio}")
        if (p95 is not None and p95 > GEN_P95_FLOOR
                and ratio is not None and ratio < ERROR_RATIO_FLOOR):
            return True, p95
    return False, promql(GEN_P95)


def set_mode(mode: str) -> dict[str, Any]:
    code, out = api("/v1/mode", "PUT", {"mode": mode}, timeout=30)
    assert code == 200, f"could not set mode {mode}: {out}"
    return dict(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    # The deterministic path by default, as for F01; --rca runs the LLM stage.
    # Diagnosis accuracy is measured separately, ten runs (acceptance 3).
    ap.add_argument("--rca", action="store_true",
                    help="run the LLM RCA stage")
    args = ap.parse_args()
    rca = "true" if args.rca else "false"

    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))

    say("=" * 74)
    say("P6 LIVE: F02 latency degradation, APPROVAL then AUTONOMOUS")
    say("=" * 74)

    code, mode = api("/v1/mode")
    say(f"  GET /v1/mode            {code}  mode={mode['mode']} "
        f"allowed={mode['allowed_actions']}")
    assert code == 200
    assert "switch_llm_endpoint" in mode["allowed_actions"], (
        "the target's manifest must allow switch_llm_endpoint before F02 can heal"
    )
    original_mode = mode["manifest_mode"]

    pre_settings = client.settings()
    pre_endpoint = str(pre_settings["llm_base_url"])
    pre_corpus = corpus()
    say(f"  pre-state endpoint      {pre_endpoint}")
    say(f"  pre-state corpus        {pre_corpus}")

    results: dict[str, bool] = {}
    fault = F02LatencyDegradation(corpus_probe=corpus)
    timings: dict[str, float] = {}

    try:
        # --- 1. APPROVAL: park, write nothing, heal on approve --------------
        say("")
        say("-" * 74)
        say("1. APPROVAL MODE: park, write nothing, heal on approve")
        say("-" * 74)
        set_mode("APPROVAL")
        fault.inject()
        say(f"  injected: {PRIMARY} toxics={[t.get('name') for t in fault._toxics()]}, "
            f"{BACKUP} enabled={fault._proxy(BACKUP).get('enabled')}")
        results["injected"] = fault.is_active()
        results["backup_untouched"] = fault.assert_scope_respected()[0]

        say("  driving load until the 2m generation p95 crosses 8s")
        ready, ratio = drive_until_detectable(client)
        say(f"  detectable              {ready} (generation p95 = {ratio})")
        results["fault_is_detectable"] = ready
        assert ready, f"generation p95 stuck at {ratio}, not above {GEN_P95_FLOOR}"

        t_run = time.time()
        code, started = api(f"/v1/loop/run?rca={rca}", "POST", timeout=120)
        say(f"  POST /v1/loop/run       {code}  {started}")
        assert code == 202, started
        parked = wait_terminal(started["incident_id"])
        timings["approval_run_to_parked_s"] = round(time.time() - t_run, 1)
        say(f"  status                  {parked['status']}  "
            f"(run -> parked {timings['approval_run_to_parked_s']}s; F01 was 15.1s)")
        say(f"  fault_class / service   {parked.get('fault_class')} / "
            f"{parked.get('service')}")
        say(f"  outcome                 {(parked.get('outcome') or '')[:220]}")
        if parked.get("decision"):
            d = parked["decision"]
            say(f"  verdict / tier          {d.get('verdict')} / {d.get('risk_tier')}")
        results["diagnosed_f02"] = parked.get("fault_class") == "F02"
        results["parked_at_awaiting"] = parked["status"] == "AWAITING_APPROVAL"

        live_now = str(client.settings()["llm_base_url"])
        say(f"  endpoint after gate     {live_now}  (must still be {pre_endpoint})")
        results["gate_wrote_nothing"] = live_now == pre_endpoint

        code, second = api(
            f"/v1/incidents/{started['incident_id']}/approve", "POST", timeout=120)
        say(f"  POST .../approve        {code}  {second}")
        assert code == 202, second
        healed = wait_terminal(second["incident_id"])
        say(f"  status                  {healed['status']}")
        say(f"  outcome                 {(healed.get('outcome') or '')[:260]}")
        act = healed.get("action") or {}
        say(f"  wrote                   {act.get('inverse_settings')} -> "
            f"{act.get('requested_settings')}")
        results["approved_run_executed"] = act.get("executed") is True
        results["approved_run_resolved"] = healed["status"] == "RESOLVED"
        say(f"  endpoint now            {client.settings()['llm_base_url']}")

        # Put it back so the autonomous half starts from the faulted state.
        client.apply_settings({"llm_base_url": pre_endpoint})
        say(f"  reset endpoint to       {client.settings()['llm_base_url']}")

        # --- 2. AUTONOMOUS: heal with no human ------------------------------
        say("")
        say("-" * 74)
        say("2. AUTONOMOUS MODE: LOW risk means it heals with NO human")
        say("-" * 74)
        m = set_mode("AUTONOMOUS")
        say(f"  mode                    {m['mode']} (overridden={m['overridden']})")

        say("  driving load until the 2m generation p95 crosses 8s")
        ready, ratio = drive_until_detectable(client)
        say(f"  detectable              {ready} (generation p95 = {ratio})")
        assert ready, f"generation p95 stuck at {ratio}"

        code, auto = api(f"/v1/loop/run?rca={rca}", "POST", timeout=120)
        say(f"  POST /v1/loop/run       {code}  {auto}")
        assert code == 202, auto
        inc = wait_terminal(auto["incident_id"])
        say(f"  status                  {inc['status']}")
        say(f"  outcome                 {(inc.get('outcome') or '')[:260]}")
        if inc.get("decision"):
            d = inc["decision"]
            say(f"  verdict / tier          {d.get('verdict')} / {d.get('risk_tier')}")
            results["allow_auto"] = d.get("verdict") == "ALLOW_AUTO"
        act = inc.get("action") or {}
        say(f"  wrote                   {act.get('inverse_settings')} -> "
            f"{act.get('requested_settings')}")
        results["autonomous_executed"] = act.get("executed") is True
        results["autonomous_resolved"] = inc["status"] == "RESOLVED"
        results["no_human_involved"] = not inc.get("decision", {}).get(
            "reasons") or all("APPROV" not in r.upper()
                              for r in inc.get("decision", {}).get("reasons", []))
        say(f"  endpoint now            {client.settings()['llm_base_url']}")

    finally:
        say("")
        say("-" * 74)
        say("RESTORING PRE-STATE")
        say("-" * 74)
        fault.revert()
        say(f"  {PRIMARY} toxics={[t.get('name') for t in fault._toxics()]} "
            f"restored_exactly={fault.restored_exactly()}")
        client.apply_settings({"llm_base_url": pre_endpoint})
        say(f"  endpoint restored to    {client.settings()['llm_base_url']}")
        set_mode(original_mode)
        say(f"  mode restored to        {original_mode}")

    post_corpus = corpus()
    say("")
    say("-" * 74)
    say("AUDIT CHAIN")
    say("-" * 74)
    code, audit = api("/v1/audit?limit=40")
    if code == 200:
        rows = audit.get("rows", [])
        say(f"  rows {len(rows)}  chain_intact={audit.get('chain_intact')}")
        say(f"  events {[r.get('event') for r in rows][-12:]}")
        results["audit_chain_intact"] = bool(audit.get("chain_intact"))

    say("")
    say("=" * 74)
    say("SUMMARY")
    say("=" * 74)
    for k, v in results.items():
        say(f"  {'PASS' if v else 'FAIL'}  {k}")
    say(f"  corpus {pre_corpus} -> {post_corpus}  "
        f"{'unchanged' if pre_corpus == post_corpus else 'MUTATED'}")
    results["corpus_unchanged"] = pre_corpus == post_corpus

    good = all(results.values())
    say("")
    say(f"  timings {timings}")
    say(f"  F02 VERTICAL (approval AND autonomous): "
        f"{'PROVEN' if good else 'NOT PROVEN'}")

    out = ROOT / "harness" / "reports" / "p6-f02-live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "results": results,
        "proven": good,
        "timings": timings,
        "pre_endpoint": pre_endpoint,
        "corpus_before": pre_corpus,
        "corpus_after": post_corpus,
    }, indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  artifact {out}")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
