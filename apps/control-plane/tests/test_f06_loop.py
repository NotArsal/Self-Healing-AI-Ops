"""F06 closed-loop and rollback-safety tests, against a fake target.

A fake rather than the live stack so these are deterministic and run in CI
without Docker. The live end-to-end run is test_f06_live.py.

The fake enforces the real target's refusals - denied keys, unknown keys,
out-of-range values - so a test cannot pass by doing something the real target
would reject.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kavach.executor.config_rollback import (
    ActionError,
    ConfigRollback,
    build_rollback_for_retrieval_collapse,
    idempotency_key,
)
from kavach.loop import KNOWN_FAULTS, IncidentStatus, run_once
from kavach.target import TargetClient, TargetEndpoints, TargetError

BASELINE_THRESHOLD = 0.35
BAD_THRESHOLD = 0.999

DENIED = {"embed_model", "db_host", "db_port", "db_name", "db_user", "db_password"}


class FakeTarget(TargetClient):
    """Stands in for TargetClient, mirroring the real target's validation.

    A subclass rather than a duck type so the loop's real signatures are
    type-checked against it: a fake that drifts from the interface would let a
    test pass against something the production path cannot do.
    """

    def __init__(self, threshold: float = BASELINE_THRESHOLD) -> None:
        super().__init__(TargetEndpoints())
        self._settings: dict[str, Any] = {
            "llm_base_url": "http://toxiproxy:21434",
            "llm_model": "llama3.2",
            "rerank_threshold": threshold,
            "max_tokens": 0,
            "chaos_enabled": False,
            "llm_timeout_s": 30.0,
        }
        self.corpus = {"chunks": 30.0, "files": 2.0}
        self.writes: list[dict[str, Any]] = []
        self.healthy = True

    # --- read
    def health(self, timeout: float = 10.0) -> dict[str, Any]:
        return {"status": "ok" if self.healthy else "unhealthy",
                "dependencies": {"database": {"ok": True}, "ollama": {"ok": True}}}

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
        """Collapses exactly as the real target does above the rerank threshold."""
        if self._settings["rerank_threshold"] >= 0.98:
            return "I don't know based on the provided documents."
        answers = {
            "What ROC-AUC did the LSTM model achieve?":
                "The LSTM model achieved a ROC-AUC of 0.91.\n\n**Sources:**\n- Page 5",
            "How many clips were used in the PhysioCheck feasibility evaluation?":
                "339 clips were used.\n\n**Sources:**\n- Page 1",
            "What was the reported Stage-2 accuracy for Arm Raise?":
                "The reported Stage-2 accuracy for Arm Raise is 91.2%.\n\n**Sources:**\n- Page 1",
        }
        return answers.get(question, "I don't know based on the provided documents.")

    # --- write
    def apply_settings(self, settings: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
        for k, v in settings.items():
            if k in DENIED:
                raise TargetError(f"PUT -> HTTP 422 ({k} is permanently denied)")
            if k not in self._settings:
                raise TargetError(f"PUT -> HTTP 422 ({k} is not settable)")
            if k == "rerank_threshold" and not (0.0 <= float(v) <= 1.0):
                raise TargetError("PUT -> HTTP 422 (rerank_threshold out of range)")
        self.writes.append(dict(settings))
        self._settings.update(settings)
        return {"applied": settings, "config_hash": self.config_hash()}


@pytest.fixture
def fast_set(tmp_path: Path) -> Path:
    import yaml
    p = tmp_path / "fast_set.yaml"
    p.write_text(yaml.safe_dump({
        "budget": {"max_duration_s": 120},
        "cases": [
            {"id": "fv-01", "question": "What ROC-AUC did the LSTM model achieve?",
             "expected_keyword": "0.91"},
            {"id": "fv-02",
             "question": "How many clips were used in the PhysioCheck "
                         "feasibility evaluation?",
             "expected_keyword": "339"},
            {"id": "fv-03", "question": "What was the reported Stage-2 accuracy for Arm Raise?",
             "expected_keyword": "91.2"},
        ],
    }), encoding="utf-8")
    return p


def promql_for(target: FakeTarget) -> Callable[[str, str], float | None]:
    """Metrics consistent with the fake's threshold, so the loop sees a
    coherent world."""
    def q(_url: str, expr: str) -> float | None:
        collapsed = target.settings()["rerank_threshold"] >= 0.98
        if "corpus_chunks" in expr:
            return target.corpus["chunks"]
        if "corpus_files" in expr:
            return target.corpus["files"]
        if "top_similarity" in expr:
            return 0.658          # unchanged by the rerank filter, by design
        if "kept_chunks_sum" in expr:
            return 0.0 if collapsed else 2.73
        if "empty_context" in expr:
            return 1.0 if collapsed else 0.0
        return None
    return q


# --- required test cases ----------------------------------------------------


def test_healthy_system_produces_no_incident(fast_set: Path) -> None:
    t = FakeTarget(BASELINE_THRESHOLD)
    inc = run_once(t, "http://prom", fast_set, promql_for(t), BASELINE_THRESHOLD)
    assert inc.status is IncidentStatus.NO_FAULT
    assert t.writes == [], "a healthy system must not be written to"


def test_baseline_threshold_passes_the_fast_set(fast_set: Path) -> None:
    from kavach.verification import fast
    t = FakeTarget(BASELINE_THRESHOLD)
    assert fast.run(t, fast_set).passed


def test_bad_threshold_fails_the_fast_set(fast_set: Path) -> None:
    from kavach.verification import fast
    t = FakeTarget(BAD_THRESHOLD)
    r = fast.run(t, fast_set)
    assert not r.passed
    assert r.pass_rate == 0.0


def test_full_loop_detects_heals_and_resolves(fast_set: Path) -> None:
    t = FakeTarget(BAD_THRESHOLD)
    inc = run_once(t, "http://prom", fast_set, promql_for(t), BASELINE_THRESHOLD)
    assert inc.status is IncidentStatus.RESOLVED
    assert inc.fault_class == "F06"
    assert inc.fault_name == "retrieval_collapse"
    assert inc.service == "backend"
    assert inc.planned_action == "rollback_config"
    assert t.settings()["rerank_threshold"] == BASELINE_THRESHOLD


def test_rollback_restores_exact_prior_value_not_a_constant() -> None:
    """The inverse replays the captured value. If the pre-state is 0.42, the
    inverse must be 0.42 - never a hardcoded 0.35."""
    t = FakeTarget(0.42)
    action = build_rollback_for_retrieval_collapse("INC-X", t, known_good_threshold=0.35)
    assert action.inverse_settings == {"rerank_threshold": 0.42}
    action.execute(t)
    assert t.settings()["rerank_threshold"] == 0.35
    action.invert(t)
    assert t.settings()["rerank_threshold"] == 0.42, "inverse must restore 0.42"
    ok, detail = action.verify_restored(t)
    assert ok, detail


def test_rollback_without_a_baseline_is_refused() -> None:
    """There is nothing to roll back TO, and a default would be a guess."""
    t = FakeTarget(BAD_THRESHOLD)
    with pytest.raises(ActionError, match="must not fall back to a constant"):
        build_rollback_for_retrieval_collapse("INC-X", t, known_good_threshold=None)


def test_execute_is_idempotent(fast_set: Path) -> None:
    t = FakeTarget(BAD_THRESHOLD)
    action = build_rollback_for_retrieval_collapse("INC-X", t, BASELINE_THRESHOLD)
    action.execute(t)
    action.execute(t)
    action.execute(t)
    assert len(t.writes) == 1, "a duplicate action must be a no-op, not a second write"


def test_idempotency_key_is_stable_and_discriminating() -> None:
    a = idempotency_key("INC-1", "rollback_config", {"rerank_threshold": 0.35})
    b = idempotency_key("INC-1", "rollback_config", {"rerank_threshold": 0.35})
    c = idempotency_key("INC-2", "rollback_config", {"rerank_threshold": 0.35})
    d = idempotency_key("INC-1", "rollback_config", {"rerank_threshold": 0.50})
    assert a == b
    assert a != c and a != d


def test_corpus_fingerprint_unchanged_across_the_loop(fast_set: Path) -> None:
    t = FakeTarget(BAD_THRESHOLD)
    inc = run_once(t, "http://prom", fast_set, promql_for(t), BASELINE_THRESHOLD)
    assert inc.corpus_before == inc.corpus_after
    assert inc.corpus_after == {"chunks": 30.0, "files": 2.0}


def test_unrelated_settings_are_untouched(fast_set: Path) -> None:
    t = FakeTarget(BAD_THRESHOLD)
    before = t.settings()
    inc = run_once(t, "http://prom", fast_set, promql_for(t), BASELINE_THRESHOLD)
    after = t.settings()
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"rerank_threshold"}, f"unexpected drift: {changed}"
    assert inc.verification["scope_respected"]["ok"]


def test_failed_verification_does_not_mark_resolved(fast_set: Path) -> None:
    """The single most important behaviour in this module."""
    t = FakeTarget(BAD_THRESHOLD)

    # The repair applies, but the quality probe still fails afterwards.
    original_ask = t.ask
    def always_refuse(_q: str, timeout: float = 240.0) -> str:
        return "I don't know based on the provided documents."

    calls = {"n": 0}
    def ask(q: str, timeout: float = 240.0) -> str:
        calls["n"] += 1
        # First three calls are pre-detection; after that keep failing.
        return original_ask(q) if calls["n"] <= 3 else always_refuse(q)

    t.ask = ask  # type: ignore[assignment]
    inc = run_once(t, "http://prom", fast_set, promql_for(t), BASELINE_THRESHOLD)
    assert inc.status is IncidentStatus.ESCALATED
    assert not inc.resolved
    assert "fast verification did not pass" in inc.escalation_reason
    assert "NOT resolved" in inc.outcome


def test_corpus_change_blocks_resolution(fast_set: Path) -> None:
    """Even a perfect repair must not be called resolved if the corpus moved."""
    t = FakeTarget(BAD_THRESHOLD)
    state = {"first": True}

    def q(_url: str, expr: str) -> float | None:
        base = promql_for(t)(_url, expr)
        if "corpus_chunks" in expr:
            if state["first"]:
                state["first"] = False
                return 30.0
            return 12.0          # corpus shrank mid-incident
        return base

    inc = run_once(t, "http://prom", fast_set, q, BASELINE_THRESHOLD)
    assert inc.status is IncidentStatus.ESCALATED
    assert "corpus fingerprint changed" in inc.escalation_reason


def test_insufficient_evidence_escalates_without_acting(fast_set: Path) -> None:
    t = FakeTarget(BAD_THRESHOLD)

    def q(_url: str, expr: str) -> float | None:
        if "top_similarity" in expr:
            return 0.05          # embeddings broken, not a threshold fault
        return promql_for(t)(_url, expr)

    inc = run_once(t, "http://prom", fast_set, q, BASELINE_THRESHOLD)
    assert inc.status is IncidentStatus.ESCALATED
    assert t.writes == [], "nothing may be written for an undiagnosed fault"
    assert "INSUFFICIENT_EVIDENCE" in inc.escalation_reason


def test_action_record_has_every_required_field(fast_set: Path) -> None:
    t = FakeTarget(BAD_THRESHOLD)
    inc = run_once(t, "http://prom", fast_set, promql_for(t), BASELINE_THRESHOLD)
    a = inc.action
    for key in ("incident_id", "action", "risk_tier", "idempotency_key",
                "requested_settings", "inverse_settings", "pre_state",
                "config_hash_before", "config_hash_after"):
        assert key in a and a[key] not in (None, ""), f"missing {key}"
    assert a["risk_tier"] == "MEDIUM"
    assert a["config_hash_before"] != a["config_hash_after"]
    assert inc.incident_id.startswith("INC-")


def test_execute_without_prepare_is_refused() -> None:
    """No pre-state witness means no inverse, so the write must not happen."""
    t = FakeTarget(BAD_THRESHOLD)
    bare = ConfigRollback(incident_id="INC-X",
                          target_settings={"rerank_threshold": 0.35})
    with pytest.raises(ActionError, match="prepare"):
        bare.execute(t)
    assert t.writes == []


def test_denied_key_cannot_be_rolled_back() -> None:
    """The deny-list is the target's, and it must hold through this path too."""
    t = FakeTarget(BASELINE_THRESHOLD)
    action = ConfigRollback(incident_id="INC-X",
                            target_settings={"embed_model": "something-large"})
    with pytest.raises(ActionError, match="does not report"):
        action.prepare(t)


def test_known_fault_map_covers_only_f06() -> None:
    """Scope control: this slice implements one fault."""
    assert KNOWN_FAULTS == {"F06": "rollback_config"}
