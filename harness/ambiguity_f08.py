"""Does a second anomaly in the frame trigger the F06 attractor? One variable.

THE QUESTION, AND WHY IT IS WORTH AN HOUR
Across four bench runs the model gave a wrong class 11 times in 80 injections
and **all eleven were F06** (`REPORT_DRAFT.md` §4.2). The report reads that as
"under-determined evidence collapses to F06", which was an interpretation with
nothing isolating it.

On 2026-11-02 a demo rehearsal supplied a hint. `make scenario` act 2 injects
F08 alone, but act 1 ninety seconds earlier is an endpoint outage and
`llm_error_ratio` is a `[2m]` rate, so act 2 diagnosed against a frame holding
**0.2697 against its own stated "expected < 0.20"** - the real config drift
plus one phantom anomaly - while every F06 signal in that frame was healthy.
The model answered F06 twice in three tries, against 19/20 correct on clean
frames. Suggestive, but n=3 and the contrast was bench-versus-scenario, which
differ in more than the error ratio. Confounded.

This harness removes the confound. Same injector, same evidence collector,
same model, same number of repetitions, same process - and exactly one
difference between the arms:

    arm A (control)       llm_error_ratio at ~0.0, the frame's healthy value
    arm B (contaminated)  llm_error_ratio in (0.20, 0.50)

WHY THAT BAND AND NOT A BIGGER NUMBER
Above 0.50 the F01 detector claims the incident - "half of all calls failing
is not noise" - and `run_all` would return F01, so the arm would be measuring
a different fault rather than an ambiguous F08. Below 0.20 the frame states
the value as healthy and there is no second anomaly. The window is therefore
(0.20, 0.50), which is exactly where the accident landed.

HOW THE DOSE IS SET, AND WHY IT IS MEASURED RATHER THAN AIMED AT
Toxiproxy's primary listener goes down, N fast-set passes drive real LLM
errors, the listener comes back, and the frame is collected immediately. More
passes means more failing samples in the `[2m]` window means a higher ratio.

The first version aimed at a target ratio instead and caught the value
descending through a band. That sweep was invalid: `build_frame` runs a
fast-set pass of its own before collecting, which diluted the ratio by
0.065-0.094 between the catch and the frame, and one arm reached the model at
**0.1744 - under the 0.20 ceiling the frame itself states**, carrying no
contamination while being reported as a dose of 0.25. Two further arms could
not be reached at all, because the descent starts near 0.27.

So the dose is whatever the FRAME carries (`EV-M06`), recorded per arm. It is
monotonic in the number of outage passes and immune to the dilution, because
the dilution now applies inside every arm equally.

THREE VALIDITY CONDITIONS, ALL ASSERTED RATHER THAN HOPED FOR
1. Deterministic detection must still say **F08**. If it says F01, the arm is
   not an ambiguous F08 and the comparison is void.
2. `EV-C04` (`max_tokens`) must be marked `DIFFERS`, or the frame carries no
   evidence of the injected fault at all.
3. **The frame's error ratio must actually be abnormal on a dosed arm, and
   actually clean on the control.** This one was missing and its absence is
   what invalidated the first sweep: conditions 1 and 2 prove the FAULT is in
   the frame and neither proves the CONTAMINANT is. A dosed arm whose frame
   is clean is a second control, and counting it as a dose is how a null
   result gets reported as a dose-response curve.

NO LOOP RUNS, SO THIS COSTS NO BLAST-RADIUS BUDGET
Like `rca_f08_live.py`, this collects the frame ONCE per arm and diagnoses
against that fixed frame N times. Nothing is repaired, so `permit()` is never
asked and the five-incidents-an-hour limiter is untouched. Twenty diagnoses
cost zero incident starts, which is the only reason this fits in an hour.

Fixing the frame per arm is also what makes it a test of the MODEL. Re-collecting
per repetition would let the metric windows move underneath the question.

    python -I harness/ambiguity_f08.py --model qwen2.5:7b-instruct --reps 10
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "control-plane")]

from harness.faults.f01_endpoint_outage import (  # noqa: E402
    PRIMARY,
    F01EndpointOutage,
)
from harness.faults.f08_config_regression import (  # noqa: E402
    SETTING,
    F08ConfigRegression,
)
from kavach.detection import base as det  # noqa: E402
from kavach.detection import catalogue  # noqa: E402, F401 - registers detectors
from kavach.llm.client import OllamaClient  # noqa: E402
from kavach.rca import evidence as ev  # noqa: E402
from kavach.rca.engine import diagnose  # noqa: E402
from kavach.rca.evidence import FRAME_ERROR_RATIO_CEILING  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = ROOT / "apps" / "control-plane" / "kavach" / "verification" / "fast_set.yaml"

TARGET = "http://127.0.0.1:8000"
PROM = "http://127.0.0.1:9091"
SERVICES = {"backend", "db", "frontend", "toxiproxy", "prometheus"}
CONFIDENCE_THRESHOLD = 0.75

ERROR_RATIO = (
    '(sum(rate(ragapp_llm_requests_total{outcome!="ok"}[2m])) or vector(0)) '
    "/ clamp_min(sum(rate(ragapp_llm_requests_total[2m])), 1e-9)"
)
# The upper edge: at or above this the F01 detector claims the incident and the
# arm stops being an ambiguous F08. Imported rather than retyped would be
# better still, but Thresholds() lives behind the detector and this file must
# not depend on which number it fires on - it depends on staying BELOW it.
F01_CLAIMS_AT = 0.50


def say(m: str = "") -> None:
    print(m, flush=True)


def promql(_url: str, query: str) -> float | None:
    url = PROM + "/api/v1/query?query=" + urllib.parse.quote(query)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            res = json.loads(r.read())["data"]["result"]
        return float(res[0]["value"][1]) if res else None
    except Exception:
        return None


def error_ratio() -> float:
    v = promql("", ERROR_RATIO)
    return 0.0 if v is None else v


def corpus() -> dict[str, float | None]:
    return {"chunks": promql("", "ragapp_corpus_chunks"),
            "files": promql("", "ragapp_corpus_files")}


def _newest_baseline() -> dict[str, Any]:
    d = ROOT / "harness" / "baselines"
    for path in sorted(d.glob("baseline-simple-rag-*.json"), reverse=True):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(doc, dict) and doc.get("settings"):
            return doc
    return {}


def settle_below(client: TargetClient, ceiling: float,
                 rounds: int = 25) -> float:
    """Drive healthy traffic until the error ratio is under `ceiling`."""
    for _ in range(rounds):
        r = error_ratio()
        if r < ceiling:
            return r
        fast.run(client, FAST_SET, check_health=False)
    return error_ratio()


def contaminate(client: TargetClient, rounds: int) -> float:
    """Drive `rounds` fast-set passes against a dead endpoint, then restore.

    DOSE BY INTENSITY, NOT BY CATCHING A BAND - AND THAT IS A CORRECTION.
    The first version aimed at a band and caught the ratio descending through
    it. Two things were wrong. `build_frame` runs a fast-set pass of its own
    before collecting, which adds healthy calls and diluted the `[2m]` ratio
    by 0.065-0.094 between the catch and the frame - so the frame carried a
    materially lower value than the arm was labelled with, and in one arm it
    fell to 0.1744, BELOW the frame's own 0.20 ceiling. That arm carried no
    contamination at all and was reported as a dose. The descent also begins
    around 0.27, so any band above that was unreachable and two arms failed.

    More outage rounds means more failing samples in the window means a higher
    ratio. The dose is then whatever the FRAME carries, which is recorded and
    asserted rather than assumed - monotonic in `rounds`, and immune to the
    dilution because the dilution now applies inside every arm equally.

    The outage is reverted before the frame is built, so the frame describes a
    reachable endpoint carrying a stale error ratio - exactly the accidental
    condition this reproduces.
    """
    if rounds <= 0:
        return error_ratio()
    # NOT `F01EndpointOutage(client, ...)`: its first parameter is
    # `corpus_probe`, unlike F08's, so a positional client would be silently
    # installed as the corpus probe and the immutability assertion would call
    # the wrong object.
    outage = F01EndpointOutage(corpus_probe=corpus, proxy=PRIMARY)
    outage.inject()
    try:
        for _ in range(rounds):
            fast.run(client, FAST_SET, check_health=False)
    finally:
        outage.revert()
    return error_ratio()


def build_frame(client: TargetClient, baseline: dict[str, Any],
                with_logs: bool = False) -> Any:
    pre = fast.run(client, FAST_SET, check_health=False)
    detection = det.run_all(
        det.registry.specs(),
        det.Signals(prometheus_url=PROM, promql=promql, client=client,
                    baseline=baseline),
        pre.passed, pre.pass_rate,
    )
    frame = ev.collect(
        client, PROM, promql, pre,
        baseline_rerank_threshold=baseline.get("rerank_threshold", 0.35),
        baseline_settings=dict(baseline.get("settings") or {}),
        baseline_config_hash=str(baseline.get("config_hash") or ""),
        baseline_prompt_files=dict(
            (baseline.get("prompt_version") or {}).get("files") or {}),
        # LOGS OFF, AND THIS IS THE FIX THAT MAKES A DOSE SWEEP POSSIBLE.
        #
        # The first sweep was invalid partly because the log channel is a
        # second, independent memory of a finished fault: connection-error
        # lines outlive the [2m] metric window, nothing drains them, and a
        # control arm run minutes after a dosed arm diagnosed F01 on a frame
        # whose error ratio was 0.0, quoting EV-L01's ConnectionError.
        #
        # With logs excluded the arms differ in exactly one thing - the
        # metric - which is what a dose-response curve needs to mean
        # anything. The cost is external validity: production frames DO carry
        # logs, so this measures the metric channel alone and the report must
        # say so rather than generalising to "the frame".
        include_logs=with_logs,
    )
    return detection, frame


def frame_value(frame: Any, eid: str) -> tuple[str, str]:
    for item in frame.items:
        if item.eid == eid:
            return str(item.value), str(item.expected)
    return "", ""


def run_arm(name: str, outage_rounds: int, client: TargetClient,
            baseline: dict[str, Any], llm: OllamaClient,
            reps: int, with_logs: bool = False) -> dict[str, Any]:
    """One arm. `outage_rounds` sets the dose; 0 is the clean control."""
    contaminated = outage_rounds > 0
    say("=" * 74)
    say(f"ARM {name}: " + (f"{outage_rounds} outage round(s)" if contaminated
                           else "clean frame, 0 outage rounds"))
    say("=" * 74)

    settled = settle_below(client, FRAME_ERROR_RATIO_CEILING)
    say(f"  settled error ratio   {settled:.4f} "
        f"(target < {FRAME_ERROR_RATIO_CEILING})")

    band: float | None = None
    if contaminated:
        band = contaminate(client, outage_rounds)
        say(f"  ratio after contamination  {band:.4f} "
            f"(the FRAME's value is what counts, below)")

    fault = F08ConfigRegression(client, corpus_probe=corpus)
    rows: list[dict[str, Any]] = []
    out: dict[str, Any] = {"arm": name, "contaminated": contaminated,
                           "outage_rounds": outage_rounds,
                           "ratio_after_contamination": band}
    try:
        fault.inject()
        say(f"  injected              {SETTING} -> {fault.current_max_tokens()}")
        detection, frame = build_frame(client, baseline, with_logs)

        m06, m06_exp = frame_value(frame, "EV-M06")
        c04, c04_exp = frame_value(frame, "EV-C04")
        say(f"  deterministic         {detection.verdict} "
            f"{detection.fault_class} {detection.fault_name}")
        say(f"  EV-M06 llm_error      {m06}   expected: {m06_exp}")
        say(f"  EV-C04 max_tokens     {c04}   expected: {c04_exp}")

        out |= {"detected_class": detection.fault_class,
                "frame_error_ratio": float(m06) if m06 else None,
                "frame_error_expected": m06_exp,
                "max_tokens_marked_differs": "DIFFERS" in c04_exp}

        # VALIDITY, asserted. An arm that fails either of these measures
        # something other than what it claims, and a silent pass would be
        # worse than no experiment.
        if detection.fault_class != "F08":
            say(f"  INVALID: deterministic detection says "
                f"{detection.fault_class}, not F08")
            out |= {"valid": False,
                    "why": f"detection returned {detection.fault_class}",
                    "rows": []}
            return out
        if "DIFFERS" not in c04_exp:
            say("  INVALID: the frame does not mark max_tokens as drifted")
            out |= {"valid": False, "why": "no fault evidence in frame",
                    "rows": []}
            return out
        # THE CHECK THAT WAS MISSING, and its absence invalidated a whole
        # sweep. Detection saying F08 and max_tokens differing prove the
        # FAULT is in the frame; neither proves the CONTAMINANT is. One arm
        # ran at a frame value of 0.1744 - under the 0.20 ceiling, so the
        # frame called it healthy - and was reported as a dose of 0.25.
        # A contaminated arm whose frame is clean is a control, not a dose.
        m06_value = float(m06) if m06 else 0.0
        if contaminated and m06_value <= FRAME_ERROR_RATIO_CEILING:
            say(f"  INVALID: the frame carries {m06_value:.4f}, at or under "
                f"the {FRAME_ERROR_RATIO_CEILING} ceiling it states as "
                f"healthy - this arm is not contaminated")
            out |= {"valid": False,
                    "why": f"frame error ratio {m06_value:.4f} is not "
                           f"abnormal; arm is a control, not a dose",
                    "rows": []}
            return out
        if not contaminated and m06_value > FRAME_ERROR_RATIO_CEILING:
            say(f"  INVALID: the control arm's frame carries {m06_value:.4f}, "
                f"above the ceiling - it is not a clean frame")
            out |= {"valid": False,
                    "why": f"control frame error ratio {m06_value:.4f} is "
                           f"abnormal",
                    "rows": []}
            return out

        for i in range(1, reps + 1):
            rca = diagnose(frame, detection, CONFIDENCE_THRESHOLD, llm=llm,
                           declared_services=SERVICES)
            d = rca.diagnosis
            row = {
                "rep": i,
                "fault_class": d.fault_class if d else None,
                "fault_name": d.fault_name if d else None,
                "confidence": d.confidence if d else None,
                "repair": d.candidate_repair if d else None,
                "approved": rca.approved,
                "latency_s": round(rca.latency_s, 1),
                "reasoning": (d.reasoning[:600] if d
                              else (rca.error or "")[:600]),
            }
            rows.append(row)
            say(f"  rep {i:2}  {row['fault_class']!s:<6} "
                f"conf={row['confidence']!s:<5} "
                f"repair={row['repair']!s:<18} "
                f"approved={rca.approved}")
    finally:
        fault.revert()
        say(f"  reverted              {SETTING}={client.settings()[SETTING]}")
        say("")

    classes = Counter(str(r["fault_class"]) for r in rows)
    out |= {"valid": True, "rows": rows, "classes": dict(classes),
            "correct": classes.get("F08", 0), "n": len(rows)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--json-out", default=str(
        ROOT / "harness" / "reports" / "ambiguity-f08.json"))
    ap.add_argument(
        "--doses", default="",
        help="comma-separated OUTAGE ROUND COUNTS for a dose sweep, e.g. "
             "1,2,3,5. More rounds means a higher error ratio in the frame. "
             "Rounds rather than target ratios because aiming at a ratio was "
             "tried and the frame-collection pass diluted it out of the band. "
             "Omitted, the original two-arm experiment runs unchanged.")
    ap.add_argument(
        "--with-logs", action="store_true",
        help="include EV-L* log evidence; OFF by default because log "
             "lines are a second memory of a finished fault that nothing "
             "drains, and they invalidated the first dose sweep")
    args = ap.parse_args()

    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))
    llm = OllamaClient(args.ollama, args.model)

    say("=" * 74)
    say("DOES A SECOND ANOMALY TRIGGER THE F06 ATTRACTOR?")
    say("=" * 74)
    say(f"  model                 {args.model} at {args.ollama}")
    say(f"  reps per arm          {args.reps}")
    say(f"  contamination band    ({FRAME_ERROR_RATIO_CEILING}, "
        f"{F01_CLAIMS_AT})")
    if not llm.available():
        say("  Ollama is not reachable; cannot measure.")
        return 1

    baseline = _newest_baseline()
    if not baseline.get("settings"):
        say("  no baseline capture with a settings snapshot; F08 cannot be "
            "diagnosed.")
        return 1

    pre_corpus = corpus()
    say(f"  corpus                {pre_corpus}")
    say("")

    doses = [int(x) for x in args.doses.split(",") if x.strip()]
    if any(d <= 0 for d in doses):
        say("  outage round counts must be positive; 0 is the control arm, "
            "which always runs.")
        return 1

    t0 = time.time()
    arms: list[dict[str, Any]] = [
        run_arm("control", 0, client, baseline, llm, args.reps, args.with_logs)]
    for d in (doses or [4]):
        arms.append(run_arm(f"{d}r", d, client, baseline, llm, args.reps, args.with_logs))
    arm_a = arms[0]
    post_corpus = corpus()

    say("=" * 74)
    say("RESULT")
    say("=" * 74)
    say(f"  {'arm':>6}  {'ratio':>7}  {'F08':>6}  {'approved':>8}  classes")
    for arm in arms:
        if not arm.get("valid"):
            say(f"  {arm['arm']:>6}  INVALID - {arm.get('why')}")
            continue
        ok = sum(1 for r in arm["rows"] if r["approved"])
        ratio = arm.get("frame_error_ratio")
        say(f"  {arm['arm']:>6}  {ratio if ratio is not None else 0.0:>7.4f}  "
            f"{arm['correct']:>3}/{arm['n']:<2}  {ok:>5}/{arm['n']:<2}  "
            f"{arm['classes']}")

    verdict = "INCONCLUSIVE"
    valid = [a for a in arms if a.get("valid")]
    if len(valid) >= 2:
        say("")
        # What the wrong answers WERE is the whole question here. A dose that
        # degrades accuracy by redirecting to the contaminant's own class is a
        # different phenomenon from one that collapses to F06, and a table of
        # accuracy alone cannot tell them apart.
        say("  where the wrong answers went:")
        for arm in valid:
            wrong = Counter(str(r["fault_class"]) for r in arm["rows"]
                            if r["fault_class"] != "F08")
            say(f"    {arm['arm']:>6}  {dict(wrong) or 'none'}")

        a = arm_a["correct"] / arm_a["n"] if arm_a.get("valid") else None
        worst = min(x["correct"] / x["n"] for x in valid[1:]) if valid[1:] \
            else None
        if a is not None and worst is not None:
            if a - worst >= 0.3:
                verdict = "contamination degrades the diagnosis"
            elif abs(a - worst) < 0.2:
                verdict = "no effect: the arms are comparable"
            else:
                verdict = "weak: a difference, but under the 0.3 threshold"

        # Dose-response, the actual question of the sweep. F06 share among the
        # wrong answers is what separates "attractor" from "follows the noise".
        if len(valid) > 2:
            say("")
            say("  dose response (F06 share OF THE WRONG ANSWERS):")
            for arm in valid[1:]:
                misses = [str(r["fault_class"]) for r in arm["rows"]
                          if r["fault_class"] != "F08"]
                f06 = sum(1 for w in misses if w == "F06")
                share = f"{f06}/{len(misses)}" if misses else "-"
                say(f"    ratio {arm.get('frame_error_ratio'):.4f}  "
                    f"wrong {len(misses)}/{arm['n']}  F06 {share}")
            say("")
            say("  Read it this way: F06 dominating the wrong answers at LOW")
            say("  doses and F01 dominating at HIGH doses is the attractor "
                "being")
            say("  a fallback for an undecidable frame. F01 dominating "
                "everywhere")
            say("  means the model simply follows the loudest signal and the")
            say("  attractor needs a different explanation.")

        say("")
        say(f"  VERDICT               {verdict}")
        say(f"  n is {args.reps} per arm, one model, one fault class. Says "
            f"nothing about")
        say("  any model but qwen2.5:7b-instruct on this prompt.")

    say(f"  corpus                {pre_corpus} -> {post_corpus}")
    say(f"  elapsed               {round(time.time() - t0, 1)}s")

    doc = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "question": "does a second anomaly in the evidence frame trigger the "
                    "F06 attractor?",
        "model": args.model,
        "reps_per_arm": args.reps,
        "band": [FRAME_ERROR_RATIO_CEILING, F01_CLAIMS_AT],
        "verdict": verdict,
        "corpus_before": pre_corpus,
        "corpus_after": post_corpus,
        "doses": doses or None,
        "log_evidence_included": args.with_logs,
        "arms": arms,
    }
    Path(args.json_out).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    say(f"  artifact              {args.json_out}")

    return 0 if all(a.get("valid") for a in arms) else 1


if __name__ == "__main__":
    raise SystemExit(main())
