"""F06 retrieval collapse — deterministic detection.

No LLM. Every signal is a number read from Prometheus or a boolean from the
fast-verification set, and the same inputs always produce the same verdict.

WHY HTTP STATUS IS USELESS HERE
During a retrieval collapse the application returns HTTP 200 with
"I don't know based on the provided documents." Nothing 5xxs, liveness passes,
and `http_requests_total` stays entirely in the 2xx bucket. That is the whole
premise of the project: the system is up and wrong. Detection must therefore
come from application-level evidence.

THE DISCRIMINATOR THAT MATTERS
`ragapp_retrieval_top_similarity` is RAW embedding similarity, observed BEFORE
reranking. A rerank threshold set too high filters chunks out *after* that
measurement, so similarity stays healthy while kept-chunks goes to zero. Broken
embeddings or an emptied corpus would instead drag similarity down too.

  similarity HEALTHY + kept_chunks ZERO  -> the filter is wrong (F06 by config)
  similarity COLLAPSED                   -> embeddings/corpus, a different fault

Conflating those two would send a config rollback at a corpus problem, which is
the symptom-matching failure mode this project is supposed to avoid. So the
detector requires healthy similarity to claim `retrieval_collapse`, and reports
INSUFFICIENT_EVIDENCE rather than guessing when the evidence is mixed.

THE ENDPOINT PRECONDITION, ADDED IN P6 WHEN F01 EXPOSED THE GAP
The discriminator above is necessary and was not sufficient. It says "chunks
are retrieved and then filtered out", and that presupposes retrieval HAPPENED -
which presupposes the query was embedded, which presupposes the LLM endpoint
answered. During a real `F01` endpoint outage none of that holds, yet the
reading looks identical to this detector: the embedding call fails, so nothing
is retrieved and grounding collapses, while `similarity_p50` is a 10-minute
quantile that still holds pre-outage observations and still looks healthy.

Measured on the first live F01, 2026-10-16: `kept_chunks 0.4,
empty_context 0.85, similarity_p50 0.675` - and `llm_error_ratio 1.0`. This
detector claimed, `F01`'s detector claimed, the registry refused to choose
between two live diagnoses, and nothing was repaired. Correct, and useless.

`llm_error_ratio` is therefore read as a PRECONDITION rather than as a
retrieval signal: above the ceiling, no retrieval is happening at all and this
cannot be the fault, whatever the grounding numbers say. This detector was
under-specified for as long as it was the only one, which is precisely the test
`ROADMAP.md` said the first fault added after P5 would be.
"""

from __future__ import annotations

from dataclasses import dataclass

# Re-exported deliberately. These used to be DEFINED here, which is why
# `loop.py`, `rca/` and every harness imported them through this F06 module and
# so depended on a RAG fault to get a generic type. They now live in
# `detection/base.py`; keeping the names importable from here means that move
# cost no churn at the call sites, and new code should import from base.
from kavach.detection.base import (
    Detection,
    DetectorSpec,
    Evidence,
    Readings,
    Signals,
    Verdict,
)

__all__ = [
    "FAULT_CLASS",
    "FAULT_NAME",
    "QUERIES",
    "SERVICE",
    "SPEC",
    "Detection",
    "Evidence",
    "Thresholds",
    "Verdict",
    "collect",
    "evaluate",
]

FAULT_CLASS = "F06"
FAULT_NAME = "retrieval_collapse"
SERVICE = "backend"


@dataclass(frozen=True)
class Thresholds:
    """Derived from the measured healthy baseline, not invented.

    Healthy readings on 2026-10-03: similarity p50 0.658, kept-chunks mean 2.73,
    empty-context ratio 0.0, fast set 3/3.
    """

    similarity_floor: float = 0.50       # kavach.yaml retrieval_similarity_p50
    empty_context_ceiling: float = 0.20  # kavach.yaml empty_context_ratio
    kept_chunks_floor: float = 1.0       # fewer than one chunk is no grounding
    # Above this, the model is not being reached and no retrieval is happening,
    # so this detector must not claim whatever the grounding metrics say. Same
    # value as F01's floor, deliberately: the two detectors have to agree on
    # where "the endpoint is broken" starts, or there is a band in which both
    # claim and the loop refuses. See the ENDPOINT PRECONDITION note above.
    llm_error_ceiling: float = 0.50


# PromQL for the signals this detector uses. None means no series, which is NOT
# zero and is treated as missing evidence.
QUERIES: dict[str, str] = {
    "similarity_p50": (
        "histogram_quantile(0.50, sum by (le) "
        "(rate(ragapp_retrieval_top_similarity_bucket[10m])))"
    ),
    # WINDOW MEASURED, NOT CHOSEN - 1m, and 10m was the demo-killer.
    #
    # This is the signal that GATES an F06 claim: similarity_p50 must stay
    # healthy during a retrieval collapse and empty_context_ratio is
    # secondary, so kept_chunks falling below the floor is what makes the
    # detector speak. At [10m] it needed minutes of driven load to fall, and
    # `PRD.md` section 12 records that blocking detection three separate
    # times.
    #
    # SHORTENING IT IS NOT A SPEC CHANGE, which is what the earlier write-up
    # got wrong. `retrieval_similarity_p50` and `empty_context_ratio` each
    # mirror a declared `window_s: 600` in the target's manifest and are
    # deliberately left at [10m]. `kept_chunks` HAS NO SLO IN kavach.yaml -
    # its only appearance there is as the denominator inside
    # empty_context_ratio's expression - so there is no declared contract for
    # this window to diverge from. Same situation as F01's error ratio, which
    # went [5m] -> [2m] on the same reasoning.
    #
    # Measured live 2026-10-18, five candidate windows, on the real stack
    # (harness/window_sweep_f06.py, artifact harness/reports/):
    #
    #     window   at rest   detects fault   forgets a prior fault
    #     30s      healthy   36.5s           19.1s
    #     1m       healthy   55.0s           19.1s     <- chosen
    #     2m       healthy   91.9s           19.1s
    #     5m       healthy   202.5s          96.7s
    #     10m      healthy   92-241s         19.1s
    #
    # No window produces a false positive on a drained healthy system; every
    # one reads 2.0-4.0 against the 1.0 floor. The case against [10m] is the
    # SPREAD: three runs measured 106s, 92s and 241s, because its latency
    # depends on how much healthy traffic preceded the fault. That history
    # dependence IS the cross-fault contamination in PRD section 12. 30s and
    # 1m were consistent across every run.
    #
    # 1m OVER 30s, despite 30s being faster and equally clean at rest, on the
    # precedent F01's note sets two entries below: sample headroom. A cold
    # fast-set round takes 33.9s, so a 30s window can hold less than one full
    # round, and `rate()` needs two samples to return anything. Sparse, it
    # returns None, which this detector correctly reads as missing evidence
    # rather than zero - safe, but blind at exactly the moment it is asked.
    # 1m holds about three rounds and still cuts worst-case detection from
    # 241s to 55s.
    "kept_chunks_mean": (
        "rate(ragapp_retrieval_kept_chunks_sum[1m]) "
        "/ clamp_min(rate(ragapp_retrieval_kept_chunks_count[1m]), 1e-9)"
    ),
    # WINDOW MEASURED, NOT CHOSEN - 1m, and this one IS a spec change.
    #
    # Unlike kept_chunks_mean two entries above, this signal mirrors a
    # declared `window_s: 600` in the target's manifest, so shortening it in
    # the detector alone would diverge from the contract. The manifest was
    # changed in the same commit and `ADR 0010` records why.
    #
    # It had to move because F06 claims on `kept_chunks low OR
    # empty_context high`. Once kept_chunks went to [1m] this became the SOLE
    # remaining contaminator, and on its own it was enough: measured
    # 2026-10-18, at [10m] it takes 494.1s - over eight minutes - to forget a
    # fault. For that whole time, any NEXT fault of any class is diagnosed
    # ambiguously, because F06 claims from the stale ratio alongside whatever
    # detector is actually right. Observed three times in a row on F07 and
    # F08 before it was understood.
    #
    #     window   detects fault   forgets it
    #     30s      18.6s           19.3s
    #     1m       37.7s           59.1s      <- chosen
    #     2m       56.6s           99.4s
    #     5m       76.0s           255.5s
    #     10m      131.9s          494.1s
    #
    # 1m over 30s to match kept_chunks_mean and for the same sample-headroom
    # reason, and because this ratio is the more fragile of the two: it is a
    # proportion with a 0.20 ceiling, so ONE empty context in a window
    # holding three requests reads 0.33. A shorter window makes a single
    # transient blip louder.
    #
    # WHAT THIS DOES NOT FIX, STATED PLAINLY: it shortens the collision
    # window from eight minutes to about one. It does not make a spurious
    # F06 claim impossible, because a blip inside that minute can still
    # coincide with another fault failing the fast set. Eliminating it would
    # mean requiring BOTH grounding signals rather than either, which makes
    # F06 strictly harder to detect and is a separate decision.
    "empty_context_ratio": (
        "(sum(rate(ragapp_retrieval_empty_context_total[1m])) or vector(0)) "
        "/ clamp_min(sum(rate(ragapp_retrieval_kept_chunks_count[1m])), 1e-9)"
    ),
    "corpus_chunks": "ragapp_corpus_chunks",
    # NOT a retrieval signal, and that is the point: it is the precondition.
    # "Chunks are retrieved and then filtered out" presupposes that retrieval
    # HAPPENED, which presupposes the embedding call succeeded. If the LLM
    # endpoint is refusing, no embedding was produced, nothing was retrieved,
    # and this is not a rerank-filter fault however the grounding metrics look.
    # WINDOW MEASURED, NOT CHOSEN - 2m, and 5m was wrong.
    #
    # This was [5m] and it made two faults contaminate each other. Measured
    # 2026-10-16 on a HEALTHY target, minutes after a sequence of F01 runs had
    # finished and been reverted:
    #
    #     [30s] 0.0   [1m] 0.0   [2m] 0.0   [5m] 0.565
    #
    # 0.565 is above the 0.50 floor, so a 5-minute window claimed an endpoint
    # outage on a healthy system purely from residue. It did real damage: on a
    # subsequent REAL F06 injection, F01 claimed from that residue, F06
    # correctly deferred to it via its endpoint precondition, and the loop
    # diagnosed F01 for an F06 fault.
    #
    # Nothing is lost by shortening. Measured during a genuine outage, every
    # window agreed because the outage is total: [1m] 1.0, [2m] 1.0, [5m] 1.0.
    # 2m over 1m only for sample headroom under the min_requests gate.
    "llm_error_ratio": (
        '(sum(rate(ragapp_llm_requests_total{outcome!="ok"}[2m])) or vector(0)) '
        "/ clamp_min(sum(rate(ragapp_llm_requests_total[2m])), 1e-9)"
    ),
}


def evaluate(
    metrics: dict[str, float | None],
    fast_set_passed: bool,
    fast_set_pass_rate: float,
    thresholds: Thresholds | None = None,
) -> Detection:
    """Decide from metric values and the fast-set outcome. Pure function."""
    t = thresholds or Thresholds()
    ev: list[Evidence] = []
    reasons: list[str] = []

    similarity = metrics.get("similarity_p50")
    kept = metrics.get("kept_chunks_mean")
    empty_ratio = metrics.get("empty_context_ratio")
    corpus = metrics.get("corpus_chunks")
    llm_errors = metrics.get("llm_error_ratio")

    # --- the quality probe: the user-visible symptom
    ev.append(Evidence(
        kind="fast_verification",
        source="kavach/verification/fast_set.yaml",
        value=f"{fast_set_pass_rate:.0%} pass",
        expected="100% pass",
        supports_fault=not fast_set_passed,
    ))

    # --- grounding: did any chunk survive the filter
    if kept is None:
        reasons.append("kept_chunks has no series; cannot assess grounding")
        ev.append(Evidence("kept_chunks", "ragapp_retrieval_kept_chunks",
                           None, f">= {t.kept_chunks_floor}", False))
    else:
        ev.append(Evidence("kept_chunks", "ragapp_retrieval_kept_chunks",
                           round(kept, 3), f">= {t.kept_chunks_floor}",
                           kept < t.kept_chunks_floor))

    if empty_ratio is None:
        reasons.append("empty_context_ratio has no series")
        ev.append(Evidence("empty_context_ratio", "ragapp_retrieval_empty_context_total",
                           None, f"< {t.empty_context_ceiling}", False))
    else:
        ev.append(Evidence("empty_context_ratio", "ragapp_retrieval_empty_context_total",
                           round(empty_ratio, 3), f"< {t.empty_context_ceiling}",
                           empty_ratio > t.empty_context_ceiling))

    # --- the discriminator: raw similarity, measured BEFORE reranking
    similarity_healthy: bool | None
    if similarity is None:
        similarity_healthy = None
        reasons.append("similarity_p50 has no series; cannot distinguish a bad "
                       "rerank filter from broken embeddings")
        ev.append(Evidence("similarity_p50", "ragapp_retrieval_top_similarity",
                           None, f">= {t.similarity_floor}", False))
    else:
        similarity_healthy = similarity >= t.similarity_floor
        ev.append(Evidence(
            kind="similarity_p50",
            source="ragapp_retrieval_top_similarity (pre-rerank)",
            value=round(similarity, 3),
            expected=f">= {t.similarity_floor} (healthy similarity means the "
                     f"filter is at fault, not the embeddings)",
            supports_fault=similarity_healthy,
        ))

    # --- corpus intact: rules out an emptied corpus masquerading as collapse
    if corpus is not None:
        ev.append(Evidence("corpus_chunks", "ragapp_corpus_chunks", int(corpus),
                           "> 0", False))
        if corpus <= 0:
            reasons.append("corpus is empty; this is not a rerank-filter fault")
            return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    # --- the endpoint precondition: was the model reached at all
    #
    # THIS WAS MISSING UNTIL F01 EXISTED, AND A LIVE RUN FOUND IT.
    # This detector's discriminator is "grounding is lost while raw similarity
    # stays healthy, so chunks are retrieved and then filtered out". During a
    # real endpoint outage that reads as TRUE and is wrong: the embedding call
    # goes through the same endpoint, so nothing is retrieved and grounding
    # collapses, while `similarity_p50` is a 10-minute quantile that still
    # holds pre-outage observations and therefore still looks healthy.
    #
    # Measured on the first live F01 run: kept_chunks 0.4, empty_context 0.85,
    # similarity_p50 0.675, llm_error_ratio 1.0. Both detectors claimed, the
    # registry refused to choose between them, and the incident escalated
    # without acting - correct, but it meant F01 could not be diagnosed.
    #
    # So the claim needs its precondition stated: filtering presupposes
    # retrieving, which presupposes the embedding call succeeded.
    if llm_errors is not None:
        ev.append(Evidence(
            kind="llm_error_ratio",
            source='ragapp_llm_requests_total{outcome!="ok"} / total',
            value=round(llm_errors, 3),
            expected=f"< {t.llm_error_ceiling} (retrieval cannot be at fault "
                     f"if the endpoint that embeds the query is refusing)",
            supports_fault=llm_errors < t.llm_error_ceiling,
        ))
        if llm_errors >= t.llm_error_ceiling:
            reasons.append(
                f"{llm_errors:.1%} of LLM calls are failing, so the query is "
                f"not being embedded and nothing is being retrieved. Grounding "
                f"is lost because there is no retrieval at all, not because a "
                f"filter discarded it - this is an endpoint fault, not a "
                f"rerank-threshold fault, and a config rollback would be the "
                f"wrong repair"
            )
            return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev,
                             reasons=reasons)

    # --- the decision
    grounding_lost = (
        (kept is not None and kept < t.kept_chunks_floor)
        or (empty_ratio is not None and empty_ratio > t.empty_context_ceiling)
    )

    if not grounding_lost and fast_set_passed:
        reasons.append("grounding intact and the fast set passes")
        return Detection(Verdict.NO_FAULT, evidence=ev, reasons=reasons)

    # The fast set is measured NOW; the grounding metrics are rates over a
    # 10-minute window and therefore lag. If the set passes, the system is
    # serving correctly at this moment whatever the window still remembers -
    # typically a fault that has already been reverted.
    #
    # Requiring current evidence is not a nicety. Without it a stale window
    # drives a repair against a healthy system, which is a self-inflicted
    # write and would be recorded as a successful heal of nothing.
    if fast_set_passed:
        reasons.append(
            "grounding metrics are degraded over the window but the fast set "
            "passes now, so the fault is not currently present - most likely "
            "residue from a recent, already-resolved collapse. No repair is "
            "proposed against a system that is working"
        )
        return Detection(Verdict.NO_FAULT, evidence=ev, reasons=reasons)

    if not grounding_lost:
        reasons.append(
            "the fast set failed but grounding metrics look healthy; the cause "
            "is not retrieval collapse"
        )
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    if similarity_healthy is None:
        reasons.append("grounding is lost but similarity is unavailable, so a bad "
                       "rerank filter cannot be distinguished from broken embeddings")
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    if not similarity_healthy:
        reasons.append(
            f"similarity {similarity:.3f} is below the {t.similarity_floor} floor, so "
            "retrieval is failing upstream of the rerank filter - embeddings or "
            "corpus, not a threshold. A config rollback would be the wrong repair"
        )
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    reasons.append(
        "grounding is lost while raw similarity stays healthy: chunks are being "
        "retrieved and then filtered out, which is the rerank threshold"
    )
    if not fast_set_passed:
        reasons.append("the fast set confirms the user-visible symptom")
    return Detection(
        verdict=Verdict.FAULT,
        fault_class=FAULT_CLASS,
        fault_name=FAULT_NAME,
        service=SERVICE,
        evidence=ev,
        reasons=reasons,
    )


def collect(signals: Signals) -> Readings:
    """Read the detector's signals. `promql` is injected so tests stay offline."""
    return {
        key: signals.promql(signals.prometheus_url, expr)
        for key, expr in QUERIES.items()
    }


SPEC = DetectorSpec(
    fault_class=FAULT_CLASS,
    fault_name=FAULT_NAME,
    service=SERVICE,
    collect=collect,
    evaluate=evaluate,
    # Measured and shipped in P2. MEDIUM risk: it changes application
    # behaviour and is reversible through the config interface plus git.
    repair_action="rollback_config",
)
