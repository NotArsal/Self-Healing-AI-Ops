"""F01 endpoint-outage detection, and the detector seam it is the test of.

`ROADMAP.md` P6 sets the bar: a new fault class supplies a detector, an
evidence set, a repair with its inverse and a verification probe, and changes
nothing in the core. These tests assert that bar directly, not just the
detector's arithmetic - the seam is the deliverable, F01 is only the first
thing to come through it.
"""

from __future__ import annotations

from typing import Any

import pytest

from kavach.detection import base as det
from kavach.detection import catalogue  # noqa: F401 - registers the detectors
from kavach.detection.base import Signals
from kavach.detection.endpoint_outage import (
    QUERIES,
    Thresholds,
    collect,
    evaluate,
)

# Measured healthy readings, 2026-10-16: 208 LLM requests in the window, all
# outcome="ok", so an error ratio of exactly 0.0.
HEALTHY: dict[str, float | None] = {
    "llm_error_ratio": 0.0,
    "llm_requests": 208.0,
    "llm_ok_rate": 0.69,
    "generation_requests": 11.0,
}

# Under a disabled listener EVERY call fails: the ratio is 1.0, not marginal.
OUTAGE: dict[str, float | None] = {
    "llm_error_ratio": 1.0,
    "llm_requests": 12.0,
    "llm_ok_rate": 0.0,
    "generation_requests": 3.0,
}


# --- 1. the two verdicts that matter ---------------------------------------


def test_healthy_endpoint_with_a_passing_set_is_no_fault() -> None:
    d = evaluate(HEALTHY, fast_set_passed=True, fast_set_pass_rate=1.0)
    assert d.verdict is det.Verdict.NO_FAULT
    assert not d.detected


def test_total_outage_with_a_failing_set_is_detected() -> None:
    d = evaluate(OUTAGE, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.FAULT
    assert d.fault_class == "F01"
    assert d.fault_name == "endpoint_outage"
    assert d.service == "backend"
    assert d.citations(), "a claim must cite the evidence that supports it"


# --- 2. the refusals -------------------------------------------------------


def test_an_idle_system_is_not_diagnosable() -> None:
    """One failure out of one request is a 1.0 ratio and means nothing."""
    d = evaluate({**OUTAGE, "llm_requests": 1.0},
                 fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE
    assert any("below the" in r for r in d.reasons)


def test_a_missing_series_is_not_read_as_zero() -> None:
    d = evaluate(dict.fromkeys(QUERIES),
                 fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE


def test_a_failing_set_with_a_reachable_endpoint_is_not_this_fault() -> None:
    """THE discriminator. This is what F06 looks like to F01's detector: the
    answers are wrong but the model was reached, so a failover would move a
    working endpoint and fix nothing."""
    d = evaluate(HEALTHY, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE
    assert any("not an endpoint outage" in r for r in d.reasons)


def test_a_stale_window_does_not_drive_a_repair() -> None:
    """Errors in the window but the set passes now: already-resolved residue.
    Repairing here would be a self-inflicted write recorded as a heal."""
    d = evaluate(OUTAGE, fast_set_passed=True, fast_set_pass_rate=1.0)
    assert d.verdict is det.Verdict.NO_FAULT
    assert any("already-resolved" in r for r in d.reasons)


def test_a_partial_failure_is_below_the_floor() -> None:
    d = evaluate({**OUTAGE, "llm_error_ratio": 0.25},
                 fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE


def test_the_floor_is_deliberately_stricter_than_the_manifest_slo() -> None:
    """The manifest declares `llm_error_ratio < 0.20` as an SLO BREACH. This
    detector requires 0.50 because a breach is not an outage: at 0.25 the model
    is still being reached most of the time, and failing over on that moves a
    working endpoint. Recorded as a test so the difference reads as a decision
    rather than as drift between two numbers for one signal."""
    assert Thresholds().error_ratio_floor == 0.50
    assert Thresholds().error_ratio_floor > 0.20


def test_collect_injects_promql_and_reads_every_declared_query() -> None:
    seen: list[str] = []

    def fake(_url: str, q: str) -> float | None:
        seen.append(q)
        return 1.0

    out = collect(Signals("http://unused", fake))
    assert set(out) == set(QUERIES)
    assert len(seen) == len(QUERIES)


# --- 3. the seam, which is the actual P6 deliverable -----------------------


def test_both_fault_classes_are_registered_with_a_buildable_repair() -> None:
    from kavach.executor import catalogue as action_catalogue  # noqa: F401
    from kavach.executor.base import registry as actions

    faults = det.registry.known_faults()
    assert {"F01", "F06"} <= set(faults)
    for fault_class, action in faults.items():
        assert actions.knows(action), f"{fault_class} -> {action!r} is unbuildable"


def test_f01_repairs_with_a_low_risk_action_so_it_can_run_unattended() -> None:
    """PRD §8.2's autonomous path depends on this: LOW is the only tier
    permit() returns ALLOW_AUTO for, so if F01's repair were MEDIUM there
    would be no autonomous demo at all."""
    from kavach.executor import catalogue as action_catalogue  # noqa: F401
    from kavach.executor.base import LOW
    from kavach.executor.base import registry as actions

    assert det.registry.repair_for("F01") == "switch_llm_endpoint"
    assert actions.tier("switch_llm_endpoint") == LOW


def test_a_detector_may_not_register_without_a_repair() -> None:
    r = det.DetectorRegistry()
    with pytest.raises(ValueError, match="repair_action"):
        r.register(det.DetectorSpec(
            fault_class="FXX", fault_name="x", service="backend",
            collect=lambda _s: {}, evaluate=lambda _m, _p, _r: det.Detection(
                det.Verdict.NO_FAULT),
            repair_action="",
        ))


def test_the_catalogue_is_assembled_in_exactly_one_place() -> None:
    r = det.DetectorRegistry()
    spec = det.DetectorSpec(
        fault_class="FXX", fault_name="x", service="backend",
        collect=lambda _s: {},
        evaluate=lambda _m, _p, _r: det.Detection(det.Verdict.NO_FAULT),
        repair_action="rollback_config",
    )
    r.register(spec)
    with pytest.raises(ValueError, match="already registered"):
        r.register(spec)


# --- 4. run_all: one verdict from many detectors ---------------------------


def _spec(name: str, verdict: det.Verdict, cls: str = "") -> det.DetectorSpec:
    def evaluate_(
        _m: dict[str, float | None], _passed: bool, _rate: float
    ) -> det.Detection:
        return det.Detection(verdict, fault_class=cls or None, fault_name=name)

    return det.DetectorSpec(
        fault_class=cls or name, fault_name=name, service="backend",
        collect=lambda _s: {}, evaluate=evaluate_,
        repair_action="rollback_config",
    )


def promql_none(_url: str, _q: str) -> float | None:
    return None


def test_one_claim_is_returned_as_is() -> None:
    specs = [_spec("a", det.Verdict.NO_FAULT, "FA"),
             _spec("b", det.Verdict.FAULT, "FB")]
    d = det.run_all(specs, det.Signals("http://u", promql_none), False, 0.0)
    assert d.verdict is det.Verdict.FAULT
    assert d.fault_class == "FB"


def test_two_claims_at_once_refuse_rather_than_choose() -> None:
    """Fail closed. Picking by registration order would be a guess dressed as
    a decision, and the wrong repair is worse than none."""
    specs = [_spec("a", det.Verdict.FAULT, "FA"),
             _spec("b", det.Verdict.FAULT, "FB")]
    d = det.run_all(specs, det.Signals("http://u", promql_none), False, 0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE
    assert d.fault_class is None, "an ambiguous verdict must name no class"
    assert any("claimed a fault at once" in r for r in d.reasons)


def test_a_missing_series_on_a_working_system_is_not_a_symptom() -> None:
    """The false alarm the suite caught. On a quiet target F01's series are
    empty; escalating a healthy system every run is how a gate gets disabled."""
    specs = [_spec("a", det.Verdict.NO_FAULT, "FA"),
             _spec("b", det.Verdict.INSUFFICIENT_EVIDENCE, "FB")]
    d = det.run_all(specs, det.Signals("http://u", promql_none),
                    fast_set_passed=True, fast_set_pass_rate=1.0)
    assert d.verdict is det.Verdict.NO_FAULT
    assert any("not a symptom" in r for r in d.reasons)


def test_a_missing_series_with_a_real_symptom_is_insufficient_evidence() -> None:
    specs = [_spec("a", det.Verdict.NO_FAULT, "FA"),
             _spec("b", det.Verdict.INSUFFICIENT_EVIDENCE, "FB")]
    d = det.run_all(specs, det.Signals("http://u", promql_none),
                    fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE


# The ACTUAL readings from the first live F01 run, 2026-10-16. Kept verbatim
# because they are the counter-example to the assumption this file was first
# written on - that F01 and F06 could not both claim.
LIVE_F01_READINGS: dict[str, float | None] = {
    "similarity_p50": 0.675,        # a STALE 10m quantile: still pre-outage
    "kept_chunks_mean": 0.4,        # collapsed: nothing is being retrieved
    "empty_context_ratio": 0.85,
    "corpus_chunks": 30.0,
    "llm_error_ratio": 1.0,         # the precondition that settles it
}


def test_an_endpoint_outage_also_destroys_grounding_which_is_the_trap() -> None:
    """Documents why F06 needed an endpoint precondition, with live readings.

    The original version of this test asserted the two detectors were mutually
    exclusive, and fed F06 HEALTHY grounding numbers to "prove" it. That was
    the assumption, not the measurement. On a real outage the embedding call
    goes through the same broken endpoint, so grounding collapses too, while
    `similarity_p50` is a 10-minute quantile that still holds pre-outage
    observations and therefore still looks healthy - which is exactly F06's
    discriminator reading TRUE on an F01.
    """
    from kavach.detection import retrieval_collapse as rc
    from kavach.detection.retrieval_collapse import Thresholds as F06Thresholds

    without_precondition = {k: v for k, v in LIVE_F01_READINGS.items()
                            if k != "llm_error_ratio"}
    fooled = rc.evaluate(without_precondition, fast_set_passed=False,
                         fast_set_pass_rate=0.0)
    assert fooled.detected, (
        "the trap must be real, or this test is not testing anything: without "
        "the error ratio, F06's own discriminator claims a real F01"
    )

    settled = rc.evaluate(LIVE_F01_READINGS, fast_set_passed=False,
                          fast_set_pass_rate=0.0)
    assert settled.verdict is det.Verdict.INSUFFICIENT_EVIDENCE
    assert not settled.detected
    assert any("endpoint fault, not a" in r for r in settled.reasons)

    # Both detectors must agree on where "the endpoint is broken" begins, or
    # there is a band in which both claim and the loop refuses to act.
    assert F06Thresholds().llm_error_ceiling == Thresholds().error_ratio_floor


def test_the_live_registry_returns_f01_alone_on_the_live_readings() -> None:
    """The end-to-end consequence: one claim, so a repair can be proposed."""
    merged = {**LIVE_F01_READINGS, **OUTAGE}

    def promql_live(_url: str, q: str) -> float | None:
        for key, expr in {**QUERIES}.items():
            if expr == q:
                return merged.get(key)
        from kavach.detection.retrieval_collapse import QUERIES as F06_QUERIES
        for key, expr in F06_QUERIES.items():
            if expr == q:
                return merged.get(key)
        return None

    d = det.run_all(det.registry.specs(),
                    det.Signals("http://u", promql_live),
                    fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.FAULT
    assert d.fault_class == "F01"


def test_a_real_f06_collapse_is_still_detected() -> None:
    """The precondition must not cost F06 its own fault: every call succeeded,
    the answers were simply ungrounded."""
    from kavach.detection import retrieval_collapse as rc

    f06 = rc.evaluate(
        {"similarity_p50": 0.657, "kept_chunks_mean": 0.0,
         "empty_context_ratio": 1.0, "corpus_chunks": 30.0,
         "llm_error_ratio": 0.0},
        fast_set_passed=False, fast_set_pass_rate=0.0,
    )
    assert f06.detected
    assert f06.fault_class == "F06"
    f01 = evaluate(HEALTHY, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert not f01.detected


def test_the_shared_detection_types_carry_no_fault_name() -> None:
    """The verdict enum used to have a RETRIEVAL_COLLAPSE member, which is what
    made the type un-shareable: a second detector cannot add a member to
    someone else's enum. WHICH fault is a field, not a verdict."""
    members = {v.value for v in det.Verdict}
    assert members == {"NO_FAULT", "FAULT", "INSUFFICIENT_EVIDENCE"}
    assert not any("RETRIEVAL" in m or "ENDPOINT" in m for m in members)


def test_the_f06_module_still_re_exports_the_shared_types() -> None:
    """The move cost no churn at the call sites, and that must stay true -
    `rca/`, the harnesses and the console client all import through it."""
    from kavach.detection import retrieval_collapse as rc

    assert rc.Detection is det.Detection
    assert rc.Verdict is det.Verdict
    assert rc.Evidence is det.Evidence


def test_every_registered_detector_reads_only_injected_promql() -> None:
    """No detector may reach the network itself: `collect` takes promql so the
    whole suite stays offline, and a detector that ignored it would make these
    tests hit a real Prometheus."""
    calls: list[str] = []

    def fake(_url: str, q: str) -> Any:
        calls.append(q)
        return None

    for spec in det.registry.specs():
        calls.clear()
        out = spec.collect(det.Signals("http://unreachable.invalid", fake))
        # Not every detector reads Prometheus. F08 and F07 compare the
        # target's control interface against the baseline capture, so with
        # neither supplied they legitimately make no promql call at all.
        #
        # Stated as a property rather than as a list of exempt classes,
        # because the list was the F08 special case this replaces and it
        # would have had to grow for every control-interface fault. What is
        # actually required of all of them is the same: a detector given
        # nothing readable reports MISSING, and never reaches the network to
        # find something.
        # What is actually required of all of them is the same: given nothing
        # readable, every reading comes back MISSING. A detector that reached
        # a real Prometheus behind the seam would return a number here, and a
        # detector that treated absence as zero would return one too - this
        # one assertion catches both, for a metric detector and a
        # control-interface detector alike.
        assert all(v is None for v in out.values()), (
            f"{spec.fault_class} returned a non-missing reading from entirely "
            f"absent evidence: {out}"
        )
        assert all(q for q in calls), f"{spec.fault_class} issued an empty query"


def test_both_detectors_read_the_same_error_signal() -> None:
    """F06 defers to F01 on this signal, so they must read it identically.

    They did not. F01 used `[5m]` while the evidence frame used `[5m]` with
    `outcome == "error"` instead of `!= "ok"` - a different window AND a
    different predicate from the verdict that rested on it. Any divergence here
    creates a band where F01 claims, F06 defers, and the diagnosis is wrong.
    """
    from kavach.detection.retrieval_collapse import QUERIES as F06_QUERIES
    from kavach.rca.evidence import METRIC_QUERIES

    f01 = QUERIES["llm_error_ratio"]
    assert F06_QUERIES["llm_error_ratio"] == f01, (
        "F06's precondition must read exactly what F01 decides on"
    )
    assert METRIC_QUERIES["llm_error_ratio"] == f01, (
        "the model must be shown the same number the detector decided on"
    )


def test_the_error_window_is_short_enough_not_to_carry_residue() -> None:
    """MEASURED, not chosen. On a healthy target minutes after a sequence of
    F01 runs had been reverted: [30s] 0.0, [1m] 0.0, [2m] 0.0, [5m] 0.565.
    0.565 is above the 0.50 floor, so a 5-minute window claimed an endpoint
    outage from residue - and on the next real F06 injection F01 claimed, F06
    deferred to it, and the loop diagnosed the wrong fault. During a genuine
    outage every window read 1.0, so shortening costs nothing."""
    for q in (QUERIES["llm_error_ratio"], QUERIES["llm_requests"]):
        assert "[5m]" not in q, (
            "a 5-minute error window carries residue across incidents"
        )
        assert "[2m]" in q


def test_the_frame_and_the_detector_read_kept_chunks_identically() -> None:
    """The signal that GATES an F06 claim must be the same number the model
    is shown.

    `kept_chunks_mean` was shortened from `[10m]` to `[1m]` on 2026-10-18
    after a live sweep (`harness/window_sweep_f06.py`): at `[10m]` its
    detection latency ranged 92-241s depending on how much healthy traffic
    preceded the fault, which is the cross-fault contamination `PRD.md`
    section 12 records three times.

    The detector and the evidence frame each carry their own copy of the
    query, so shortening one without the other would show the model a
    ten-minute average while the verdict rested on a one-minute one. That is
    the identical failure `test_both_detectors_read_the_same_error_signal`
    documents for F01's error ratio, and it is cheap to pin.
    """
    from kavach.detection.retrieval_collapse import QUERIES as F06_QUERIES
    from kavach.rca.evidence import METRIC_QUERIES

    assert (F06_QUERIES["kept_chunks_mean"]
            == METRIC_QUERIES["retrieval_kept_chunks_mean"]), (
        "the detector and the evidence frame read kept_chunks differently, so "
        "the model is shown a different number from the one the verdict rests on"
    )


def test_only_the_unconstrained_retrieval_window_was_shortened() -> None:
    """`similarity_p50` and `empty_context_ratio` mirror a declared
    `window_s: 600` in the target's manifest; `kept_chunks` has no SLO at all.

    That asymmetry is the whole reason the shortening was a detector-local
    change rather than a spec change, and it is load-bearing: a later edit
    that quietly shortened one of the manifest-backed signals WOULD diverge
    from the contract, and nothing else in the suite would notice.
    """
    from kavach.detection.retrieval_collapse import QUERIES as F06_QUERIES

    assert "[1m]" in F06_QUERIES["kept_chunks_mean"]
    for constrained in ("similarity_p50", "empty_context_ratio"):
        assert "[10m]" in F06_QUERIES[constrained], (
            f"{constrained} mirrors kavach.yaml's declared window_s: 600. "
            f"Shortening it is a spec change and needs a decision record, "
            f"not an edit"
        )
