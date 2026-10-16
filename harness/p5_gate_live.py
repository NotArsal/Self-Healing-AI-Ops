"""P5 LIVE: does the safety gate actually park a real repair, and heal on approve?

Drives the HTTP API, not the library, because the API is the demo path and the
API is where the container bugs live. Injects a real F06, asserts the loop
parks at AWAITING_APPROVAL having written NOTHING, approves, and asserts the
repair then executed against the captured pre-state value.

RESOLVED IS PART OF THE CLAIM AGAIN, AS OF 2026-10-16
It briefly was not. While the corpus was missing `1662.pdf`, `fv-01` retrieved
zero chunks on every run, so post-repair verification failed for a reason that
had nothing to do with the repair and the loop correctly unwound and escalated.
The gate claim held even then - park, write nothing, execute on approve, and
restore the pre-state witness when verification says no, are all independent of
`fv-01`. With the corpus restored, the full vertical closes, so RESOLVED is
asserted here rather than merely reported.

It also does not read the live threshold to decide whether the repair ran. If
verification fails the loop unwinds, so that read reports "never executed" for
a run that executed and then correctly rolled back. The action record and the
audit chain are the witnesses.

Requires both stacks up and the real admin token in the environment:
    KAVACH_TARGET_ADMIN_TOKEN=...
    uv run --project apps/control-plane python -I harness/p5_gate_live.py

The injector reverts in a finally block, so the target is healthy however this
exits.
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

from harness.faults.f06_retrieval_collapse import (  # noqa: E402
    BAD_THRESHOLD,
    F06RetrievalCollapse,
)
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = ROOT / "apps" / "control-plane" / "kavach" / "verification" / "fast_set.yaml"

API = "http://127.0.0.1:8080"
# 127.0.0.1 throughout: `localhost` resolves to ::1 first on this host and the
# published ports are IPv4, so urlopen times out instead of refusing.
TARGET = "http://127.0.0.1:8000"
PROM = "http://127.0.0.1:9091"


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


def wait_terminal(incident_id: str, limit_s: int = 900) -> dict[str, Any]:
    """Poll until the incident leaves the in-flight states."""
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


def corpus() -> dict[str, float | None]:
    return {"chunks": promql("ragapp_corpus_chunks"),
            "files": promql("ragapp_corpus_files")}


# The detector's own grounding signal and floor, so this waits on exactly what
# `permit()`'s upstream will read rather than on a guessed sleep.
KEPT_CHUNKS_MEAN = (
    "rate(ragapp_retrieval_kept_chunks_sum[10m]) "
    "/ clamp_min(rate(ragapp_retrieval_kept_chunks_count[10m]), 1e-9)"
)
KEPT_CHUNKS_FLOOR = 1.0


def drive_until_detectable(
    client: TargetClient, fast_set: Path, max_rounds: int = 18
) -> tuple[bool, float | None]:
    """Put load on the faulted system until its 10m grounding average collapses.

    A FIXED SLEEP IS NOT ENOUGH, AND FINDING THAT OUT COST A RUN.
    Detection reads `rate(...[10m])`, so it reports on the last ten minutes,
    not on the last ten seconds. Three collapsed queries arriving after a
    healthy baseline run leave the average at roughly
    `(9 x 2.7 + 3 x 0) / 12 = 2.0` - comfortably above the 1.0 floor - and the
    detector correctly answers INSUFFICIENT_EVIDENCE: on a ten-minute average,
    grounding really was healthy. It is not a false negative, it is the window
    being honest.

    So the fault has to DOMINATE the window before the loop is asked to
    diagnose, which it does either by taking traffic or by the healthy samples
    ageing out. This drives real fast-set traffic through the faulted system -
    every request returning the silent 200 that is the fault - and watches the
    detector's own signal until it crosses, which is also what a real outage
    would look like.

    It is a precondition for the test, never part of the claim: nothing here
    touches Kavach, and the loop still has to detect, diagnose and repair on
    its own.

    THE BOUND WENT FROM 8 ROUNDS TO 18, AND THE REASON IS WORTH KEEPING.
    Eight was enough when the window started around 2.0. Run immediately after
    the `F08` live harness it was not: F08 leaves grounding entirely INTACT -
    that is its signature - so its run fills this ten-minute window with
    healthy samples, and F06 started from 2.61 instead. Eight rounds decayed it
    to 1.49 and the harness correctly refused to proceed rather than ask the
    loop to diagnose an undetectable fault.

    So the bound is not a magic number, it is "long enough to outlast a
    ten-minute window that another fault's harness just filled". That cost is
    structural, it is now the third time this window has bitten, and `PRD.md`
    §12 carries it as an open decision rather than something to keep papering
    over with a larger bound.
    """
    for round_no in range(1, max_rounds + 1):
        r = fast.run(client, fast_set, check_health=False)
        mean = promql(KEPT_CHUNKS_MEAN)
        say(f"    round {round_no}: fast set {r.pass_rate:.0%} in {r.total_s:.1f}s, "
            f"kept_chunks 10m mean = {mean}")
        if mean is not None and mean < KEPT_CHUNKS_FLOOR:
            return True, mean
    return False, promql(KEPT_CHUNKS_MEAN)


def main() -> int:
    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))

    say("=" * 74)
    say("P5 LIVE: the safety gate on a real F06, through the HTTP API")
    say("=" * 74)

    code, mode = api("/v1/mode")
    say(f"  GET /v1/mode            {code}  {mode}")
    assert code == 200, "the mode route must answer before anything is injected"
    assert mode["mode"] == "APPROVAL", "expected APPROVAL, got {}".format(mode["mode"])
    assert mode["enforced"] is True
    # The invariant, not the literal list: the allow-list grows with every
    # fault class, and a literal here would have to be edited by whoever
    # adds one - which is the edit P6 says a new fault must not require.
    # It did, in fact, break the moment F01 added switch_llm_endpoint.
    assert "rollback_config" in mode["allowed_actions"], (
        "F06's repair must be allowed or this test cannot run"
    )

    pre_threshold = float(client.settings()["rerank_threshold"])
    pre_hash = client.config_hash()
    pre_corpus = corpus()
    say(f"  pre-state               threshold={pre_threshold} hash={pre_hash}")
    say(f"  pre-state corpus        {pre_corpus}")
    say("")

    results: dict[str, bool] = {}
    fault = F06RetrievalCollapse(client, corpus_probe=corpus)
    try:
        # --- 1. inject ------------------------------------------------------
        say("-" * 74)
        say(f"1. INJECT F06: rerank_threshold -> {BAD_THRESHOLD}")
        say("-" * 74)
        fault.inject()
        live = fault.current_threshold()
        say(f"  live threshold          {live}")
        results["injected"] = live == BAD_THRESHOLD
        say("  driving load until the 10m grounding average crosses the floor")
        ready, mean = drive_until_detectable(client, FAST_SET)
        say(f"  detectable              {ready} (kept_chunks 10m mean = {mean})")
        results["fault_is_detectable"] = ready
        assert ready, (
            f"the 10m grounding average is still {mean}, above the {KEPT_CHUNKS_FLOOR} "
            f"floor, so the detector would correctly answer INSUFFICIENT_EVIDENCE. "
            f"This is the window being honest, not a Kavach defect - see "
            f"drive_until_detectable()."
        )

        # --- 2. the gate ----------------------------------------------------
        say("")
        say("-" * 74)
        say("2. RUN THE LOOP IN APPROVAL MODE: it must PARK and write NOTHING")
        say("-" * 74)
        code, started = api("/v1/loop/run?rca=true", "POST", timeout=120)
        say(f"  POST /v1/loop/run       {code}  {started}")
        assert code == 202, f"the run was refused: {started}"
        first_id = started["incident_id"]
        results["run_reports_approval_mode"] = started.get("mode") == "APPROVAL"

        parked = wait_terminal(first_id)
        say("  status                  {}".format(parked["status"]))
        say(f"  fault_class / service   {parked.get('fault_class')} / "
            f"{parked.get('service')}")
        say("  outcome                 {}".format((parked.get("outcome") or "")[:250]))
        say("  escalation_reason       {}".format((parked.get("escalation_reason") or "")[:250]))
        if parked.get("decision"):
            say("  decision                {}".format(json.dumps(parked["decision"])[:500]))
        if parked.get("action"):
            say("  prepared action         {}".format(json.dumps(parked["action"])[:300]))
        if parked.get("unwind"):
            say("  inverse                 {}".format(json.dumps(parked["unwind"])[:300]))

        results["parked_at_awaiting"] = parked["status"] == "AWAITING_APPROVAL"

        # THE claim: parking writes nothing.
        after_gate = fault.current_threshold()
        say(f"  live threshold after    {after_gate}  (must still be {BAD_THRESHOLD})")
        results["gate_wrote_nothing"] = after_gate == BAD_THRESHOLD

        # --- 3. approve -----------------------------------------------------
        say("")
        say("-" * 74)
        say("3. APPROVE: it must now execute and restore the captured value")
        say("-" * 74)
        code, second = api(f"/v1/incidents/{first_id}/approve", "POST", timeout=120)
        say(f"  POST .../approve        {code}  {second}")
        assert code == 202, f"approval was refused: {second}"
        results["approve_accepted"] = True
        results["approve_cites_source"] = second.get("approved_from") == first_id

        healed = wait_terminal(second["incident_id"])
        say("  status                  {}".format(healed["status"]))
        say("  outcome                 {}".format((healed.get("outcome") or "")[:350]))
        say("  escalation_reason       {}".format((healed.get("escalation_reason") or "")[:350]))
        if healed.get("verification_after"):
            after = json.dumps(healed["verification_after"])[:300]
            say(f"  verification after      {after}")

        # DO NOT read the live threshold to decide whether the repair ran.
        # If post-repair verification fails the loop unwinds, so the live value
        # is back to the faulty one by design and a threshold read here reports
        # "never executed" for a run that executed and then correctly rolled
        # back. The action record and the audit chain are the witnesses.
        act = healed.get("action") or {}
        say("  action executed flag    {}".format(act.get("executed")))
        say(f"  wrote                   {act.get('inverse_settings')} -> "
            f"{act.get('requested_settings')}")
        say(f"  config hash             {act.get('config_hash_before')} -> "
            f"{act.get('config_hash_after')}")
        results["executed_the_repair"] = (
            act.get("executed") is True
            and act.get("requested_settings") == {"rerank_threshold": pre_threshold}
        )

        unwound = healed.get("unwind") or {}
        if unwound:
            say(f"  unwind                  "
                f"attempted={unwound.get('attempted')} "
                f"restored={unwound.get('restored')} "
                f"clean={unwound.get('clean')} {unwound.get('failures')}")
        results["resolved"] = healed["status"] == "RESOLVED"
        # Verification failed on fv-01 for a corpus reason, so the ONLY correct
        # behaviour left is to put the target back exactly as it was found.
        results["unwound_cleanly_when_verification_failed"] = (
            True if healed["status"] == "RESOLVED"
            else bool(unwound.get("clean"))
        )
        say(f"  live threshold now      {fault.current_threshold()}")

        # --- 4. a used approval cannot be replayed --------------------------
        code, again = api(f"/v1/incidents/{first_id}/approve", "POST", timeout=60)
        say(f"  re-approve same id      {code} (want 409)  {str(again)[:120]}")
        results["approval_is_single_use"] = code == 409

    finally:
        say("")
        fault.revert()
        say(f"  reverted; live threshold {fault.current_threshold()}")

    # --- 5. the audit chain -------------------------------------------------
    say("")
    say("-" * 74)
    say("5. AUDIT CHAIN")
    say("-" * 74)
    code, audit = api("/v1/audit?limit=60")
    if code == 200:
        rows = audit.get("rows", [])
        say(f"  rows                    {len(rows)}  "
            f"chain_intact={audit.get('chain_intact')}")
        for row in rows[-20:]:
            rest = {k: v for k, v in row.items()
                    if k not in ("at", "event", "hash", "prev_hash", "prev")}
            at = str(row.get("at", ""))[-8:]
            event = str(row.get("event", "?"))
            say(f"    {at} {event:<22} {json.dumps(rest, default=str)[:130]}")
        results["audit_chain_intact"] = bool(audit.get("chain_intact"))
        events = [r.get("event") for r in rows]
        say(f"  events                  {events}")
        results["audit_records_the_execution"] = (
            "execute_start" in events and "execute_done" in events)
    else:
        say(f"  GET /v1/audit           {code} {audit}")
        results["audit_chain_intact"] = False

    post_corpus = corpus()
    say("")
    say("=" * 74)
    say("SUMMARY")
    say("=" * 74)
    for k, v in results.items():
        say("  {}  {}".format("PASS" if v else "FAIL", k))
    say("  corpus {} -> {}  {}".format(pre_corpus, post_corpus,
           "unchanged" if pre_corpus == post_corpus else "MUTATED"))
    say(f"  final threshold {fault.current_threshold()}")

    gate = all(results.get(k) for k in (
        "injected", "fault_is_detectable", "parked_at_awaiting",
        "gate_wrote_nothing", "approve_accepted", "executed_the_repair",
        "resolved", "approval_is_single_use", "audit_chain_intact",
        "audit_records_the_execution"))
    say("")
    verdict = "PROVEN" if gate else "NOT PROVEN"
    say(f"  FULL VERTICAL (detect, park, write nothing, approve, execute, "
        f"verify, resolve): {verdict}")

    out = ROOT / "harness" / "reports" / "p5-gate-live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": mode,
        "results": results,
        "gate_proven": gate,
        "corpus_before": pre_corpus,
        "corpus_after": post_corpus,
        "pre_threshold": pre_threshold,
        "pre_config_hash": pre_hash,
    }, indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  artifact {out}")
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
