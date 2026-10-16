"""F01 stability: 20 inject/heal/revert cycles must leave the stack identical.

`ROADMAP.md`'s per-fault acceptance requires the injector to be deterministic,
to revert cleanly, and to be stable over 20 cycles. That criterion is
load-bearing for every other F01 number: if cycle 19 is not operating on the
same system as cycle 1, no measurement taken across cycles means anything.

HEALED BY KAVACH'S ACTION, NOT BY THE INJECTOR'S REVERT
Each cycle disables the primary Toxiproxy listener, confirms fast verification
breaks, then heals with the REAL `switch_llm_endpoint` action - failing over to
the declared backup - and confirms verification passes again through it. The
injector's `revert()` only puts the listener back, in a `finally`, so a failed
cycle never leaves the target faulted.

IT ALSO EXERCISES `invert()`, WHICH THE F06 RUN DOES NOT
F06's repair writes the baseline value, so the system ends each cycle where it
started and the inverse is never applied. A failover does not: healing leaves
the application pointed at the BACKUP, which is the correct healed state but
not the starting state. So each cycle applies the action's recorded inverse to
return to the primary, and checks it against the pre-state witness. Twenty
cycles therefore test the inverse twenty times, not zero.

WHY THE ENDPOINT MUST GO BACK EVERY CYCLE
`build_switch_for_endpoint_outage` refuses to prepare a failover when the
application is already on the backup - a no-op whose inverse would restore the
faulty endpoint. Leaving the endpoint on the backup would make cycle 2 refuse
to build, so the inverse is not optional bookkeeping here; it is what makes the
run repeatable.

Requires both stacks up and the real admin token in the environment:
    KAVACH_TARGET_ADMIN_TOKEN=...
    uv run --project apps/control-plane python -I harness/stability_f01.py
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = ROOT / "apps" / "control-plane"
sys.path[:0] = [str(ROOT), str(CONTROL_PLANE)]

from harness.faults.f01_endpoint_outage import F01EndpointOutage  # noqa: E402
from kavach.executor.endpoint_switch import (  # noqa: E402
    SETTING,
    build_switch_for_endpoint_outage,
)
from kavach.onboarding.manifest import load  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"
TARGET = "http://127.0.0.1:8000"
DEFAULT_PROM = "http://127.0.0.1:9091"


def say(msg: str = "") -> None:
    print(msg, flush=True)


@dataclass
class CycleResult:
    n: int
    pre_endpoint: str = ""
    injected: bool = False
    broke: bool = False
    broke_detail: str = ""
    healed: bool = False
    healed_detail: str = ""
    inverted: bool = False
    invert_detail: str = ""
    listener_restored: bool = False
    listener_detail: str = ""
    scope_ok: bool = False
    scope_detail: str = ""
    corpus_ok: bool = False
    corpus_detail: str = ""
    action_record_ok: bool = False
    action_detail: str = ""
    seconds: float = 0.0
    error: str = ""

    @property
    def passed(self) -> bool:
        return all((
            self.injected, self.broke, self.healed, self.inverted,
            self.listener_restored, self.scope_ok, self.corpus_ok,
            self.action_record_ok,
        )) and not self.error

    def line(self) -> str:
        def m(b: bool) -> str:
            return "ok" if b else "FAIL"

        head = "PASS" if self.passed else "FAIL"
        return (f"  cycle {self.n:2}  {head}  "
                f"inject={m(self.injected)} broke={m(self.broke)} "
                f"healed={m(self.healed)} invert={m(self.inverted)} "
                f"listener={m(self.listener_restored)} "
                f"scope={m(self.scope_ok)} corpus={m(self.corpus_ok)} "
                f"record={m(self.action_record_ok)}  {self.seconds:5.1f}s"
                + (f"  {self.error}" if self.error else ""))


@dataclass
class Report:
    started_at: str
    cycles: list[CycleResult] = field(default_factory=list)
    settings_at_start: dict[str, Any] = field(default_factory=dict)
    settings_at_end: dict[str, Any] = field(default_factory=dict)
    corpus_at_start: dict[str, Any] = field(default_factory=dict)
    corpus_at_end: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cycles if c.passed)

    @property
    def identical(self) -> bool:
        """The acceptance wording: the stack must be identical to the start."""
        return (self.settings_at_start == self.settings_at_end
                and self.corpus_at_start == self.corpus_at_end)


def promql(prometheus_url: str, query: str) -> float | None:
    url = prometheus_url + "/api/v1/query?query=" + urllib.parse.quote(query)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            res = json.loads(r.read())["data"]["result"]
        return float(res[0]["value"][1]) if res else None
    except Exception:
        return None


def run(n_cycles: int, prometheus_url: str, admin_token: str) -> Report:
    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config", admin_token=admin_token))

    def corpus() -> dict[str, float | None]:
        return {"chunks": promql(prometheus_url, "ragapp_corpus_chunks"),
                "files": promql(prometheus_url, "ragapp_corpus_files")}

    # The failover target is DECLARED, never guessed - same source the runner
    # reads, so this cannot drift from what production would do.
    manifest = load(Path("D:/Vit/Academics Sem-5/EDI/Target_RAG-App/kavach.yaml"))
    backup_url = manifest.llm.paths.backup if manifest.llm else None
    if not backup_url:
        raise SystemExit(
            "the target's manifest declares no llm.paths.backup, so there is "
            "nowhere to fail over to and F01 has no repair to test"
        )

    rep = Report(started_at=datetime.now(UTC).isoformat(timespec="seconds"))
    rep.settings_at_start = client.settings()
    rep.corpus_at_start = corpus()
    start_endpoint = str(rep.settings_at_start[SETTING])

    say(f"F01 stability: {n_cycles} cycles")
    say(f"  started            {rep.started_at}")
    say(f"  primary endpoint   {start_endpoint}")
    say(f"  declared backup    {backup_url}")
    say(f"  corpus             {rep.corpus_at_start}")
    say(f"  fast set           {FAST_SET.name}")
    say("")

    for i in range(1, n_cycles + 1):
        c = CycleResult(n=i)
        t0 = time.perf_counter()
        fault = F01EndpointOutage(corpus_probe=corpus)
        action = None
        try:
            # 1. healthy pre-state
            c.pre_endpoint = str(client.settings()[SETTING])
            if c.pre_endpoint != start_endpoint:
                c.error = (f"pre-state endpoint {c.pre_endpoint} is not the "
                           f"starting {start_endpoint}; refusing to proceed")
                rep.cycles.append(c)
                say(c.line())
                break

            # 2. inject
            fault.inject()
            c.injected = fault.is_active()

            # 3. the fault must break fast verification
            under_fault = fast.run(client, FAST_SET, check_health=False)
            c.broke = not under_fault.passed and under_fault.pass_rate == 0.0
            c.broke_detail = f"{under_fault.pass_rate:.0%} pass under fault"

            # 4. heal with Kavach's REAL action, not the injector's revert
            action = build_switch_for_endpoint_outage(
                f"STAB01-{i:02d}", client, backup_url=backup_url
            )
            action.execute(client)

            # 5. fast verification must pass again, through the backup
            after = fast.run(client, FAST_SET, check_health=False)
            c.healed = after.passed
            c.healed_detail = (f"{after.pass_rate:.0%} pass on "
                               f"{client.settings()[SETTING]}")

            # 6. the recorded inverse must return the exact pre-state value.
            #    Not optional: a cycle that ends on the backup makes the next
            #    one refuse to build.
            action.invert(client)
            c.inverted, c.invert_detail = action.verify_restored(client)

            # 7. nothing else moved
            c.scope_ok, c.scope_detail = fault.assert_scope_respected()
            c.corpus_ok, c.corpus_detail = fault.assert_corpus_unchanged()

            rec = action.to_dict()
            required = ("incident_id", "action", "risk_tier", "idempotency_key",
                        "requested_settings", "inverse_settings", "pre_state",
                        "config_hash_before")
            missing = [k for k in required if not rec.get(k)]
            wanted_backup = rec["requested_settings"] == {SETTING: backup_url}
            inverse_is_primary = rec["inverse_settings"] == {SETTING: c.pre_endpoint}
            c.action_record_ok = (not missing and rec["risk_tier"] == "LOW"
                                  and wanted_backup and inverse_is_primary)
            c.action_detail = (f"missing={missing} risk={rec['risk_tier']} "
                               f"inverse={rec['inverse_settings']}")
        except Exception as exc:
            c.error = f"{type(exc).__name__}: {exc}"
        finally:
            # Always put the listener back, even on an exception mid-cycle.
            try:
                fault.revert()
                c.listener_restored, c.listener_detail = fault.restored_exactly()
            except Exception as exc:
                c.error = (c.error + " | " if c.error else "") + f"revert failed: {exc}"
            # And the endpoint, if the inverse above never ran.
            try:
                if str(client.settings()[SETTING]) != start_endpoint:
                    client.apply_settings({SETTING: start_endpoint})
            except Exception as exc:
                c.error = (c.error + " | " if c.error else "") + f"endpoint reset failed: {exc}"
            c.seconds = time.perf_counter() - t0

        rep.cycles.append(c)
        say(c.line())
        if not c.passed:
            say(f"           broke:    {c.broke_detail}")
            say(f"           healed:   {c.healed_detail}")
            say(f"           invert:   {c.invert_detail}")
            say(f"           listener: {c.listener_detail}")
            say(f"           scope:    {c.scope_detail}")
            say(f"           corpus:   {c.corpus_detail}")
            say(f"           record:   {c.action_detail}")

    rep.settings_at_end = client.settings()
    rep.corpus_at_end = corpus()
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=20)
    ap.add_argument("--prometheus", default=DEFAULT_PROM)
    ap.add_argument("--admin-token",
                    default=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", ""))
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports" / "f01-stability.json"))
    args = ap.parse_args()

    rep = run(args.cycles, args.prometheus, args.admin_token)
    secs = [c.seconds for c in rep.cycles]

    say("")
    say("=" * 74)
    say("SUMMARY")
    say("=" * 74)
    say(f"  cycles passed      {rep.passed}/{len(rep.cycles)}")
    if secs:
        say(f"  seconds per cycle  min {min(secs):.1f} mean "
            f"{statistics.mean(secs):.1f} max {max(secs):.1f}")
    same = rep.settings_at_start == rep.settings_at_end
    say(f"  settings           {'identical' if same else 'CHANGED'}")
    say(f"  corpus             {rep.corpus_at_start} -> {rep.corpus_at_end}")
    say(f"  stack identical    {rep.identical}")

    ok = (rep.passed == len(rep.cycles) == args.cycles) and rep.identical
    say("")
    say(f"  F01 STABILITY: {'PASS' if ok else 'FAIL'}")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "started_at": rep.started_at,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "cycles_requested": args.cycles,
        "cycles_passed": rep.passed,
        "stack_identical": rep.identical,
        "settings_at_start": rep.settings_at_start,
        "settings_at_end": rep.settings_at_end,
        "corpus_at_start": rep.corpus_at_start,
        "corpus_at_end": rep.corpus_at_end,
        "seconds": secs,
        "passed": ok,
        "cycles": [c.__dict__ for c in rep.cycles],
    }, indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  artifact {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
