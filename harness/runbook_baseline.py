"""The runbook baseline: what a written manual procedure costs.

WHAT THIS IS, AND WHAT IT IS EMPHATICALLY NOT
This is **not a human baseline**. No person is involved and no number it
produces may be reported as one. It is a *scripted procedure*: the documented
diagnostic runbook for this system, executed as code and timed.

`PRD.md` §10.3 asks for a human baseline to give MTTR a denominator. That
requires a person and `docs/HUMAN_BASELINE.md` is the protocol for it. This
file exists because a runbook baseline answers a *different and sharper*
question that needs no people at all:

    What does the fully-anticipated manual path cost, and what does
    Kavach buy over it?

WHY THIS IS THE MORE INTERESTING COMPARISON
A runbook can only repair faults somebody already thought of. This one checks
four things in a fixed order because four fault classes exist; it will score
near-perfectly on them and would score **zero** on a fifth. Kavach's claim is
that it diagnoses from evidence rather than from a checklist, so the honest
comparison is not "who is faster" - the runbook will usually win on speed,
because looking up a known answer is cheap - but "what happens when the fault
is not on the list".

Report it that way. A runbook beating Kavach on the four faults it was
written for is the expected result and is not a finding; a runbook being
useless on anything else is the finding.

THE PROCEDURE, IN THE ORDER A WRITTEN RUNBOOK WOULD GIVE IT
  1. Is the model endpoint reachable?          -> F01
  2. Has any runtime setting left its baseline? -> F06 (rerank) / F08 (other)
  3. Has any prompt file left its baseline?     -> F07
  4. Nothing moved                              -> UNKNOWN, escalate

Each step is a comparison against the SAME captured baseline Kavach uses, so
neither side gets evidence the other lacks. Step 4 is why the honest answer
to an unanticipated fault is an escalation rather than a guess - a runbook
that guessed would be worse than one that stops.

ZERO THINKING TIME IS DELIBERATE AND MUST BE STATED
A person reads, hesitates, mistypes and re-reads. This script does none of
that, so its timings are a **lower bound on the manual path** - the best case
a perfectly-prepared operator could achieve, not a realistic one. Quoting it
as "the manual baseline" without that caveat would overstate how good manual
response is, which happens to be the direction that flatters Kavach least, so
it is the safe error - but it is still an error.

    uv run --project apps/control-plane python -I harness/runbook_baseline.py --runs 8
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
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

from harness.faults.base import Fault  # noqa: E402
from harness.faults.f01_endpoint_outage import F01EndpointOutage  # noqa: E402
from harness.faults.f06_retrieval_collapse import F06RetrievalCollapse  # noqa: E402
from harness.faults.f07_prompt_regression import F07PromptRegression  # noqa: E402
from harness.faults.f08_config_regression import F08ConfigRegression  # noqa: E402
from kavach.api.runner import newest_baseline_doc  # noqa: E402
from kavach.config import get_settings  # noqa: E402
from kavach.onboarding.manifest import load as load_manifest  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"
TARGET = "http://127.0.0.1:8000"
PROM = "http://127.0.0.1:9091"
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


def build(fault_class: str, client: TargetClient) -> Fault:
    if fault_class == "F01":
        return F01EndpointOutage(corpus_probe=corpus)
    if fault_class == "F06":
        return F06RetrievalCollapse(client, corpus_probe=corpus)
    if fault_class == "F07":
        return F07PromptRegression(client, prompts_dir(), corpus_probe=corpus)
    return F08ConfigRegression(client, corpus_probe=corpus)


@dataclass
class RunbookResult:
    fault_class: str
    detected_s: float | None = None
    diagnosed: str = ""
    # What the runbook actually saw. Kept rather than discarded: when a run
    # diagnoses wrongly this is the only record of WHY, and a baseline whose
    # failures cannot be explained is not worth much.
    signal: str = ""
    diagnosed_s: float | None = None
    correct: bool = False
    fix_applied: str = ""
    resolved_s: float | None = None
    verified: bool = False
    false_recovery: bool = False
    error: str = ""


def detect(client: TargetClient) -> bool:
    """Step 0: is anything wrong? The same fast set Kavach is held to."""
    return not fast.run(client, FAST_SET, check_health=False).passed


def diagnose(
    client: TargetClient, baseline: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """The written runbook, in order. Returns (class, what it found).

    Reads exactly what a documented procedure would tell an operator to read,
    and compares against the SAME baseline capture Kavach compares against.
    """
    cfg = client.config()

    # 1. endpoint reachable?
    try:
        health = client.health()
        if not (health.get("dependencies", {}).get("ollama", {}).get("ok", True)):
            return "F01", {"signal": "healthz reports ollama unreachable"}
    except Exception:
        return "F01", {"signal": "healthz unreachable"}

    # 2. runtime settings against the captured baseline
    base_settings = dict(baseline.get("settings") or {})
    live_settings = dict(cfg.get("settings") or {})
    drifted = {k: {"baseline": base_settings[k], "live": live_settings[k]}
               for k in base_settings
               if k in live_settings and live_settings[k] != base_settings[k]}
    if "llm_base_url" in drifted:
        return "F01", {"signal": "llm_base_url moved", "drift": drifted}
    if "rerank_threshold" in drifted:
        return "F06", {"signal": "rerank_threshold moved", "drift": drifted}
    if drifted:
        return "F08", {"signal": "a setting moved", "drift": drifted}

    # 3. prompt files against the captured baseline
    base_prompts = dict((baseline.get("prompt_version") or {}).get("files") or {})
    live_prompts = dict((cfg.get("prompt_version") or {}).get("files") or {})
    moved = sorted(n for n, d in live_prompts.items()
                   if n in base_prompts and base_prompts[n] != d)
    if moved:
        return "F07", {"signal": "prompt digest moved", "files": moved}

    # 4. nothing on the checklist moved
    return "UNKNOWN", {"signal": "nothing the runbook knows how to check moved"}


def repair(
    fault_class: str, client: TargetClient, baseline: dict[str, Any],
) -> str:
    """The documented fix for each class. Restores from the baseline capture."""
    base_settings = dict(baseline.get("settings") or {})
    if fault_class == "F01":
        manifest = load_manifest(Path(get_settings().target_path) / "kavach.yaml")
        backup = manifest.llm.paths.backup if manifest.llm and manifest.llm.paths else None
        if not backup:
            return "no backup endpoint declared"
        client.apply_settings({"llm_base_url": backup})
        return f"llm_base_url -> {backup}"
    if fault_class in ("F06", "F08"):
        live = client.settings()
        restore = {k: v for k, v in base_settings.items()
                   if k in live and live[k] != v}
        if not restore:
            return "nothing to restore"
        client.apply_settings(restore)
        return f"restored {restore}"
    if fault_class == "F07":
        contents = dict(baseline.get("prompt_contents") or {})
        if not contents:
            return "baseline holds no prompt text"
        d = prompts_dir()
        written = []
        for name, text in contents.items():
            path = d / name
            if path.is_file() and path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8", newline="")
                written.append(name)
        return f"restored {written}" if written else "prompts already correct"
    return "no documented fix"


def one_run(client: TargetClient, fault_class: str,
            baseline: dict[str, Any]) -> RunbookResult:
    r = RunbookResult(fault_class=fault_class)
    fault = build(fault_class, client)
    try:
        fault.inject()
        t0 = time.time()

        if detect(client):
            r.detected_s = round(time.time() - t0, 1)
        r.diagnosed, found = diagnose(client, baseline)
        r.signal = str(found.get("signal", ""))
        r.diagnosed_s = round(time.time() - t0, 1)
        r.correct = r.diagnosed == fault_class

        if r.correct:
            r.fix_applied = repair(r.diagnosed, client, baseline)
            after = fast.run(client, FAST_SET, check_health=False)
            r.verified = after.passed
            if after.passed:
                r.resolved_s = round(time.time() - t0, 1)
            else:
                r.false_recovery = True
        else:
            r.fix_applied = "none - runbook did not identify the fault"
    except Exception as exc:
        r.error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            fault.revert()
            if fault_class == "F01":
                prior = (baseline.get("settings") or {}).get("llm_base_url")
                if prior:
                    client.apply_settings({"llm_base_url": prior})
        except Exception as exc:
            r.error = (r.error + f" | revert failed: {exc}").strip(" |")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=8)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports" / "runbook-baseline.json"))
    args = ap.parse_args()

    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))
    settings = get_settings()
    baseline, baseline_name = newest_baseline_doc(
        settings.baselines_dir(), settings.target_project)
    rng = random.Random(args.seed)
    classes = ["F01", "F06", "F07", "F08"]

    say("=" * 78)
    say("RUNBOOK BASELINE - a scripted procedure, NOT a human baseline")
    say("=" * 78)
    say(f"  baseline capture   {baseline_name}")
    say(f"  corpus             {corpus()}")
    if corpus() != EXPECTED_CORPUS:
        say("  REFUSING: corpus has drifted; results would measure the drift.")
        return 1
    if not fast.run(client, FAST_SET, check_health=False).passed:
        say("  REFUSING: the fast set must pass before injecting.")
        return 1
    say("")

    results: list[RunbookResult] = []
    for i in range(1, args.runs + 1):
        fc = classes[(i - 1) % len(classes)] if args.seed is None else rng.choice(classes)
        r = one_run(client, fc, baseline)
        results.append(r)
        say(f"  run {i:2} {fc}  detect={r.detected_s}s  "
            f"diagnose={r.diagnosed}({'ok' if r.correct else 'WRONG'}) "
            f"{r.diagnosed_s}s  resolve="
            f"{r.resolved_s if r.resolved_s is not None else 'none'}s  "
            f"{r.fix_applied[:48]}"
            + (f"  {r.error[:50]}" if r.error else ""))

    say("")
    say("=" * 78)
    say("RESULT")
    say("=" * 78)
    correct = sum(1 for r in results if r.correct)
    resolved = sum(1 for r in results if r.verified)
    say(f"  diagnosed correctly  {correct}/{len(results)}")
    say(f"  verified resolved    {resolved}/{len(results)}")
    say(f"  false recoveries     {sum(1 for r in results if r.false_recovery)}")
    times = [r.resolved_s for r in results if r.resolved_s is not None]
    if times:
        say(f"  median resolve       {statistics.median(times):.1f}s   "
            f"(raw: {sorted(times)})")
    say("")
    for fc in classes:
        rs = [r for r in results if r.fault_class == fc]
        if rs:
            ts = [r.resolved_s for r in rs if r.resolved_s is not None]
            say(f"  {fc}  correct {sum(1 for r in rs if r.correct)}/{len(rs)}  "
                f"resolve {f'{statistics.median(ts):.1f}s' if ts else 'none'}")

    say("")
    say("  READ THIS BEFORE QUOTING ANY NUMBER ABOVE:")
    say("  * This is NOT a human baseline. No person was involved. It is the")
    say("    documented runbook executed as code, with zero thinking time, so")
    say("    it is a LOWER BOUND on the manual path - the best case a")
    say("    perfectly-prepared operator could reach, not a realistic one.")
    say("  * A high score here is EXPECTED and is not a finding. The runbook")
    say("    checks exactly the four faults that exist because four exist. It")
    say("    would score zero on a fifth, which is the actual comparison with")
    say("    Kavach: a checklist repairs what was anticipated, a diagnosis")
    say("    engine is supposed to handle what was not.")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "what_this_is": "scripted runbook procedure, NOT a human baseline",
        "baseline": baseline_name,
        "runs": [asdict(r) for r in results],
    }, indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  artifact {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
