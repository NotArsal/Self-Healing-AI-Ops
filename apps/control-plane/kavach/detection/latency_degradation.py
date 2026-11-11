"""F02 primary LLM endpoint latency degradation - deterministic detection.

No LLM. Same shape as `endpoint_outage` (F01), and deliberately its mirror.

THE DISCRIMINATOR
F01 and F02 share an endpoint and a repair, and differ in one thing: under F01
the model is never reached, under F02 it is reached and answers late.

  llm error ratio >= 0.50                 -> the endpoint refuses (F01)
  error ratio < 0.50 + generation slow    -> the endpoint is slow (F02)

The 0.50 boundary is F01's own `error_ratio_floor`, used here from the other
side, so there is no band in which both claim and none in which a total outage
reads as slowness. Measured 2026-11-10 (`harness/sweep_f02_latency.py`): the
12s injector produces generation calls of ~13s and ZERO errors across every
LLM operation, so F02 lands far from that boundary.

THE THRESHOLD: 2 x THE DECLARED SLO
PRD section 6 detects F02 at "p95 LLM operation duration > SLO x 2". The
target declares `llm_latency_p95 < 4.0` in `kavach.yaml`, so 8.0s. Twice the
*measured* healthy p95 (0.94s) would be 1.9s, inside run-to-run jitter. 8.0 is
also a bucket edge of `ragapp_llm_duration_seconds`, which matters:
`histogram_quantile` interpolates inside a bucket, so ">8" means "more than
5% of the window's generation calls landed past the 8s edge".

WHY 2m AND NOT THE SLO'S 5m
`endpoint_outage.QUERIES` records a 5m window claiming an outage on a healthy
system from residue, and that residue then mis-attributing a later F06.
Latency residue would do the same to F07 and F08, whose fast sets fail too.

LATENCY IS SLOWER TO SURFACE THAN AN OUTAGE, BY CONSTRUCTION
A histogram observes a call when it ENDS. A refused call ends in milliseconds;
a slow one ends after the delay. So the first F02 evidence cannot exist until
a slow generation completes, and p95 crosses only once slow calls exceed 5%
of the window. Detection time is measured in the acceptance run, not assumed.
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
from kavach.detection.endpoint_outage import Thresholds as OutageThresholds
from kavach.promscope import scope

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

FAULT_CLASS = "F02"
FAULT_NAME = "latency_degradation"
SERVICE = "backend"


@dataclass(frozen=True)
class Thresholds:
    # 2 x `llm_latency_p95 < 4.0` declared in the target's kavach.yaml.
    p95_floor_s: float = 8.0
    # F01's floor, from the other side. Imported, not copied, so the two can
    # never drift apart into a band where both claim.
    error_ratio_ceiling: float = OutageThresholds().error_ratio_floor
    # Healthy generation never exceeded 1s in 204 of 204 calls (2026-11-10),
    # so even one slow call is real evidence; but p95 over zero calls is
    # undefined, so at least one generation must have completed in the window.
    min_generations: float = 1.0


QUERIES: dict[str, str] = {
    "generation_p95_s": (
        "histogram_quantile(0.95, sum by (le) (rate("
        'ragapp_llm_duration_seconds_bucket{operation="generation"}[2m])))'
    ),
    "generations": (
        'sum(increase(ragapp_llm_requests_total{operation="generation"}[2m])) '
        "or vector(0)"
    ),
    # The same expression and window as `endpoint_outage`, so the boundary
    # between the two detectors is read from one number.
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

    ev.append(Evidence(
        kind="fast_verification",
        source="kavach/verification/fast_set.yaml",
        value=f"{fast_set_pass_rate:.0%} pass",
        expected="100% pass within the time budget",
        supports_fault=not fast_set_passed,
    ))

    gens = metrics.get("generations")
    p95 = metrics.get("generation_p95_s")
    ratio = metrics.get("llm_error_ratio")

    if gens is None or gens < t.min_generations:
        reasons.append(
            f"{0 if gens is None else gens:.1f} generation calls completed in the "
            f"window; a latency quantile over none is undefined. A slow call is "
            f"only observed when it ends")
        ev.append(Evidence("generations", "ragapp_llm_requests_total",
                           gens, f">= {t.min_generations}", False))
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    if p95 is None or ratio is None:
        missing = [k for k, v in (("generation_p95_s", p95), ("llm_error_ratio", ratio))
                   if v is None]
        reasons.append(f"no series for {missing}; cannot separate slow from down")
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    slow = p95 > t.p95_floor_s
    answering = ratio < t.error_ratio_ceiling
    ev.append(Evidence(
        kind="generation_p95_s",
        source='ragapp_llm_duration_seconds_bucket{operation="generation"}',
        value=round(p95, 3),
        expected=f"> {t.p95_floor_s}s (2 x the declared 4.0s SLO)",
        supports_fault=slow,
    ))
    ev.append(Evidence(
        kind="llm_error_ratio",
        source='ragapp_llm_requests_total{outcome!="ok"} / total',
        value=round(ratio, 3),
        expected=f"< {t.error_ratio_ceiling} (the model is answering; at or "
                 f"above this it is an outage, F01)",
        supports_fault=answering,
    ))

    if not slow:
        reasons.append(f"generation p95 {p95:.2f}s is within {t.p95_floor_s}s")
        verdict = Verdict.NO_FAULT if fast_set_passed else Verdict.INSUFFICIENT_EVIDENCE
        if not fast_set_passed:
            reasons.append("the fast set fails, but not because generation is slow")
        return Detection(verdict, evidence=ev, reasons=reasons)

    if not answering:
        reasons.append(
            f"generation is slow but {ratio:.1%} of LLM calls are failing: that is "
            f"an outage, which is F01's to claim, not a slowdown")
        return Detection(Verdict.INSUFFICIENT_EVIDENCE, evidence=ev, reasons=reasons)

    if fast_set_passed:
        reasons.append(
            "generation was slow over the window but the fast set passes within "
            "its time budget now - residue from a slowdown that has already "
            "ended. No repair is proposed against a system that is working")
        return Detection(Verdict.NO_FAULT, evidence=ev, reasons=reasons)

    reasons.append(
        f"generation p95 is {p95:.1f}s against an {t.p95_floor_s}s floor while "
        f"only {ratio:.1%} of LLM calls fail: the endpoint answers, late")
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
        key: signals.promql(signals.prometheus_url, scope(signals.project, expr))
        for key, expr in QUERIES.items()
    }


SPEC = DetectorSpec(
    fault_class=FAULT_CLASS,
    fault_name=FAULT_NAME,
    service=SERVICE,
    collect=collect,
    evaluate=evaluate,
    # LOW per PRD section 6: config-only, instantly reversible, shared with F01.
    repair_action="switch_llm_endpoint",
)
