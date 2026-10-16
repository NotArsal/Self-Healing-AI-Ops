"""F08 config regression: detection, discrimination, and the whole loop.

The hard part of F08 is not detecting it. Every config-driven fault changes the
config hash, so "hash changed + fast set failing" is true during an `F06` too.
Most of this file is therefore about F08 NOT claiming what it does not own.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kavach.detection import base as det
from kavach.detection import catalogue  # noqa: F401 - registers the detectors
from kavach.detection.config_regression import (
    CLAIMED_ELSEWHERE,
    collect,
    evaluate,
)
from kavach.executor import catalogue as action_catalogue  # noqa: F401
from kavach.loop import IncidentStatus, run_once
from kavach.target import TargetClient, TargetEndpoints, TargetError

BASELINE_SETTINGS: dict[str, Any] = {
    "llm_base_url": "http://toxiproxy:21434",
    "llm_model": "llama3.2",
    "rerank_threshold": 0.35,
    "max_tokens": 0,
    "chaos_enabled": False,
    "llm_timeout_s": 30.0,
}
BASELINE = {"settings": dict(BASELINE_SETTINGS), "config_hash": "de4cfaed14a8bb98",
            "rerank_threshold": 0.35}

# Measured: the highest clamp that fails all three fast-set cases in every
# repetition. See harness/faults/f08_config_regression.py for the sweep.
BAD_MAX_TOKENS = 2


def readings(live: dict[str, Any], baseline: dict[str, Any] | None = None) -> Any:
    """What `collect` would return for a given live/baseline pair."""
    class _Client:
        def settings(self) -> dict[str, Any]:
            return dict(live)

        def config_hash(self) -> str:
            return "live-hash"

    return collect(det.Signals(
        prometheus_url="http://unused",
        promql=lambda _u, _q: None,
        client=_Client(),
        baseline=BASELINE if baseline is None else baseline,
    ))


# --- 1. the two verdicts that matter ---------------------------------------


def test_an_unclaimed_setting_drifting_with_a_failing_set_is_detected() -> None:
    live = {**BASELINE_SETTINGS, "max_tokens": BAD_MAX_TOKENS}
    d = evaluate(readings(live), fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.FAULT
    assert d.fault_class == "F08"
    assert d.service == "backend"
    assert d.citations()


def test_the_repair_target_is_the_captured_value_of_only_the_drifted_key() -> None:
    """Not the whole baseline. Rolling back a key no fault involved would
    overrule a deliberate operator change on something nobody asked about."""
    live = {**BASELINE_SETTINGS, "max_tokens": BAD_MAX_TOKENS}
    d = evaluate(readings(live), fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.repair_target == {"max_tokens": 0}


def test_a_matching_config_is_no_fault() -> None:
    d = evaluate(readings(dict(BASELINE_SETTINGS)),
                 fast_set_passed=True, fast_set_pass_rate=1.0)
    assert d.verdict is det.Verdict.NO_FAULT
    assert d.repair_target is None


# --- 2. the refusals, which are most of the value --------------------------


def test_drift_on_a_working_system_is_reported_not_repaired() -> None:
    """An operator may have changed a setting on purpose. Rolling that back
    because it is merely DIFFERENT would be the control plane overruling its
    own owner."""
    live = {**BASELINE_SETTINGS, "llm_timeout_s": 60.0}
    d = evaluate(readings(live), fast_set_passed=True, fast_set_pass_rate=1.0)
    assert d.verdict is det.Verdict.NO_FAULT
    assert any("nothing is broken" in r for r in d.reasons)
    # The drift is still visible to a human in the evidence.
    assert any(e.kind == "config_drift" and e.value for e in d.evidence)


def test_f06s_setting_drifting_is_not_f08() -> None:
    """THE discrimination test. An F06 injection moves rerank_threshold, which
    moves the config hash and fails the fast set - so without ownership F08
    would claim every retrieval collapse and run_all would refuse to choose."""
    live = {**BASELINE_SETTINGS, "rerank_threshold": 0.999}
    d = evaluate(readings(live), fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE
    assert any("owned by a more specific fault class" in r for r in d.reasons)


def test_f01s_setting_drifting_is_not_f08() -> None:
    live = {**BASELINE_SETTINGS, "llm_base_url": "http://toxiproxy:21435"}
    d = evaluate(readings(live), fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE


def test_a_claimed_and_an_unclaimed_key_drifting_together_still_claims() -> None:
    """F08 owns the part nobody else does, and repairs only that part."""
    live = {**BASELINE_SETTINGS, "rerank_threshold": 0.999,
            "max_tokens": BAD_MAX_TOKENS}
    d = evaluate(readings(live), fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.FAULT
    assert d.repair_target == {"max_tokens": 0}, (
        "the rollback must not include the key F06 owns"
    )


def test_no_baseline_snapshot_is_missing_evidence_not_absent_drift() -> None:
    d = evaluate(readings(dict(BASELINE_SETTINGS), baseline={}),
                 fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE
    assert any("missing evidence" in r for r in d.reasons)


def test_an_unreachable_control_interface_is_missing_evidence() -> None:
    class _Broken:
        def settings(self) -> dict[str, Any]:
            raise TargetError("GET /v1/admin/config -> connection refused")

        def config_hash(self) -> str:
            raise TargetError("unreachable")

    out = collect(det.Signals(
        prometheus_url="http://unused", promql=lambda _u, _q: None,
        client=_Broken(), baseline=BASELINE,
    ))
    assert out["drift"] is None, "a dead control interface must not read as clean"
    d = evaluate(out, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE


def test_a_key_the_baseline_never_recorded_is_not_drift() -> None:
    """It cannot be rolled back to anything, so proposing a repair for it
    would name a target that does not exist."""
    live = {**BASELINE_SETTINGS, "some_new_setting": 7}
    d = evaluate(readings(live), fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.NO_FAULT


def test_the_ownership_list_matches_the_other_detectors() -> None:
    """If a class stops owning its setting, F08 must start claiming it - and
    if a new detector claims one, this list has to learn about it. Asserted so
    the two cannot drift apart silently."""
    from kavach.detection import endpoint_outage, retrieval_collapse

    assert "rerank_threshold" in CLAIMED_ELSEWHERE
    assert "llm_base_url" in CLAIMED_ELSEWHERE
    assert retrieval_collapse.SPEC.fault_class == "F06"
    assert endpoint_outage.SPEC.fault_class == "F01"


# --- 3. the whole loop, offline --------------------------------------------


REFUSAL = "I don't know based on the provided documents."
SOURCES = "\n\n**Sources:**\n- Page 1"
FULL = {
    "What ROC-AUC did the LSTM model achieve?":
        "The LSTM model achieved a ROC-AUC of 0.91." + SOURCES,
    "How many clips were used in the PhysioCheck feasibility evaluation?":
        "339 clips were used." + SOURCES,
    "What was the reported Stage-2 accuracy for Arm Raise?":
        "The reported Stage-2 accuracy for Arm Raise is 91.2%." + SOURCES,
}
# What a 2-token clamp actually returns, measured: a truncated answer that is
# NOT a refusal and still carries its sources block.
TRUNCATED = {
    "What ROC-AUC did the LSTM model achieve?": "The LSTM" + SOURCES,
    "How many clips were used in the PhysioCheck feasibility evaluation?":
        "The Phys" + SOURCES,
    "What was the reported Stage-2 accuracy for Arm Raise?": "91." + SOURCES,
}


class FakeClampedTarget(TargetClient):
    """A target whose answers truncate when `max_tokens` is clamped."""

    def __init__(self, max_tokens: int = 0) -> None:
        super().__init__(TargetEndpoints())
        self._settings: dict[str, Any] = {**BASELINE_SETTINGS,
                                          "max_tokens": max_tokens}
        self.corpus = {"chunks": 30.0, "files": 2.0}
        self.writes: list[dict[str, Any]] = []

    @property
    def clamped(self) -> bool:
        mt = int(self._settings["max_tokens"])
        return 0 < mt <= 3

    def health(self, timeout: float = 10.0) -> dict[str, Any]:
        return {"status": "ok", "dependencies": {
            "database": {"ok": True, "detail": "ok"},
            "ollama": {"ok": True, "detail": "ok"}}}

    def config(self, timeout: float = 15.0) -> dict[str, Any]:
        return {"settings": dict(self._settings),
                "config_hash": self.config_hash(),
                "prompt_version": {"files": {"answer.txt": "d55c"}}}

    def settings(self) -> dict[str, Any]:
        return dict(self._settings)

    def config_hash(self) -> str:
        import hashlib
        import json
        blob = json.dumps(self._settings, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def ask(self, question: str, timeout: float = 240.0) -> str:
        table = TRUNCATED if self.clamped else FULL
        return table.get(question, REFUSAL)

    def apply_settings(self, settings: dict[str, Any],
                       timeout: float = 20.0) -> dict[str, Any]:
        for k in settings:
            if k not in self._settings:
                raise TargetError(f"PUT -> HTTP 422 (unknown setting {k})")
        self._settings.update(settings)
        self.writes.append(dict(settings))
        return {"settings": dict(self._settings), "config_hash": self.config_hash()}


def promql_for(target: FakeClampedTarget) -> Callable[[str, str], float | None]:
    """Healthy metrics throughout: that is the point of this fault.

    Grounding is intact and the endpoint answers every call, so neither F06 nor
    F01 has anything to claim. Only the config comparison and the fast set see
    anything wrong.
    """
    def q(_url: str, expr: str) -> float | None:
        if "corpus_chunks" in expr:
            return target.corpus["chunks"]
        if "corpus_files" in expr:
            return target.corpus["files"]
        if "outcome" in expr and "clamp_min" in expr:
            return 0.0                    # llm_error_ratio: endpoint is fine
        if "increase(ragapp_llm_requests_total" in expr:
            return 12.0
        if 'outcome="ok"' in expr:
            return 0.7
        if "top_similarity" in expr:
            return 0.658
        if "kept_chunks_sum" in expr:
            return 2.73                   # grounding intact
        if "empty_context" in expr:
            return 0.0
        return None
    return q


@pytest.fixture
def fast_set() -> Path:
    return (Path(__file__).resolve().parents[1]
            / "kavach" / "verification" / "fast_set.yaml")


def _run(target: FakeClampedTarget, fast_set: Path) -> Any:
    return run_once(target, "http://prom", fast_set, promql_for(target),
                    baseline_value=0.35, baseline=BASELINE)


def test_f08_is_detected_and_healed_by_rolling_the_setting_back(
    fast_set: Path,
) -> None:
    t = FakeClampedTarget(max_tokens=BAD_MAX_TOKENS)
    inc = _run(t, fast_set)

    assert inc.status is IncidentStatus.RESOLVED, inc.escalation_reason
    assert inc.fault_class == "F08"
    assert inc.planned_action == "rollback_config"
    assert t.settings()["max_tokens"] == 0
    assert inc.action is not None
    assert inc.action["requested_settings"] == {"max_tokens": 0}
    assert inc.action["inverse_settings"] == {"max_tokens": BAD_MAX_TOKENS}
    assert inc.action["risk_tier"] == "MEDIUM"


def test_a_clean_config_produces_no_incident(fast_set: Path) -> None:
    t = FakeClampedTarget(max_tokens=0)
    inc = _run(t, fast_set)
    assert inc.status is IncidentStatus.NO_FAULT
    assert t.writes == []


def test_without_a_baseline_the_loop_cannot_diagnose_f08(fast_set: Path) -> None:
    """The detector refuses rather than guessing, so the loop escalates."""
    t = FakeClampedTarget(max_tokens=BAD_MAX_TOKENS)
    inc = run_once(t, "http://prom", fast_set, promql_for(t),
                   baseline_value=0.35, baseline={})
    assert inc.status is IncidentStatus.ESCALATED
    assert t.writes == [], "nothing may be written from an undiagnosed fault"


def test_a_rollback_that_does_not_fix_quality_unwinds(fast_set: Path) -> None:
    """The forced-verification-failure case for F08."""
    t = FakeClampedTarget(max_tokens=BAD_MAX_TOKENS)

    original = t.apply_settings

    def apply_but_stay_broken(settings: dict[str, Any],
                              timeout: float = 20.0) -> dict[str, Any]:
        out = original(settings, timeout)
        # The write lands, but something else keeps answers truncated.
        t._settings["max_tokens"] = BAD_MAX_TOKENS if settings.get(
            "max_tokens") == 0 else t._settings["max_tokens"]
        return out

    t.apply_settings = apply_but_stay_broken  # type: ignore[method-assign]
    inc = _run(t, fast_set)

    assert inc.status is IncidentStatus.ESCALATED
    assert not inc.resolved
    assert "fast verification did not pass" in inc.escalation_reason
