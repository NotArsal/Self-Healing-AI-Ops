"""Does the bounded frame saturate Evidence Closure? The controlled test.

Implements `docs/EXPERIMENT_CLOSURE_ABLATION.md`, which is a pre-registration:
its predictions and refutation conditions were written before any data
existed and must not be edited to fit a result.

THE QUESTION. `REPORT_DRAFT.md` §4.4a reports closure at 37/37 = 1.00 on the
detector's class, against Cloud-OpsBench's 0.38, and explains it as an effect
of handing the model a bounded frame. Nothing has ever varied the frame and
watched closure move, so that is an observation and a reviewer may read our
1.00 as "better grounded" instead.

WHAT IS HELD CONSTANT. One frame is collected per incident and every arm is
derived from that one object, so the injected fault, the deterministic
verdict, the target state, the timing and the underlying readings are
identical across arms by construction. This is a paired, within-incident
design: each incident contributes one observation per arm, which is what
makes McNemar the right test and makes the comparison far tighter than
running the arms as separate benches.

WHAT IS VARIED, and the frame does three things at once that the report
conflates into "bounded":

    curation       only signals some detector reads are present
    labelling      a stable short id per item, so citing is a copy
    interpretation an `expected` field answering "is this abnormal?"
                   before the model reads a thing

  A  control, the shipped frame                curated, labelled, interpreted
  B  size-matched noise  <- PRIMARY            uncurated
  C  unbounded noise                           uncurated, longer
  D  expectations stripped                     uninterpreted

ARM B IS PRIMARY BECAUSE IT IS SIZE-MATCHED. Distractors REPLACE
non-discriminating items rather than being added, so A and B hold the same
item count. An arm that is merely bigger confounds signal density with
context length, and that is the likeliest way to get a wrong answer here.
Arm C carries the realistic unbounded case and is reported as secondary for
exactly that reason.

DISTRACTORS ARE REAL. They are metrics the target already exports that no
detector reads - garbage-collection counters, resident memory, per-handler
request latencies, embedding-operation timings. Synthetic noise would be
rejected by a reviewer and should be: a model ignoring `EV-X99 foo_bar = 1.0`
tells us nothing about an operator's real telemetry.

IDS ARE RESOLVED BY NAME, NOT POSITION. `evidence_closure.DISCRIMINATING`
maps a fault class to SIGNAL NAMES, so arms may renumber freely as long as
the map is recomputed per arm against `item.name`. That was checked before
this was designed; had it been positional the design would have needed
rebuilding.

NOTHING EXECUTES. This calls `collect()` and `diagnose()` directly, the way
`rca_f08_live.py` does, and never reaches `permit()`. No repair runs, so no
blast-radius budget is consumed beyond the injections themselves.

`rca/evidence.py` IS NOT EDITED. `AGENTS.md` forbids changing the code every
published number was measured with, and mutating the measured path would
invalidate the control arm. Arms are built by transforming the returned
frame object here.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.request
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = ROOT / "apps" / "control-plane"
sys.path[:0] = [str(ROOT), str(CONTROL_PLANE)]

from harness.evidence_closure import DISCRIMINATING  # noqa: E402
from harness.kavach_baseline import (  # noqa: E402
    FAST_SET,
    PROM,
    TARGET,
    build,
    drive_until_detectable,
    warm_up_f01,
)
from kavach.config import get_settings  # noqa: E402
from kavach.detection import base as det  # noqa: E402
from kavach.llm import providers  # noqa: E402
from kavach.rca import evidence as ev  # noqa: E402
from kavach.rca.engine import diagnose  # noqa: E402
from kavach.rca.evidence import EvidenceFrame, EvidenceItem  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

ARMS = ("A", "B", "C", "D", "E")
ARM_LABEL = {
    "A": "control, the shipped frame",
    "B": "size-matched noise (PRIMARY)",
    "C": "unbounded noise",
    "D": "expectations stripped",
    "E": "same items removed as B, nothing added",
}

# Metric families a detector reads. Anything whose Prometheus name starts with
# one of these is REAL SIGNAL and may never be used as a distractor, however
# irrelevant the particular series looks.
SIGNAL_PREFIXES = ("ragapp_retrieval", "ragapp_llm", "ragapp_corpus")


def say(*parts: object) -> None:
    print(*parts, flush=True)


def promql(_url: str, query: str) -> float | None:
    """Two-arg, because `Signals` and `collect()` both pass the url.

    `kavach_baseline.promql` takes one argument and cannot be used here; the
    other live harnesses define this same wrapper for the same reason.
    """
    import urllib.parse
    url = PROM + "/api/v1/query?query=" + urllib.parse.quote(query)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            res = json.loads(r.read())["data"]["result"]
        return float(res[0]["value"][1]) if res else None
    except Exception:
        return None


def newest_baseline() -> tuple[dict[str, Any], str]:
    """The newest HEALTHY capture carrying a settings snapshot.

    The `healthy is True` filter is not decoration. `api/runner.py` had no
    such check until 2026-11-03, and a capture saved with `--force` while the
    system was broken could become the rollback target; four `healthy: false`
    captures are committed under `harness/baselines/`. An ablation that
    silently used one would hand every arm a baseline measured during a
    fault, and F07 and F08 are defined entirely by comparison against it.
    Absent `healthy` is treated as unusable rather than assumed good, the
    same way the runner now treats it.
    """
    for path in sorted((ROOT / "harness" / "baselines").glob(
            "baseline-simple-rag-*.json"), reverse=True):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict) or doc.get("healthy") is not True:
            continue
        if doc.get("settings"):
            return doc, path.name
    return {}, ""


# --- distractors ------------------------------------------------------------


def detector_drop_note(fault_class: str, incident: int,
                       detection: det.Detection) -> str:
    """The `dropped` entry for an incident the detector did not attribute.

    EXPERIMENT_CLOSURE_ABLATION.md section 31.8. Until 2026-11-10 this recorded
    the verdict and not WHY, so section 29.10's two dropped incidents could not
    be explained after the fact. `Detection.reasons` already carried the why.
    A log string only: no observation, arm, prompt or metric reads it.
    """
    why = "; ".join(r[:120] for r in detection.reasons[:3]) or "none recorded"
    return (f"{fault_class}#{incident}: detector said "
            f"{detection.fault_class or detection.verdict}, not the injected "
            f"class; every arm would measure agreement with the wrong answer. "
            f"detector reasons: {why}")


def scrape_distractors(url: str, need: int) -> list[tuple[str, float]]:
    """Real metrics the target exports that no detector reads.

    Pulled live rather than hardcoded, so the noise is whatever that target
    actually emits. A second workload would therefore get its own distractors
    without this script changing.
    """
    with urllib.request.urlopen(f"{url}/metrics", timeout=20) as r:
        body = r.read().decode("utf-8", "replace")

    seen: dict[str, float] = {}
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-0-9.eE+]+)$",
                         line)
        if not match:
            continue
        name, labels, raw = match.groups()
        if name.startswith(SIGNAL_PREFIXES):
            continue          # real signal, never a distractor
        if name.endswith(("_created", "_bucket")):
            continue          # noise of a shape the frame never carries
        try:
            value = float(raw)
        except ValueError:
            continue
        key = name + (labels or "")
        seen.setdefault(key, value)

    picked = sorted(seen.items())
    if len(picked) < need:
        raise SystemExit(
            f"only {len(picked)} distractor metrics available at "
            f"{url}/metrics and at least {need} are needed. Arm B replaces "
            f"every non-discriminating item, so the pool must be at least as "
            f"large as the frame; with fewer, B silently comes out shorter "
            f"than A and stops being size-matched. That is what the first "
            f"smoke run of this script did - 29 items against 35 - and the "
            f"arm was correctly dropped rather than used.")
    return [(k, v) for k, v in picked]


def as_items(distractors: list[tuple[str, float]], start: int) -> list[EvidenceItem]:
    return [
        EvidenceItem(eid=f"EV-M{start + n:02d}", kind="metric",
                     name=name, value=round(value, 4))
        for n, (name, value) in enumerate(distractors)
    ]


# --- arm construction -------------------------------------------------------


def discriminating_items(frame: EvidenceFrame, fault_class: str) -> list[EvidenceItem]:
    """The items whose NAME discriminates this class. Never dropped by any arm."""
    names = set(DISCRIMINATING.get(fault_class, ()))
    return [i for i in frame.items if i.name in names]


def renumber(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """Fresh contiguous ids per kind, in list order.

    Renumbering is safe because closure resolves by name. It is NECESSARY
    because an arm that reused the shipped ids while holding different items
    would let a model that had seen this frame shape answer from the id rather
    than the value.
    """
    prefix = {"metric": "M", "config": "C", "log": "L", "service": "S",
              "baseline": "B", "verification": "V", "health": "H"}
    counter: dict[str, int] = {}
    out: list[EvidenceItem] = []
    for item in items:
        p = prefix.get(item.kind, "X")
        counter[p] = counter.get(p, 0) + 1
        fresh = deepcopy(item)
        fresh.eid = f"EV-{p}{counter[p]:02d}"
        out.append(fresh)
    return out


def build_arm(
    arm: str,
    frame: EvidenceFrame,
    fault_class: str,
    distractors: list[tuple[str, float]],
    rng: random.Random,
    shuffle: bool,
) -> EvidenceFrame:
    keep = discriminating_items(frame, fault_class)
    keep_names = {i.name for i in keep}
    others = [i for i in frame.items if i.name not in keep_names]

    if arm == "A":
        items = list(frame.items)
    elif arm == "D":
        items = []
        for i in frame.items:
            stripped = deepcopy(i)
            stripped.expected = ""
            items.append(stripped)
    elif arm in ("B", "C", "E"):
        # Metrics are the only kind a distractor can impersonate, so noise
        # displaces non-discriminating METRICS first and other kinds only if
        # the budget demands it. Service identity is never displaced: without
        # EV-S the model has to invent a service name, which `collect()`'s own
        # comment records as a real past failure and is not what this arm is
        # testing.
        #
        # Computed for B, C and E together because E must hold EXACTLY the
        # real content B holds - that identity is what makes B vs E isolate
        # noise, and it would not survive the two arms deciding separately
        # what counts as protected.
        protected = [i for i in others if i.kind in ("service", "baseline")]
        displaceable = [i for i in others if i.kind not in ("service", "baseline")]
        if arm == "E":
            # ARM B REMOVES AND ADDS AT ONCE, which the 2026-11-07 pacing run
            # exposed: it reaches size-matching by REPLACING non-discriminating
            # real items with distractors, so a wrong answer in B could be the
            # removal rather than the noise and the design could not say which.
            #
            # E holds exactly the real content B holds and adds nothing, so
            # B vs E is the clean noise comparison - same real signals,
            # distractors the only difference - and A vs E is the removal
            # effect with no noise present. The three decompose what A vs B
            # alone confounds.
            items = keep + protected
        elif arm == "B":
            room = len(displaceable)
            noise = as_items(distractors[:room], start=90)
            items = keep + protected + noise
        else:
            noise = as_items(distractors, start=90)
            items = keep + protected + displaceable + noise
    else:
        raise ValueError(f"unknown arm {arm!r}")

    if shuffle:
        items = list(items)
        rng.shuffle(items)

    out = EvidenceFrame(collected_at=frame.collected_at)
    out.items = renumber(items)
    out.problems = list(frame.problems)
    return out


# --- validity ---------------------------------------------------------------


def check_arm(
    arm: str, built: EvidenceFrame, fault_class: str, reference: int,
    real_names: set[str] | None = None,
) -> str:
    """Empty string when the arm is what it claims to be, else why not.

    An arm that fails is DROPPED AND COUNTED, never silently repaired. The
    2026-11-02 dose sweep produced four invalid arms because nothing asserted
    each arm was the arm intended before the model was asked.
    """
    present = {i.name for i in built.items}
    needed = set(DISCRIMINATING.get(fault_class, ()))
    missing = needed - present
    if missing:
        return (f"arm {arm} lost discriminating signal(s) {sorted(missing)}, "
                f"so closure would be trivially 0 and measure nothing")
    if arm == "B" and len(built.items) != reference:
        return (f"arm B holds {len(built.items)} items against control's "
                f"{reference}; it is not size-matched and would confound "
                f"density with length")
    if arm == "C" and len(built.items) <= reference:
        return f"arm C is not longer than control ({len(built.items)} vs {reference})"
    if arm == "E":
        if len(built.items) >= reference:
            return (f"arm E holds {len(built.items)} items against control's "
                    f"{reference}; it is supposed to be the REMOVAL arm and "
                    f"removed nothing")
        intruders = sorted({i.name for i in built.items} - (real_names or set()))
        if intruders:
            return (f"arm E contains items that are not in the real frame "
                    f"{intruders[:4]}; it must add nothing, or B vs E stops "
                    f"isolating noise")
    if arm == "D" and any(i.expected for i in built.items):
        return "arm D still carries an `expected` field"
    if len({i.eid for i in built.items}) != len(built.items):
        return f"arm {arm} has duplicate evidence ids"
    return ""


# --- measurement ------------------------------------------------------------


def closed_on(diag: Any, built: EvidenceFrame, fault_class: str) -> bool:
    """Did the diagnosis cite evidence discriminating `fault_class`?

    Resolved per arm against item NAMES, because the ids differ between arms
    by construction.
    """
    if diag is None:
        return False
    names = set(DISCRIMINATING.get(fault_class, ()))
    want = {i.eid for i in built.items if i.name in names}
    return bool(want & set(diag.evidence_ids or ()))


@dataclass
class Observation:
    fault_class: str
    incident: int
    arm: str
    rep: int
    items: int
    prompt_tokens: int
    named: str = ""
    closed_detector: bool = False
    closed_named: bool = False
    agreed: bool = False
    cited: int = 0
    unresolved: int = 0
    confidence: float | None = None
    latency_s: float = 0.0
    error: str = ""
    # Which distractor draw this incident got. Varies per incident now, so the
    # analysis can ask whether an arm's outcome tracks the draw rather than
    # the arm - which section 14 found it does.
    draw: str = ""


@dataclass
class Run:
    at: str = ""
    model: str = ""
    shuffled: bool = False
    observations: list[Observation] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


# --- reporting --------------------------------------------------------------


def mcnemar(pairs: list[tuple[bool, bool]]) -> tuple[int, int, float]:
    """Exact McNemar on paired binary outcomes. Returns (b, c, two-sided p).

    b = control closed and the arm did not; c = the reverse. Only the
    discordant pairs carry information, which is the whole point of pairing.
    """
    from math import comb

    b = sum(1 for a, x in pairs if a and not x)
    c = sum(1 for a, x in pairs if x and not a)
    n = b + c
    if n == 0:
        return b, c, 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    return b, c, min(1.0, 2 * tail)


def summarise(run: Run) -> None:
    say("")
    say("=" * 78)
    say("CLOSURE ABLATION")
    say("=" * 78)
    say(f"  model      {run.model}")
    say(f"  shuffled   {run.shuffled}")
    ok = [o for o in run.observations if not o.error]
    say(f"  usable     {len(ok)} of {len(run.observations)} diagnoses"
        f"   dropped arms: {len(run.dropped)}")
    say("")

    say(f"  {'arm':4} {'label':32} {'closure(detector)':>18} {'closure(named)':>15}"
        f" {'agreed':>8} {'items':>6} {'tokens':>7}")
    for arm in ARMS:
        rows = [o for o in ok if o.arm == arm]
        if not rows:
            continue
        n = len(rows)
        cd = sum(o.closed_detector for o in rows)
        cn = sum(o.closed_named for o in rows)
        ag = sum(o.agreed for o in rows)
        say(f"  {arm:4} {ARM_LABEL[arm]:32} {f'{cd}/{n} = {cd / n:.2f}':>18}"
            f" {f'{cn}/{n} = {cn / n:.2f}':>15} {f'{ag}/{n}':>8}"
            f" {sum(o.items for o in rows) // n:>6}"
            f" {sum(o.prompt_tokens for o in rows) // n:>7}")

    # Paired comparisons against the control, on the primary outcome.
    say("")
    say("  PAIRED against arm A, primary outcome = closure on the detector's class")
    # THE PAIRING UNIT IS THE INCIDENT, NOT THE DIAGNOSIS. Reps of one
    # incident share a frame and a draw and the measured within-cell spread
    # is 0.01, so pairing per diagnosis treats the same observation three
    # times as three independent ones and inflates every p-value. On the
    # 2026-11-09 run that was the difference between p=0.0007 and p=0.1250
    # for the primary comparison. Fixed 2026-11-10 here and in
    # closure_ablation_report.py, which had the same defect while its
    # bootstrap next to it had always resampled incidents.
    grouped: dict[tuple[str, int, str], list[bool]] = defaultdict(list)
    for o in ok:
        grouped[(o.fault_class, o.incident, o.arm)].append(o.closed_detector)
    index = {k: sum(v) * 2 > len(v) for k, v in grouped.items()}
    for arm in ("B", "C", "D", "E"):
        pairs = [
            (index[k], index[(k[0], k[1], arm)])
            for k in index
            if k[2] == "A" and (k[0], k[1], arm) in index
        ]
        if not pairs:
            continue
        b, c, p = mcnemar(pairs)
        a_rate = sum(x for x, _ in pairs) / len(pairs)
        x_rate = sum(y for _, y in pairs) / len(pairs)
        verdict = ""
        if arm == "B":
            drop = a_rate - x_rate
            verdict = ("  <- PREDICTION MET" if drop >= 0.15 and p < 0.05
                       else "  <- prediction NOT met")
        say(f"    A vs {arm}: incidents={len(pairs)}  A={a_rate:.2f}  {arm}={x_rate:.2f}"
            f"  drop={a_rate - x_rate:+.2f}  b={b} c={c}  p={p:.4f}{verdict}")

    if run.dropped:
        say("")
        say("  arms dropped as invalid, never repaired:")
        for d in run.dropped[:10]:
            say(f"    {d}")


# --- the run ----------------------------------------------------------------


def one_incident(
    fault_class: str,
    incident: int,
    client: TargetClient,
    llm: Any,
    baseline: dict[str, Any],
    distractors: list[tuple[str, float]],
    reps: int,
    shuffle: bool,
    arms: tuple[str, ...],
    run: Run,
    max_transient: int = 8,
) -> None:
    settings = get_settings()
    fault = build(fault_class, client)
    rng = random.Random(f"{fault_class}-{incident}")
    transient = 0

    try:
        fault.inject()
        if fault_class == "F06":
            drive_until_detectable(client)
        elif fault_class == "F01":
            warm_up_f01(client)

        pre = fast.run(client, FAST_SET, check_health=False)
        detection = det.run_all(
            det.registry.specs(),
            det.Signals(prometheus_url=PROM, promql=promql, client=client,
                        baseline=baseline),
            pre.passed, pre.pass_rate,
        )
        if detection.fault_class != fault_class:
            run.dropped.append(detector_drop_note(fault_class, incident, detection))
            return

        frame = ev.collect(
            client, PROM, promql, pre,
            baseline_rerank_threshold=baseline.get("rerank_threshold", 0.35),
            baseline_settings=dict(baseline.get("settings") or {}),
            baseline_config_hash=str(baseline.get("config_hash") or ""),
            baseline_prompt_files=dict(
                (baseline.get("prompt_version") or {}).get("files") or {}),
        )
        control_size = len(frame.items)

        # Arm B takes a PREFIX of this list, so a fixed order gave every
        # incident in a run the same distractors: the treatment was applied
        # once per run, not once per incident, while the design varied the
        # things that barely vary. Two draws that differed by one metric gave
        # opposite answers on F01 (section 14), so the draw is not a nuisance
        # parameter - it is the treatment. Shuffled per incident, which is the
        # cluster unit, on its own stream so `--shuffle` is unaffected.
        draw = list(distractors)
        random.Random(f"draw-{fault_class}-{incident}").shuffle(draw)
        draw_id = sha256(
            "\n".join(n for n, _ in draw).encode()).hexdigest()[:8]

        built: dict[str, EvidenceFrame] = {}
        for arm in arms:
            candidate = build_arm(arm, frame, fault_class, draw, rng,
                                  shuffle)
            why = check_arm(arm, candidate, fault_class, control_size,
                            {i.name for i in frame.items})
            if why:
                run.dropped.append(f"{fault_class}#{incident}: {why}")
                continue
            built[arm] = candidate

        if "A" not in built:
            run.dropped.append(
                f"{fault_class}#{incident}: control arm invalid, incident unusable")
            return

        for arm, arm_frame in built.items():
            rep = 0
            while rep < reps:
                rep += 1
                obs = Observation(
                    fault_class=fault_class, incident=incident, arm=arm,
                    rep=rep, items=len(arm_frame.items), prompt_tokens=0,
                    draw=draw_id,
                )
                try:
                    t0 = time.perf_counter()
                    result = diagnose(
                        arm_frame, detection, settings.confidence_threshold,
                        llm=llm,
                        declared_services=set(settings.target_services()),
                    )
                    obs.latency_s = round(time.perf_counter() - t0, 2)
                    obs.prompt_tokens = result.prompt_tokens
                    d = result.diagnosis
                    if d is None:
                        obs.error = result.error or "no diagnosis"
                    else:
                        obs.named = d.fault_class
                        obs.confidence = d.confidence
                        obs.cited = len(d.evidence_ids or ())
                        obs.unresolved = len(
                            set(d.evidence_ids or ()) - arm_frame.ids)
                        obs.agreed = d.fault_class == detection.fault_class
                        obs.closed_detector = closed_on(
                            d, arm_frame, detection.fault_class or "")
                        obs.closed_named = closed_on(d, arm_frame, d.fault_class)
                except Exception as exc:
                    obs.error = f"{type(exc).__name__}: {exc}"
                run.observations.append(obs)
                if obs.error and "LLM call failed" in obs.error:
                    # TRANSIENT vs FATAL, and the five-arm pacing run of
                    # 2026-11-07 is why this distinction exists: a single
                    # Ollama HTTP 500 aborted the whole run twelve minutes
                    # in, after the injections had already been paid for.
                    # A model that does not exist is fatal and aborting is
                    # right; a 500 or a timeout from a model that answered a
                    # moment ago is weather.
                    fatal = any(w in obs.error.lower() for w in
                                ("does not exist", "not found", "404",
                                 "unauthorized", "401", "forbidden", "403"))
                    if fatal:
                        raise SystemExit(
                            f"ABORTING on a fatal LLM error: {obs.error}. "
                            f"The fault has been reverted. Recording hundreds "
                            f"of identical failures would waste the run.")
                    transient += 1
                    if transient > max_transient:
                        raise SystemExit(
                            f"ABORTING after {transient} transient LLM "
                            f"failures, the last: {obs.error}. The fault has "
                            f"been reverted. Past this many the model is not "
                            f"having a bad minute, it is unwell.")
                    say(f"      transient LLM failure {transient}/"
                        f"{max_transient}, retrying this cell after a pause")
                    time.sleep(10)
                    run.observations.pop()
                    rep -= 1
                    continue
                # `draw` is logged as well as stored because the log has twice
                # been the only surviving record of a run, and without it the
                # outcome cannot be attributed to the draw - the one thing
                # section 14 says is the treatment.
                say(f"    {fault_class}#{incident} arm {arm} rep {rep}: "
                    f"named={obs.named or '-'} closed(det)={obs.closed_detector} "
                    f"cited={obs.cited} tok={obs.prompt_tokens} draw={obs.draw}"
                    + (f"  {obs.error}" if obs.error else ""))
    finally:
        try:
            fault.revert()
        except Exception as exc:
            run.dropped.append(f"{fault_class}#{incident}: REVERT FAILED: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--classes", default="F01,F06,F07,F08")
    ap.add_argument("--incidents", type=int, default=15,
                    help="injections per fault class")
    ap.add_argument("--reps", type=int, default=3,
                    help="model samples per (incident, arm)")
    ap.add_argument("--distractors", type=int, default=40,
                    help="minimum distractor pool required, not a cap")
    # HOST address, not the container's. `settings.llm_base_url` is
    # host.docker.internal because that is what the API container needs; this
    # script runs on the host, where that name does not resolve. Every other
    # live harness defaults to 127.0.0.1 for the same reason, and the
    # preflight defect fixed on 2026-11-03 was this same confusion one layer
    # down.
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--provider", default="",
                    help="override KAVACH_LLM_PROVIDER. The container does "
                         "not receive .env - compose passes only what its "
                         "`environment:` block lists - so a provider set in "
                         ".env applies to this host-side script and NOT to "
                         "the API being measured. Default follows Settings; "
                         "pass `ollama` to match a container that has no "
                         "provider set.")
    ap.add_argument("--model", default="",
                    help="override KAVACH_LLM_MODEL. .env holds an Ollama "
                         "tag, and a cloud provider answers a 404 for it - "
                         "so a cross-provider run must name its own model "
                         "here rather than edit .env, which the in-flight "
                         "local runs also read.")
    ap.add_argument("--arms", default="".join(ARMS),
                    help="which arms to run, e.g. AB. A is mandatory: arm B "
                         "is size-matched to the control, so no arm can be "
                         "validated without it. Arms A, C, D and E are "
                         "saturated at 1.00 on qwen2.5:7b-instruct, so a "
                         "cross-provider check only needs A and B.")
    ap.add_argument("--shuffle", action="store_true",
                    help="shuffle item order in EVERY arm. Off by default so "
                         "arm A is the shipped frame exactly; on, it tests "
                         "whether position rather than composition drives any "
                         "difference")
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports"
                                / "closure-ablation.json"))
    args = ap.parse_args()

    settings = get_settings()
    client = TargetClient(TargetEndpoints(
        health=f"{TARGET}/healthz", chat=f"{TARGET}/v1/chat",
        config=f"{TARGET}/v1/admin/config",
        admin_token=settings.target_admin_token))
    provider = args.provider or settings.llm_provider
    model = args.model or settings.llm_model
    llm = providers.build(provider, model, ollama_base_url=args.ollama)

    arms = tuple(c for c in args.arms.strip().upper())
    unknown = [c for c in arms if c not in ARMS]
    if unknown:
        raise SystemExit(f"--arms {args.arms!r}: not an arm: "
                         f"{', '.join(unknown)}. Arms are {''.join(ARMS)}.")
    if "A" not in arms:
        raise SystemExit(
            "REFUSING: --arms must include A. Every other arm is validated "
            "against the control's item count, so dropping A does not save "
            "work - it makes the run unusable.")

    baseline, source = newest_baseline()
    if not baseline:
        raise SystemExit("no usable baseline; F07 and F08 would be undiagnosable")

    say("=" * 78)
    say("CLOSURE ABLATION - docs/EXPERIMENT_CLOSURE_ABLATION.md")
    say("=" * 78)
    say(f"  provider     {provider}"
        + ("  (overridden; .env says "
           f"{settings.llm_provider!r})" if args.provider else ""))
    say(f"  model        {model}"
        + ("  (overridden; .env says "
           f"{settings.llm_model!r})" if args.model else ""))
    say(f"  arms         {''.join(arms)}"
        + ("" if len(arms) == len(ARMS) else "  (subset)"))
    say(f"  ollama       {args.ollama}")
    say(f"  baseline     {source}")
    say(f"  shuffle      {args.shuffle}")

    distractors = scrape_distractors(TARGET, args.distractors)
    say(f"  distractors  {len(distractors)} real metrics no detector reads")
    say(f"               e.g. {', '.join(n for n, _ in distractors[:3])}")

    # A SIGKILL skips one_incident's `finally`, so a killed run leaves its
    # fault injected - which is exactly what happened on 2026-11-08 when the
    # host reaped the full run mid-F06. It must be checked FIRST: an injected
    # fault also fails the fast set, so behind that check the operator is told
    # to warm the target instead of to revert. Starting dirty would
    # measure the leftover and the new injection together, and nothing
    # downstream could tell the difference.
    dirty = [c for c in ("F01", "F06", "F07", "F08")
             if build(c, client).is_active()]
    if dirty:
        raise SystemExit(
            f"REFUSING: {', '.join(dirty)} already active on the target. "
            f"Nothing has been injected. A killed run cannot revert itself, "
            f"so this is most likely a leftover - `inject.py revert --all` "
            f"clears it.")

    # BEFORE ANY INJECTION. The first smoke run injected F08, then found the
    # model unreachable, then reverted - burning an injection to learn
    # something a probe answers for free. An unreachable model is also the
    # single likeliest way to lose a four-hour run.
    # `available()` alone is NOT enough, and the second smoke run proved it:
    # it probes whether the PROVIDER answers, not whether it serves this
    # MODEL. Against a provider that was up but had never heard of
    # qwen2.5:7b-instruct it returned True, the run injected a fault, and
    # every arm then failed with a 404. So the probe is a real structured
    # call - the same kind the experiment makes - and it happens before
    # anything is touched.
    probe_schema: dict[str, Any] = {
        "type": "object", "additionalProperties": False,
        "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
    }
    try:
        llm.structured("Reply with {\"ok\": true}.", "ping", probe_schema)
    except Exception as exc:
        raise SystemExit(
            f"REFUSING: provider {provider!r} cannot serve "
            f"{model!r}. Nothing has been injected. "
            f"[{type(exc).__name__}: {str(exc)[:160]}] "
            f"  The API container does not read .env - compose passes only "
            f"what its `environment:` block lists - so KAVACH_LLM_PROVIDER "
            f"in .env configures THIS script and not the system it measures. "
            f"Pass --provider ollama to match the container."
        ) from exc

    pre = fast.run(client, FAST_SET, check_health=True)
    if not pre.passed:
        raise SystemExit(
            "REFUSING: the fast set must pass before injecting. Warm the "
            "target first - a cold stack fails this and it is not a bug.")

    run = Run(at=datetime.now(UTC).isoformat(timespec="seconds"),
              model=f"{provider}:{model}", shuffled=args.shuffle)
    out = Path(args.json_out)

    def flush() -> None:
        """Write the artifact as it stands.

        Called after EVERY incident, not only at the end. Three runs in a row
        were lost - a memory reap, a timeout, and a KMODE_EXCEPTION bluescreen
        on 2026-11-09 - and each time the observations existed in the log but
        no artifact had been serialised, because serialising happened once in
        the `finally`. A `finally` does not run under SIGKILL or a kernel
        panic. Written to a temp file and replaced, so a crash mid-write
        cannot leave a half-parsed artifact either.
        """
        tmp = out.with_suffix(out.suffix + ".part")
        tmp.write_text(json.dumps(
            {"at": run.at, "model": run.model, "shuffled": run.shuffled,
             "arms": ARM_LABEL, "dropped": run.dropped,
             "complete": False,
             "observations": [o.__dict__ for o in run.observations]},
            indent=2), encoding="utf-8")
        tmp.replace(out)

    finished = False
    try:
        for fault_class in [c.strip() for c in args.classes.split(",") if c.strip()]:
            say("")
            say(f"--- {fault_class} ---")
            for incident in range(1, args.incidents + 1):
                one_incident(fault_class, incident, client, llm, baseline,
                             distractors, args.reps, args.shuffle, arms,
                             run)
                flush()
        finished = True
    finally:
        summarise(run)
        flush()
        # `complete` is only true when the loop ran to the end. The `finally`
        # also runs when the harness ABORTS - a fatal provider error, the
        # transient budget exhausted - and marking those complete would be
        # the same mistake as serialising only at the end.
        if finished:
            doc = json.loads(out.read_text(encoding="utf-8"))
            doc["complete"] = True
            out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        say("")
        say(f"  artifact {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
