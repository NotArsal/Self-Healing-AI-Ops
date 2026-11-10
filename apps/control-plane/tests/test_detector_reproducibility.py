"""Guards for `harness/detector_reproducibility.py`.

Two things in that script can fail silently and both are checked here. It
injects a real fault on every trial, so the revert must survive an exception
anywhere after the injection - a measurement script that leaves the target
faulted would corrupt every later trial AND whatever ran next on that host.
And its `--trials` floor exists because one trial cannot measure
reproducibility; a guard that is easy to delete deserves a test that fails
when it is.

No network, no Docker, no model: the fault and the detector are both fakes.
`AGENTS.md` PL-02 requires the suite to run offline.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from harness import detector_reproducibility as dr
from kavach.detection import base as det
from kavach.verification import fast


class _SpyFault:
    """Records what was called on it. `inject` succeeds, `revert` counts."""

    def __init__(self) -> None:
        self.injected = 0
        self.reverted = 0

    def inject(self) -> None:
        self.injected += 1

    def revert(self) -> None:
        self.reverted += 1


def test_detect_once_reverts_when_detection_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fault comes back out even when the measurement itself blows up."""
    spy = _SpyFault()
    monkeypatch.setattr(dr, "build", lambda _cls, _client: spy)

    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("prometheus went away mid-trial")

    monkeypatch.setattr(fast, "run", boom)

    with pytest.raises(RuntimeError, match="prometheus went away"):
        dr.detect_once("F07", client=None, baseline={})  # type: ignore[arg-type]

    assert spy.injected == 1, "the trial must actually inject"
    assert spy.reverted == 1, (
        "REVERT MISSING: an exception after injection left the fault on the "
        "target. Every later trial, and anything else using that host, would "
        "measure the leftover.")


def test_detect_once_reverts_on_the_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """And on success, with the detector's class read off the result."""
    spy = _SpyFault()
    monkeypatch.setattr(dr, "build", lambda _cls, _client: spy)
    monkeypatch.setattr(
        fast, "run",
        lambda *_a, **_k: type("P", (), {"passed": 0, "pass_rate": 0.0})())
    monkeypatch.setattr(
        det, "run_all",
        lambda *_a, **_k: type(
            "D", (), {"fault_class": "F07", "verdict": "CONFIRMED"})())
    monkeypatch.setattr(det.registry, "specs", lambda: [])

    verdict, pass_rate, seconds, reason = dr.detect_once(
        "F07", None, {})  # type: ignore[arg-type]

    assert verdict == "F07"
    assert reason == "", "a detector with no reasons must give an empty string"
    assert pass_rate == 0.0
    assert seconds >= 0.0
    assert spy.reverted == 1


def test_detect_once_falls_back_to_the_bare_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INSUFFICIENT_EVIDENCE` carries no class, and that is the whole point.

    The drop rule in the closure ablation reads exactly this case, so if the
    fallback were lost the script would report an empty verdict for the one
    outcome it was written to count.
    """
    spy = _SpyFault()
    monkeypatch.setattr(dr, "build", lambda _cls, _client: spy)
    monkeypatch.setattr(
        fast, "run",
        lambda *_a, **_k: type("P", (), {"passed": 0, "pass_rate": 0.0})())
    monkeypatch.setattr(
        det, "run_all",
        lambda *_a, **_k: type(
            "D", (), {"fault_class": "", "verdict": "INSUFFICIENT_EVIDENCE"})())
    monkeypatch.setattr(det.registry, "specs", lambda: [])

    verdict, _rate, _s, _reason = dr.detect_once(
        "F08", None, {})  # type: ignore[arg-type]

    assert verdict == "INSUFFICIENT_EVIDENCE"


def test_detect_once_returns_the_detectors_first_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare INSUFFICIENT_EVIDENCE cannot say WHICH branch produced it."""
    spy = _SpyFault()
    monkeypatch.setattr(dr, "build", lambda _cls, _client: spy)
    monkeypatch.setattr(
        fast, "run",
        lambda *_a, **_k: type("P", (), {"passed": 0, "pass_rate": 0.0})())
    monkeypatch.setattr(
        det, "run_all",
        lambda *_a, **_k: type("D", (), {
            "fault_class": "", "verdict": "INSUFFICIENT_EVIDENCE",
            "reasons": ["the control interface was unreachable",
                        "a second reason that must not be returned"]})())
    monkeypatch.setattr(det.registry, "specs", lambda: [])

    _v, _r, _s, reason = dr.detect_once("F07", None, {})  # type: ignore[arg-type]

    assert reason == "the control interface was unreachable"


@pytest.mark.parametrize("trials", ["1", "0", "-3"])
def test_main_refuses_fewer_than_two_trials(
    monkeypatch: pytest.MonkeyPatch, trials: str,
) -> None:
    """One trial cannot measure reproducibility; the script must say so."""
    monkeypatch.setattr(
        sys, "argv",
        ["detector_reproducibility.py", "--classes", "F08", "--trials", trials])

    with pytest.raises(SystemExit) as caught:
        dr.main()

    assert "at least 2" in str(caught.value)


def test_main_refuses_a_class_with_no_injector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F03 is in the catalogue and has no injector (`PRD.md` §6)."""
    monkeypatch.setattr(
        sys, "argv",
        ["detector_reproducibility.py", "--classes", "F03", "--trials", "5"])

    with pytest.raises(SystemExit) as caught:
        dr.main()

    assert "no injector for F03" in str(caught.value)
