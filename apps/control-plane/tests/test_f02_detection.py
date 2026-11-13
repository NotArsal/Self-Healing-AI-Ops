"""F02 latency-degradation detection, and its boundary with F01.

The readings are the ones measured on 2026-11-10 (`harness/sweep_f02_latency.py`):
healthy generation p95 0.975s with no errors; the 12s injector, generation
calls of ~13s (p95 reads 14.65 because every call lands in the (8, 15] bucket)
with zero errors. No network, no model.
"""

from __future__ import annotations

import pytest

from kavach.detection import base as det
from kavach.detection import (
    catalogue,  # noqa: F401 - registers the detectors
    endpoint_outage,
)
from kavach.detection.base import Signals, Verdict
from kavach.detection.latency_degradation import QUERIES, Thresholds, collect, evaluate

HEALTHY: dict[str, float | None] = {
    "generation_p95_s": 0.975, "generations": 3.0, "llm_error_ratio": 0.0}
SLOW: dict[str, float | None] = {
    "generation_p95_s": 14.65, "generations": 3.0, "llm_error_ratio": 0.0}


def test_a_slow_answering_endpoint_is_f02() -> None:
    d = evaluate(SLOW, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is Verdict.FAULT
    assert d.fault_class == "F02"


def test_a_healthy_endpoint_is_not_a_fault() -> None:
    d = evaluate(HEALTHY, fast_set_passed=True, fast_set_pass_rate=1.0)
    assert d.verdict is Verdict.NO_FAULT


def test_slow_and_failing_is_an_outage_and_left_to_f01() -> None:
    d = evaluate({**SLOW, "llm_error_ratio": 0.9},
                 fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert any("F01" in r for r in d.reasons)


def test_slowness_that_has_already_ended_is_residue_not_a_fault() -> None:
    d = evaluate(SLOW, fast_set_passed=True, fast_set_pass_rate=1.0)
    assert d.verdict is Verdict.NO_FAULT


def test_no_completed_generation_means_no_quantile_and_no_verdict() -> None:
    d = evaluate({**SLOW, "generations": 0.0},
                 fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is Verdict.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("missing", ["generation_p95_s", "llm_error_ratio"])
def test_a_missing_series_is_not_read_as_zero(missing: str) -> None:
    d = evaluate({**SLOW, missing: None}, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is Verdict.INSUFFICIENT_EVIDENCE


def test_a_failing_fast_set_without_slowness_is_not_claimed() -> None:
    d = evaluate(HEALTHY, fast_set_passed=False, fast_set_pass_rate=0.33)
    assert d.verdict is Verdict.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("ratio", [0.0, 0.25, 0.49, 0.50, 0.75, 1.0])
def test_f01_and_f02_never_both_claim_at_any_error_ratio(ratio: float) -> None:
    """The boundary is one number read from both sides."""
    f02 = evaluate({**SLOW, "llm_error_ratio": ratio},
                   fast_set_passed=False, fast_set_pass_rate=0.0)
    f01 = endpoint_outage.evaluate(
        {"llm_error_ratio": ratio, "llm_requests": 12.0, "llm_ok_rate": 0.1,
         "generation_requests": 3.0},
        fast_set_passed=False, fast_set_pass_rate=0.0)
    claims = [d for d in (f01, f02) if d.verdict is Verdict.FAULT]
    assert len(claims) == 1


def test_the_boundary_is_imported_from_f01_not_copied() -> None:
    assert Thresholds().error_ratio_ceiling == endpoint_outage.Thresholds().error_ratio_floor


def test_the_floor_is_twice_the_declared_slo() -> None:
    assert Thresholds().p95_floor_s == 2 * 4.0


def test_registered_with_the_shared_repair() -> None:
    spec = next(s for s in det.registry.specs() if s.fault_class == "F02")
    assert spec.repair_action == "switch_llm_endpoint"


def test_collect_reads_every_query_through_the_injected_promql() -> None:
    seen: list[str] = []

    def fake(_url: str, expr: str) -> float | None:
        seen.append(expr)
        return 1.0

    readings = collect(Signals(prometheus_url="http://prom", promql=fake))
    assert set(readings) == set(QUERIES)
    assert seen == list(QUERIES.values())


# --- F06 must not claim from a window with no retrievals in it --------------
# Bench 2026-11-10, INC-201735: under F02 a chat takes ~78s, so F06's [1m]
# kept_chunks window often holds no retrieval. The query divided by
# `clamp_min(count, 1e-9)` and read that as 0 kept chunks - F06's own
# signature - so F06 claimed beside F02 and the loop refused to choose.


def test_kept_chunks_reads_an_empty_window_as_no_series_not_zero() -> None:
    from kavach.detection import retrieval_collapse
    from kavach.rca.evidence import METRIC_QUERIES as FRAME_QUERIES

    q = retrieval_collapse.QUERIES["kept_chunks_mean"]
    assert "clamp_min" not in q and "> 0)" in q
    assert FRAME_QUERIES["retrieval_kept_chunks_mean"] == q


def test_f02_with_an_empty_retrieval_window_is_claimed_by_f02_alone() -> None:
    from kavach.detection import retrieval_collapse

    values: dict[str, float | None] = {
        **{QUERIES[k]: v for k, v in SLOW.items()},
        **dict(zip(endpoint_outage.QUERIES.values(), (0.0, 12.0, 0.2, 3.0), strict=True)),
        retrieval_collapse.QUERIES["similarity_p50"]: 0.65,
        retrieval_collapse.QUERIES["kept_chunks_mean"]: None,  # no series
        retrieval_collapse.QUERIES["empty_context_ratio"]: 0.0,
        "ragapp_corpus_chunks": 30.0,
    }
    specs = [s for s in det.registry.specs() if s.fault_class in {"F01", "F02", "F06"}]
    d = det.run_all(specs, Signals(prometheus_url="http://prom",
                                   promql=lambda _u, e: values[e]),
                    fast_set_passed=False, fast_set_pass_rate=1.0)
    assert d.verdict is Verdict.FAULT
    assert d.fault_class == "F02"


def test_ev_v00_names_the_probe_that_failed_not_just_the_verdict() -> None:
    """`FAIL (100% of cases)` read as "every case failed"; the model then said F06."""
    from kavach.rca.evidence import fast_set_summary
    from kavach.verification.fast import CaseResult, FastVerificationResult

    def run(ok: bool, total_s: float) -> FastVerificationResult:
        case = CaseResult("c1", "q", "kw", ok, ok, ok, total_s / 3)
        return FastVerificationResult(cases=[case] * 3, total_s=total_s,
                                      budget_s=180, health_ok=True)

    slow = fast_set_summary(run(True, 236.0))  # F02: correct but late
    assert slow == ("FAIL: health ok, 100% of cases passed, "
                    "took 236s, OVER the 180s budget")
    wrong = fast_set_summary(run(False, 30.0))  # quality fault, on time
    assert wrong.startswith("FAIL") and "0% of cases passed" in wrong
    assert "within the 180s budget" in wrong
    assert fast_set_summary(run(True, 30.0)).startswith("PASS")


def test_ev_v00_says_when_the_cases_ran_at_once() -> None:
    """ADR 0026. In parallel the time is the slowest case; read as a serial
    total, '83s, within the budget' would understate an F02 latency."""
    from kavach.rca.evidence import fast_set_summary
    from kavach.verification.fast import CaseResult, FastVerificationResult

    case = CaseResult("c1", "q", "kw", True, True, True, 83.0)
    r = FastVerificationResult(cases=[case] * 3, total_s=83.0, budget_s=120,
                               health_ok=False, parallel=True)
    assert fast_set_summary(r) == (
        "FAIL: health FAIL, 100% of cases passed, took 83s with all cases "
        "asked at once, within the 120s budget")
