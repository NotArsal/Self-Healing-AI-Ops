"""P6 LIVE: F08 config regression, through the HTTP API.

APPROVAL mode only, and that is not a shortcut: `rollback_config` is MEDIUM, and
`permit()` routes MEDIUM to the sandbox under AUTONOMOUS - a sandbox that does
not exist until P7. F01 is the catalogue's only LOW-risk repair and therefore
the only autonomous path there is. Running F08 in AUTONOMOUS would prove that
it parks, which `tests/test_safety.py` already proves offline.

F08 NEEDS NO WARM-UP, AND IT IS THE ONLY FAULT THAT DOES NOT
`F06` reads a ten-minute grounding average and `F01` a two-minute error ratio,
so both need the fault to dominate a window before the loop can see it -
`p5_gate_live.py` needed five rounds of driven load, `p6_f01_live.py` two.
F08's signal is a config comparison against the baseline capture plus the fast
set, and both are read at the instant the loop runs. Inject, run, detected.

That makes it the best demo candidate in the catalogue, and it is worth saying
so somewhere other than a slide: the fault that is easiest to show on stage is
not the one that carries the research claim.

Requires both stacks up and the real admin token in the environment:
    KAVACH_TARGET_ADMIN_TOKEN=...
    uv run --project apps/control-plane python -I harness/p6_f08_live.py
"""

from __future__ import annotations

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

from harness.faults.f08_config_regression import (  # noqa: E402
    BAD_MAX_TOKENS,
    SETTING,
    F08ConfigRegression,
)
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402

API = "http://127.0.0.1:8080"
TARGET = "http://127.0.0.1:8000"
PROM = "http://127.0.0.1:9091"


def api(path: str, method: str = "GET", body: dict[str, Any] | None = None,
        timeout: int = 60) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
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


def main() -> int:
    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))

    say("=" * 74)
    say("P6 LIVE: F08 config regression, APPROVAL mode")
    say("=" * 74)

    code, mode = api("/v1/mode")
    say(f"  GET /v1/mode            {code}  mode={mode['mode']} "
        f"allowed={mode['allowed_actions']}")
    assert code == 200
    assert "rollback_config" in mode["allowed_actions"], (
        "F08 shares F06's repair, so it needs no new allow-list entry - but it "
        "does need that one"
    )

    pre_settings = client.settings()
    pre_max_tokens = pre_settings[SETTING]
    pre_hash = client.config_hash()
    pre_corpus = corpus()
    say(f"  pre-state               {SETTING}={pre_max_tokens} hash={pre_hash}")
    say(f"  pre-state corpus        {pre_corpus}")

    results: dict[str, bool] = {}
    fault = F08ConfigRegression(client, corpus_probe=corpus)

    try:
        say("")
        say("-" * 74)
        say(f"1. INJECT F08: {SETTING} -> {BAD_MAX_TOKENS}")
        say("-" * 74)
        fault.inject()
        say(f"  live {SETTING}          {fault.current_max_tokens()}")
        say(f"  live config hash        {client.config_hash()} "
            f"(was {pre_hash})")
        results["injected"] = fault.is_active()
        results["hash_moved"] = client.config_hash() != pre_hash

        say("")
        say("-" * 74)
        say("2. RUN THE LOOP: no warm-up, the signal is read at run time")
        say("-" * 74)
        code, started = api("/v1/loop/run?rca=false", "POST", timeout=120)
        say(f"  POST /v1/loop/run       {code}  {started}")
        assert code == 202, started
        parked = wait_terminal(started["incident_id"])

        say(f"  status                  {parked['status']}")
        say(f"  fault_class / service   {parked.get('fault_class')} / "
            f"{parked.get('service')}")
        say(f"  outcome                 {(parked.get('outcome') or '')[:220]}")
        if parked.get("decision"):
            d = parked["decision"]
            say(f"  verdict / tier          {d.get('verdict')} / "
                f"{d.get('risk_tier')}")
        results["diagnosed_f08"] = parked.get("fault_class") == "F08"
        results["parked_at_awaiting"] = parked["status"] == "AWAITING_APPROVAL"

        live_now = client.settings()[SETTING]
        say(f"  {SETTING} after gate    {live_now}  "
            f"(must still be {BAD_MAX_TOKENS})")
        results["gate_wrote_nothing"] = live_now == BAD_MAX_TOKENS

        say("")
        say("-" * 74)
        say("3. APPROVE: it must roll back only the setting that drifted")
        say("-" * 74)
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
        results["executed_the_repair"] = act.get("executed") is True
        results["resolved"] = healed["status"] == "RESOLVED"
        # The whole point of `repair_target`: only the drifted key is restored.
        results["rolled_back_only_the_drifted_key"] = (
            act.get("requested_settings") == {SETTING: pre_max_tokens}
        )
        say(f"  live {SETTING} now      {client.settings()[SETTING]}")
        say(f"  live config hash        {client.config_hash()} "
            f"(want {pre_hash})")
        results["hash_restored"] = client.config_hash() == pre_hash

    finally:
        say("")
        fault.revert()
        say(f"  reverted; {SETTING}={client.settings()[SETTING]} "
            f"hash={client.config_hash()}")

    post_settings = client.settings()
    post_corpus = corpus()
    results["settings_identical"] = post_settings == pre_settings
    results["corpus_unchanged"] = post_corpus == pre_corpus

    say("")
    say("-" * 74)
    say("AUDIT CHAIN")
    say("-" * 74)
    code, audit = api("/v1/audit?limit=40")
    if code == 200:
        rows = audit.get("rows", [])
        say(f"  rows {len(rows)}  chain_intact={audit.get('chain_intact')}")
        say(f"  events {[r.get('event') for r in rows][-8:]}")
        results["audit_chain_intact"] = bool(audit.get("chain_intact"))

    say("")
    say("=" * 74)
    say("SUMMARY")
    say("=" * 74)
    for k, v in results.items():
        say(f"  {'PASS' if v else 'FAIL'}  {k}")
    say(f"  settings {pre_settings} -> {post_settings}")

    good = all(results.values())
    say("")
    say(f"  F08 VERTICAL (approval): {'PROVEN' if good else 'NOT PROVEN'}")

    out = ROOT / "harness" / "reports" / "p6-f08-live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "results": results,
        "proven": good,
        "bad_max_tokens": BAD_MAX_TOKENS,
        "settings_before": pre_settings,
        "settings_after": post_settings,
        "corpus_before": pre_corpus,
        "corpus_after": post_corpus,
    }, indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  artifact {out}")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
