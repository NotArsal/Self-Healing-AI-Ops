"""`make scenario NAME=demo-full` — the four acts, scripted and rehearsable.

`ROADMAP.md` P8 asks for "a scripted sequence: one autonomous heal, one
approval heal, one rollback, one unknown-failure escalation". This is it,
and the acceptance bar it has to clear is "runs clean three times
consecutively on the demo machine".

THE ORDER IS CHOSEN, AND ACT 4 IS THE ONE THAT MATTERS
A demo of four successes is less persuasive than three successes and a
refusal, so the sequence builds:

  1. AUTONOMOUS HEAL   F01, LOW risk, AUTONOMOUS mode. No human in the loop:
                       permit() returns ALLOW_AUTO, the endpoint fails over
                       to the backup listener, verification passes. This is
                       the only fault class in the catalogue that qualifies
                       - LOW is the one tier permit() executes unattended.

  2. APPROVAL HEAL     F08, MEDIUM risk, APPROVAL mode. The loop parks at
                       AWAITING_APPROVAL having written NOTHING, shows the
                       plan, the risk tier, the pre-state and the inverse,
                       and only acts when a human approves.

  3. ROLLBACK          F01 again, but with BOTH Toxiproxy listeners down, so
                       the correct repair cannot work. The repair applies,
                       verification fails on its own terms, and the undo
                       stack restores the endpoint exactly, verified against
                       the pre-state witness. Nothing is mocked: "both paths
                       to the model are unreachable" is an ordinary outage.

  4. UNKNOWN FAILURE   The database is stopped. This is deliberately NOT in
                       the catalogue - no detector owns it - and the point
                       of the act is that Kavach says so instead of
                       guessing. Measured 2026-10-18, it answers
                       INSUFFICIENT_EVIDENCE and escalates with reasoning a
                       human can read:

                         "only 2.3 LLM requests in the window, below the 3.0
                          needed for an error ratio to mean anything. An idle
                          system is not a healthy system and is not a broken
                          one"

                       Showing the system decline to act on a fault it does
                       not understand is the most honest thing in the demo.

TWO OPERATIONAL FACTS THE SCRIPT HAS TO RESPECT

**permit() allows five incident starts an hour and an approved heal costs
two.** Four acts is at most seven incidents, so a single run fits, but a
THIRD consecutive rehearsal inside one hour will not. The script checks and
says so rather than letting the blast-radius limiter turn a rehearsal into a
mystery. Nothing resets it.

**Stopping the database leaves `ragapp_corpus_chunks` stale at 0** until a
query repopulates it, which would make the next act's preflight refuse. Act
4 drives one query on the way out. Found by doing it.

    make scenario NAME=demo-full
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = ROOT / "apps" / "control-plane"
sys.path[:0] = [str(ROOT), str(CONTROL_PLANE)]

from harness.faults.f01_endpoint_outage import (  # noqa: E402
    BACKUP,
    F01EndpointOutage,
)
from harness.faults.f08_config_regression import F08ConfigRegression  # noqa: E402
from harness.kavach_baseline import (  # noqa: E402
    api,
    corpus,
    drain,
    rca_model,
    wait_terminal,
    warm_up_f01,
)
from kavach.config import get_settings  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"
TARGET = "http://127.0.0.1:8000"
TOXI = "http://127.0.0.1:8474"
DB_CONTAINER = "rag_db"
EXPECTED_CORPUS = {"chunks": 30.0, "files": 2.0}


def say(m: str = "") -> None:
    print(m, flush=True)


def act_header(n: int, title: str, shows: str) -> None:
    say("")
    say("=" * 78)
    say(f"  ACT {n}: {title}")
    say(f"  what to point at: {shows}")
    say("=" * 78)


def proxy(name: str, enabled: bool) -> None:
    body = json.dumps({"enabled": enabled}).encode()
    req = urllib.request.Request(f"{TOXI}/proxies/{name}", data=body,
                                 method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10):
        pass


def set_mode(mode: str) -> str:
    code, out = api("/v1/mode", "PUT", {"mode": mode})
    return str(out.get("mode")) if code == 200 and isinstance(out, dict) else "?"


def ask_one(client: TargetClient) -> None:
    """One real question, to repopulate gauges the database stop left stale."""
    with contextlib.suppress(Exception):
        client.ask("What ROC-AUC did the LSTM model achieve?", timeout=180)


@dataclass
class Act:
    n: int
    title: str
    passed: bool = False
    detail: str = ""
    seconds: float = 0.0
    # permit() refused because this rehearsal has already spent the hour's
    # five incidents. That is the limiter working, not the act failing, and
    # reporting it as a bare FAIL would send someone hunting a bug an hour
    # before a demo.
    limiter: bool = False

    def note(self, inc: dict[str, Any]) -> None:
        if "blast_radius" in str(inc.get("escalation_reason") or ""):
            self.limiter = True


def act1_autonomous(client: TargetClient) -> Act:
    a = Act(1, "autonomous heal (F01, LOW risk, no human)")
    t0 = time.time()
    fault = F01EndpointOutage()
    pre = str(client.settings()["llm_base_url"])
    try:
        set_mode("AUTONOMOUS")
        drain(client)
        fault.inject()
        warm_up_f01(client)
        code, started = api("/v1/loop/run?rca=true", "POST")
        if code != 202:
            a.detail = f"loop/run {code}"
            return a
        inc = wait_terminal(str(started["incident_id"]))
        verdict = (inc.get("decision") or {}).get("verdict")
        a.passed = (inc.get("status") == "RESOLVED"
                    and verdict == "ALLOW_AUTO")
        a.detail = (f"{inc.get('fault_class')} -> {inc.get('planned_action')}, "
                    f"verdict {verdict}, status {inc.get('status')}, "
                    f"no approval requested")
    except Exception as exc:
        a.detail = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            fault.revert()
            client.apply_settings({"llm_base_url": pre})
        except Exception as exc:
            a.detail += f" | restore failed: {exc}"
        set_mode("APPROVAL")
        a.seconds = round(time.time() - t0, 1)
    return a


def act2_approval(client: TargetClient) -> Act:
    a = Act(2, "approval heal (F08, MEDIUM risk, human gates it)")
    t0 = time.time()
    fault = F08ConfigRegression(client, corpus_probe=corpus)
    try:
        set_mode("APPROVAL")
        drain(client)
        fault.inject()
        clamped = client.settings()["max_tokens"]
        code, started = api("/v1/loop/run?rca=true", "POST")
        if code != 202:
            a.detail = f"loop/run {code}"
            return a
        parked = wait_terminal(str(started["incident_id"]))
        wrote_nothing = client.settings()["max_tokens"] == clamped
        a.note(parked)
        if parked.get("status") != "AWAITING_APPROVAL":
            a.detail = (f"did not park: {parked.get('status')}"
                        + ("  <-- THE BLAST-RADIUS LIMITER, not this act. "
                           "Wait for the hour to slide and rehearse again."
                           if a.limiter else ""))
            return a
        say(f"    parked: {parked.get('fault_class')} -> "
            f"{parked.get('planned_action')}, "
            f"tier {(parked.get('decision') or {}).get('risk_tier')}, "
            f"target untouched = {wrote_nothing}")
        say("    <-- ON STAGE, PAUSE HERE. Show the plan and the inverse.")
        code, second = api(
            f"/v1/incidents/{started['incident_id']}/approve", "POST")
        if code != 202:
            a.detail = f"approve {code}"
            return a
        healed = wait_terminal(str(second["incident_id"]))
        a.passed = healed.get("status") == "RESOLVED" and wrote_nothing
        a.detail = (f"parked writing nothing, then approved -> "
                    f"{healed.get('status')}")
    except Exception as exc:
        a.detail = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            fault.revert()
        except Exception as exc:
            a.detail += f" | revert failed: {exc}"
        a.seconds = round(time.time() - t0, 1)
    return a


def act3_rollback(client: TargetClient) -> Act:
    a = Act(3, "rollback (both LLM paths down, so the right repair fails)")
    t0 = time.time()
    fault = F01EndpointOutage()
    pre = str(client.settings()["llm_base_url"])
    try:
        set_mode("AUTONOMOUS")
        drain(client)
        fault.inject()
        proxy(BACKUP, False)
        warm_up_f01(client)
        code, started = api("/v1/loop/run?rca=true", "POST")
        if code != 202:
            a.detail = f"loop/run {code}"
            return a
        inc = wait_terminal(str(started["incident_id"]))
        unwind = inc.get("unwind") or {}
        after = str(client.settings()["llm_base_url"])
        a.passed = (inc.get("status") == "ESCALATED"
                    and bool(unwind.get("clean"))
                    and after == pre)
        a.detail = (f"repair applied and failed verification; unwound "
                    f"{unwind.get('restored')}/{unwind.get('attempted')} "
                    f"clean={unwind.get('clean')}; endpoint back at {after}")
    except Exception as exc:
        a.detail = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            fault.revert()
            proxy(BACKUP, True)
            client.apply_settings({"llm_base_url": pre})
        except Exception as exc:
            a.detail += f" | restore failed: {exc}"
        set_mode("APPROVAL")
        a.seconds = round(time.time() - t0, 1)
    return a


def act4_unknown(client: TargetClient) -> Act:
    a = Act(4, "unknown failure (database down - NOT in the catalogue)")
    t0 = time.time()
    stopped = False
    try:
        set_mode("APPROVAL")
        # Act 3 leaves an endpoint-outage error ratio behind; without this
        # the loop diagnoses THAT instead of the stopped database.
        drain(client)
        subprocess.run(["docker", "stop", DB_CONTAINER], check=True,
                       capture_output=True, timeout=60)
        stopped = True
        time.sleep(3)
        code, started = api("/v1/loop/run?rca=true", "POST")
        if code != 202:
            a.detail = f"loop/run {code}"
            return a
        inc = wait_terminal(str(started["incident_id"]))
        reasons = (inc.get("detection") or {}).get("reasons") or []
        a.passed = (inc.get("status") == "ESCALATED"
                    and not inc.get("fault_class"))
        a.detail = (f"{inc.get('status')}, no class claimed, nothing written. "
                    f"Reason: {reasons[0][:120] if reasons else '-'}")
        say("    <-- ON STAGE, READ THE REASON OUT. This is the system")
        say("        declining to act on a fault it does not understand.")
    except Exception as exc:
        a.detail = f"{type(exc).__name__}: {exc}"
    finally:
        if stopped:
            try:
                subprocess.run(["docker", "start", DB_CONTAINER], check=True,
                               capture_output=True, timeout=120)
                for _ in range(20):
                    if client.is_healthy():
                        break
                    time.sleep(5)
                # The stop leaves ragapp_corpus_chunks stale at 0 until a
                # query repopulates it, which would make a later preflight
                # refuse. Found by doing it.
                # The gauge is set on a query and scraped afterwards, so
                # read it back rather than assuming one question is enough -
                # a stale 0 here fails the scenario for no reason.
                for _ in range(6):
                    ask_one(client)
                    time.sleep(8)
                    if corpus() == EXPECTED_CORPUS:
                        break
            except Exception as exc:
                a.detail += f" | database restore failed: {exc}"
        a.seconds = round(time.time() - t0, 1)
    return a


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="demo-full")
    ap.add_argument("--acts", default="1,2,3,4")
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports" / "scenario.json"))
    args = ap.parse_args()

    # THE ENVIRONMENT FIRST, THEN `.env`. Reading os.environ alone is why
    # `make offline` died on a 401 from the target on 2026-10-19: no
    # Makefile target exports this, and the three P8 runs that passed were
    # driven by a script that happened to export it by hand. Settings is
    # the one thing here that knows to look at the repository root and not
    # only the cwd - see `config.py`, `_env_files`, whose docstring already
    # records this same 401 costing time twice before.
    admin_token = (os.environ.get("KAVACH_TARGET_ADMIN_TOKEN")
                   or get_settings().target_admin_token)
    if not admin_token:
        raise SystemExit(
            "KAVACH_TARGET_ADMIN_TOKEN is set neither in the environment nor "
            "in .env. Every act that writes target config would answer 401.")
    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config", admin_token=admin_token))

    say("=" * 78)
    say(f"  SCENARIO: {args.name}")
    say("=" * 78)
    start_mode = "APPROVAL"
    _, mode = api("/v1/mode")
    if isinstance(mode, dict):
        start_mode = str(mode.get("mode"))
    say(f"  mode at start      {start_mode} (restored at the end)")
    live = corpus()
    say(f"  corpus             {live}")
    if live != EXPECTED_CORPUS:
        say("  REFUSING: the corpus has drifted. Run one query against the")
        say("  target to refresh the gauge, or re-ingest; a demo on a drifted")
        say("  corpus shows the drift.")
        return 1
    if not client.is_healthy():
        say("  REFUSING: the target is not healthy before the first act.")
        return 1
    if not fast.run(client, FAST_SET, check_health=False).passed:
        say("  REFUSING: the fast set must pass before injecting anything.")
        return 1
    say("  preflight          healthy, fast set passing")
    # NAMED ON STAGE, because on 2026-10-19 a rebuild without `--env-file
    # .env` silently put the control plane on compose's `llama3.2` default
    # while `.env` said qwen, and a full rehearsal failed three acts before
    # anyone could see why. A demo that cannot say which model is reasoning
    # is not a demo of reasoning.
    model = rca_model()
    say(f"  RCA model          {model or 'UNKNOWN - /v1/system did not say'}")
    say("")
    say("  NOTE: these four acts cost up to 7 incident starts, and permit()")
    say("  allows 5 an hour. ONE full run fits. A second rehearsal inside the")
    say("  same hour will hit the blast-radius limiter and park - which is")
    say("  correct behaviour, not a bug. Space rehearsals an hour apart.")

    wanted = {int(x) for x in args.acts.split(",") if x.strip()}
    acts: list[Act] = []
    try:
        if 1 in wanted:
            act_header(1, "AUTONOMOUS HEAL",
                       "no human touched it; verdict ALLOW_AUTO")
            acts.append(act1_autonomous(client))
            say(f"    {acts[-1].detail}")
        if 2 in wanted:
            act_header(2, "APPROVAL HEAL",
                       "it parked and wrote NOTHING until a human approved")
            acts.append(act2_approval(client))
            say(f"    {acts[-1].detail}")
        if 3 in wanted:
            act_header(3, "ROLLBACK",
                       "the repair failed and the target went back exactly")
            acts.append(act3_rollback(client))
            say(f"    {acts[-1].detail}")
        if 4 in wanted:
            act_header(4, "UNKNOWN FAILURE",
                       "it refused to guess, and said why")
            acts.append(act4_unknown(client))
            say(f"    {acts[-1].detail}")
    finally:
        set_mode(start_mode)

    say("")
    say("=" * 78)
    say("  SCENARIO RESULT")
    say("=" * 78)
    for a in acts:
        mark = "PASS" if a.passed else ("LIMIT" if a.limiter else "FAIL")
        say(f"  {mark:<5} act {a.n} {a.title} ({a.seconds}s)")
        if not a.passed:
            say(f"        {a.detail}")
    if any(a.limiter for a in acts):
        say("")
        say("  One or more acts were stopped by permit()'s blast radius, not")
        say("  by a defect. Five incident starts an hour; an approved heal")
        say("  costs two. Leave an hour between rehearsals.")
    post = corpus()
    healthy = client.is_healthy()
    say(f"  corpus {live} -> {post}   target healthy: {healthy}")
    good = all(a.passed for a in acts) and post == live and healthy
    say("")
    say(f"  {args.name}: {'CLEAN' if good else 'NOT CLEAN'}")
    if good:
        say("  Acceptance asks for three consecutive clean runs. Leave an")
        say("  hour between them, for the blast-radius reason above.")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "name": args.name,
        "rca_model": model,
        "acts": [asdict(a) for a in acts],
        "corpus_before": live, "corpus_after": post,
        "target_healthy_after": healthy,
        "clean": good,
    }, indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  artifact {out}")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
