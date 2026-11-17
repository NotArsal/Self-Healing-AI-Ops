"""The Logs page shows what Kavach did, not only what went wrong.

Before, the control plane logged only failures and its own startup, so a day
of runs and approvals left the page holding one line and looking broken.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from kavach import loop, telemetry
from kavach.api import runner as runner_mod
from kavach.api.runner import LoopRunner
from kavach.config import Settings


@pytest.fixture(autouse=True)
def fresh_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    # The module logger caches its config on first use, so an earlier test
    # could have pinned one without the buffer. A fresh one sees this config.
    telemetry.configure_logging(Settings(log_level="DEBUG"))
    monkeypatch.setattr(runner_mod, "logger", structlog.get_logger("kavach.api.runner"))


def events() -> list[tuple[str, str, str]]:
    return [(r.level, r.event, r.incident_id) for r in telemetry.recent_logs(limit=20)]


def parked(tmp_path: Path) -> LoopRunner:
    r = LoopRunner(Settings(kavach_root=str(tmp_path)))
    inc = loop.Incident(incident_id="INC-1", project="simple-rag",
                        status=loop.IncidentStatus.AWAITING)
    r._remember(inc)
    plan = loop.ApprovedPlan(
        incident_id="INC-1", fault_class="F08", service="backend",
        action="rollback_config", requested_settings={"max_tokens": 0},
        rca={}, diagnosed_by="deterministic")
    r._awaiting["INC-1"] = {"plan": plan, "use_rca": False}
    return r


def test_a_rejection_is_logged(tmp_path: Path) -> None:
    parked(tmp_path).reject("INC-1", "looks deliberate")
    assert ("info", "plan rejected", "INC-1") in events()


@pytest.mark.asyncio
async def test_an_approval_is_logged_with_the_run_that_fixes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = parked(tmp_path)

    async def start(use_rca: bool = True,
                    approved: loop.ApprovedPlan | None = None) -> loop.Incident:
        return loop.Incident(incident_id="INC-2", project="p")

    monkeypatch.setattr(r, "start", start)
    await r.approve("INC-1")
    row = next(x for x in telemetry.recent_logs(limit=20) if x.event == "plan approved")
    assert row.incident_id == "INC-1" and "fix_run=INC-2" in row.detail


@pytest.mark.parametrize(("status", "level"), [
    (loop.IncidentStatus.RESOLVED, "info"),
    (loop.IncidentStatus.AWAITING, "info"),
    (loop.IncidentStatus.NO_FAULT, "info"),
    (loop.IncidentStatus.ESCALATED, "warning"),
])
def test_every_finished_run_is_logged_and_an_escalation_stands_out(
    status: loop.IncidentStatus, level: str,
) -> None:
    runner_mod.log_run_end(loop.Incident(incident_id="INC-9", project="p", status=status))
    row = telemetry.recent_logs(limit=1)[0]
    assert (row.level, row.event, row.incident_id) == (level, "run finished", "INC-9")
    assert f"status={status}" in row.detail


@pytest.mark.target_repo
def test_a_mode_change_is_logged(tmp_path: Path) -> None:
    LoopRunner(Settings(kavach_root=str(tmp_path))).set_mode("AUTONOMOUS")
    row = telemetry.recent_logs(limit=1)[0]
    assert row.event == "mode changed" and "mode=AUTONOMOUS" in row.detail
