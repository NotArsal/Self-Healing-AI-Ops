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
"""

from __future__ import annotations

from collections.abc import Callable
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


# PromQL for the signals this detector uses. None means no series, which is NOT
# zero and is treated as missing evidence.
QUERIES: dict[str, str] = {
    "similarity_p50": (
        "histogram_quantile(0.50, sum by (le) "
        "(rate(ragapp_retrieval_top_similarity_bucket[10m])))"
    ),
    "kept_chunks_mean": (
        "rate(ragapp_retrieval_kept_chunks_sum[10m]) "
        "/ clamp_min(rate(ragapp_retrieval_kept_chunks_count[10m]), 1e-9)"
    ),
    "empty_context_ratio": (
        "(sum(rate(ragapp_retrieval_empty_context_total[10m])) or vector(0)) "
        "/ clamp_min(sum(rate(ragapp_retrieval_kept_chunks_count[10m])), 1e-9)"
    ),
    "corpus_chunks": "ragapp_corpus_chunks",
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


def collect(
    prometheus_url: str, promql: Callable[[str, str], float | None]
) -> dict[str, float | None]:
    """Read the detector's signals. `promql` is injected so tests stay offline."""
    return {name: promql(prometheus_url, expr) for name, expr in QUERIES.items()}


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
