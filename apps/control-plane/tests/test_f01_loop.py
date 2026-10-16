"""F01 through the whole loop, offline.

`ROADMAP.md`'s per-fault acceptance asks for two things this file provides: an
integration test green in CI, and a forced-verification-failure test. The live
runs (`harness/p6_f01_live.py`, `harness/stability_f01.py`) prove F01 against a
real target; these prove it stays proved, on every commit, with no Docker.

A LOCAL FAKE RATHER THAN AN IMPORT FROM test_f06_loop
`FakeTarget` there is a `TargetClient` subclass whose `ask()` collapses on the
rerank threshold - the F06 world. F01's world is different: the endpoint either
answers or refuses, and the threshold is irrelevant. Importing across test
modules also makes mypy see `tests/` under two module names, which broke the
type gate once already. A subclass rather than a duck type, so the loop's real
signatures are type-checked against it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kavach.executor import catalogue  # noqa: F401 - registers the actions
from kavach.executor.endpoint_switch import SETTING, build_switch_for_endpoint_outage
from kavach.loop import IncidentStatus, run_once
from kavach.target import TargetClient, TargetEndpoints, TargetError

PRIMARY_URL = "http://toxiproxy:21434"
BACKUP_URL = "http://toxiproxy:21435"

REFUSAL = "I don't know based on the provided documents."
GROUNDED = {
    "What ROC-AUC did the LSTM model achieve?":
        "The LSTM model achieved a ROC-AUC of 0.91.\n\n**Sources:**\n- Page 5",
    "How many clips were used in the PhysioCheck feasibility evaluation?":
        "339 clips were used.\n\n**Sources:**\n- Page 1",
    "What was the reported Stage-2 accuracy for Arm Raise?":
        "The reported Stage-2 accuracy for Arm Raise is 91.2%.\n\n**Sources:**\n- Page 1",
}


class FakeEndpointTarget(TargetClient):
    """A target whose answers depend on which LLM endpoint it is pointed at.

    The primary listener is "down": any call routed through it fails the way a
    refused connection does. The backup always works. That is the whole F01
    world, and nothing here depends on the rerank threshold.
    """

    def __init__(self, primary_down: bool = True) -> None:
        super().__init__(TargetEndpoints())
        self._settings: dict[str, Any] = {
            "llm_base_url": PRIMARY_URL,
            "llm_model": "llama3.2",
            "rerank_threshold": 0.35,
            "max_tokens": 0,
            "chaos_enabled": False,
            "llm_timeout_s": 30.0,
        }
        self.primary_down = primary_down
        self.corpus = {"chunks": 30.0, "files": 2.0}
        self.writes: list[dict[str, Any]] = []
        self.force_quality_failure = False

    # --- read
    @property
    def reachable(self) -> bool:
        on_primary = self._settings[SETTING] == PRIMARY_URL
        return not (on_primary and self.primary_down)

    def health(self, timeout: float = 10.0) -> dict[str, Any]:
        ok = self.reachable
        return {"status": "ok" if ok else "unhealthy",
                "dependencies": {
                    "database": {"ok": True, "detail": "ok"},
                    "ollama": {"ok": ok, "detail": "ok" if ok
                               else "Max retries exceeded"},
                }}

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
        if not self.reachable:
            # The target returns a refusal rather than raising: its own chat
            # path catches the connection error. The silent-200 shape again,
            # which is why detection cannot rely on HTTP status alone.
            return REFUSAL
        if self.force_quality_failure:
            return REFUSAL
        return GROUNDED.get(question, REFUSAL)

    # --- write
    def apply_settings(self, settings: dict[str, Any],
                       timeout: float = 20.0) -> dict[str, Any]:
        for k in settings:
            if k not in self._settings:
                raise TargetError(f"PUT -> HTTP 422 (unknown setting {k})")
        self._settings.update(settings)
        self.writes.append(dict(settings))
        return {"settings": dict(self._settings), "config_hash": self.config_hash()}


def promql_for(target: FakeEndpointTarget) -> Callable[[str, str], float | None]:
    """Metrics consistent with the fake's endpoint state.

    The numbers under fault are the ones MEASURED on the live target, not
    invented: during a real outage the embedding call fails too, so grounding
    collapses while `top_similarity` keeps a stale, healthy-looking quantile.
    That combination is what used to make F06 claim an F01.
    """
    def q(_url: str, expr: str) -> float | None:
        down = not target.reachable
        if "corpus_chunks" in expr:
            return target.corpus["chunks"]
        if "corpus_files" in expr:
            return target.corpus["files"]
        if "outcome" in expr and "clamp_min" in expr:
            return 1.0 if down else 0.0          # llm_error_ratio
        if "increase(ragapp_llm_requests_total" in expr:
            return 12.0                          # enough traffic to judge
        if 'outcome="ok"' in expr:
            return 0.0 if down else 0.7          # llm_ok_rate
        if "top_similarity" in expr:
            return 0.675                         # stale under fault, by design
        if "kept_chunks_sum" in expr:
            return 0.0 if down else 2.73
        if "empty_context" in expr:
            return 1.0 if down else 0.0
        return None
    return q


@pytest.fixture
def fast_set() -> Path:
    return Path(__file__).resolve().parents[1] / "kavach" / "verification" / "fast_set.yaml"


def _run(target: FakeEndpointTarget, fast_set: Path) -> Any:
    return run_once(
        target, "http://prom", fast_set, promql_for(target),
        baseline_value=0.35,
        repair_values={"switch_llm_endpoint": BACKUP_URL},
    )


# --- 1. the integration test the acceptance asks for ------------------------


def test_f01_is_detected_diagnosed_and_healed_by_failover(fast_set: Path) -> None:
    t = FakeEndpointTarget(primary_down=True)
    inc = _run(t, fast_set)

    assert inc.status is IncidentStatus.RESOLVED, inc.escalation_reason
    assert inc.fault_class == "F01"
    assert inc.service == "backend"
    assert inc.planned_action == "switch_llm_endpoint"
    assert t.settings()[SETTING] == BACKUP_URL, "the failover must have happened"
    assert inc.resolved


def test_a_healthy_endpoint_produces_no_incident(fast_set: Path) -> None:
    t = FakeEndpointTarget(primary_down=False)
    inc = _run(t, fast_set)
    assert inc.status is IncidentStatus.NO_FAULT
    assert t.writes == [], "nothing may be written to a working system"


def test_the_inverse_is_the_endpoint_that_was_actually_live(fast_set: Path) -> None:
    """Not the manifest's `primary`, which can be stale - the live value."""
    t = FakeEndpointTarget(primary_down=True)
    inc = _run(t, fast_set)
    assert inc.action is not None
    assert inc.action["inverse_settings"] == {SETTING: PRIMARY_URL}
    assert inc.action["requested_settings"] == {SETTING: BACKUP_URL}


def test_the_f01_action_record_is_complete_and_low_risk(fast_set: Path) -> None:
    t = FakeEndpointTarget(primary_down=True)
    inc = _run(t, fast_set)
    rec = inc.action
    assert rec is not None
    for key in ("incident_id", "action", "risk_tier", "idempotency_key",
                "requested_settings", "inverse_settings", "pre_state",
                "config_hash_before", "config_hash_after"):
        assert rec.get(key), f"{key} missing from the action record"
    assert rec["risk_tier"] == "LOW", (
        "LOW is what lets permit() run this unattended; MEDIUM would route it "
        "to a sandbox that does not exist yet"
    )


# --- 2. the forced-verification-failure test -------------------------------


def test_a_failover_that_does_not_fix_quality_unwinds_and_escalates(
    fast_set: Path,
) -> None:
    """The single most important behaviour: a repair that runs and does not
    work must leave the target where it was found, and must not report success.

    Here the failover lands - the endpoint is written and reachable again - but
    the answers are still wrong. The loop must notice, apply the recorded
    inverse, and escalate.
    """
    t = FakeEndpointTarget(primary_down=True)
    t.force_quality_failure = True

    inc = _run(t, fast_set)

    assert inc.status is IncidentStatus.ESCALATED
    assert not inc.resolved
    assert "fast verification did not pass" in inc.escalation_reason
    assert t.settings()[SETTING] == PRIMARY_URL, (
        "the inverse must have restored the endpoint that was live before"
    )
    assert inc.unwind is not None
    assert inc.unwind["clean"] is True
    assert inc.unwind["restored"] == 1


def test_an_unwound_failover_leaves_no_net_change(fast_set: Path) -> None:
    """Every setting back where it started, not just the one that was touched."""
    t = FakeEndpointTarget(primary_down=True)
    before = t.settings()
    t.force_quality_failure = True

    _run(t, fast_set)

    assert t.settings() == before


# --- 3. the refusals -------------------------------------------------------


def test_a_failover_is_refused_when_no_backup_is_declared() -> None:
    """A workload with no second path cannot be failed over, and a guessed
    address would be a write into the dark."""
    from kavach.executor.config_rollback import ActionError

    t = FakeEndpointTarget(primary_down=True)
    with pytest.raises(ActionError, match="no backup LLM endpoint"):
        build_switch_for_endpoint_outage("INC-1", t, backup_url=None)
    assert t.writes == []


def test_a_failover_is_refused_when_already_on_the_backup() -> None:
    """A no-op whose inverse would restore the faulty endpoint."""
    from kavach.executor.config_rollback import ActionError

    t = FakeEndpointTarget(primary_down=True)
    t.apply_settings({SETTING: BACKUP_URL})
    t.writes.clear()
    with pytest.raises(ActionError, match="already pointed at"):
        build_switch_for_endpoint_outage("INC-1", t, backup_url=BACKUP_URL)
    assert t.writes == []


def test_the_loop_refuses_an_unregistered_repair(fast_set: Path) -> None:
    """Scope control: the planner may only name what the registry can build."""
    from kavach.executor.base import registry

    assert registry.knows("switch_llm_endpoint")
    assert not registry.knows("restart_container"), (
        "restart_container arrives in a later phase; if this starts passing, "
        "F01's tests are no longer pinning the catalogue they were written for"
    )
