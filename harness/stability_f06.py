"""F06 stability: 20 deterministic inject -> heal -> verify cycles.

Separate from the single full end-to-end run (which exercises the whole
control-plane flow including detection) because the two answer different
questions. This one answers: does the injector plus the real rollback action
plus fast verification return the target to EXACTLY its prior state, every
time, without drift?

It is a LIVE test. Nothing is mocked: the real target, the real config
interface, the real reranker, the real fast-verification set, real Prometheus.
What it skips per cycle is the detector and the Prometheus-window wait, since
those are covered by the end-to-end run and waiting ~20s per cycle for metric
windows to settle is what pushed the previous attempt past the command timeout.

Each cycle proves all seven properties:
  1. the healthy threshold is what the baseline says (0.35)
  2. injecting 0.999 is accepted
  3. fast verification FAILS under the fault (all three cases)
  4. Kavach's own rollback_config action restores the value
  5. fast verification PASSES again (all three cases)
  6. the restored value equals the injector's recorded pre-state EXACTLY
  7. the corpus fingerprint and every unrelated setting are unchanged

Output is flushed per line: the previous attempt was block-buffered, so when it
was terminated the log was not a complete record of what had run. A partially
flushed log cannot be used as evidence, which is why those cycles were discarded
rather than counted.

Run it in the background; it takes roughly fifteen minutes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
CONTROL_PLANE = REPO_ROOT / "apps" / "control-plane"
if str(CONTROL_PLANE) not in sys.path:
    sys.path.insert(0, str(CONTROL_PLANE))

from harness.faults.f06_retrieval_collapse import (  # noqa: E402
    BAD_THRESHOLD,
    F06RetrievalCollapse,
)
from kavach.executor.config_rollback import (  # noqa: E402
    build_rollback_for_retrieval_collapse,
)
from kavach.onboarding.baseline import _promql  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"
HEALTHY_THRESHOLD = 0.35


def say(msg: str = "") -> None:
    print(msg, flush=True)


@dataclass
class CycleResult:
    n: int
    pre_threshold: float | None = None
    injected: bool = False
    broke: bool = False
    broke_detail: str = ""
    healed: bool = False
    healed_detail: str = ""
    restored_exactly: bool = False
    restore_detail: str = ""
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
            self.scope_ok, self.corpus_ok, self.action_record_ok,
        )) and not self.error

    def line(self) -> str:
        def m(b: bool) -> str:
            return "ok" if b else "FAIL"
        return (
            f"  cycle {self.n:2}  {'PASS' if self.passed else 'FAIL'}  "
            f"pre={self.pre_threshold} inject={m(self.injected)} "
            f"broke={m(self.broke)} healed={m(self.healed)} "
            f"exact={m(self.restored_exactly)} scope={m(self.scope_ok)} "
            f"corpus={m(self.corpus_ok)} record={m(self.action_record_ok)} "
            f"{self.seconds:5.1f}s"
            + (f"  ERROR {self.error}" if self.error else "")
        )


@dataclass
class Report:
    started_at: str
    cycles: list[CycleResult] = field(default_factory=list)
    settings_at_start: dict[str, object] = field(default_factory=dict)
    settings_at_end: dict[str, object] = field(default_factory=dict)
    corpus_at_start: dict[str, float | None] = field(default_factory=dict)
    corpus_at_end: dict[str, float | None] = field(default_factory=dict)

    @property
    def passed_count(self) -> int:
        return sum(c.passed for c in self.cycles)

    @property
    def all_passed(self) -> bool:
        return bool(self.cycles) and all(c.passed for c in self.cycles)

    @property
    def state_identical(self) -> bool:
        return (self.settings_at_start == self.settings_at_end
                and self.corpus_at_start == self.corpus_at_end)


def run(n_cycles: int, prometheus_url: str, admin_token: str) -> Report:
    client = TargetClient(TargetEndpoints(admin_token=admin_token))

    def corpus() -> dict[str, float | None]:
        return {"chunks": _promql(prometheus_url, "ragapp_corpus_chunks"),
                "files": _promql(prometheus_url, "ragapp_corpus_files")}

    rep = Report(started_at=datetime.now(UTC).isoformat(timespec="seconds"))
    rep.settings_at_start = client.settings()
    rep.corpus_at_start = corpus()

    say(f"F06 stability: {n_cycles} cycles")
    say(f"  started            {rep.started_at}")
    say(f"  healthy threshold  {rep.settings_at_start.get('rerank_threshold')}")
    say(f"  bad threshold      {BAD_THRESHOLD}")
    say(f"  corpus             {rep.corpus_at_start}")
    say(f"  fast set           {FAST_SET.name}")
    say("")

    for i in range(1, n_cycles + 1):
        c = CycleResult(n=i)
        t0 = time.perf_counter()
        fault = F06RetrievalCollapse(client, corpus_probe=corpus)
        try:
            # 1. healthy pre-state, captured by the injector
            c.pre_threshold = fault.current_threshold()
            if c.pre_threshold != HEALTHY_THRESHOLD:
                c.error = (f"pre-state threshold {c.pre_threshold} is not the "
                           f"healthy {HEALTHY_THRESHOLD}; refusing to proceed")
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
            action = build_rollback_for_retrieval_collapse(
                f"STAB-{i:02d}", client, known_good_threshold=HEALTHY_THRESHOLD
            )
            action.execute(client)

            # 5. fast verification must pass again
            after = fast.run(client, FAST_SET, check_health=False)
            c.healed = after.passed
            c.healed_detail = f"{after.pass_rate:.0%} pass after rollback"

            # 6. exactly the injector's recorded pre-state, not a constant
            c.restored_exactly, c.restore_detail = fault.restored_exactly()

            # 7. nothing else moved
            c.scope_ok, c.scope_detail = fault.assert_scope_respected()
            c.corpus_ok, c.corpus_detail = fault.assert_corpus_unchanged()

            # the action record must be complete and consistent
            rec = action.to_dict()
            required = ("incident_id", "action", "risk_tier", "idempotency_key",
                        "requested_settings", "inverse_settings", "pre_state",
                        "config_hash_before", "config_hash_after")
            missing = [k for k in required if not rec.get(k)]
            inverse_is_fault = rec["inverse_settings"] == {"rerank_threshold": BAD_THRESHOLD}
            wanted_baseline = rec["requested_settings"] == {"rerank_threshold": HEALTHY_THRESHOLD}
            c.action_record_ok = (not missing and rec["risk_tier"] == "MEDIUM"
                                  and inverse_is_fault and wanted_baseline)
            c.action_detail = (f"missing={missing} risk={rec['risk_tier']} "
                               f"inverse={rec['inverse_settings']}")
        except Exception as exc:
            # Any failure is a cycle failure; nothing is allowed to escape and
            # skip the revert in the finally block below.
            c.error = f"{type(exc).__name__}: {exc}"
        finally:
            # Always revert, even on an exception mid-cycle, so a failed run
            # never leaves the target faulted.
            try:
                fault.revert()
            except Exception as exc:
                c.error = (c.error + " | " if c.error else "") + f"revert failed: {exc}"
            c.seconds = time.perf_counter() - t0

        rep.cycles.append(c)
        say(c.line())
        if not c.passed:
            say(f"           broke:  {c.broke_detail}")
            say(f"           healed: {c.healed_detail}")
            say(f"           restore:{c.restore_detail}")
            say(f"           scope:  {c.scope_detail}")
            say(f"           corpus: {c.corpus_detail}")
            say(f"           record: {c.action_detail}")

    rep.settings_at_end = client.settings()
    rep.corpus_at_end = corpus()
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=20)
    ap.add_argument("--prometheus", default="http://localhost:9091")
    ap.add_argument("--admin-token", default="local-dev-token")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    rep = run(args.cycles, args.prometheus, args.admin_token)

    say("")
    say("=" * 72)
    say(f"RESULT: {rep.passed_count}/{len(rep.cycles)} cycles passed")
    say(f"  settings identical to start : {rep.settings_at_start == rep.settings_at_end}")
    say(f"  corpus identical to start   : {rep.corpus_at_start == rep.corpus_at_end}")
    say(f"  corpus                      : {rep.corpus_at_start} -> {rep.corpus_at_end}")
    say(f"  rerank_threshold at end     : {rep.settings_at_end.get('rerank_threshold')}")
    if rep.cycles:
        times = [c.seconds for c in rep.cycles]
        say(f"  per-cycle seconds           : min {min(times):.1f} "
            f"mean {sum(times)/len(times):.1f} max {max(times):.1f}")
    say("=" * 72)

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(
            {"started_at": rep.started_at,
             "passed": rep.passed_count, "total": len(rep.cycles),
             "all_passed": rep.all_passed,
             "state_identical": rep.state_identical,
             "settings_at_start": rep.settings_at_start,
             "settings_at_end": rep.settings_at_end,
             "corpus_at_start": rep.corpus_at_start,
             "corpus_at_end": rep.corpus_at_end,
             "cycles": [c.__dict__ for c in rep.cycles]},
            indent=2) + "\n", encoding="utf-8")
        say(f"artifact: {args.json_out}")

    ok = rep.all_passed and rep.state_identical and len(rep.cycles) == args.cycles
    say("STABILITY: PASS" if ok else "STABILITY: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
