"""Every RCA's ranked candidates reach the `hypotheses` table.

The table existed from the start and nothing ever wrote to it: the flow it was
built for (`PRD.md` §8.4) is not implemented, while every LLM diagnosis was
already ranking candidates in its JSON.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from kavach import loop
from kavach.api.runner import LoopRunner, hypotheses_from
from kavach.config import Settings
from kavach.safety.engine import ProjectPolicy

# The shape stored for INC-20261117-135102, trimmed.
RCA: dict[str, Any] = {
    "approved": True,
    "diagnosis": {
        "fault_class": "F08", "fault_name": "Configuration regression",
        "service": "backend", "confidence": 0.85,
        "evidence_ids": ["EV-M06", "EV-C04"],
        "rejected_alternatives": [
            {"fault_class": "F01", "reason": "llm_error_ratio=0.0"},
            {"fault_class": "F06", "reason": "grounding intact"},
        ],
    },
}


def an_incident(**kw: Any) -> loop.Incident:
    return loop.Incident(incident_id="INC-1", project="p", rca=RCA, **kw)


def test_the_chosen_fault_ranks_first_and_the_ruled_out_follow() -> None:
    rows = hypotheses_from(an_incident(status=loop.IncidentStatus.RESOLVED,
                                       verification={"passed": 3}))
    assert [r["rank"] for r in rows] == [1, 2, 3]
    top = rows[0]
    assert top["description"] == "F08 Configuration regression on backend"
    assert top["confidence"] == 0.85 and top["evidence_ids"] == ["EV-M06", "EV-C04"]
    assert top["tested"] is True
    assert top["outcome"] == "accepted by validation; incident RESOLVED"
    assert rows[2] == {"rank": 3, "description": "F06: grounding intact", "confidence": 0.0,
                       "evidence_ids": [], "tested": False,
                       "outcome": "ruled out by the model"}


def test_a_parked_plan_is_not_marked_tested() -> None:
    rows = hypotheses_from(an_incident(status=loop.IncidentStatus.AWAITING))
    assert rows[0]["tested"] is False


@pytest.mark.parametrize("rca", [{}, {"error": "timeout"}, {"diagnosis": {}}])
def test_no_diagnosis_means_no_rows(rca: dict[str, Any]) -> None:
    assert hypotheses_from(loop.Incident(incident_id="INC-1", project="p", rca=rca)) == []


@pytest.mark.asyncio
async def test_a_finished_run_writes_its_hypotheses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = LoopRunner(Settings(kavach_root=str(tmp_path)))
    saved: list[tuple[str, list[dict[str, Any]]]] = []

    def run_once(*_: Any, incident_id: str = "", **__: Any) -> loop.Incident:
        return loop.Incident(incident_id=incident_id, project="p", rca=RCA,
                             status=loop.IncidentStatus.ESCALATED)

    monkeypatch.setattr(loop, "run_once", run_once)
    monkeypatch.setattr(runner.store, "save_hypotheses",
                        lambda iid, items: saved.append((iid, items)))
    monkeypatch.setattr(runner, "baseline", lambda: (0.35, "test"))
    monkeypatch.setattr(runner, "baseline_doc", lambda: {})
    monkeypatch.setattr(runner, "repair_values", lambda: {})
    monkeypatch.setattr(runner, "fast_set_path", lambda: tmp_path / "unused.yaml")
    monkeypatch.setattr(runner, "policy", lambda: ProjectPolicy(name="p", compose_project="c"))

    inc = await runner.start(use_rca=False)
    for _ in range(500):
        if not runner._running:
            break
        await asyncio.sleep(0.01)

    assert [(iid, len(items)) for iid, items in saved] == [(inc.incident_id, 3)]
