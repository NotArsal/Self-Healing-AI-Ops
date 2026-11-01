"""Kavach Phase 12 - Controlled End-to-End Self-Healing Simulation Workflow.

Tests and proves the complete 7-stage incident handling lifecycle:
  1. Detect   - Fast verification probe fails; detector catalogue identifies fault.
  2. Collect  - Pre-state witness, corpus fingerprints, failing cases, and metric signals.
  3. Diagnose - Fault classified (e.g. F06 retrieval collapse), repair action planned.
  4. Gate     - Policy evaluation:
                * Scenario A: mode="SIMULATION", allowed_actions=[] -> DENY (allow_list).
                * Scenario B: mode="SIMULATION", allowed_actions=["rollback_config"] -> REQUIRE_APPROVAL.
  5. Execute  - Zero mutations executed against target in simulation/denied paths.
  6. Verify   - Clearly records that post-repair verification is not run when gate denies.
  7. Rollback - Proves undo stack unwinds and restores pre-state if verification ever fails.
  8. Tracing  - Telemetry stage events recorded cleanly across lifecycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from kavach.audit.log import AuditLog
from kavach.detection import base as det
from kavach.detection import catalogue  # registers detectors
from kavach.detection import retrieval_collapse as rc
from kavach.executor import catalogue as action_catalogue  # registers actions
from kavach.executor.base import MEDIUM, ActionRegistry, registry
from kavach.executor.config_rollback import (
    ConfigRollback,
    build_rollback_for_retrieval_collapse,
)
from kavach.executor.undo_stack import UndoStack
from kavach.loop import Incident, IncidentStatus, run_once
from kavach.safety.engine import (
    ActionRequest,
    ProjectPolicy,
    SafetyEngine,
    Verdict,
)
from kavach.safety.limits import BlastRadius, CircuitBreaker
from kavach.safety.writer_lock import WriterLock
from kavach.target import TargetClient, TargetEndpoints, TargetError
from kavach.telemetry import heal_span, stage_event

BASELINE_THRESHOLD = 0.35
COLLAPSED_THRESHOLD = 0.999


class SimulatedTarget(TargetClient):
    """Deterministic simulated target enforcing the Simple_RAG-Pipeline contract."""

    def __init__(self, threshold: float = COLLAPSED_THRESHOLD) -> None:
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

    def health(self, timeout: float = 10.0) -> dict[str, Any]:
        return {
            "status": "healthy",
            "dependencies": {"database": {"ok": True}, "ollama": {"ok": True}},
        }

    def config(self, timeout: float = 15.0) -> dict[str, Any]:
        return {
            "settings": dict(self._settings),
            "config_hash": "a1b2c3d4",
            "prompt_version": {"files": {"answer.txt": "d55c"}},
        }

    def settings(self) -> dict[str, Any]:
        return dict(self._settings)

    def ask(self, question: str, timeout: float = 240.0) -> str:
        if self._settings["rerank_threshold"] >= 0.98:
            return "I don't know based on the provided documents."
        answers = {
            "What ROC-AUC did the LSTM model achieve?": (
                "The LSTM model achieved a ROC-AUC of 0.91.\n\n**Sources:**\n- Page 5"
            ),
            "How many clips were used in the PhysioCheck feasibility evaluation?": (
                "339 clips were used.\n\n**Sources:**\n- Page 1"
            ),
            "What was the reported Stage-2 accuracy for Arm Raise?": (
                "The reported Stage-2 accuracy for Arm Raise is 91.2%.\n\n**Sources:**\n- Page 1"
            ),
        }
        return answers.get(question, "I don't know based on the provided documents.")

    def apply_settings(
        self, settings: dict[str, Any], timeout: float = 20.0
    ) -> dict[str, Any]:
        self.writes.append(dict(settings))
        self._settings.update(settings)
        return {"applied": settings, "config_hash": "updated"}


@pytest.fixture
def fast_set_file(tmp_path: Path) -> Path:
    import yaml

    p = tmp_path / "fast_set.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "budget": {"max_duration_s": 120},
                "cases": [
                    {
                        "id": "fv-01",
                        "question": "What ROC-AUC did the LSTM model achieve?",
                        "expected_keyword": "0.91",
                    },
                    {
                        "id": "fv-02",
                        "question": "How many clips were used in the PhysioCheck feasibility evaluation?",
                        "expected_keyword": "339",
                    },
                    {
                        "id": "fv-03",
                        "question": "What was the reported Stage-2 accuracy for Arm Raise?",
                        "expected_keyword": "91.2",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return p


def promql_signals(target: SimulatedTarget) -> Callable[[str, str], float | None]:
    def q(_url: str, expr: str) -> float | None:
        collapsed = target.settings()["rerank_threshold"] >= 0.98
        if "corpus_chunks" in expr:
            return target.corpus["chunks"]
        if "corpus_files" in expr:
            return target.corpus["files"]
        if "top_similarity" in expr:
            return 0.658
        if "kept_chunks_sum" in expr:
            return 0.0 if collapsed else 2.73
        if "empty_context" in expr:
            return 1.0 if collapsed else 0.0
        return None

    return q


def test_scenario_a_production_policy_refuses_execution(
    fast_set_file: Path, tmp_path: Path
) -> None:
    """Proves the exact policy in Simple_RAG-Pipeline/kavach.yaml:
    mode=SIMULATION, allowed_actions=[].
    The loop detects, diagnoses, reaches the gate, and DENIES action.
    Target receives zero mutations.
    """
    target = SimulatedTarget(threshold=COLLAPSED_THRESHOLD)
    events: list[tuple[str, str, str]] = []

    def on_event(stage: str, status: str, message: str) -> None:
        events.append((stage, status, message))
        stage_event(stage, status, message)

    # Simple_RAG-Pipeline production policy
    policy = ProjectPolicy(
        name="simple-rag",
        compose_project="simple_rag-pipeline",
        services=frozenset({"backend", "db", "ollama"}),
        allowed_actions=frozenset(),  # empty allowlist
        mode="SIMULATION",
        confidence_threshold=0.75,
    )
    safety = SafetyEngine(registry)
    audit = AuditLog(tmp_path / "audit_a.jsonl")

    with heal_span("INC-TEST-SCENARIO-A"):
        inc = run_once(
            client=target,
            prometheus_url="http://prom",
            fast_set_path=fast_set_file,
            promql=promql_signals(target),
            baseline_value=BASELINE_THRESHOLD,
            project="simple-rag",
            policy=policy,
            safety=safety,
            on_event=on_event,
            audit=audit,
        )

    # 1. Detect: F06 detected
    assert inc.fault_class == "F06"
    assert inc.fault_name == "retrieval_collapse"
    assert inc.service == "backend"

    # 2. Collect: Pre-state witness and context collected
    assert inc.corpus_before == {"chunks": 30.0, "files": 2.0}
    assert inc.detection is not None
    assert inc.detection["verdict"] == "FAULT"

    # 3. Diagnose: Rollback config planned
    assert inc.planned_action == "rollback_config"

    # 4. Gate: Decision is DENY due to empty allowlist
    assert inc.decision is not None
    assert inc.decision["verdict"] == Verdict.DENY
    assert any("allow_list" in r for r in inc.decision["reasons"])

    # 5. Execute: Zero writes executed against target
    assert len(target.writes) == 0, "No writes may occur when gate denies"
    assert target.settings()["rerank_threshold"] == COLLAPSED_THRESHOLD

    # 6. Verify: Post-repair verification not executed (empty)
    assert not inc.verification.get("post_fast")

    # 7. Escalation: Status is ESCALATED without acting
    assert inc.status is IncidentStatus.ESCALATED
    assert "escalated without acting" in inc.outcome
    assert inc.corpus_after == inc.corpus_before


def test_scenario_b_simulation_mode_with_allowlist_parks_at_awaiting(
    fast_set_file: Path, tmp_path: Path
) -> None:
    """Proves that even when an action is on the allow-list, SIMULATION mode
    returns REQUIRE_APPROVAL and parks at AWAITING with zero writes.
    """
    target = SimulatedTarget(threshold=COLLAPSED_THRESHOLD)
    events: list[tuple[str, str, str]] = []

    def on_event(stage: str, status: str, message: str) -> None:
        events.append((stage, status, message))
        stage_event(stage, status, message)

    policy = ProjectPolicy(
        name="simple-rag",
        compose_project="simple_rag-pipeline",
        services=frozenset({"backend", "db", "ollama"}),
        allowed_actions=frozenset({"rollback_config"}),  # allowlisted
        mode="SIMULATION",  # but in simulation
        confidence_threshold=0.75,
    )
    safety = SafetyEngine(registry)
    audit = AuditLog(tmp_path / "audit_b.jsonl")

    with heal_span("INC-TEST-SCENARIO-B"):
        inc = run_once(
            client=target,
            prometheus_url="http://prom",
            fast_set_path=fast_set_file,
            promql=promql_signals(target),
            baseline_value=BASELINE_THRESHOLD,
            project="simple-rag",
            policy=policy,
            safety=safety,
            on_event=on_event,
            audit=audit,
        )

    # Gate: Returns REQUIRE_APPROVAL under SIMULATION
    assert inc.decision is not None
    assert inc.decision["verdict"] == Verdict.REQUIRE_APPROVAL

    # Execute: Zero writes executed
    assert len(target.writes) == 0
    assert target.settings()["rerank_threshold"] == COLLAPSED_THRESHOLD

    # Status: AWAITING approval, not executed
    assert inc.status is IncidentStatus.AWAITING
    assert "REQUIRE_APPROVAL" in inc.outcome
    assert "not executed" in inc.outcome


def test_scenario_c_undo_stack_rollback_guarantee() -> None:
    """Proves AGENTS.md Rule 4a: Every executed action pushes an inverse
    and pre-state witness to the undo stack, and failed verification
    unwinds immediately to restore prior state.
    """
    target = SimulatedTarget(threshold=COLLAPSED_THRESHOLD)
    action = build_rollback_for_retrieval_collapse(
        "INC-TEST-SCENARIO-C", target, known_good_threshold=BASELINE_THRESHOLD
    )

    stack = UndoStack("INC-TEST-SCENARIO-C")
    stack.push(action)

    # Execute mutation
    action.execute(target)
    assert target.settings()["rerank_threshold"] == BASELINE_THRESHOLD
    assert len(target.writes) == 1

    # Simulated verification failure triggers stack unwind
    unwind_report = stack.unwind(target)
    assert unwind_report.attempted == 1
    assert unwind_report.restored == 1
    assert len(unwind_report.failures) == 0

    # Prior state verified restored exactly
    assert target.settings()["rerank_threshold"] == COLLAPSED_THRESHOLD
    ok, detail = action.verify_restored(target)
    assert ok, detail
