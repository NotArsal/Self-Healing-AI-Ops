"""F02 through the whole loop, offline.

The per-fault acceptance asks for an integration test green in CI and a
forced-verification-failure test. These are F02's, mirroring `test_f01_loop`.

WHAT IS DIFFERENT FROM F01, AND HOW IT IS SIMULATED WITHOUT WAITING
Under F01 the slowed answers are WRONG (refusals). Under F02 they are RIGHT
but LATE, so the fast set fails on its 120s time budget, not on quality. An
offline test cannot wait 78s a question, so the fast set's own clock
(`time.perf_counter`, `kavach/verification/fast.py`) is replaced by a fake one
that the fake target advances by the chat times MEASURED on 2026-11-10
(`harness/reports/f02-latency-sweep.json`): ~78s through the slowed primary,
~6.2s healthy. Everything else is the real loop.

The metric values are also the measured ones: generation p95 14.65 under the
12s injector (every call in the (8, 15] bucket), 0.975 healthy, and an LLM
error ratio of 0.0 throughout, because a slow endpoint still answers. /healthz
returns 503 under F02 (its own 5s Ollama check times out), which is mirrored.

A LOCAL FAKE, NOT AN IMPORT FROM test_f01_loop, for the reason that file gives:
importing across test modules made mypy see `tests/` under two names.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kavach.detection import latency_degradation
from kavach.executor import catalogue  # noqa: F401 - registers the actions
from kavach.executor.endpoint_switch import SETTING
from kavach.loop import IncidentStatus, run_once
from kavach.rca import evidence
from kavach.target import TargetClient, TargetEndpoints, TargetError

PRIMARY_URL = "http://toxiproxy:21434"
BACKUP_URL = "http://toxiproxy:21435"
SLOW_CHAT_S = 78.0      # measured, 12s toxic
HEALTHY_CHAT_S = 6.2    # measured, no toxic

REFUSAL = "I don't know based on the provided documents."
GROUNDED = {
    "What ROC-AUC did the LSTM model achieve?":
        "The LSTM model achieved a ROC-AUC of 0.91.\n\n**Sources:**\n- Page 5",
    "How many clips were used in the PhysioCheck feasibility evaluation?":
        "339 clips were used.\n\n**Sources:**\n- Page 1",
    "What was the reported Stage-2 accuracy for Arm Raise?":
        "The reported Stage-2 accuracy for Arm Raise is 91.2%.\n\n**Sources:**\n- Page 1",
}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeLatencyTarget(TargetClient):
    """The primary listener is slow (or, for the boundary test, down)."""

    def __init__(self, clock: Clock, primary: str = "slow",
                 healthz_sees_it: bool = True) -> None:
        super().__init__(TargetEndpoints())
        self.clock = clock
        self.primary = primary  # "slow" | "down" | "healthy"
        # Measured: /healthz is 503 under F02 because its own Ollama check has
        # a 5s timeout. False models a target whose health probe is patient
        # enough not to notice, leaving the fast set's time budget as the ONLY
        # symptom - which is the path a test has to pin on its own.
        self.healthz_sees_it = healthz_sees_it
        self._settings: dict[str, Any] = {
            "llm_base_url": PRIMARY_URL, "llm_model": "llama3.2",
            "rerank_threshold": 0.35, "max_tokens": 0,
            "chaos_enabled": False, "llm_timeout_s": 30.0,
        }
        self.writes: list[dict[str, Any]] = []
        self.force_quality_failure = False

    @property
    def mode(self) -> str:
        on_primary = self._settings[SETTING] == PRIMARY_URL
        return self.primary if on_primary else "healthy"

    def health(self, timeout: float = 10.0) -> dict[str, Any]:
        ok = self.mode == "healthy" or (self.mode == "slow" and not self.healthz_sees_it)
        return {"status": "ok" if ok else "unhealthy",
                "dependencies": {"database": {"ok": True, "detail": "ok"},
                                 "ollama": {"ok": ok, "detail": "ok" if ok else "timeout"}}}

    def config(self, timeout: float = 15.0) -> dict[str, Any]:
        return {"settings": dict(self._settings), "config_hash": self.config_hash(),
                "prompt_version": {"files": {"answer.txt": "d55c"}}}

    def settings(self) -> dict[str, Any]:
        return dict(self._settings)

    def config_hash(self) -> str:
        import hashlib
        import json
        blob = json.dumps(self._settings, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def ask(self, question: str, timeout: float = 240.0) -> str:
        if self.mode == "down":
            return REFUSAL
        self.clock.now += SLOW_CHAT_S if self.mode == "slow" else HEALTHY_CHAT_S
        if self.force_quality_failure:
            return REFUSAL
        return GROUNDED.get(question, REFUSAL)

    def apply_settings(self, settings: dict[str, Any],
                       timeout: float = 20.0) -> dict[str, Any]:
        for k in settings:
            if k not in self._settings:
                raise TargetError(f"PUT -> HTTP 422 (unknown setting {k})")
        self._settings.update(settings)
        self.writes.append(dict(settings))
        return {"settings": dict(self._settings), "config_hash": self.config_hash()}


def promql_for(t: FakeLatencyTarget) -> Callable[[str, str], float | None]:
    def q(_url: str, expr: str) -> float | None:
        mode = t.mode
        if "corpus_chunks" in expr:
            return 30.0
        if "corpus_files" in expr:
            return 2.0
        if "ragapp_llm_duration_seconds_bucket" in expr:
            return 14.65 if mode == "slow" else 0.975
        if "outcome" in expr and "clamp_min" in expr:
            return 1.0 if mode == "down" else 0.0      # llm_error_ratio
        if "increase(ragapp_llm_requests_total" in expr:
            return 12.0
        if 'outcome="ok"' in expr:
            return 0.0 if mode == "down" else 0.7
        if "top_similarity" in expr:
            return 0.675
        if "kept_chunks_sum" in expr:
            return 0.0 if mode == "down" else 2.73
        if "empty_context" in expr:
            return 1.0 if mode == "down" else 0.0
        return None
    return q


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    c = Clock()
    # fast.py times itself with time.perf_counter; replacing it for the test
    # replaces the clock the fast set reads, and monkeypatch restores it.
    monkeypatch.setattr(time, "perf_counter", c)
    return c


@pytest.fixture
def fast_set() -> Path:
    return Path(__file__).resolve().parents[1] / "kavach" / "verification" / "fast_set.yaml"


def _run(t: FakeLatencyTarget, fast_set: Path) -> Any:
    return run_once(t, "http://prom", fast_set, promql_for(t), baseline_value=0.35,
                    repair_values={"switch_llm_endpoint": BACKUP_URL})


# --- 1. the integration test ------------------------------------------------


def test_f02_is_detected_diagnosed_and_healed_by_failover(
        clock: Clock, fast_set: Path) -> None:
    t = FakeLatencyTarget(clock, "slow")
    inc = _run(t, fast_set)
    assert inc.status is IncidentStatus.RESOLVED, inc.escalation_reason
    assert inc.fault_class == "F02"
    assert inc.planned_action == "switch_llm_endpoint"
    assert t.settings()[SETTING] == BACKUP_URL
    assert inc.resolved


def test_slowness_alone_is_caught_by_the_time_budget(
        clock: Clock, fast_set: Path) -> None:
    """Health passes and every answer is correct, only late: the fast set's
    120s budget is the only thing that can fail. Pins the timing path, which
    the /healthz 503 would otherwise mask in every other test here."""
    t = FakeLatencyTarget(clock, "slow", healthz_sees_it=False)
    inc = _run(t, fast_set)
    assert inc.status is IncidentStatus.RESOLVED, inc.escalation_reason
    assert inc.fault_class == "F02"


def test_a_healthy_endpoint_produces_no_incident(clock: Clock, fast_set: Path) -> None:
    t = FakeLatencyTarget(clock, "healthy")
    inc = _run(t, fast_set)
    assert inc.status is IncidentStatus.NO_FAULT
    assert t.writes == []


def test_an_outage_on_the_same_listener_is_still_f01_not_f02(
        clock: Clock, fast_set: Path) -> None:
    """The boundary through the whole loop, not just the two evaluate()s."""
    t = FakeLatencyTarget(clock, "down")
    inc = _run(t, fast_set)
    assert inc.fault_class == "F01"


def test_the_inverse_is_the_endpoint_that_was_actually_live(
        clock: Clock, fast_set: Path) -> None:
    t = FakeLatencyTarget(clock, "slow")
    inc = _run(t, fast_set)
    assert inc.action is not None
    assert inc.action["inverse_settings"] == {SETTING: PRIMARY_URL}
    assert inc.action["requested_settings"] == {SETTING: BACKUP_URL}
    assert inc.action["risk_tier"] == "LOW"


# --- 2. the forced-verification-failure test ---------------------------------


def test_a_failover_that_does_not_fix_quality_unwinds_and_escalates(
        clock: Clock, fast_set: Path) -> None:
    t = FakeLatencyTarget(clock, "slow")
    before = t.settings()
    t.force_quality_failure = True
    inc = _run(t, fast_set)
    assert inc.status is IncidentStatus.ESCALATED
    assert not inc.resolved
    assert inc.unwind is not None and inc.unwind["clean"] is True
    assert t.settings() == before, "the unwind must leave no net change"


# --- 3. the detector and the evidence the model sees agree -------------------


def _window(expr: str) -> str:
    found: list[str] = re.findall(r"\[(\d+[smh])\]", expr)
    assert len(set(found)) == 1, expr
    return found[0]


def test_the_model_is_shown_the_latency_window_the_detector_decides_on() -> None:
    """`evidence.py` once showed the error ratio over a different window from
    the detector deciding on it. The latency evidence is held to the same rule."""
    assert (_window(evidence.METRIC_QUERIES["llm_generation_latency_p95"])
            == _window(latency_degradation.QUERIES["generation_p95_s"]))
