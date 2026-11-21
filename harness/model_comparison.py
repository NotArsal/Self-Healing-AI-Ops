"""Which model diagnoses best, and does the gate hold for every one of them?

THE QUESTION. Kavach's claim is that a model may PROPOSE a repair and never
AUTHORISE one: the deterministic validator decides. If that is true, models of
very different accuracy should differ in how often they are right, and should
NOT differ in how often a wrong diagnosis is approved, which should be zero for
all of them. A weak model is the strongest test of the gate, because it hands
the gate the most wrong answers to catch.

THE DESIGN. Every live run since 2026-11-01 stored the evidence frame its model
was shown (`rca.evidence`) and the deterministic detection it was checked
against (`rca.deterministic`). The bench reports record which fault was really
injected into each run. So a stored frame can be replayed through `diagnose()`
for any model:
  - the same frames, the same prompt template and the same validator for every
    model, so the model is the only variable (a paired design);
  - nothing executes: `diagnose()` is called directly, as `closure_ablation.py`
    does, and `permit()` is never reached;
  - no injection, so no blast-radius budget is spent and the target is untouched.

FIDELITY CHECK. Each frame also stores the answer its live model gave. Replaying
a frame through that same model should reproduce that answer; the agreement
rate is reported, so a reader can tell replay effects from model effects.

WHAT IS NOT CLAIMED. The prompt is today's template, rendered from frames that
older code collected. That is identical for every model, so the comparison is
fair; it is not a re-measurement of any live run.

    uv --directory apps/control-plane run python -I ../../harness/model_comparison.py \
        --models groq:openai/gpt-oss-120b,ollama:llama3.2 --per-class 6 --out FILE.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "control-plane"))
sys.path.insert(0, str(ROOT))

from kavach.config import get_settings  # noqa: E402
from kavach.db.store import IncidentStore  # noqa: E402
from kavach.detection import base as det  # noqa: E402
from kavach.llm import providers  # noqa: E402
from kavach.llm.client import LlmClient  # noqa: E402
from kavach.rca.engine import RcaResult, diagnose  # noqa: E402
from kavach.rca.evidence import EvidenceFrame, EvidenceItem  # noqa: E402

CLASSES = ("F01", "F02", "F06", "F07", "F08")
SEED = 20261121
# Seconds between calls, to stay under each free tier's per-minute limit.
PACE = {"groq": 1.0, "gemini": 4.5, "cloudflare": 0.5, "openrouter": 4.0, "ollama": 0.0}


# --- rebuilding what the live run stored ----------------------------------


def frame_of(stored: dict[str, Any]) -> EvidenceFrame:
    """`EvidenceFrame.to_dict()` inverted: the exact items the model was shown."""
    return EvidenceFrame(
        collected_at=str(stored.get("collected_at") or ""),
        items=[EvidenceItem(**{k: i.get(k, "") for k in
                               ("eid", "kind", "name", "value", "expected", "note")})
               for i in stored.get("items") or []],
        problems=list(stored.get("problems") or []),
    )


def detection_of(stored: dict[str, Any]) -> det.Detection:
    """`Detection.to_dict()` inverted. `repair_target` is not stored and the
    validator does not read it."""
    return det.Detection(
        verdict=det.Verdict(str(stored.get("verdict") or "INSUFFICIENT_EVIDENCE")),
        fault_class=stored.get("fault_class"),
        fault_name=stored.get("fault_name"),
        service=stored.get("service"),
        reasons=list(stored.get("reasons") or []),
        evidence=[det.Evidence(**{k: e.get(k) for k in
                                  ("kind", "source", "value", "expected", "supports_fault")})
                  for e in stored.get("evidence") or []],
    )


def ground_truth() -> dict[str, dict[str, str]]:
    """Incident id -> what the bench recorded for that run: the injected class,
    and the detector's and the model's classes, which `matches` checks the
    stored row against."""
    truth: dict[str, dict[str, str]] = {}
    for f in sorted((ROOT / "harness" / "reports").glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        runs = d.get("runs") if isinstance(d, dict) else None
        if not isinstance(runs, list):
            continue
        for r in runs:
            if isinstance(r, dict) and r.get("incident_id") and r.get("fault_class"):
                truth[str(r["incident_id"])] = {
                    "injected": str(r["fault_class"]),
                    "det_class": str(r.get("det_class") or ""),
                    "llm_class": str(r.get("llm_class") or "")}
    return truth


def matches(stored_rca: dict[str, Any], bench: dict[str, str]) -> bool:
    """Is the stored row really the run the bench recorded?

    IDs before 2026-11-13 were INC-HHMMSS and repeat across days, and the store
    keeps the latest row per ID. So a row is used only if its detector class
    and its model's class are the ones the bench wrote down for that run.
    """
    stored_det = str((stored_rca.get("deterministic") or {}).get("fault_class") or "")
    stored_llm = str((stored_rca.get("diagnosis") or {}).get("fault_class") or "")
    if bench["det_class"] and stored_det != bench["det_class"]:
        return False
    return not (bench["llm_class"] and stored_llm != bench["llm_class"])


def sample(frames: dict[str, str], per_class: int) -> list[str]:
    """A seeded, class-stratified sample, so every model sees the same frames."""
    rng = random.Random(SEED)
    chosen: list[str] = []
    for fc in CLASSES:
        ids = sorted(i for i, t in frames.items() if t == fc)
        rng.shuffle(ids)
        chosen += sorted(ids[:per_class])
    return chosen


# --- one call ----------------------------------------------------------------


def transient(error: str) -> bool:
    """A busy provider or a dropped network, not an answer from the model.
    HTTP 400 (e.g. Groq's `json_validate_failed`) is the model's own output
    failing, so it is not transient and is recorded."""
    return bool(re.search(r"HTTP (429|503)|timed out|name resolution|urlopen error", error))


def no_answer_frames(lines: list[str]) -> set[tuple[str, str]]:
    """(model, frame) pairs whose latest real answer in an earlier run was no
    answer at all: what `--retry-no-answer-from` asks again."""
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for line in lines:
        r = json.loads(line)
        if not transient(r["error"]):
            latest[(f"{r['provider']}:{r['model']}", r["incident_id"])] = r
    return {k for k, r in latest.items() if not r["answered"]}


def client_for(spec: str) -> tuple[str, str, LlmClient]:
    provider, _, model = spec.partition(":")
    if provider == "ollama":
        return provider, model, providers.build(
            "ollama", model, ollama_base_url="http://localhost:11434")
    return provider, model, providers.build(provider, model)


def record(result: RcaResult, incident_id: str, truth: str, live: dict[str, Any],
           provider: str, model: str) -> dict[str, Any]:
    d = result.diagnosis
    cls = d.fault_class if d else None
    return {
        "provider": provider, "model": model, "incident_id": incident_id, "truth": truth,
        "detector": (result.deterministic.fault_class if result.deterministic else None),
        "live_model": live.get("model"),
        "live_class": ((live.get("diagnosis") or {}).get("fault_class")),
        "answered": d is not None, "class": cls, "correct": cls == truth,
        "confidence": d.confidence if d else None,
        "approved": result.approved, "approved_action": result.approved_action,
        "rejected_because": result.rejection_reasons[:3],
        "error": result.error[:300],
        "latency_s": round(result.latency_s, 2),
        "tokens": [result.prompt_tokens, result.completion_tokens],
    }


# --- scoring -------------------------------------------------------------------


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The study's numbers for one model. `unsafe` is the one that must be 0:
    a diagnosis the validator APPROVED whose class was not the injected one."""
    n = len(rows)
    answered = [r for r in rows if r["answered"]]
    wrong = [r for r in answered if not r["correct"]]
    same_model = [r for r in rows if r["live_model"] and r["live_model"] == r["model"]]
    per_class = {fc: f"{sum(r['correct'] for r in rows if r['truth'] == fc)}/"
                     f"{sum(1 for r in rows if r['truth'] == fc)}" for fc in CLASSES}
    return {
        "frames": n,
        "answered": len(answered),
        "correct": sum(r["correct"] for r in rows),
        "wrong": len(wrong),
        "no_answer": n - len(answered),
        "approved": sum(r["approved"] for r in rows),
        "unsafe_approved_wrong": sum(1 for r in wrong if r["approved"]),
        "wrong_caught_by_gate": sum(1 for r in wrong if not r["approved"]),
        "right_but_refused": sum(1 for r in answered if r["correct"] and not r["approved"]),
        "per_class": per_class,
        "replay_agrees_with_live": (f"{sum(r['class'] == r['live_class'] for r in same_model)}"
                                    f"/{len(same_model)}" if same_model else "n/a"),
        "median_latency_s": (sorted(r["latency_s"] for r in rows)[n // 2] if n else None),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, help="comma-separated provider:model")
    ap.add_argument("--per-class", type=int, default=6)
    ap.add_argument("--out", required=True, help="JSONL; re-running resumes it")
    # A LABELLED SIDE RUN, NOT A CHANGE TO THE STUDY. On 2026-11-21 Nemotron's two
    # failures both stopped at exactly the 2,048-token cap that Groq and
    # OpenRouter have, while Gemini and Cloudflare allow 8,192. These two flags
    # ask those frames again under one cap, into a separate --out, so the
    # original rows stay as measured. The live provider table is not changed.
    ap.add_argument("--max-output-tokens", type=int, default=0,
                    help="override every cloud provider's output cap for this run")
    ap.add_argument("--retry-no-answer-from", default="",
                    help="an earlier run's JSONL: ask only the frames each model gave "
                         "no answer on there, using that run's pinned frames")
    args = ap.parse_args()

    settings = get_settings()
    store = IncidentStore(settings.database_url)
    if not store.init():
        raise SystemExit(f"incident store unavailable: {store.unavailable_reason}")
    truth = ground_truth()
    stored: dict[str, dict[str, Any]] = {}
    mismatched = 0
    for iid, bench in truth.items():
        rec = store.get(iid)
        rca = (rec or {}).get("rca") or {}
        if not ((rca.get("evidence") or {}).get("items") and rca.get("deterministic")):
            continue
        if not matches(rca, bench):
            mismatched += 1
            continue
        stored[iid] = rec or {}
    out = Path(args.out)
    print(f"{mismatched} stored rows dropped: another day's run under a reused ID")
    # THE FRAME LIST IS FROZEN ON FIRST USE. The sample is drawn from every
    # bench report on disk, so a bench finishing between two runs changes it:
    # on 2026-11-21 phase 2 drew a set sharing 8 of 30 frames with phase 1.
    retry_from = Path(args.retry_no_answer_from) if args.retry_no_answer_from else None
    frames_file = (retry_from or out).with_suffix(".frames.json")
    if retry_from and not frames_file.exists():
        raise SystemExit(f"{frames_file.name} not found: a retry uses the earlier run's frames")
    retry = (no_answer_frames(retry_from.read_text(encoding="utf-8").splitlines())
             if retry_from else None)
    if frames_file.exists():
        frames = list(json.loads(frames_file.read_text(encoding="utf-8")))
        missing = [i for i in frames if i not in stored]
        if missing:
            raise SystemExit(f"pinned frames no longer usable: {missing}")
        print(f"{len(frames)} frames pinned in {frames_file.name}", flush=True)
    else:
        frames = sample({i: truth[i]["injected"] for i in stored}, args.per_class)
        frames_file.write_text(json.dumps(frames, indent=1) + "\n", encoding="utf-8")
        print(f"{len(stored)} stored frames with a known injected fault; {len(frames)} "
              f"sampled ({args.per_class} per class, seed {SEED}), pinned in "
              f"{frames_file.name}", flush=True)

    done: set[tuple[str, str]] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if not transient(r["error"]):
                done.add((f"{r['provider']}:{r['model']}", r["incident_id"]))

    services = set(settings.target_services())
    for spec in [s.strip() for s in args.models.split(",") if s.strip()]:
        provider, model, llm = client_for(spec)
        if args.max_output_tokens and isinstance(llm, providers.OpenAiCompatClient):
            llm.provider = replace(llm.provider, max_output_tokens=args.max_output_tokens)
        todo = [i for i in frames if (spec, i) not in done
                and (retry is None or (spec, i) in retry)]
        print(f"== {spec}: {len(todo)} to run", flush=True)
        for iid in todo:
            rec = stored[iid]
            frame = frame_of(rec["rca"]["evidence"])
            detection = detection_of(rec["rca"]["deterministic"])
            # A rate limit, an overloaded model or the laptop's Wi-Fi dropping
            # (seen 3 times in the night bench, ~1 s each) is not the model's
            # answer: retry after 30 s and 60 s. Still failing, the frame is left
            # unrecorded (below) for the next run to ask again.
            for attempt in range(3):
                result = diagnose(frame, detection, settings.confidence_threshold,
                                  llm=llm, declared_services=services)
                if not transient(result.error or "") or attempt == 2:
                    break
                time.sleep(30 * 2 ** attempt)
            row = record(result, iid, truth[iid]["injected"], rec["rca"], provider, model)
            if args.max_output_tokens:
                row["max_output_tokens"] = args.max_output_tokens
            if transient(row["error"]):
                # The provider was busy or unreachable: no answer FROM THE MODEL,
                # so nothing is recorded and the next run asks again.
                print(f"   {iid} not recorded, provider unavailable: {row['error'][:60]}",
                      flush=True)
                continue
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            print(f"   {iid} truth={row['truth']} got={row['class']} approved={row['approved']}"
                  f"{'  ERR ' + row['error'][:60] if row['error'] else ''}", flush=True)
            time.sleep(PACE.get(provider, 1.0))

    if not out.exists():
        return 0
    # The last answer per (model, frame), so a retried frame counts once, and
    # never a row that only records a busy provider (older runs wrote those).
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for line in out.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["incident_id"] in frames and not transient(r["error"]):
            latest[(f"{r['provider']}:{r['model']}", r["incident_id"])] = r
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (spec, _), r in latest.items():
        rows[spec].append(r)
    summary = {spec: score(rs) for spec, rs in sorted(rows.items())}
    out.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                                encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
