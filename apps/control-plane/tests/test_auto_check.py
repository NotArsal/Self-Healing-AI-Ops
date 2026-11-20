"""Automatic checks: a loop run every few minutes with nobody clicking (ADR 0032)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from kavach import loop
from kavach.api import routes
from kavach.api import schemas as s
from kavach.api.runner import LoopRunner, NoBaselineError
from kavach.config import Settings

T0 = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)


def a_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
             **settings: Any) -> tuple[LoopRunner, list[str]]:
    """A runner whose `start()` only records who started it."""
    runner = LoopRunner(Settings(kavach_root=str(tmp_path), **settings))
    started: list[str] = []

    async def start(use_rca: bool = True, approved: Any = None,
                    started_by: str = "operator") -> loop.Incident:
        started.append(started_by)
        return loop.Incident(incident_id=f"INC-{len(started)}", project="p")

    monkeypatch.setattr(runner, "start", start)
    return runner, started


@pytest.mark.asyncio
async def test_off_by_default_and_does_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, started = a_runner(tmp_path, monkeypatch)
    assert await runner.auto_check_tick(T0) == "off"
    assert started == [] and runner.auto_check_state()["enabled"] is False


@pytest.mark.asyncio
async def test_on_it_checks_at_once_then_once_per_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, started = a_runner(tmp_path, monkeypatch)
    runner.set_auto_check(True)

    assert await runner.auto_check_tick(T0) == "started INC-1"
    assert await runner.auto_check_tick(T0 + timedelta(seconds=299)) == "waiting"
    assert await runner.auto_check_tick(T0 + timedelta(seconds=300)) == "started INC-2"
    assert started == ["automatic check", "automatic check"]

    state = runner.auto_check_state()
    assert state["next_at"] == (T0 + timedelta(seconds=600)).isoformat(timespec="seconds")
    assert state["last_result"] == "started INC-2"


@pytest.mark.asyncio
async def test_it_never_runs_while_a_plan_waits_for_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each run would park a duplicate and spend the limit the Approve needs."""
    runner, started = a_runner(tmp_path, monkeypatch)
    runner._awaiting["INC-7"] = {}
    runner.set_auto_check(True)
    result = await runner.auto_check_tick(T0)
    assert result == "skipped: 1 plan(s) waiting for approval (INC-7)"
    assert started == []


@pytest.mark.asyncio
async def test_it_never_runs_alongside_another_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, started = a_runner(tmp_path, monkeypatch)
    runner._running = "INC-8"
    runner.set_auto_check(True)
    assert await runner.auto_check_tick(T0) == "skipped: INC-8 is already running"
    assert started == []


@pytest.mark.asyncio
async def test_a_refused_start_is_recorded_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = LoopRunner(Settings(kavach_root=str(tmp_path)))

    async def start(**_: Any) -> loop.Incident:
        raise NoBaselineError("no baseline capture")

    monkeypatch.setattr(runner, "start", start)
    runner.set_auto_check(True)
    assert await runner.auto_check_tick(T0) == "not started: NoBaselineError: no baseline capture"
    assert runner.auto_check_state()["last_result"].startswith("not started")


def test_switching_is_audited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner, _ = a_runner(tmp_path, monkeypatch)
    runner.set_auto_check(True)
    row = next(r for r in runner.audit.rows() if r["event"] == "auto_check_change")
    assert (row["actor"], row["previous"], row["enabled"]) == ("operator", False, True)
    assert runner.audit.verify().intact


def test_the_setting_is_the_default_and_the_interval_has_a_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, _ = a_runner(tmp_path, monkeypatch, auto_check=True, auto_check_every_s=600)
    assert runner.auto_check_state()["enabled"] is True
    assert runner.auto_check_state()["every_s"] == 600
    with pytest.raises(ValidationError):
        Settings(auto_check_every_s=10)


@pytest.mark.asyncio
async def test_the_routes_read_and_switch_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, _ = a_runner(tmp_path, monkeypatch)
    assert (await routes.get_auto_check(runner)).enabled is False
    out = await routes.set_auto_check(s.AutoCheckChange(enabled=True), runner)
    assert out.enabled is True and out.every_s == 300


@pytest.mark.asyncio
async def test_the_timeline_says_who_started_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kavach.api.events import bus
    from kavach.safety.engine import ProjectPolicy

    runner = LoopRunner(Settings(kavach_root=str(tmp_path)))
    monkeypatch.setattr(loop, "run_once", lambda *_, incident_id="", **__: loop.Incident(
        incident_id=incident_id, project="p", status=loop.IncidentStatus.NO_FAULT))
    monkeypatch.setattr(runner, "baseline", lambda: (0.35, "test"))
    monkeypatch.setattr(runner, "baseline_doc", lambda: {})
    monkeypatch.setattr(runner, "repair_values", lambda: {})
    monkeypatch.setattr(runner, "fast_set_path", lambda: tmp_path / "unused.yaml")
    monkeypatch.setattr(runner, "policy", lambda: ProjectPolicy(name="p", compose_project="c"))

    inc = await runner.start(use_rca=False, started_by="automatic check")
    for _ in range(500):
        if not runner._running:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    first = next(e for e in bus.replay()
                 if e.get("incident_id") == inc.incident_id and e["stage"] == "run")
    assert first["message"].startswith("automatic check started a loop run")


@pytest.mark.asyncio
async def test_one_bad_tick_does_not_end_automatic_checks() -> None:
    from kavach.main import auto_check_forever

    ticks: list[int] = []

    class Runner:
        async def auto_check_tick(self, _now: datetime) -> str:
            ticks.append(1)
            if len(ticks) == 1:
                raise RuntimeError("one bad tick")
            return "off"

    task = asyncio.create_task(auto_check_forever(cast(LoopRunner, Runner()), tick_s=0))
    while len(ticks) < 3:
        await asyncio.sleep(0)
    task.cancel()
    assert len(ticks) >= 3
