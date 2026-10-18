"""Kavach's own MTTD/MTTR per fault class, and the non-LLM comparison.

TWO OF THE FOUR BASELINES `PRD.md` §10.3 ASKS FOR, NEITHER NEEDING A HUMAN

**Kavach's side of the human comparison.** `docs/HUMAN_BASELINE.md` times a
person on these same four classes. This times Kavach on them, under the same
definition of resolved - the real fast set passing - so the two numbers are
comparable rather than merely adjacent.

**The non-LLM baseline.** §10.3 calls this one irrecoverable: *"P2's
hardcoded signal→action mapping, measured before the LLM RCA engine
existed. This number cannot be recovered later."* It was recorded for `F06`
alone. It is in fact still recoverable for every class, because `rca=false`
runs the identical loop with the diagnosis stage switched off, so each class
can be run both ways on the same injection shape and the LLM's contribution
read off the difference. Three classes were added after that note was
written and none of them has the number.

WHAT IS AND IS NOT INCLUDED IN THE TIME
The clock starts when the injector writes and stops when the loop reports
RESOLVED, which requires the fast set to pass. Two things are measured
separately rather than hidden inside that total:

  * **warm-up** - driven load some classes need before their signal crosses
    a threshold. F08 and F07 need none; F06 and F01 read windowed metrics.
    A human does not need this, so folding it into Kavach's MTTR would
    flatter the human comparison in Kavach's favour. It is reported apart.
  * **approval wait** - this harness approves instantly. A real operator
    does not. Machine time is what is reported; the approval pause is a
    property of the operator, not of Kavach, and `PRD.md` §10's MTTR target
    is about the machine.

So the headline number here is DECIDE-AND-ACT time, honestly bounded, and
the report should say so rather than quoting it as wall-clock recovery.

    uv run --project apps/control-plane python -I harness/kavach_baseline.py
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import statistics
import sys
import time
import urllib.error
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
from kavach.detection.retrieval_collapse import QUERIES as F06_QUERIES  # noqa: E402
from kavach.detection.retrieval_collapse import Thresholds  # noqa: E402
from kavach.onboarding.manifest import load as load_manifest  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"
API = "http://127.0.0.1:8080"
TARGET = "http://127.0.0.1:8000"
PROM = "http://127.0.0.1:9091"
CLASSES = ["F01", "F06", "F07", "F08"]


def say(m: str = "") -> None:
    print(m, flush=True)


def api(path: str, method: str = "GET", body: dict[str, Any] | None = None,
        timeout: int = 120) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as exc:
        return 0, str(exc)


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


def wait_terminal(incident_id: str, limit_s: int = 900) -> dict[str, Any]:
    terminal = {"NO_FAULT", "AWAITING_APPROVAL", "RESOLVED", "ESCALATED"}
    t0 = time.time()
    while time.time() - t0 < limit_s:
        code, inc = api("/v1/incidents/" + incident_id)
        if code == 200 and inc.get("status") in terminal:
            return dict(inc)
        time.sleep(3)
    raise TimeoutError(f"{incident_id} never reached a terminal status")


def drive_until_detectable(client: TargetClient, max_rounds: int = 6) -> float:
    """Seconds of driven load before the grounding signal crosses the floor.

    Only F06 needs this. Reported separately from MTTR because a human does
    not need a metric window to fill before they can see a broken answer, so
    charging it to Kavach would distort the comparison in the human's favour.
    """
    floor = Thresholds().kept_chunks_floor
    t0 = time.time()
    for _ in range(max_rounds):
        fast.run(client, FAST_SET, check_health=False)
        v = promql(F06_QUERIES["kept_chunks_mean"])
        if v is not None and v < floor:
            return round(time.time() - t0, 1)
    return round(time.time() - t0, 1)


ERROR_RATIO = (
    '(sum(rate(ragapp_llm_requests_total{outcome!="ok"}[2m])) or vector(0)) '
    "/ clamp_min(sum(rate(ragapp_llm_requests_total[2m])), 1e-9)"
)


def drain(client: TargetClient, max_rounds: int = 40) -> tuple[bool, float]:
    """Drive healthy traffic until the LOOP ITSELF reports NO_FAULT.

    WHY THIS EXISTS, AND IT IS A CORRECTION
    The first version of this harness ran four classes back to back with no
    gap. Every run after the first inherited the previous fault's samples,
    two detectors then claimed at once, and `run_all()` correctly refused to
    choose - so F07 and F08 came back ESCALATED and looked broken when they
    had each passed their own live gate the same day. That is the cross-fault
    contamination `PRD.md` section 12 records three times, walked into by a
    harness written hours after fixing another instance of it.

    IT READS THE METRICS, NOT THE LOOP, AND THAT IS THE SECOND CORRECTION
    The first drain asked the loop and waited for NO_FAULT. That cannot work,
    and the reason is structural rather than a bug: EVERY detector gates on
    the fast set failing, by design - `retrieval_collapse.py` says so
    explicitly, refusing to repair "against a system that is working" however
    degraded the window looks. So on a healthy system the loop answers
    NO_FAULT whatever its windows still hold, and a drain built on that
    answer is incapable of detecting the contamination it exists to remove.
    It reported a clean system eight times in a row and every measurement
    after the first was still dirty.

    So this reads the two grounding signals directly and waits for both to be
    healthy. `empty_context_ratio` is the slow one: it is still `[10m]`
    because it mirrors a declared `window_s: 600` in the target manifest,
    which `kept_chunks_mean` does not, so shortening it would be a spec
    change rather than a detector-local fix.
    """
    t = Thresholds()
    t0 = time.time()
    for _ in range(max_rounds):
        fast.run(client, FAST_SET, check_health=False)
        kept = promql(F06_QUERIES["kept_chunks_mean"])
        empty = promql(F06_QUERIES["empty_context_ratio"])
        kept_ok = kept is None or kept >= t.kept_chunks_floor
        empty_ok = empty is None or empty <= t.empty_context_ceiling
        if kept_ok and empty_ok:
            return True, round(time.time() - t0, 1)
    return False, round(time.time() - t0, 1)


def warm_up_f01(client: TargetClient, max_rounds: int = 6) -> float:
    """F01 reads a two-minute error ratio, so it needs load too.

    The first version warmed up F06 only, so F01 was measured before its own
    signal existed: at 15s the error ratio had not crossed, F06 claimed on the
    collapsed grounding an outage also produces, and the run recorded F06 for
    an F01 fault.
    """
    t0 = time.time()
    for _ in range(max_rounds):
        fast.run(client, FAST_SET, check_health=False)
        v = promql(ERROR_RATIO)
        if v is not None and v >= 0.50:
            return round(time.time() - t0, 1)
    return round(time.time() - t0, 1)


@dataclass
class Measurement:
    fault_class: str
    rca: bool
    drained: bool = True
    drain_s: float = 0.0
    warmup_s: float = 0.0
    detect_s: float | None = None
    decide_s: float | None = None
    resolve_s: float | None = None
    # The DETERMINISTIC detector's verdict. `incident.fault_class` is this,
    # in both arms, which is the trap below.
    diagnosed: str = ""
    # The LLM's OWN answer, read from the RCA stage. Recorded separately
    # because the first version of this harness scored the LLM arm off
    # `incident.fault_class` - the deterministic verdict - and so credited
    # the model with 4/4 on a run where it had said F06 for an F07 at 0.95
    # confidence and been rejected. A comparison that reads the same field
    # for both arms is not a comparison.
    llm_diagnosed: str = ""
    llm_confidence: float | None = None
    llm_approved: bool | None = None
    llm_correct: bool | None = None
    correct: bool = False
    status: str = ""
    action: str = ""
    # Whether the target really went back to how this measurement found it.
    # A run that leaves the system dirty poisons every run after it, so this
    # is recorded per measurement rather than hoped for.
    # Set when permit() refused for a reason that is about the HARNESS
    # rather than the fault - the blast-radius limiter counting this run's
    # own earlier incidents. A measurement blocked by rate limiting measured
    # the rate limiter, not the thing it claims to.
    blocked_by_safety: str = ""
    state_clean: bool = True
    restored: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def line(self) -> str:
        mode = "LLM " if self.rca else "det "
        r = "-" if self.resolve_s is None else f"{self.resolve_s:6.1f}s"
        d = "-" if self.decide_s is None else f"{self.decide_s:6.1f}s"
        return (f"  {self.fault_class} {mode} drain {self.drain_s:5.1f}s "
                f"warmup {self.warmup_s:5.1f}s  "
                f"decide {d}  resolve {r}  "
                f"{self.diagnosed or '-':<4} "
                f"{'OK ' if self.correct else 'xx '} {self.status}"
                + (f"  {self.error[:60]}" if self.error else ""))


def measure(client: TargetClient, fault_class: str, rca: bool) -> Measurement:
    m = Measurement(fault_class=fault_class, rca=rca)
    # Before anything: the previous class's samples must be out of the
    # windows, or two detectors claim and the loop correctly refuses.
    m.drained, m.drain_s = drain(client)
    if not m.drained:
        m.error = ("the system never went quiet before injection; measuring "
                   "on a contaminated window would measure the contamination")
        return m

    # THE FULL PRE-STATE, CAPTURED HERE RATHER THAN TRUSTED TO THE INJECTOR.
    # This replaces a restore that read
    # `fault.record.pre_state["settings"]["llm_base_url"]` - a key F01's
    # injector never populates, so after a successful switch_llm_endpoint the
    # restore silently did nothing and the target stayed on the BACKUP
    # listener. Every later F01 injection then disabled a primary the
    # application was no longer using and correctly produced NO_FAULT, and
    # every later measurement of ANY class ran against a non-baseline system.
    # It cost two whole runs, and I made the same mistake in two files.
    #
    # So the harness no longer asks the injector what the pre-state was. It
    # reads it, restores it, and VERIFIES the restore - a measurement that
    # silently starts from the wrong state is worse than one that fails.
    pre_settings = dict(client.settings())
    pre_prompts = dict((client.config().get("prompt_version") or {}).get("files") or {})

    fault = build(fault_class, client)
    try:
        fault.inject()
        t0 = time.time()
        if fault_class == "F06":
            m.warmup_s = drive_until_detectable(client)
        elif fault_class == "F01":
            m.warmup_s = warm_up_f01(client)

        code, started = api(f"/v1/loop/run?rca={'true' if rca else 'false'}",
                            "POST")
        if code != 202:
            m.error = f"loop/run {code}: {started}"
            return m
        inc = wait_terminal(str(started["incident_id"]))
        m.decide_s = round(time.time() - t0, 1)
        m.status = str(inc.get("status", ""))
        m.diagnosed = str(inc.get("fault_class") or "")
        m.correct = m.diagnosed == fault_class
        rca_stage = inc.get("rca") or {}
        diag = rca_stage.get("diagnosis") or {}
        if diag:
            m.llm_diagnosed = str(diag.get("fault_class") or "")
            conf = diag.get("confidence")
            m.llm_confidence = float(conf) if conf is not None else None
            m.llm_approved = bool(rca_stage.get("approved"))
            m.llm_correct = m.llm_diagnosed == fault_class
        m.action = str(inc.get("planned_action") or "")

        if m.status == "AWAITING_APPROVAL":
            # Approved instantly. A real operator would not be; that pause is
            # a property of the operator and is excluded deliberately.
            code, second = api(
                f"/v1/incidents/{started['incident_id']}/approve", "POST")
            if code != 202:
                m.error = f"approve {code}: {second}"
                return m
            inc = wait_terminal(str(second["incident_id"]))
            m.status = str(inc.get("status", ""))
        if m.status == "RESOLVED":
            m.resolve_s = round(time.time() - t0, 1)
        elif "blast_radius" in str(inc.get("escalation_reason") or ""):
            m.blocked_by_safety = str(inc.get("escalation_reason"))[:160]
    except Exception as exc:
        m.error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            fault.revert()
        except Exception as exc:  # pragma: no cover - teardown only
            m.error = (m.error + f" | revert failed: {exc}").strip(" |")
        # Restore every setting the repair or the injector moved, from the
        # pre-state THIS function captured, then check it actually took.
        with contextlib.suppress(Exception):
            live = client.settings()
            drifted = {k: v for k, v in pre_settings.items()
                       if k in live and live[k] != v}
            if drifted:
                client.apply_settings(drifted)
                m.restored = drifted
            after = client.settings()
            after_prompts = dict(
                (client.config().get("prompt_version") or {}).get("files") or {})
            m.state_clean = (after == pre_settings
                             and after_prompts == pre_prompts)
            if not m.state_clean:
                still = {k: (pre_settings.get(k), after.get(k))
                         for k in pre_settings
                         if after.get(k) != pre_settings.get(k)}
                m.error = (m.error
                           + f" | STATE NOT RESTORED: {still}").strip(" |")
    return m


@dataclass
class Report:
    at: str = ""
    measurements: list[Measurement] = field(default_factory=list)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", default=",".join(CLASSES))
    ap.add_argument("--arms", default="det,llm",
                    help="which arms to run. permit()'s blast-radius limiter "
                         "allows 5 incidents an hour, and each arm is one "
                         "incident per class, so 4 classes x 2 arms trips it "
                         "and the later arm measures the limiter instead of "
                         "the LLM. Run one arm per session.")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports" / "kavach-baseline.json"))
    args = ap.parse_args()

    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))
    classes = [c.strip() for c in args.classes.split(",") if c.strip()]

    say("=" * 78)
    say("KAVACH BASELINE: MTTR per fault class, LLM vs deterministic")
    say("=" * 78)

    _, mode = api("/v1/mode")
    start_mode = mode.get("mode") if isinstance(mode, dict) else None
    say(f"  mode at start      {start_mode}")
    if start_mode != "APPROVAL":
        code, _ = api("/v1/mode", "PUT", {"mode": "APPROVAL"})
        say(f"  switched to APPROVAL for the run ({code}); "
            f"{start_mode} restored at the end")

    pre_corpus = corpus()
    say(f"  corpus             {pre_corpus}")
    pre = fast.run(client, FAST_SET, check_health=False)
    say(f"  fast set at start  {pre.pass_rate:.0%}")
    if not pre.passed:
        say("  REFUSING: the fast set must pass on the clean system, or "
            "'resolved' means nothing.")
        return 1
    say("")

    rep = Report(at=datetime.now(UTC).isoformat(timespec="seconds"))
    try:
        for rep_no in range(1, args.reps + 1):
            arms = [a.strip() for a in args.arms.split(",") if a.strip()]
            for fc in classes:
                for rca in [a == "llm" for a in arms]:
                    m = measure(client, fc, rca)
                    rep.measurements.append(m)
                    say(m.line())
            if args.reps > 1:
                say(f"  --- repetition {rep_no} done ---")
    finally:
        if start_mode and start_mode != "APPROVAL":
            api("/v1/mode", "PUT", {"mode": start_mode})
            say(f"\n  restored mode to {start_mode}")

    say("")
    say("=" * 78)
    say("RESULT  (decide-and-act time; warm-up and approval wait excluded)")
    say("=" * 78)
    say(f"  {'class':<6} {'det resolve':>12} {'LLM resolve':>12} "
        f"{'det right':>10} {'LLM right':>10}")
    for fc in classes:
        det = [m for m in rep.measurements if m.fault_class == fc and not m.rca]
        llm = [m for m in rep.measurements if m.fault_class == fc and m.rca]

        def med(ms: list[Measurement]) -> str:
            vals = [m.resolve_s for m in ms if m.resolve_s is not None]
            return f"{statistics.median(vals):.1f}s" if vals else "none"

        def right(ms: list[Measurement]) -> str:
            """The LLM arm is scored on the LLM's OWN answer, not on the
            deterministic verdict that sits in the same incident."""
            if not ms:
                return "-"
            if ms[0].rca:
                scored = [m for m in ms if m.llm_correct is not None]
                if scored:
                    return f"{sum(1 for m in scored if m.llm_correct)}/{len(scored)}"
            return f"{sum(1 for m in ms if m.correct)}/{len(ms)}"

        say(f"  {fc:<6} {med(det):>12} {med(llm):>12} "
            f"{right(det):>10} {right(llm):>10}")

    blocked = [m for m in rep.measurements if m.blocked_by_safety]
    if blocked:
        say("")
        say(f"  {len(blocked)} measurement(s) were REFUSED BY permit()'s "
            f"blast-radius limiter, not by anything about the fault:")
        for m in blocked:
            say(f"    {m.fault_class} {'LLM' if m.rca else 'det'}: "
                f"{m.blocked_by_safety}")
        say("  Those timings measure the limiter. Re-run that arm in a "
            "separate session (--arms), or wait out the hour.")

    resolved = [m for m in rep.measurements if m.resolve_s is not None]
    if resolved:
        times = sorted(m.resolve_s or 0 for m in resolved)
        say("")
        say(f"  resolved           {len(resolved)}/{len(rep.measurements)}")
        say(f"  median resolve     {statistics.median(times):.1f}s   "
            f"(PRD section 10 target: < 180s)")
    rejected = [m for m in rep.measurements
                if m.llm_approved is False and m.llm_diagnosed]
    if rejected:
        say("")
        say("  CROSS-CHECK REJECTIONS (the architecture's case, live):")
        for m in rejected:
            say(f"    {m.fault_class}: the model said {m.llm_diagnosed} at "
                f"{m.llm_confidence} confidence; deterministic detection said "
                f"{m.diagnosed}. Refused, nothing written.")

    say("")
    say("  The LLM column is the non-LLM comparison PRD section 10.3 calls "
        "irrecoverable. It is recoverable: rca=false runs the same loop with "
        "the diagnosis stage off. Where the two columns agree, the LLM is "
        "costing time and buying nothing on that class.")
    say(f"  corpus {pre_corpus} -> {corpus()}")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"at": rep.at, "measurements": [asdict(m) for m in rep.measurements]},
        indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  artifact {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
