"""An incident that reads AWAITING_APPROVAL can be approved at that moment.

Found 2026-11-19 by the larger-corpus bench: the worker stored the status
first, then wrote the decision and the hypotheses rows, then parked the plan,
and freed the run slot last. The bench polls every 3 s and approves on sight,
so it landed in that gap and got 409 (not parked yet, or "a run is already
in flight"), and the heal never ran.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from kavach import loop
from kavach.api.runner import LoopRunner
from kavach.config import Settings
from kavach.safety.engine import ProjectPolicy


def stub(runner: LoopRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
         status: loop.IncidentStatus) -> None:
    def run_once(*_: Any, incident_id: str = "", **__: Any) -> loop.Incident:
        return loop.Incident(
            incident_id=incident_id, project="p", status=status, fault_class="F08",
            service="backend", planned_action="rollback_config",
            diagnosed_by="deterministic", action={"requested_settings": {"max_tokens": 0}})

    monkeypatch.setattr(loop, "run_once", run_once)
    monkeypatch.setattr(runner, "baseline", lambda: (0.35, "test"))
    monkeypatch.setattr(runner, "baseline_doc", lambda: {})
    monkeypatch.setattr(runner, "repair_values", lambda: {})
    monkeypatch.setattr(runner, "fast_set_path", lambda: tmp_path / "unused.yaml")
    monkeypatch.setattr(runner, "policy", lambda: ProjectPolicy(name="p", compose_project="c"))


@pytest.mark.asyncio
async def test_awaiting_is_shown_only_once_it_can_be_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = LoopRunner(Settings(kavach_root=str(tmp_path)))
    stub(runner, tmp_path, monkeypatch, loop.IncidentStatus.AWAITING)
    seen: list[tuple[bool, str]] = []
    remember = runner._remember

    def watch(inc: loop.Incident) -> None:
        if inc.status is loop.IncidentStatus.AWAITING:
            # What an approve arriving at exactly this moment would meet.
            seen.append((inc.incident_id in runner._awaiting, runner._running))
        remember(inc)

    monkeypatch.setattr(runner, "_remember", watch)
    await runner.start(use_rca=False)
    for _ in range(500):
        if seen:
            break
        await asyncio.sleep(0.01)

    assert seen and seen[0] == (True, ""), f"parked, slot held: {seen}"


@pytest.mark.asyncio
async def test_a_run_never_frees_a_slot_another_run_now_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Freeing the slot early means the old worker's `finally` must not clear
    a slot a newer run has taken in the meantime."""
    runner = LoopRunner(Settings(kavach_root=str(tmp_path)))
    stub(runner, tmp_path, monkeypatch, loop.IncidentStatus.NO_FAULT)
    remember = runner._remember

    def take_slot(inc: loop.Incident) -> None:
        if inc.status is loop.IncidentStatus.NO_FAULT:
            runner._running = "INC-NEWER"   # a new run started in the gap
        remember(inc)

    monkeypatch.setattr(runner, "_remember", take_slot)
    await runner.start(use_rca=False)
    for _ in range(500):
        if runner._running == "INC-NEWER":
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)   # let the old worker reach its `finally`
    assert runner._running == "INC-NEWER"
