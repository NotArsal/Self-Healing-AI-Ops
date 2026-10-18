"""P6 LIVE: F07 prompt regression, through the HTTP API.

APPROVAL mode only, for the same reason as F08: `rollback_prompt` is MEDIUM,
and `permit()` routes MEDIUM to the sandbox under AUTONOMOUS - a sandbox that
does not exist until P7. F01 remains the catalogue's only LOW repair and
therefore the only autonomous path there is.

WHAT THIS RUN HAS TO PROVE THAT THE OTHER THREE DID NOT

1. **The write lands somewhere the target can see.** Every repair before this
   one went through the target's HTTP config interface, where the target
   itself applies the change. This one writes a file on one side of a bind
   mount and trusts a container on the other side to read it. Every check
   here therefore asks the TARGET what it hashes its prompts to, never the
   filesystem Kavach just wrote.

2. **The symptom keeps F07's shape and not F06's.** `rag.py` appends the
   `**Sources:**` block only when the answer is not a fallback, so a prompt
   that induces a refusal also suppresses the sources block, and the fast set
   then reads exactly like a retrieval collapse. Step 2 runs the fast set
   under injection and fails the run if that is what happened - an injector
   that quietly injects the wrong fault invalidates everything downstream.

3. **Only the drifted prompt is written.** `query_expansion.txt` is left alone
   by the injector, so the repair must leave it alone too; its digest is
   checked before and after.

Requires both stacks up, a baseline captured WITH `prompt_contents`, and the
real admin token in the environment:
    KAVACH_TARGET_ADMIN_TOKEN=...
    uv run --project apps/control-plane python -I harness/p6_f07_live.py
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

from harness.faults.f07_prompt_regression import (  # noqa: E402
    PROMPT_FILE,
    F07PromptRegression,
    digest,
)
from kavach.config import get_settings  # noqa: E402
from kavach.onboarding.manifest import load as load_manifest  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

API = "http://127.0.0.1:8080"
TARGET = "http://127.0.0.1:8000"
PROM = "http://127.0.0.1:9091"
FAST_SET = ROOT / "apps" / "control-plane" / "kavach" / "verification" / "fast_set.yaml"
OTHER_PROMPT = "query_expansion.txt"


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


def prompts_dir() -> Path:
    target = Path(get_settings().target_path)
    declared = load_manifest(target / "kavach.yaml").versioned_paths["prompts"]
    return (target / declared).resolve()


def reported(client: TargetClient) -> dict[str, str]:
    """The digests the RUNNING target computes, which is the only authority."""
    cfg = client.config()
    return dict((cfg.get("prompt_version") or {}).get("files") or {})


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
    say("P6 LIVE: F07 prompt regression, APPROVAL mode")
    say("=" * 74)

    code, mode = api("/v1/mode")
    say(f"  GET /v1/mode            {code}  mode={mode['mode']} "
        f"allowed={mode['allowed_actions']}")
    assert code == 200
    assert "rollback_prompt" in mode["allowed_actions"], (
        "F07 is the first fault to need a NEW allow-list entry since F01. "
        "Without it `permit()` denies the repair and this run proves nothing"
    )

    d = prompts_dir()
    pre_digests = reported(client)
    pre_settings = client.settings()
    pre_hash = client.config_hash()
    pre_corpus = corpus()
    say(f"  prompts directory       {d}")
    say(f"  pre-state digests       {pre_digests}")
    say(f"  pre-state config hash   {pre_hash}")
    say(f"  pre-state corpus        {pre_corpus}")

    # The control plane and the target must be looking at the same directory.
    # Checked here as well as inside the injector, because a mismatch makes
    # every later result meaningless rather than merely wrong.
    on_disk = {p.name: digest(p.read_text(encoding="utf-8"))
               for p in sorted(d.glob("*.txt"))}
    assert on_disk == pre_digests, (
        f"the host sees {on_disk} but the target reports {pre_digests}; these "
        f"are different directories and nothing written here would reach it"
    )
    say("  host and target agree   True")

    results: dict[str, bool] = {}
    fault = F07PromptRegression(client, d, corpus_probe=corpus)

    try:
        say("")
        say("-" * 74)
        say(f"1. INJECT F07: rewrite {PROMPT_FILE}, no restart")
        say("-" * 74)
        fault.inject()
        now = reported(client)
        say(f"  target now reports      {now}")
        say(f"  {PROMPT_FILE} digest     {pre_digests[PROMPT_FILE]} -> "
            f"{now.get(PROMPT_FILE)}")
        results["injected"] = fault.is_active()
        results["config_hash_held"] = client.config_hash() == pre_hash
        results["other_prompt_untouched_by_injector"] = (
            now.get(OTHER_PROMPT) == pre_digests[OTHER_PROMPT])
        ok, why = fault.assert_scope_respected()
        say(f"  scope                   {ok} - {why}")
        results["injector_scope_respected"] = ok

        say("")
        say("-" * 74)
        say("2. SYMPTOM SHAPE: it must fail like F07, not like F06")
        say("-" * 74)
        r = fast.run(client, FAST_SET, check_health=False)
        for c in r.cases:
            say(f"  {c.case_id}  keyword={c.keyword_present} "
                f"non_refusal={c.non_refusal} grounded={c.sources_block} "
                f"{c.latency_s:.1f}s")
        ok, why = fault.assert_symptom_shape(list(r.cases))
        say(f"  shape                   {ok} - {why}")
        results["symptom_is_f07_shaped"] = ok

        say("")
        say("-" * 74)
        say("3. RUN THE LOOP: the signal is read at run time, like F08")
        say("-" * 74)
        code, started = api("/v1/loop/run?rca=false", "POST", timeout=180)
        say(f"  POST /v1/loop/run       {code}  {started}")
        assert code == 202, started
        parked = wait_terminal(started["incident_id"])

        say(f"  status                  {parked['status']}")
        say(f"  fault_class / service   {parked.get('fault_class')} / "
            f"{parked.get('service')}")
        say(f"  outcome                 {(parked.get('outcome') or '')[:240]}")
        if parked.get("decision"):
            dec = parked["decision"]
            say(f"  verdict / tier          {dec.get('verdict')} / "
                f"{dec.get('risk_tier')}")
        results["diagnosed_f07"] = parked.get("fault_class") == "F07"
        results["parked_at_awaiting"] = parked["status"] == "AWAITING_APPROVAL"
        results["gate_wrote_nothing"] = (
            reported(client).get(PROMPT_FILE) == now.get(PROMPT_FILE))

        say("")
        say("-" * 74)
        say("4. APPROVE: the control plane writes a FILE, and the target must")
        say("   be the one that confirms it")
        say("-" * 74)
        code, second = api(
            f"/v1/incidents/{started['incident_id']}/approve", "POST", timeout=180)
        say(f"  POST .../approve        {code}  {second}")
        assert code == 202, second
        healed = wait_terminal(second["incident_id"])

        say(f"  status                  {healed['status']}")
        say(f"  outcome                 {(healed.get('outcome') or '')[:260]}")
        act = healed.get("action") or {}
        say(f"  action                  {act.get('action')} "
            f"tier={act.get('risk_tier')}")
        say(f"  restored files          {act.get('restored_files')}")
        say(f"  bytes written           {act.get('bytes_written')}")
        say(f"  digests                 {act.get('inverse_settings')} -> "
            f"{act.get('requested_settings')}")
        results["executed_the_repair"] = act.get("executed") is True
        results["resolved"] = healed["status"] == "RESOLVED"
        results["wrote_only_the_drifted_prompt"] = (
            act.get("restored_files") == [PROMPT_FILE])
        # The audit record must never carry prompt text.
        results["audit_record_has_no_prompt_text"] = (
            "CONTEXT:" not in json.dumps(act))

        after = reported(client)
        say(f"  target now reports      {after}")
        results["target_reports_known_good"] = (
            after.get(PROMPT_FILE) == pre_digests[PROMPT_FILE])
        results["other_prompt_untouched_by_repair"] = (
            after.get(OTHER_PROMPT) == pre_digests[OTHER_PROMPT])

        say("")
        say("-" * 74)
        say("5. VERIFY: the fast set must pass again, with no restart")
        say("-" * 74)
        r2 = fast.run(client, FAST_SET, check_health=False)
        for c in r2.cases:
            say(f"  {c.case_id}  {'PASS' if c.passed else 'FAIL'}  "
                f"keyword={c.keyword_present} grounded={c.sources_block} "
                f"{c.latency_s:.1f}s")
        say(f"  pass rate               {r2.pass_rate:.0%}")
        results["fast_set_passes_after_repair"] = r2.passed

    finally:
        say("")
        fault.revert()
        say(f"  reverted; target reports {reported(client)}")

    post_digests = reported(client)
    post_settings = client.settings()
    post_corpus = corpus()
    results["prompts_identical_to_start"] = post_digests == pre_digests
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
        say(f"  events {[row.get('event') for row in rows][-8:]}")
        results["audit_chain_intact"] = bool(audit.get("chain_intact"))

    say("")
    say("=" * 74)
    say("SUMMARY")
    say("=" * 74)
    for k, v in results.items():
        say(f"  {'PASS' if v else 'FAIL'}  {k}")
    say(f"  prompts {pre_digests} -> {post_digests}")

    good = all(results.values())
    say("")
    say(f"  F07 VERTICAL (approval): {'PROVEN' if good else 'NOT PROVEN'}")

    out = ROOT / "harness" / "reports" / "p6-f07-live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "results": results,
        "proven": good,
        "prompts_dir": str(d),
        "digests_before": pre_digests,
        "digests_after": post_digests,
        "settings_before": pre_settings,
        "settings_after": post_settings,
        "corpus_before": pre_corpus,
        "corpus_after": post_corpus,
    }, indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  artifact {out}")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
