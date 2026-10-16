"""F08 stability: 20 inject/heal/revert cycles must leave the stack identical.

Same acceptance criterion as the other two, and the same reason it matters: if
cycle 19 is not operating on the same system as cycle 1, no measurement taken
across cycles means anything.

WHAT THIS ONE CHECKS THAT THE OTHERS CANNOT
F08's whole detection signal is "which settings drifted from the baseline", so
this run asserts something the F06 and F01 runs have no reason to: that the
injector moves EXACTLY ONE setting, every cycle. An injector that disturbed a
second key would manufacture the very evidence the detector is being tested on,
and the fault would appear to be detected for the wrong reason twenty times in
a row. `assert_scope_respected()` is therefore checked per cycle rather than
once at the end.

It also checks the config hash returns to its captured value, not merely that
`max_tokens` does. The hash covers every setting, so a cycle that restored the
clamp while leaving something else moved would pass a `max_tokens` check and
fail this one.

THREE STABILITY HARNESSES NOW SHARE MOST OF THIS SHAPE
`stability_f06.py`, `stability_f01.py` and this one differ in which setting
they move, which action heals it, and which assertions apply. A shared driver
taking a Fault and an action builder is the obvious next move, and is
deliberately NOT done here: two of the three differ in more than parameters -
F01 must apply the action's inverse every cycle to stay repeatable, F06 and F08
must not - and an abstraction that has to special-case a third of its callers
costs more than it saves. If a fourth arrives, extract then.

Requires both stacks up and the real admin token in the environment:
    KAVACH_TARGET_ADMIN_TOKEN=...
    uv run --project apps/control-plane python -I harness/stability_f08.py
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

from harness.faults.f08_config_regression import (  # noqa: E402
    BAD_MAX_TOKENS,
    SETTING,
    F08ConfigRegression,
)
from kavach.executor.config_rollback import (  # noqa: E402
    build_rollback_for_retrieval_collapse,
)
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
    pre_value: Any = None
    injected: bool = False
    broke: bool = False
    broke_detail: str = ""
    healed: bool = False
    healed_detail: str = ""
    restored_exactly: bool = False
    restore_detail: str = ""
    hash_restored: bool = False
    hash_detail: str = ""
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
            self.injected, self.broke, self.healed, self.restored_exactly,
            self.hash_restored, self.scope_ok, self.corpus_ok,
            self.action_record_ok,
        )) and not self.error

    def line(self) -> str:
        def m(b: bool) -> str:
            return "ok" if b else "FAIL"

        head = "PASS" if self.passed else "FAIL"
        return (f"  cycle {self.n:2}  {head}  "
                f"inject={m(self.injected)} broke={m(self.broke)} "
                f"healed={m(self.healed)} restore={m(self.restored_exactly)} "
                f"hash={m(self.hash_restored)} scope={m(self.scope_ok)} "
                f"corpus={m(self.corpus_ok)} record={m(self.action_record_ok)}"
                f"  {self.seconds:5.1f}s"
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

    rep = Report(started_at=datetime.now(UTC).isoformat(timespec="seconds"))
    rep.settings_at_start = client.settings()
    rep.corpus_at_start = corpus()
    start_value = rep.settings_at_start[SETTING]
    start_hash = client.config_hash()

    say(f"F08 stability: {n_cycles} cycles")
    say(f"  started            {rep.started_at}")
    say(f"  healthy {SETTING}  {start_value}")
    say(f"  clamped to         {BAD_MAX_TOKENS}")
    say(f"  config hash        {start_hash}")
    say(f"  corpus             {rep.corpus_at_start}")
    say("")

    for i in range(1, n_cycles + 1):
        c = CycleResult(n=i)
        t0 = time.perf_counter()
        fault = F08ConfigRegression(client, corpus_probe=corpus)
        try:
            c.pre_value = client.settings()[SETTING]
            if c.pre_value != start_value:
                c.error = (f"pre-state {SETTING} {c.pre_value} is not the "
                           f"starting {start_value}; refusing to proceed")
                rep.cycles.append(c)
                say(c.line())
                break

            fault.inject()
            c.injected = fault.is_active()

            under_fault = fast.run(client, FAST_SET, check_health=False)
            c.broke = not under_fault.passed and under_fault.pass_rate == 0.0
            c.broke_detail = f"{under_fault.pass_rate:.0%} pass under fault"

            # Heal with Kavach's REAL action, not the injector's revert. The
            # dict form of the builder is F08's: restore exactly the drifted
            # key to its captured value.
            action = build_rollback_for_retrieval_collapse(
                f"STAB08-{i:02d}", client, {SETTING: start_value}
            )
            action.execute(client)

            after = fast.run(client, FAST_SET, check_health=False)
            c.healed = after.passed
            c.healed_detail = f"{after.pass_rate:.0%} pass after rollback"

            c.restored_exactly, c.restore_detail = fault.restored_exactly()

            # The hash covers EVERY setting, so this catches a cycle that put
            # max_tokens back while leaving something else moved.
            live_hash = client.config_hash()
            c.hash_restored = live_hash == start_hash
            c.hash_detail = f"{live_hash} (want {start_hash})"

            # Per cycle, not once: an injector that moved a second setting
            # would manufacture the evidence this detector is tested on.
            c.scope_ok, c.scope_detail = fault.assert_scope_respected()
            c.corpus_ok, c.corpus_detail = fault.assert_corpus_unchanged()

            rec = action.to_dict()
            required = ("incident_id", "action", "risk_tier", "idempotency_key",
                        "requested_settings", "inverse_settings", "pre_state",
                        "config_hash_before", "config_hash_after")
            missing = [k for k in required if not rec.get(k)]
            wanted = rec["requested_settings"] == {SETTING: start_value}
            inverse_is_fault = rec["inverse_settings"] == {SETTING: BAD_MAX_TOKENS}
            c.action_record_ok = (not missing and rec["risk_tier"] == "MEDIUM"
                                  and wanted and inverse_is_fault)
            c.action_detail = (f"missing={missing} risk={rec['risk_tier']} "
                               f"inverse={rec['inverse_settings']}")
        except Exception as exc:
            c.error = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                fault.revert()
            except Exception as exc:
                c.error = (c.error + " | " if c.error else "") + f"revert failed: {exc}"
            c.seconds = time.perf_counter() - t0

        rep.cycles.append(c)
        say(c.line())
        if not c.passed:
            say(f"           broke:   {c.broke_detail}")
            say(f"           healed:  {c.healed_detail}")
            say(f"           restore: {c.restore_detail}")
            say(f"           hash:    {c.hash_detail}")
            say(f"           scope:   {c.scope_detail}")
            say(f"           corpus:  {c.corpus_detail}")
            say(f"           record:  {c.action_detail}")

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
                    default=str(ROOT / "harness" / "reports" / "f08-stability.json"))
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
    say(f"  F08 STABILITY: {'PASS' if ok else 'FAIL'}")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "started_at": rep.started_at,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "cycles_requested": args.cycles,
        "cycles_passed": rep.passed,
        "stack_identical": rep.identical,
        "clamped_to": BAD_MAX_TOKENS,
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
