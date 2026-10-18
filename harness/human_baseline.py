"""The human baseline: time a person resolving the same faults Kavach does.

`PRD.md` §10 calls MTTR < 3 min "the core claim". A duration with nothing to
compare it against is not a claim, it is a number. This produces the
comparison. The full protocol, the biases and how to report it are in
`docs/HUMAN_BASELINE.md`; this file is the instrument.

THREE THINGS THIS ENFORCES THAT A STOPWATCH WOULD NOT

**Blindness.** The fault is chosen at random from the implemented catalogue
and never printed until the run is scored. An operator who knows the class is
being timed on repair alone, and detection plus diagnosis are two thirds of
what Kavach is compared on.

**The same bar.** The resolve clock stops when the real fast set passes 3/3
and health is 200 - not when the operator says they are done. A run declared
resolved over a still-broken system is recorded as a FALSE RECOVERY, not as a
slightly longer time. That asymmetry is the whole point: `AGENTS.md` ranks a
false-healthy verdict above every other failure mode, and a baseline that
let a human quietly produce one would be measuring something kinder than what
Kavach is held to.

**Restoration.** Whatever the operator did or did not do, the injector's
revert runs in a finally block and the final state is checked against the
pre-state witness. A session cannot leave the target broken for the next run.

WHAT IT DELIBERATELY DOES NOT DO
It does not tell the operator anything, score their diagnosis for them, or
run Kavach. Kavach should be left running in SIMULATION so the same incident
yields a paired observation - see the protocol - but this script neither
starts nor reads it, because a runner that drove both would be able to
influence the comparison it is measuring.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = ROOT / "apps" / "control-plane"
sys.path[:0] = [str(ROOT), str(CONTROL_PLANE)]

from harness.faults.base import Fault  # noqa: E402
from harness.faults.f01_endpoint_outage import F01EndpointOutage  # noqa: E402
from harness.faults.f06_retrieval_collapse import F06RetrievalCollapse  # noqa: E402
from harness.faults.f07_prompt_regression import F07PromptRegression  # noqa: E402
from harness.faults.f08_config_regression import F08ConfigRegression  # noqa: E402
from kavach.config import get_settings  # noqa: E402
from kavach.onboarding.manifest import load as load_manifest  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"
TARGET = "http://127.0.0.1:8000"
PROM = "http://127.0.0.1:9091"

# The corpus the fast set was built against. A session run on a drifted corpus
# measures the drift; PRD.md section 12 records that happening twice.
EXPECTED_CORPUS = {"chunks": 30.0, "files": 2.0}


def say(m: str = "") -> None:
    print(m, flush=True)


def promql(query: str) -> float | None:
    url = PROM + "/api/v1/query?query=" + urllib.parse.quote(query)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            res = json.loads(r.read())["data"]["result"]
        return float(res[0]["value"][1]) if res else None
    except Exception:
        return None


def corpus() -> dict[str, float | None]:
    return {"chunks": promql("ragapp_corpus_chunks"),
            "files": promql("ragapp_corpus_files")}


def prompts_dir() -> Path:
    target = Path(get_settings().target_path)
    declared = load_manifest(target / "kavach.yaml").versioned_paths["prompts"]
    return (target / declared).resolve()


def build_catalogue(client: TargetClient) -> dict[str, Fault]:
    """One injector per implemented class. F09 is absent and closed - see
    PRD.md section 12: three mechanisms measured, none reaches 3x tokens."""
    return {
        "F01": F01EndpointOutage(corpus_probe=corpus),
        "F06": F06RetrievalCollapse(client, corpus_probe=corpus),
        "F07": F07PromptRegression(client, prompts_dir(), corpus_probe=corpus),
        "F08": F08ConfigRegression(client, corpus_probe=corpus),
    }


@dataclass
class Run:
    operator: str
    fault_class: str
    started_at: str = ""
    mttd_s: float | None = None
    diagnosis_s: float | None = None
    resolve_s: float | None = None
    operator_diagnosis: str = ""
    operator_action: str = ""
    diagnosis_correct: bool | None = None
    declared_resolved_at_s: float | None = None
    verified: bool = False
    false_recovery: bool = False
    pass_rate_at_declaration: float | None = None
    gave_up: bool = False
    notes: str = ""
    corpus_before: dict[str, float | None] = field(default_factory=dict)
    corpus_after: dict[str, float | None] = field(default_factory=dict)


def ask(prompt: str) -> str:
    """Blocking prompt. The operator is the instrument here, not the script."""
    try:
        return input(prompt).strip()
    except EOFError:
        # Non-interactive invocation would otherwise record a zero-second
        # run, which is worse than refusing.
        raise SystemExit(
            "\nhuman_baseline.py needs an interactive terminal: it is timing "
            "a person. Run it directly, not through a pipe or a task runner."
        ) from None


def one_run(client: TargetClient, operator: str, rng: random.Random) -> Run:
    catalogue = build_catalogue(client)
    fault_class = rng.choice(sorted(catalogue))
    fault = catalogue[fault_class]
    run = Run(operator=operator, fault_class=fault_class,
              started_at=datetime.now(UTC).isoformat(timespec="seconds"))
    run.corpus_before = corpus()

    say("")
    say("=" * 74)
    say("  A fault will be injected when you press enter.")
    say("  You are NOT told which one. You may use the target, Prometheus at")
    say("  :9091, the logs and the repository - anything except Kavach.")
    say("=" * 74)
    ask("  press enter to inject> ")

    t0 = time.time()
    try:
        fault.inject()
        say(f"  INJECTED at t=0. Clock running. ({operator})")
        say("")

        ask("  [1/3] press enter the moment you can tell something is WRONG> ")
        run.mttd_s = round(time.time() - t0, 1)
        say(f"        MTTD {run.mttd_s}s")

        run.operator_diagnosis = ask(
            "  [2/3] name the CAUSE in one line> ")
        run.operator_action = ask(
            "        name the CHANGE you intend to make> ")
        run.diagnosis_s = round(time.time() - t0, 1)
        say(f"        diagnosis at {run.diagnosis_s}s")

        say("")
        say("  Now fix it. Press enter when you believe it is resolved, or")
        say("  type 'give up' if you want to stop.")
        answer = ask("  [3/3] resolved?> ")
        run.declared_resolved_at_s = round(time.time() - t0, 1)
        if answer.lower() in ("give up", "giveup", "q", "quit"):
            run.gave_up = True
            say(f"        gave up at {run.declared_resolved_at_s}s")
        else:
            say(f"        declared resolved at {run.declared_resolved_at_s}s; "
                f"verifying with the real fast set...")
            r = fast.run(client, FAST_SET, check_health=True)
            run.pass_rate_at_declaration = r.pass_rate
            run.verified = r.passed
            if r.passed:
                run.resolve_s = round(time.time() - t0, 1)
                say(f"        VERIFIED. MTTR {run.resolve_s}s")
            else:
                # The asymmetry that makes this honest. A human declaring
                # victory over a broken system has produced the same false
                # recovery the gate exists to prevent, and recording it as a
                # longer time would hide it.
                run.false_recovery = True
                say(f"        NOT RESOLVED - fast set {r.pass_rate:.0%}. "
                    f"Recorded as a FALSE RECOVERY, not as a slower fix.")
                for c in r.cases:
                    say(f"          {c.case_id} "
                        f"{'PASS' if c.passed else 'FAIL'} "
                        f"keyword={c.keyword_present} grounded={c.sources_block}")
    finally:
        say("")
        say(f"  the fault was {fault_class}. Reverting whatever is left.")
        try:
            fault.revert()
        except Exception as exc:  # pragma: no cover - teardown only
            run.notes = f"revert failed: {exc}"
            say(f"  REVERT FAILED: {exc}")
        run.corpus_after = corpus()

    verdict = ask(f"  was '{run.operator_diagnosis}' the right cause "
                  f"for {fault_class}? [y/n/skip]> ").lower()
    if verdict.startswith("y"):
        run.diagnosis_correct = True
    elif verdict.startswith("n"):
        run.diagnosis_correct = False
    run.notes = (run.notes + " " + ask("  any note for the record> ")).strip()
    return run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--operator", required=True,
                    help="who is being timed; recorded per run")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--seed", type=int, default=None,
                    help="only for rehearsing the script; leave unset for real")
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports" / "human-baseline.json"))
    args = ap.parse_args()

    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))
    rng = random.Random(args.seed)

    say("=" * 74)
    say("HUMAN BASELINE")
    say("=" * 74)
    say(f"  operator           {args.operator}")
    say(f"  runs               {args.runs}")
    say("  protocol           docs/HUMAN_BASELINE.md")

    # A session on a drifted corpus measures the drift, not the operator.
    live = corpus()
    say(f"  corpus             {live}")
    if live != EXPECTED_CORPUS:
        say(f"  REFUSING: corpus is {live}, expected {EXPECTED_CORPUS}. "
            f"PRD.md section 12 records two silent drifts; a baseline taken "
            f"on a drifted corpus is not comparable to anything.")
        return 1
    if not client.is_healthy():
        say("  REFUSING: the target is not healthy before injection.")
        return 1
    pre = fast.run(client, FAST_SET, check_health=False)
    say(f"  fast set at start  {pre.pass_rate:.0%}")
    if not pre.passed:
        say("  REFUSING: the fast set does not pass on the clean system, so a "
            "post-fix verification would be meaningless.")
        return 1

    runs: list[Run] = []
    for i in range(1, args.runs + 1):
        say("")
        say(f"########## RUN {i} of {args.runs} ##########")
        runs.append(one_run(client, args.operator, rng))

    say("")
    say("=" * 74)
    say("SESSION SUMMARY")
    say("=" * 74)
    for r in runs:
        mttr = ("gave up" if r.gave_up
                else "FALSE RECOVERY" if r.false_recovery
                else f"{r.resolve_s}s")
        say(f"  {r.fault_class}  MTTD {r.mttd_s}s  diagnosis {r.diagnosis_s}s  "
            f"MTTR {mttr}  correct={r.diagnosis_correct}")
    resolved = [r for r in runs if r.verified]
    say("")
    say(f"  verified resolutions {len(resolved)}/{len(runs)}")
    say(f"  false recoveries     {sum(1 for r in runs if r.false_recovery)}")
    say(f"  gave up              {sum(1 for r in runs if r.gave_up)}")
    if resolved:
        times = sorted(r.resolve_s or 0 for r in resolved)
        mid = times[len(times) // 2]
        say(f"  median MTTR          {mid}s  (raw: {times})")
    say("")
    say("  Report PER FAULT CLASS, not pooled - see docs/HUMAN_BASELINE.md "
        "section 6. F01 is trivial for a human and F07/F08 are not, and that "
        "contrast is the result.")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if out.is_file():
        try:
            existing = json.loads(out.read_text(encoding="utf-8")).get("runs", [])
        except Exception:
            existing = []
    out.write_text(json.dumps({
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "protocol": "docs/HUMAN_BASELINE.md",
        "runs": existing + [asdict(r) for r in runs],
    }, indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  appended to {out}  ({len(existing) + len(runs)} runs total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
