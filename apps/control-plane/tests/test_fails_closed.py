"""Failing closed is a cross-cutting invariant, so it is tested in one place.

WHY THIS FILE EXISTS SEPARATELY FROM THE PER-FAULT TESTS
There are already a dozen assertions that nothing is written on an undiagnosed
fault, spread across `test_f06_loop.py`, `test_f01_loop.py`,
`test_f08_config.py` and `test_rca.py`. Every one of them is bound to a fault
class that exists today. None of them would notice a FOURTH detector that
failed to fail closed, because none of them runs the live registry — and the
whole point of P6's seam is that new fault classes arrive without the core
changing.

So these tests run `detection/base.py`'s real registry and assert the property
for every detector registered in it, present and future.

THE HOLE THIS FOUND
`run_all()` reached `NO_FAULT` when the fast set was FAILING and no detector
claimed. The loop's own wording for NO_FAULT is "no fault detected; nothing to
do", so a demonstrably broken system - three real questions answered wrongly by
the live target - would have been reported healthy. It was unreachable in
practice only by luck: F01 and F06 both happen to return INSUFFICIENT_EVIDENCE
when they cannot explain a failing set. A detector that returned NO_FAULT
instead would have opened it, and nothing per-fault would have caught that.

`AGENTS.md` puts a false-healthy verdict above every other failure mode, and
`fast_set.yaml` says the same thing about editing a keyword to make a probe
pass. This is the same rule applied to the verdict rather than to the probe.
"""

from __future__ import annotations

from typing import Any

import pytest

from kavach.detection import base as det
from kavach.detection import catalogue  # noqa: F401 - registers the detectors


def _nothing_readable(_url: str, _query: str) -> float | None:
    """Every signal missing. Not zero - missing."""
    return None


def _signals(promql: Any = _nothing_readable, **kw: Any) -> det.Signals:
    return det.Signals(prometheus_url="http://unreachable.invalid",
                       promql=promql, **kw)


def _always(verdict: det.Verdict, name: str) -> det.DetectorSpec:
    def evaluate(_m: det.Readings, _passed: bool, _rate: float) -> det.Detection:
        return det.Detection(verdict, fault_class=name, fault_name=name.lower())

    return det.DetectorSpec(
        fault_class=name, fault_name=name.lower(), service="backend",
        collect=lambda _s: {}, evaluate=evaluate,
        repair_action="rollback_config",
    )


# --- the invariant, over the registry as it actually is ---------------------


def test_a_failing_fast_set_can_never_produce_no_fault() -> None:
    """THE one that was broken. A failing probe is ground truth that something
    is wrong; a verdict of NO_FAULT on it is a false-healthy report."""
    specs = [_always(det.Verdict.NO_FAULT, "FAA"),
             _always(det.Verdict.NO_FAULT, "FBB")]
    d = det.run_all(specs, _signals(), fast_set_passed=False,
                    fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE
    assert not d.detected
    assert any("cannot produce a NO_FAULT" in r for r in d.reasons)


def test_the_live_registry_claims_nothing_when_no_signal_is_readable() -> None:
    """With every series missing and the fast set failing, no registered
    detector may claim a fault. A detector that guesses from absent evidence
    would drive a repair against a system nobody can see."""
    d = det.run_all(det.registry.specs(), _signals(),
                    fast_set_passed=False, fast_set_pass_rate=0.0)
    assert not d.detected, (
        f"{d.fault_class} claimed a fault on entirely unreadable evidence"
    )
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("spec", det.registry.specs(),
                         ids=lambda s: str(s.fault_class))
def test_each_registered_detector_refuses_unreadable_evidence(
    spec: det.DetectorSpec,
) -> None:
    """Per detector, so a new fault class is covered the day it registers.

    Parametrised over the LIVE registry rather than a hardcoded list: adding
    `F07` adds a case here automatically, which is the point.
    """
    d = spec.evaluate(spec.collect(_signals()), False, 0.0)
    assert not d.detected, (
        f"{spec.fault_class} claims a fault when it can read nothing at all"
    )


@pytest.mark.parametrize("spec", det.registry.specs(),
                         ids=lambda s: str(s.fault_class))
def test_each_registered_detector_is_quiet_on_a_healthy_system(
    spec: det.DetectorSpec,
) -> None:
    """The opposite error: a detector that claims when the fast set passes
    would repair a working system."""
    d = spec.evaluate(spec.collect(_signals()), True, 1.0)
    assert not d.detected, (
        f"{spec.fault_class} claims a fault while the fast set is passing"
    )


def test_ambiguity_never_resolves_to_a_repair() -> None:
    """Two live claims must not be broken by registration order. Picking one
    would be a guess dressed as a decision, and the wrong repair is worse than
    none."""
    specs = [_always(det.Verdict.FAULT, "FAA"), _always(det.Verdict.FAULT, "FBB")]
    d = det.run_all(specs, _signals(), fast_set_passed=False,
                    fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE
    assert d.fault_class is None, "an ambiguous verdict must name no class"
    assert d.repair_target is None, "and must propose nothing to write"


def test_an_ambiguous_verdict_carries_no_repair_target() -> None:
    """`Detection.repair_target` is what the loop prefers over every other
    source, so a non-claiming verdict leaking one would be a write with no
    diagnosis behind it."""
    for verdict in (det.Verdict.NO_FAULT, det.Verdict.INSUFFICIENT_EVIDENCE):
        specs = [_always(verdict, "FAA")]
        d = det.run_all(specs, _signals(), fast_set_passed=False,
                        fast_set_pass_rate=0.0)
        assert d.repair_target is None


def test_every_registered_detector_names_a_buildable_repair() -> None:
    """A detector that can see a fault but names a repair the executor cannot
    build escalates every time, which is worse than being absent."""
    from kavach.executor import catalogue as action_catalogue  # noqa: F401
    from kavach.executor.base import registry as actions

    for spec in det.registry.specs():
        assert spec.repair_action, f"{spec.fault_class} names no repair"
        assert actions.knows(spec.repair_action), (
            f"{spec.fault_class} names {spec.repair_action!r}, which the "
            f"executor registry cannot build"
        )
