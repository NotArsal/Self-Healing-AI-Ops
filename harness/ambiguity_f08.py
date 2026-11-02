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

HOW THE BAND IS REACHED, AND WHY IT IS MEASURED RATHER THAN ASSUMED
Toxiproxy's primary listener goes down, a few fast-set runs drive real LLM
errors, the listener comes back, and healthy traffic then dilutes the ratio as
it descends through the band. Trying to hit a target number would be fragile,
so the harness instead collects the frame when the ratio is in range and
**records the value the frame actually carried** (`EV-M06`). That number is the
independent variable and it goes in the artifact.

TWO VALIDITY CONDITIONS, BOTH ASSERTED RATHER THAN HOPED FOR
1. Deterministic detection must still say **F08** in both arms. If it says
   F01, the arm is not an ambiguous F08 and the comparison is void.
2. `EV-C04` (`max_tokens`) must be marked `DIFFERS` in both arms, or the frame
   carries no evidence of the injected fault at all.

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


def raise_into_band(client: TargetClient, low: float, high: float,
                    rounds: int = 30) -> float | None:
    """Put the error ratio between `low` and `high`, or return None.

    Errors first: the primary listener goes down and real LLM calls fail.
    Then the listener comes back and healthy traffic dilutes the ratio, which
    descends through the band. The descent is what gets caught, because
    holding a rate steady is harder than catching it on the way past.
    """
    # NOT `F01EndpointOutage(client, ...)`: its first parameter is
    # `corpus_probe`, unlike F08's, so a positional client would be silently
    # installed as the corpus probe and the immutability assertion would call
    # the wrong object.
    outage = F01EndpointOutage(corpus_probe=corpus, proxy=PRIMARY)
    outage.inject()
    try:
        for _ in range(4):
            fast.run(client, FAST_SET, check_health=False)
            if error_ratio() > high:
                break
    finally:
        outage.revert()

    for _ in range(rounds):
        r = error_ratio()
        if low < r < high:
            return r
        if r <= low:        # decayed past the band before it was caught
            return None
        fast.run(client, FAST_SET, check_health=False)
    return None


def build_frame(client: TargetClient, baseline: dict[str, Any]) -> Any:
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
    )
    return detection, frame


def frame_value(frame: Any, eid: str) -> tuple[str, str]:
    for item in frame.items:
        if item.eid == eid:
            return str(item.value), str(item.expected)
    return "", ""


def run_arm(name: str, contaminated: bool, client: TargetClient,
            baseline: dict[str, Any], llm: OllamaClient,
            reps: int) -> dict[str, Any]:
    say("=" * 74)
    say(f"ARM {name}: {'contaminated frame' if contaminated else 'clean frame'}")
    say("=" * 74)

    settled = settle_below(client, FRAME_ERROR_RATIO_CEILING)
    say(f"  settled error ratio   {settled:.4f} "
        f"(target < {FRAME_ERROR_RATIO_CEILING})")

    band: float | None = None
    if contaminated:
        band = raise_into_band(client, FRAME_ERROR_RATIO_CEILING, F01_CLAIMS_AT)
        if band is None:
            say("  COULD NOT HOLD THE BAND - the ratio passed through "
                f"({FRAME_ERROR_RATIO_CEILING}, {F01_CLAIMS_AT}) uncaught.")
            return {"arm": name, "contaminated": contaminated,
                    "valid": False, "why": "error ratio never caught in band",
                    "rows": []}
        say(f"  error ratio in band   {band:.4f}")

    fault = F08ConfigRegression(client, corpus_probe=corpus)
    rows: list[dict[str, Any]] = []
    out: dict[str, Any] = {"arm": name, "contaminated": contaminated}
    try:
        fault.inject()
        say(f"  injected              {SETTING} -> {fault.current_max_tokens()}")
        detection, frame = build_frame(client, baseline)

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

    t0 = time.time()
    arm_a = run_arm("A", False, client, baseline, llm, args.reps)
    arm_b = run_arm("B", True, client, baseline, llm, args.reps)
    post_corpus = corpus()

    say("=" * 74)
    say("RESULT")
    say("=" * 74)
    for arm in (arm_a, arm_b):
        if not arm.get("valid"):
            say(f"  arm {arm['arm']}  INVALID - {arm.get('why')}")
            continue
        say(f"  arm {arm['arm']}  error_ratio={arm.get('frame_error_ratio')}  "
            f"F08 {arm['correct']}/{arm['n']}  classes={arm['classes']}")

    verdict = "INCONCLUSIVE"
    if arm_a.get("valid") and arm_b.get("valid"):
        a, b = arm_a["correct"] / arm_a["n"], arm_b["correct"] / arm_b["n"]
        say("")
        say(f"  clean frame           {arm_a['correct']}/{arm_a['n']} correct "
            f"({a:.0%})")
        say(f"  contaminated frame    {arm_b['correct']}/{arm_b['n']} correct "
            f"({b:.0%})")
        wrong_b = [r["fault_class"] for r in arm_b["rows"]
                   if r["fault_class"] != "F08"]
        say(f"  wrong answers, arm B  {Counter(wrong_b) or 'none'}")
        if a - b >= 0.3:
            verdict = "SUPPORTS: ambiguity degrades the diagnosis"
        elif abs(a - b) < 0.2:
            verdict = "DOES NOT SUPPORT: the arms are comparable"
        else:
            verdict = "WEAK: a difference, but under the 0.3 threshold"
        say("")
        say(f"  VERDICT               {verdict}")
        say("  n is 10 per arm. This is one experiment on one model, and it "
            "says nothing about")
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
        "arms": [arm_a, arm_b],
    }
    Path(args.json_out).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    say(f"  artifact              {args.json_out}")

    both_valid = bool(arm_a.get("valid") and arm_b.get("valid"))
    return 0 if both_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
