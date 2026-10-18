"""P6 acceptance: does RCA name F07 in at least 8 of 10 runs?

`ROADMAP.md`'s per-fault acceptance requires "diagnosis names the right class
in >= 8 of 10 runs". This measures exactly that, for `F07`, with the real model.

ONE FRAME, TEN DIAGNOSES - DELIBERATELY
The evidence is collected ONCE under a live fault and then diagnosed ten
times. Re-collecting per repetition would vary the evidence as metric windows
move, and the question being asked is about the MODEL's consistency on fixed
evidence. Injector determinism is a separate criterion with its own run.

THIS IS THE HARDEST DISCRIMINATION IN THE CATALOGUE SO FAR
F01 is blunt: the error ratio is 1.0 and the logs carry ConnectionError. F06
and F08 differ in grounding. F07 and F08 do not differ in ANY behavioural
signal - the model answers, the answer is grounded, the keyword is missing,
the endpoint is healthy, the retrieval metrics are healthy. They separate on
one thing only: whether the artifact that moved from its captured known-good
was a prompt file (`EV-C08`) or a settings key (`EV-C01`..`EV-C06`).

So this measurement is not really asking whether the model knows what a
prompt regression is. It is asking whether the evidence frame carries the
distinction at all, and whether the model reads it.

THE BASELINES ARE PASSED IN, AND THAT IS NOT INCIDENTAL
`ev.collect` takes `baseline_settings`, `baseline_config_hash` and
`baseline_prompt_files`. Without them every `EV-C` line renders as "no
baseline captured for this key" and both F07 and F08 become undiagnosable
from the frame however the prompt is worded - a live value with nothing to
compare it against cannot identify a class defined entirely by that
comparison.

`rca_f08_live.py` does NOT pass them, which was found while writing this
file. Its recorded 0 of 10 was therefore measured against a frame that showed
the model no baseline at all, so it does not measure what it reports. That is
noted in `ROADMAP.md` and `rca_f08_live.py` needs the same three arguments
before its number means anything.

The injector reverts in a finally block, so the target is healthy however
this exits.
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

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = ROOT / "apps" / "control-plane"
sys.path[:0] = [str(ROOT), str(CONTROL_PLANE)]

from harness.faults.f07_prompt_regression import (  # noqa: E402
    PROMPT_FILE,
    F07PromptRegression,
)
from kavach.api.runner import newest_baseline_doc  # noqa: E402
from kavach.config import get_settings  # noqa: E402
from kavach.detection import base as det  # noqa: E402
from kavach.detection import catalogue  # noqa: E402, F401 - registers detectors
from kavach.llm.client import OllamaClient  # noqa: E402
from kavach.onboarding.manifest import load as load_manifest  # noqa: E402
from kavach.rca import evidence as ev  # noqa: E402
from kavach.rca.engine import diagnose  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"
TARGET = "http://127.0.0.1:8000"
PROM = "http://127.0.0.1:9091"
SERVICES = {"backend", "db", "frontend", "toxiproxy", "prometheus"}
CONFIDENCE_THRESHOLD = 0.75


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


def corpus() -> dict[str, float | None]:
    return {"chunks": promql("", "ragapp_corpus_chunks"),
            "files": promql("", "ragapp_corpus_files")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="llama3.2")
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports" / "p6-f07-rca.json"))
    args = ap.parse_args()

    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))
    llm = OllamaClient(args.ollama, args.model)

    settings = get_settings()
    target_path = Path(settings.target_path)
    declared = load_manifest(target_path / "kavach.yaml").versioned_paths["prompts"]
    prompts_dir = (target_path / declared).resolve()

    baseline, baseline_name = newest_baseline_doc(
        settings.baselines_dir(), settings.target_project)
    baseline_settings = dict(baseline.get("settings") or {})
    baseline_hash = str(baseline.get("config_hash") or "")
    baseline_prompts = dict((baseline.get("prompt_version") or {}).get("files") or {})

    say("=" * 74)
    say("P6 ACCEPTANCE: RCA names F07 in >= 8 of 10 runs?")
    say("=" * 74)
    say(f"  model              {args.model} at {args.ollama}")
    say(f"  ollama reachable   {llm.available()}")
    say(f"  baseline           {baseline_name}")
    say(f"  baseline prompts   {baseline_prompts}")
    if not llm.available():
        say("  Ollama is not reachable; cannot measure.")
        return 1
    if not baseline_prompts or not baseline_settings:
        say("  the baseline records no prompt digests or no settings, so the "
            "frame would carry nothing to compare against. Re-run the capture.")
        return 1

    pre_corpus = corpus()
    results: list[dict[str, object]] = []
    fault = F07PromptRegression(client, prompts_dir, corpus_probe=corpus)

    try:
        fault.inject()
        say(f"  injected           {PROMPT_FILE} -> "
            f"{fault.reported_digests().get(PROMPT_FILE)} "
            f"(baseline {baseline_prompts.get(PROMPT_FILE)})")

        pre = fast.run(client, FAST_SET, check_health=False)
        shape_ok, shape_why = fault.assert_symptom_shape(list(pre.cases))
        say(f"  symptom shape      {shape_ok} - {shape_why}")
        assert shape_ok, (
            "the injection did not produce an F07-shaped symptom, so this "
            "would measure the model against evidence of a different fault"
        )

        detection = det.run_all(
            det.registry.specs(),
            det.Signals(prometheus_url=PROM, promql=promql, client=client,
                        baseline=baseline),
            pre.passed, pre.pass_rate,
        )
        say(f"  deterministic      {detection.verdict} "
            f"{detection.fault_class} {detection.fault_name}")
        assert detection.fault_class == "F07", (
            f"deterministic detection says {detection.fault_class}, so this "
            f"would measure agreement with the wrong answer"
        )

        # All three baselines. Without them every EV-C line reads "no baseline
        # captured" and the one fact that identifies this fault is absent.
        frame = ev.collect(
            client, PROM, promql, pre,
            baseline_rerank_threshold=baseline.get("rerank_threshold", 0.35),
            baseline_settings=baseline_settings,
            baseline_config_hash=baseline_hash,
            baseline_prompt_files=baseline_prompts,
        )
        say(f"  evidence frame     {len(frame.items)} items, "
            f"{len(frame.problems)} collection problem(s)")
        for item in frame.items:
            if item.eid == "EV-C08":
                say(f"  EV-C08             {item.value}")
                say(f"                     expected: {item.expected}")
                assert "DIFFERS" in str(item.expected), (
                    "EV-C08 does not mark the prompt as changed, so the frame "
                    "carries no evidence of the fault being injected"
                )
        say("")

        for i in range(1, args.reps + 1):
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
                "cited_ev_c08": "EV-C08" in (list(d.evidence_ids) if d else []),
                "reasoning": (d.reasoning[:1200] if d else (rca.error or "")[:1200]),
            }
            results.append(row)
            say(f"  rep {i:2}  {row['fault_class']!s:<22} "
                f"conf={row['confidence']!s:<5} "
                f"repair={row['repair']!s:<18} "
                f"EV-C08={row['cited_ev_c08']!s:<5} "
                f"approved={rca.approved}  {latency}s")
            if not rca.approved and rca.rejection_reasons:
                say(f"          rejected: {rca.rejection_reasons[0][:120]}")
    finally:
        say("")
        fault.revert()
        say(f"  reverted; target reports {fault.reported_digests()}")

    post_corpus = corpus()
    classes = Counter(str(r["fault_class"]) for r in results)
    correct = classes.get("F07", 0)
    approved = sum(1 for r in results if r["approved"])
    cited = sum(1 for r in results if r["cited_ev_c08"])
    lat = [float(str(r["latency_s"])) for r in results]

    say("")
    say("=" * 74)
    say("RESULT")
    say("=" * 74)
    say(f"  classes returned   {dict(classes)}")
    say(f"  correct (F07)      {correct}/{len(results)}   (acceptance: >= 8/10)")
    say(f"  validator approved {approved}/{len(results)}")
    say(f"  cited EV-C08       {cited}/{len(results)}  "
        f"(the ONE line that distinguishes F07 from F08)")
    if lat:
        say(f"  RCA latency        min {min(lat):.1f}s mean "
            f"{statistics.mean(lat):.1f}s max {max(lat):.1f}s  (PF-02 budget 45s)")
    say(f"  corpus             {pre_corpus} -> {post_corpus}")

    # Copied-skeleton canary, both generations, as the F01 harness carries.
    leaked = [r["rep"] for r in results
              if any(s in str(r["reasoning"])
                     for s in ("0.658", "0.999", "the endpoint is serving"))]
    skeleton_values = [r["rep"] for r in results
                       if r["confidence"] == 0.0 or r["repair"] == "none"]
    say(f"  old strings copied {leaked or 'none'}")
    say(f"  skeleton defaults  {skeleton_values or 'none'}")

    expected_repair = det.registry.repair_for("F07")
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
    say(f"  F07 RCA ACCEPTANCE: {'PASS' if passed else 'FAIL'}")
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
        "correct_f07": correct,
        "classes": dict(classes),
        "validator_approved": approved,
        "cited_ev_c08": cited,
        "latency_s": lat,
        "baseline": baseline_name,
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
