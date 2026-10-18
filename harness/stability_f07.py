"""F07 stability: 20 inject/heal/revert cycles must leave the stack identical.

Same acceptance criterion as the other three, and the same reason it matters:
if cycle 19 is not operating on the same system as cycle 1, no measurement
taken across cycles means anything.

WHAT THIS ONE CHECKS THAT THE OTHER THREE CANNOT

**That the write keeps reaching the running target, every cycle.** Every
other repair in the catalogue goes through the target's HTTP config
interface, where the target itself applies the change and reports the result.
This one writes a file on one side of a bind mount and trusts a container on
the other side to notice. So every check here reads the digests the TARGET
reports, never the bytes on disk: re-reading the file Kavach just wrote would
confirm only that the write succeeded, which is never the thing in doubt.

**That the symptom keeps F07's shape and does not drift into F06's.**
`rag.py` appends the `**Sources:**` block only when the answer is not a
fallback, so a prompt that induces a refusal also suppresses that block and
the fast set then reads exactly like a retrieval collapse. This is checked
per cycle, not once, because it is a property of a stochastic model's
response rather than of the file: 20 cycles that quietly became F06 halfway
through would otherwise report a clean 20/20.

WHY THERE IS STILL NO SHARED DRIVER, AGAINST THIS FILE'S OWN PREDICTION
`stability_f08.py` says a shared driver taking a Fault and an action builder
"is the obvious next move", deliberately not done at three, and *"if a fourth
arrives, extract then"*. A fourth has arrived and the extraction is still
wrong, for a reason the note could not have known: F07 differs from the other
three by MORE than its parameters, not less. It heals by writing files rather
than settings, it has no config hash to compare, its action is built from the
baseline's recorded text rather than from a single value, and it carries a
per-cycle symptom-shape assertion none of the others need. A driver over four
callers that special-cases three of them is worse than four explicit files.
The note was right to set a trigger and the trigger fired on the wrong fault;
re-evaluate at F09, which shares F08's shape closely.

Requires both stacks up, a baseline captured WITH `prompt_contents`, and the
real admin token in the environment:
    KAVACH_TARGET_ADMIN_TOKEN=...
    uv run --project apps/control-plane python -I harness/stability_f07.py
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

from harness.faults.f07_prompt_regression import (  # noqa: E402
    PROMPT_FILE,
    F07PromptRegression,
)
from kavach.api.runner import newest_baseline_doc  # noqa: E402
from kavach.config import get_settings  # noqa: E402
from kavach.executor.prompt_rollback import (  # noqa: E402
    build_rollback_for_prompt_regression,
)
from kavach.onboarding.manifest import load as load_manifest  # noqa: E402
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
    injected: bool = False
    broke: bool = False
    broke_detail: str = ""
    shape_ok: bool = False
    shape_detail: str = ""
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
        """The ACCEPTANCE criterion, which is about the injector.

        `broke` is deliberately absent, for the reason `stability_f08.py`
        records at length: it asks whether the TARGET collapsed, which is a
        property of the model's response and not of the injector. Folding the
        two together once made a perfect injector look flaky. The
        manifestation rate is reported separately and prominently instead.

        `shape_ok` IS in this list, unlike `broke`, and the distinction is
        the point. Whether the fault manifests at all is stochastic. Whether
        it manifests as F07 rather than as F06 is not negotiable: a cycle
        that injected the wrong fault did not inject this one.
        """
        return all((
            self.injected, self.healed, self.restored_exactly,
            self.shape_ok, self.scope_ok, self.corpus_ok,
            self.action_record_ok,
        )) and not self.error

    @property
    def manifested(self) -> bool:
        return self.broke

    def line(self) -> str:
        def m(b: bool) -> str:
            return "ok" if b else "XX"

        return (
            f"  cycle {self.n:2}  inj={m(self.injected)} "
            f"broke={m(self.broke)} shape={m(self.shape_ok)} "
            f"heal={m(self.healed)} restore={m(self.restored_exactly)} "
            f"scope={m(self.scope_ok)} corpus={m(self.corpus_ok)} "
            f"record={m(self.action_record_ok)}  {self.seconds:5.1f}s  "
            f"{'PASS' if self.passed else 'FAIL'}"
            + (f"  {self.error}" if self.error else "")
        )


@dataclass
class Report:
    started_at: str = ""
    cycles: list[CycleResult] = field(default_factory=list)
    digests_at_start: dict[str, str] = field(default_factory=dict)
    digests_at_end: dict[str, str] = field(default_factory=dict)
    settings_at_start: dict[str, Any] = field(default_factory=dict)
    settings_at_end: dict[str, Any] = field(default_factory=dict)
    corpus_at_start: dict[str, float | None] = field(default_factory=dict)
    corpus_at_end: dict[str, float | None] = field(default_factory=dict)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=20)
    ap.add_argument("--prometheus", default=DEFAULT_PROM)
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports" / "stability-f07.json"))
    args = ap.parse_args()

    def promql(query: str) -> float | None:
        url = args.prometheus + "/api/v1/query?query=" + urllib.parse.quote(query)
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                res = json.loads(r.read())["data"]["result"]
            return float(res[0]["value"][1]) if res else None
        except Exception:
            return None

    def corpus() -> dict[str, float | None]:
        return {"chunks": promql("ragapp_corpus_chunks"),
                "files": promql("ragapp_corpus_files")}

    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))

    settings = get_settings()
    target_path = Path(settings.target_path)
    declared = load_manifest(target_path / "kavach.yaml").versioned_paths["prompts"]
    prompts_dir = (target_path / declared).resolve()

    doc, baseline_name = newest_baseline_doc(
        settings.baselines_dir(), settings.target_project)
    known_good = dict(doc.get("prompt_contents") or {})
    if not known_good:
        say(f"the newest baseline ({baseline_name}) records no prompt_contents, "
            f"so the repair cannot be built. Re-run the capture.")
        return 1

    def reported() -> dict[str, str]:
        cfg = client.config()
        return dict((cfg.get("prompt_version") or {}).get("files") or {})

    rep = Report(started_at=datetime.now(UTC).isoformat(timespec="seconds"))
    rep.digests_at_start = reported()
    rep.settings_at_start = client.settings()
    rep.corpus_at_start = corpus()
    start_digests = dict(rep.digests_at_start)

    say("=" * 78)
    say(f"F07 STABILITY: {args.cycles} inject/heal/revert cycles")
    say("=" * 78)
    say(f"  prompts directory  {prompts_dir}")
    say(f"  baseline           {baseline_name}")
    say(f"  known-good held    { {k: len(v) for k, v in known_good.items()} }")
    say(f"  digests at start   {start_digests}")
    say(f"  corpus             {rep.corpus_at_start}")
    say("")

    for i in range(1, args.cycles + 1):
        c = CycleResult(n=i)
        t0 = time.perf_counter()
        fault = F07PromptRegression(client, prompts_dir, corpus_probe=corpus)
        try:
            pre = reported()
            if pre != start_digests:
                c.error = (f"pre-state digests {pre} are not the starting "
                           f"{start_digests}; refusing to proceed")
                rep.cycles.append(c)
                say(c.line())
                break

            fault.inject()
            c.injected = fault.is_active()

            under_fault = fast.run(client, FAST_SET, check_health=False)
            c.broke = not under_fault.passed and under_fault.pass_rate == 0.0
            c.broke_detail = f"{under_fault.pass_rate:.0%} pass under fault"
            c.shape_ok, c.shape_detail = fault.assert_symptom_shape(
                list(under_fault.cases))

            # Heal with Kavach's REAL action, not the injector's revert. The
            # injector putting its own file back would demonstrate nothing
            # about healing.
            action = build_rollback_for_prompt_regression(
                f"STAB07-{i:02d}", client,
                {"dir": str(prompts_dir), "files": known_good},
            )
            action.execute(client)

            after = fast.run(client, FAST_SET, check_health=False)
            c.healed = after.passed
            c.healed_detail = f"{after.pass_rate:.0%} pass after rollback"

            c.restored_exactly, c.restore_detail = fault.restored_exactly()
            c.scope_ok, c.scope_detail = fault.assert_scope_respected()
            c.corpus_ok, c.corpus_detail = fault.assert_corpus_unchanged()

            rec = action.to_dict()
            required = ("incident_id", "action", "risk_tier", "idempotency_key",
                        "requested_settings", "inverse_settings", "pre_state",
                        "prompts_dir", "restored_files", "bytes_written")
            missing = [k for k in required if not rec.get(k)]
            only_drifted = rec["restored_files"] == [PROMPT_FILE]
            # The audit log is append-only forever; prompt text must never
            # enter it. "CONTEXT:" appears in every prompt in this project.
            no_text = "CONTEXT:" not in json.dumps(rec)
            c.action_record_ok = (not missing and rec["risk_tier"] == "MEDIUM"
                                  and only_drifted and no_text)
            c.action_detail = (f"missing={missing} risk={rec['risk_tier']} "
                               f"files={rec['restored_files']} no_text={no_text}")
        except Exception as exc:
            c.error = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                fault.revert()
            except Exception as exc:  # pragma: no cover - teardown only
                c.error = (c.error + f" | revert failed: {exc}").strip(" |")
            c.seconds = time.perf_counter() - t0

        rep.cycles.append(c)
        say(c.line())
        if c.error:
            say(f"           {c.error}")
        if not c.shape_ok:
            say(f"           shape: {c.shape_detail}")

    rep.digests_at_end = reported()
    rep.settings_at_end = client.settings()
    rep.corpus_at_end = corpus()

    passed = sum(1 for c in rep.cycles if c.passed)
    manifested = sum(1 for c in rep.cycles if c.manifested)
    shaped = sum(1 for c in rep.cycles if c.shape_ok)
    times = [c.seconds for c in rep.cycles if c.seconds]
    stack_identical = (
        rep.digests_at_end == rep.digests_at_start
        and rep.settings_at_end == rep.settings_at_start
        and rep.corpus_at_end == rep.corpus_at_start
    )

    say("")
    say("=" * 78)
    say("RESULT")
    say("=" * 78)
    say(f"  cycles passed      {passed}/{len(rep.cycles)}   (acceptance: all)")
    say(f"  symptom manifested {manifested}/{len(rep.cycles)}  "
        f"= {manifested / max(len(rep.cycles), 1):.0%}  "
        f"(reported, not asserted - generation is stochastic)")
    say(f"  F07-shaped         {shaped}/{len(rep.cycles)}  "
        f"(asserted: a cycle shaped like F06 injected the wrong fault)")
    if times:
        say(f"  cycle time         min {min(times):.1f}s mean "
            f"{statistics.mean(times):.1f}s max {max(times):.1f}s")
    say(f"  digests            {rep.digests_at_start} -> {rep.digests_at_end}")
    say(f"  corpus             {rep.corpus_at_start} -> {rep.corpus_at_end}")
    say(f"  stack identical    {stack_identical}")

    good = (passed == len(rep.cycles) == args.cycles) and stack_identical
    say("")
    say(f"  F07 STABILITY: {'PASS' if good else 'FAIL'}")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "at": rep.started_at,
        "cycles_requested": args.cycles,
        "cycles_run": len(rep.cycles),
        "cycles_passed": passed,
        "manifested": manifested,
        "f07_shaped": shaped,
        "stack_identical": stack_identical,
        "baseline": baseline_name,
        "digests_at_start": rep.digests_at_start,
        "digests_at_end": rep.digests_at_end,
        "settings_at_start": rep.settings_at_start,
        "settings_at_end": rep.settings_at_end,
        "corpus_at_start": rep.corpus_at_start,
        "corpus_at_end": rep.corpus_at_end,
        "passed": good,
        "runs": [vars(c) for c in rep.cycles],
    }, indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  artifact {out}")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
