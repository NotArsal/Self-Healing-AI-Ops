"""P6 acceptance: does RCA name F08 in at least 8 of 10 runs?

`ROADMAP.md`'s per-fault acceptance requires "diagnosis names the right class
in >= 8 of 10 runs". This measures exactly that, for `F08`, with the real model.

ONE FRAME, TEN DIAGNOSES - DELIBERATELY
The evidence is collected ONCE under a live fault and then diagnosed ten times.
Re-collecting per repetition would vary the evidence as metric windows move,
and the question being asked is about the MODEL's consistency on fixed
evidence, not about the metrics' stability. Injector determinism is a separate
criterion with its own 20-cycle run (`stability_f08.py`).

F08 IS THE HARDEST OF THE THREE FOR A MODEL TO GET RIGHT
`F01` has a blunt signal - the error ratio is 1.0 and the logs are full of
connection errors. `F06` has a trained one: the prompt's whole discrimination
section is about retrieval, and the model reaches for it readily. `F08` has
neither. Its evidence is a config comparison, and the honest answer requires
noticing what is NOT wrong: grounding is intact, the endpoint answered every
call, and only the content of the answers is short. A model that pattern-matches
on "the fast set is failing" will reach for F06 here, which is precisely the
failure this measurement exists to catch.

It is also the first class whose repair collides with another's.
`rollback_config` is F06's action too, so naming the right repair is no evidence
of naming the right class - which is why this harness reports the class, the
repair and the validator verdict separately rather than collapsing them.

NO WARM-UP IS NEEDED, UNLIKE THE OTHER TWO
`rca_f01_live.py` drives load until a two-minute error ratio crosses, and
`p5_gate_live.py` until a ten-minute grounding average does. F08's signal is
read at the instant the loop runs, so one fast-set run under fault establishes
the symptom and the evidence frame can be collected immediately.

WHAT THE PASS CONDITION REQUIRES, AND WHY IT IS NOT JUST THE CLASS
A correct class with a diagnosis the validator refuses cannot drive a repair, so
counting it as correct would be the false-healthy verdict this project forbids.
It happened: on F01 the model returned the right class ten times out of ten
while every one of those diagnoses was rejected, and an earlier version of this
pass condition printed PASS over that. `approved >= 8` is required too.

The injector reverts in a finally block, so the target is healthy however this
exits.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "control-plane")]

from harness.faults.f08_config_regression import (  # noqa: E402
    SETTING,
    F08ConfigRegression,
)
from kavach.detection import base as det  # noqa: E402
from kavach.detection import catalogue  # noqa: E402, F401 - registers detectors
from kavach.llm.client import OllamaClient  # noqa: E402
from kavach.rca import evidence as ev  # noqa: E402
from kavach.rca.engine import diagnose  # noqa: E402
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
ERROR_RATIO_FLOOR = 0.50


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


def _newest_baseline() -> dict[str, Any]:
    """The newest capture with a settings snapshot, as the runner reads it."""
    d = ROOT / "harness" / "baselines"
    for path in sorted(d.glob("baseline-simple-rag-*.json"), reverse=True):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(doc, dict) and doc.get("settings"):
            return doc
    return {}


def corpus() -> dict[str, float | None]:
    return {"chunks": promql("", "ragapp_corpus_chunks"),
            "files": promql("", "ragapp_corpus_files")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="llama3.2")
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports" / "p6-f08-rca.json"))
    args = ap.parse_args()

    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))
    llm = OllamaClient(args.ollama, args.model)

    say("=" * 74)
    say("P6 ACCEPTANCE: RCA names F08 in >= 8 of 10 runs?")
    say("=" * 74)
    say(f"  model              {args.model} at {args.ollama}")
    say(f"  ollama reachable   {llm.available()}")
    say(f"  confidence gate    {CONFIDENCE_THRESHOLD}")
    if not llm.available():
        say("  Ollama is not reachable; cannot measure.")
        return 1

    # F08's detector compares against the baseline capture, so the harness
    # has to load the same one the runner would.
    baseline = _newest_baseline()
    assert baseline.get("settings"), (
        "no baseline capture with a settings snapshot under harness/baselines/; "
        "F08 cannot be diagnosed without one and would report "
        "INSUFFICIENT_EVIDENCE"
    )
    pre_corpus = corpus()
    say(f"  pre-state          {SETTING}={client.settings()[SETTING]} corpus={pre_corpus}")
    say("")

    fault = F08ConfigRegression(client, corpus_probe=corpus)
    results: list[dict[str, object]] = []

    try:
        fault.inject()
        say(f"  injected: {SETTING} -> {fault.current_max_tokens()}")

        # NO WARM-UP. F08's signal is a config comparison plus the fast
        # set, both read at the instant the loop runs - unlike F06's
        # ten-minute grounding average or F01's two-minute error ratio. One
        # fast-set run is enough to establish the symptom.
        pre = fast.run(client, FAST_SET, check_health=False)
        detection = det.run_all(
            det.registry.specs(),
            det.Signals(prometheus_url=PROM, promql=promql, client=client,
                        baseline=baseline),
            pre.passed, pre.pass_rate,
        )
        say(f"  deterministic      {detection.verdict} "
            f"{detection.fault_class} {detection.fault_name}")
        assert detection.fault_class == "F08", (
            f"deterministic detection says {detection.fault_class}, so this "
            f"would measure agreement with the wrong answer"
        )

        # ALL of the baselines, not just the rerank threshold. Until
        # 2026-10-17 this call passed only the threshold, so every EV-C line
        # rendered as "no baseline captured for this key" and the model was
        # shown `max_tokens = 2` with nothing to compare it against - the
        # exact defect `rca/evidence.py` was changed to fix, left out of the
        # path that measures it. The 0 of 10 recorded before this date was
        # therefore not a measurement of the fixed frame.
        frame = ev.collect(
            client, PROM, promql, pre,
            baseline_rerank_threshold=baseline.get("rerank_threshold", 0.35),
            baseline_settings=dict(baseline.get("settings") or {}),
            baseline_config_hash=str(baseline.get("config_hash") or ""),
            baseline_prompt_files=dict(
                (baseline.get("prompt_version") or {}).get("files") or {}),
        )
        for item in frame.items:
            if item.eid == "EV-C04":   # max_tokens, the drifted key
                say(f"  EV-C04             {item.value}  "
                    f"expected: {item.expected}")
                assert "DIFFERS" in str(item.expected), (
                    "the frame does not mark max_tokens as drifted, so it "
                    "carries no evidence of the fault being injected"
                )
        say(f"  evidence frame     {len(frame.items)} items, "
            f"{len(frame.problems)} collection problem(s)")
        say("")

        for i in range(1, args.reps + 1):
            # NOT `r`: that name holds a FastVerificationResult above, and
            # reusing it here hid the real type from mypy.
            rca = diagnose(frame, detection, CONFIDENCE_THRESHOLD, llm=llm,
                           declared_services=SERVICES)
            d = rca.diagnosis
            latency = round(rca.latency_s, 1)
            row: dict[str, object] = {
                "rep": i,
                "fault_class": d.fault_class if d else None,
                "service": d.service if d else None,
                "confidence": d.confidence if d else None,
                "repair": d.candidate_repair if d else None,
                "approved": rca.approved,
                "latency_s": latency,
                "cited": list(d.evidence_ids) if d else [],
                # 1200, not 160: the first version cut the reasoning before
                # its conclusion, so a transposed-evidence diagnosis had to be
                # re-run to be read. The artifact is the audit trail.
                "reasoning": (d.reasoning[:1200] if d else (rca.error or "")[:1200]),
            }
            results.append(row)
            say(f"  rep {i:2}  {row['fault_class']!s:<22} "
                f"conf={row['confidence']!s:<5} "
                f"repair={row['repair']!s:<20} "
                f"approved={rca.approved}  {latency}s")
            if not rca.approved and rca.rejection_reasons:
                say(f"          rejected: {rca.rejection_reasons[0][:120]}")
    finally:
        say("")
        fault.revert()
        say(f"  reverted; {SETTING}={client.settings()[SETTING]}")

    post_corpus = corpus()
    classes = Counter(str(r["fault_class"]) for r in results)
    correct = classes.get("F08", 0)
    approved = sum(1 for r in results if r["approved"])
    lat = [float(str(r["latency_s"])) for r in results]

    say("")
    say("=" * 74)
    say("RESULT")
    say("=" * 74)
    say(f"  classes returned   {dict(classes)}")
    say(f"  correct (F08)      {correct}/{len(results)}   (acceptance: >= 8/10)")
    say(f"  validator approved {approved}/{len(results)}")
    if lat:
        say(f"  RCA latency        min {min(lat):.1f}s mean "
            f"{statistics.mean(lat):.1f}s max {max(lat):.1f}s  (PF-02 budget 45s)")
    say(f"  corpus             {pre_corpus} -> {post_corpus}")

    # Copied-skeleton canary. Checks BOTH generations of leak, because the
    # first version of this canary only knew the old strings and therefore
    # reported PASS on a run where every repetition came back with the
    # skeleton's `confidence: 0.0` and `candidate_repair: "none"` - a sound
    # diagnosis that could never authorise anything.
    leaked = [r["rep"] for r in results
              if any(s in str(r["reasoning"])
                     for s in ("0.658", "0.999", "the endpoint is serving"))]
    skeleton_values = [r["rep"] for r in results
                       if r["confidence"] == 0.0 or r["repair"] == "none"]
    say(f"  old strings copied {leaked or 'none'}")
    say(f"  skeleton defaults  {skeleton_values or 'none'}  "
        f"(confidence 0.0 or repair none)")

    # A CORRECT CLASS IS NOT A USABLE DIAGNOSIS, and the criterion is only
    # worth anything if it measures one. A diagnosis the validator refuses can
    # never drive a repair, so counting it as correct would be exactly the
    # false-healthy verdict this project forbids.
    expected_repair = det.registry.repair_for("F08")
    named_repair = sum(1 for r in results if r["repair"] == expected_repair)
    say(f"  named the repair   {named_repair}/{len(results)}  "
        f"(expected {expected_repair!r})")

    passed = (
        correct >= 8
        and approved >= 8
        and len(results) == args.reps
        and pre_corpus == post_corpus
        and not leaked
        and not skeleton_values
    )
    say("")
    say(f"  F08 RCA ACCEPTANCE: {'PASS' if passed else 'FAIL'}")
    if correct >= 8 and approved < 8:
        say(f"    class correct {correct}/{len(results)} but only "
            f"{approved}/{len(results)} survived validation - the class is "
            f"right and the diagnosis is unusable")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": args.model,
        "reps": len(results),
        "correct_f01": correct,
        "classes": dict(classes),
        "validator_approved": approved,
        "latency_s": lat,
        "old_strings_copied_in": leaked,
        "skeleton_defaults_in": skeleton_values,
        "named_expected_repair": named_repair,
        "corpus_before": pre_corpus,
        "corpus_after": post_corpus,
        "passed": passed,
        "runs": results,
    }, indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  artifact {out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
