"""F01 primary LLM endpoint outage — deterministic detection.

No LLM. Every signal is a number read from Prometheus or a boolean from the
fast-verification set, and the same inputs always produce the same verdict.

THIS IS THE EASY CASE, AND THAT IS WHY IT IS WORTH HAVING
`F06` is the project's hard case: the application returns HTTP 200 with
"I don't know based on the provided documents", nothing 5xxs, and detection has
to come from grounding metrics because HTTP status carries no information at
all. `F01` is the exact opposite. The configured endpoint refuses connections,
so the target's own `/healthz` answers **503** and every LLM call records
`outcome="error"`. Measured 2026-10-16: the target surfaced the outage in
**0.034s**, because a disabled listener refuses rather than hangs.

Having both shapes in the catalogue is what stops the research claim resting on
one fault. A system that only ever detects silent-200 faults has not been shown
to detect outages, and vice versa.

THE DISCRIMINATOR THAT MATTERS
`F01` and `F06` both end with the fast set failing, so the fast set alone
cannot tell them apart. The separator is **whether the model answered at all**:

  llm error ratio HIGH                 -> the endpoint is gone (F01)
  llm error ratio ~0 + grounding lost  -> it answered from nothing (F06)

So this detector requires a genuinely elevated error ratio and reports
INSUFFICIENT_EVIDENCE rather than guessing when the series are missing.

AND THAT IS NOT ENOUGH ON ITS OWN - THE FIRST LIVE RUN PROVED IT
This module first claimed the two detectors were "mutually exclusive on live
evidence". They are not, and the assumption was mine rather than a
measurement. Under a real outage the EMBEDDING call goes through the same
broken endpoint, so nothing is retrieved and grounding collapses too, while
`similarity_p50` is a 10-minute quantile still holding pre-outage
observations - which is F06's discriminator reading TRUE on an F01. Measured:
`kept_chunks 0.4, empty_context 0.85, similarity_p50 0.675,
llm_error_ratio 1.0`. Both detectors claimed, `run_all()` refused to choose,
and the incident escalated without acting.

The separation is therefore enforced from BOTH sides: this detector requires a
high error ratio, and `retrieval_collapse.py` now requires a LOW one, because
"chunks are retrieved and then filtered out" presupposes that retrieval
happened. Both use the same 0.50 boundary on purpose - if they disagreed there
would be a band in which both claim and nothing can be repaired.

WHY NOT JUST READ /healthz
Because a health probe is a liveness signal and this has to be a *diagnosis*.
`/healthz` going 503 says "something about Ollama is wrong", which is also true
during `F02` latency degradation and during a model-not-pulled
misconfiguration. The error-ratio and request-rate series say which, and they
are what the RCA stage cites. The health probe is still collected as
corroborating evidence, not as the decision.

NOT MEASURED YET
The error-ratio floor below is reasoned from the metric's own semantics, not
swept: with the listener disabled EVERY request fails, so the ratio under fault
is 1.0 rather than something marginal, and any floor in (0, 1) separates it
from a healthy 0.0. A sweep would be theatre. What DOES still need measuring is
the behaviour of a PARTIAL outage - some requests failing - which is where the
floor's exact value would start to matter. `F02` is the phase that forces it.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    "Thresholds",
    "collect",
    "evaluate",
]

FAULT_CLASS = "F01"
FAULT_NAME = "endpoint_outage"
SERVICE = "backend"


@dataclass(frozen=True)
class Thresholds:
    """Reasoned from the metric's semantics; see NOT MEASURED YET above.

    Healthy readings on 2026-10-16: error ratio 0.0 across 208 requests
    (`ragapp_llm_requests_total{outcome="ok"}` only), generation requests
    flowing.
    """

    error_ratio_floor: float = 0.50   # half of all calls failing is not noise
    # Below this many requests in the window the ratio is not meaningful: one
    # failure out of one request is a 1.0 ratio and tells you nothing.
    min_requests: float = 3.0


# PromQL for the signals this detector uses. None means no series, which is NOT
# zero and is treated as missing evidence.
#
# The `outcome` label is the whole basis of this detector and it already exists
# on the target's instrumentation from P1 - nothing was added to the target for
# F01.
QUERIES: dict[str, str] = {
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
    # SAME WINDOW as the ratio above, deliberately: a gate that counts
    # traffic the ratio does not look at would admit a ratio computed from
    # three requests while claiming it saw thirty.
    "llm_requests": "sum(increase(ragapp_llm_requests_total[2m])) or vector(0)",
    "llm_ok_rate": (
        'sum(rate(ragapp_llm_requests_total{outcome="ok"}[2m])) or vector(0)'
    ),
    # Corroboration, never the decision. See WHY NOT JUST READ /healthz.
    "generation_requests": (
        'sum(increase(ragapp_llm_requests_total{operation="generation"}[2m])) '
        "or vector(0)"
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

    ratio = metrics.get("llm_error_ratio")
    requests = metrics.get("llm_requests")
    ok_rate = metrics.get("llm_ok_rate")

    # --- the quality probe: the user-visible symptom
    ev.append(Evidence(
        kind="fast_verification",
        source="kavach/verification/fast_set.yaml",
        value=f"{fast_set_pass_rate:.0%} pass",
        expected="100% pass",
        supports_fault=not fast_set_passed,
    ))

    # --- is there enough traffic for a ratio to mean anything
    if requests is None:
        reasons.append("llm_requests has no series; cannot assess the endpoint")
        ev.append(Evidence("llm_requests", "ragapp_llm_requests_total", None,
                           f">= {t.min_requests}", False))
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    ev.append(Evidence("llm_requests", "ragapp_llm_requests_total",
                       round(requests, 1), f">= {t.min_requests} for a "
                       f"meaningful ratio", False))
    if requests < t.min_requests:
        reasons.append(
            f"only {requests:.1f} LLM requests in the window, below the "
            f"{t.min_requests} needed for an error ratio to mean anything. "
            f"An idle system is not a healthy system and is not a broken one"
        )
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    # --- the discriminator: did the model answer at all
    if ratio is None:
        reasons.append("llm_error_ratio has no series; cannot distinguish an "
                       "endpoint outage from a grounding fault")
        ev.append(Evidence("llm_error_ratio", "ragapp_llm_requests_total{outcome}",
                           None, f">= {t.error_ratio_floor}", False))
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    endpoint_failing = ratio >= t.error_ratio_floor
    ev.append(Evidence(
        kind="llm_error_ratio",
        source='ragapp_llm_requests_total{outcome!="ok"} / total',
        value=round(ratio, 3),
        expected=f">= {t.error_ratio_floor} (a high ratio means the model was "
                 f"never reached, which separates this from a grounding fault)",
        supports_fault=endpoint_failing,
    ))
    if ok_rate is not None:
        ev.append(Evidence("llm_ok_rate", 'ragapp_llm_requests_total{outcome="ok"}',
                           round(ok_rate, 4), "~0 under an outage",
                           ok_rate <= 0.0))

    # --- the decision
    if not endpoint_failing and fast_set_passed:
        reasons.append("the endpoint is answering and the fast set passes")
        return Detection(Verdict.NO_FAULT, evidence=ev, reasons=reasons)

    # The fast set is measured NOW; the error ratio is a rate over a 5-minute
    # window and therefore lags. The same stale-window trap as F06: without
    # requiring current evidence, residue from an already-reverted outage would
    # drive a repair against a healthy system and be recorded as a heal of
    # nothing.
    if fast_set_passed:
        reasons.append(
            "the error ratio is elevated over the window but the fast set "
            "passes now, so the endpoint is serving at this moment - most "
            "likely residue from a recent, already-resolved outage. No repair "
            "is proposed against a system that is working"
        )
        return Detection(Verdict.NO_FAULT, evidence=ev, reasons=reasons)

    if not endpoint_failing:
        reasons.append(
            f"the fast set failed but only {ratio:.1%} of LLM calls errored, so "
            f"the model is being reached and this is not an endpoint outage. A "
            f"failover would move a working endpoint and fix nothing"
        )
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    reasons.append(
        f"{ratio:.1%} of LLM calls are failing while requests are still being "
        f"attempted: the configured endpoint is refusing them, so the model is "
        f"never reached"
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
    # LOW risk per ARCHITECTURE.md §6.2: config-only, instantly reversible, no
    # data touched. LOW is what gives PRD.md §8.2 its autonomous demo path -
    # this is the one fault class that `permit()` will ALLOW_AUTO.
    repair_action="switch_llm_endpoint",
)
