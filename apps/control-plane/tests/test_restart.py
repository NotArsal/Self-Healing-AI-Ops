"""What a restart may lose, and what it must not leave lying (ADR 0028).

Parked plans and the operator's mode change live in the API process's memory.
Before ADR 0028 a restart lost both while the stored rows and the console
still claimed otherwise: 117 incidents read "Awaiting approval" with an
Approve button that could only fail, and every one of them had in fact been
approved. Zero network: the store is a stand-in, the audit log is a temp file.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from kavach import loop
from kavach.api import routes
from kavach.api.runner import LoopRunner
from kavach.config import Settings
from kavach.db.store import IncidentStore

T0 = "2026-11-12T20:46:36+00:00"
EARLIER = "2026-11-11T20:46:50+00:00"
LATER = "2026-11-12T20:46:51.395+00:00"


class FakeStore(IncidentStore):
    """Only the two calls recovery makes. The constructor never connects."""

    def __init__(self, *records: dict[str, Any]) -> None:
        super().__init__("postgresql+psycopg://nobody@127.0.0.1:1/none")
        self.rows = {r["incident_id"]: dict(r) for r in records}

    def with_status(self, *statuses: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.rows.values() if r["status"] in statuses]

    def save(self, record: dict[str, Any]) -> None:
        self.rows[record["incident_id"]] = dict(record)


def a_runner(tmp_path: Path, *records: dict[str, Any]) -> tuple[LoopRunner, FakeStore]:
    runner = LoopRunner(Settings(kavach_root=str(tmp_path)))
    store = FakeStore(*records)
    runner.store = store
    return runner, store


def row(status: str, incident_id: str = "INC-204636") -> dict[str, Any]:
    return {"incident_id": incident_id, "project": "simple-rag", "status": status,
            "detected_at": T0, "outcome": "", "escalation_reason": "",
            "rca": {"kept": "every other field survives"}}


def audit_at(runner: LoopRunner, at: str, event: str, **fields: Any) -> None:
    """An audit row with a chosen time. `append` stamps now, so rewrite it."""
    runner.audit.append(event, **fields)
    lines = runner.audit.path.read_text(encoding="utf-8").splitlines()
    last = json.loads(lines[-1])
    last["at"] = at
    lines[-1] = json.dumps(last)
    runner.audit.path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- parked plans -----------------------------------------------------------


def test_a_parked_plan_the_audit_shows_approved_becomes_approved(tmp_path: Path) -> None:
    runner, store = a_runner(tmp_path, row("AWAITING_APPROVAL"))
    audit_at(runner, LATER, "approved", incident_id="INC-204636", actor="operator")
    audit_at(runner, LATER, "permit", incident_id="INC-204651",
             approved_from="INC-204636")

    runner.recover()

    saved = store.rows["INC-204636"]
    assert saved["status"] == "APPROVED"
    assert "INC-204651" in saved["outcome"]
    assert saved["rca"] == {"kept": "every other field survives"}


def test_an_approval_from_another_day_with_the_same_id_does_not_count(
    tmp_path: Path,
) -> None:
    """IDs are INC-HHMMSS and repeat across days."""
    runner, store = a_runner(tmp_path, row("AWAITING_APPROVAL"))
    audit_at(runner, EARLIER, "approved", incident_id="INC-204636", actor="operator")

    runner.recover()

    assert store.rows["INC-204636"]["status"] == "ESCALATED"


def test_a_parked_plan_nobody_decided_lapses_and_says_so(tmp_path: Path) -> None:
    runner, store = a_runner(tmp_path, row("AWAITING_APPROVAL"))

    runner.recover()

    saved = store.rows["INC-204636"]
    assert saved["status"] == "ESCALATED"
    assert "approval lapsed" in saved["escalation_reason"]
    assert "not executed" in saved["outcome"]
    assert [r["event"] for r in runner.audit.rows()] == ["approval_lapsed"]


# --- runs that never finished -----------------------------------------------


@pytest.mark.parametrize("status", ["DETECTED", "HEALING"])
def test_a_run_that_never_finished_is_escalated(tmp_path: Path, status: str) -> None:
    runner, store = a_runner(tmp_path, row(status))

    runner.recover()

    saved = store.rows["INC-204636"]
    assert saved["status"] == "ESCALATED"
    assert "nothing was written" in saved["outcome"]


def test_an_unfinished_run_that_started_a_repair_says_check_the_target(
    tmp_path: Path,
) -> None:
    runner, store = a_runner(tmp_path, row("DETECTED"))
    audit_at(runner, LATER, "execute_start", incident_id="INC-204636",
             action="rollback_config")

    runner.recover()

    assert "check the target" in store.rows["INC-204636"]["outcome"]


def test_finished_incidents_are_left_alone(tmp_path: Path) -> None:
    runner, store = a_runner(tmp_path, row("RESOLVED"), row("APPROVED", "INC-2"))

    runner.recover()

    assert store.rows["INC-204636"]["status"] == "RESOLVED"
    assert store.rows["INC-2"]["status"] == "APPROVED"
    assert runner.audit.rows() == []


# --- the Approve button -----------------------------------------------------


@pytest.mark.asyncio
async def test_approve_is_offered_only_while_the_plan_is_held(tmp_path: Path) -> None:
    """Status alone is not enough: the plan may be gone with a restart."""
    runner, _ = a_runner(tmp_path)
    inc = loop.Incident(incident_id="INC-1", project="simple-rag")
    inc.status = loop.IncidentStatus.AWAITING
    runner._remember(inc)

    assert (await routes.get_incident("INC-1", runner)).awaiting_approval is False

    runner._awaiting["INC-1"] = {}
    assert (await routes.get_incident("INC-1", runner)).awaiting_approval is True


# --- the operator's mode ----------------------------------------------------


def a_manifest_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LoopRunner:
    """Recovery reads only the manifest's mode, so that is all this carries."""
    runner, _ = a_runner(tmp_path)
    monkeypatch.setattr(runner, "manifest", lambda: SimpleNamespace(mode="APPROVAL"))
    return runner


def test_a_stricter_mode_comes_back_after_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator who stopped all writes must not get them back by a restart."""
    runner = a_manifest_runner(tmp_path, monkeypatch)
    runner.audit.append("mode_change", actor="operator",
                        previous="APPROVAL", mode="SIMULATION")

    runner.recover()

    assert runner._mode_override == "SIMULATION"
    assert runner.audit.rows()[-1]["event"] == "mode_restored"


def test_a_looser_mode_does_not_come_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A restart never loosens. AUTONOMOUS is set again by a person or not at all."""
    runner = a_manifest_runner(tmp_path, monkeypatch)
    runner.audit.append("mode_change", actor="operator",
                        previous="APPROVAL", mode="AUTONOMOUS")

    runner.recover()

    assert runner._mode_override is None
    assert runner.audit.rows()[-1]["event"] == "mode_not_restored"


def test_the_manifest_mode_needs_no_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = a_manifest_runner(tmp_path, monkeypatch)
    runner.audit.append("mode_change", actor="operator",
                        previous="SIMULATION", mode="APPROVAL")

    runner.recover()

    assert runner._mode_override is None
    assert runner.audit.rows()[-1]["event"] == "mode_change"


# --- a store that connects late (Docker restart, 2026-11-13) ---------------


class LateStore(FakeStore):
    """Refuses `ok_after` connection attempts, then accepts."""

    def __init__(self, *records: dict[str, Any], ok_after: int = 0) -> None:
        super().__init__(*records)
        self.attempts = 0
        self.ok_after = ok_after

    def init(self, create: bool = True) -> bool:
        self.attempts += 1
        if self.attempts <= self.ok_after:
            self._reason = "the database system is starting up"
            return False
        self._reason = ""
        return True

    def available(self) -> bool:
        return self.attempts > self.ok_after

    def save(self, record: dict[str, Any]) -> None:
        # The real store drops writes while it is down.
        if self.available():
            super().save(record)


def late_runner(tmp_path: Path, *records: dict[str, Any], ok_after: int) -> tuple[
    LoopRunner, LateStore
]:
    runner = LoopRunner(Settings(kavach_root=str(tmp_path)))
    store = LateStore(*records, ok_after=ok_after)
    runner.store = store
    return runner, store


@pytest.mark.asyncio
async def test_the_api_keeps_trying_the_store_and_then_settles_it(tmp_path: Path) -> None:
    """It tried once at startup, failed, and served an empty list for good."""
    from kavach.main import connect_when_ready

    runner, store = late_runner(tmp_path, row("AWAITING_APPROVAL"), ok_after=3)
    assert runner.init_store() is False  # the one startup attempt

    await connect_when_ready(runner, every_s=0)

    assert store.available()
    assert store.rows["INC-204636"]["status"] == "ESCALATED"  # settled once up
    inits = [r for r in runner.audit.rows() if r["event"] == "store_init"]
    # The startup failure and the success; the quiet retries leave no row.
    assert [r["available"] for r in inits] == [False, True]


def test_incidents_run_while_the_store_was_down_are_written_when_it_connects(
    tmp_path: Path,
) -> None:
    runner, store = late_runner(tmp_path, ok_after=1)
    runner.init_store()
    inc = loop.Incident(incident_id="INC-1", project="simple-rag")
    inc.status = loop.IncidentStatus.RESOLVED
    runner._remember(inc)  # store down: memory only
    assert "INC-1" not in store.rows

    assert runner.init_store(quiet=True) is True
    assert store.rows["INC-1"]["status"] == "RESOLVED"


def test_a_late_settle_leaves_this_process_s_own_plan_and_run_alone(
    tmp_path: Path,
) -> None:
    runner, store = a_runner(
        tmp_path, row("AWAITING_APPROVAL", "INC-PARKED"), row("DETECTED", "INC-RUNNING"),
    )
    runner._awaiting["INC-PARKED"] = {}
    runner._running = "INC-RUNNING"

    runner.settle()

    assert store.rows["INC-PARKED"]["status"] == "AWAITING_APPROVAL"
    assert store.rows["INC-RUNNING"]["status"] == "DETECTED"


# --- wiring -----------------------------------------------------------------


@pytest.mark.parametrize(("available", "retries"), [(False, 1), (True, 0)])
def test_startup_recovers_and_retries_the_store_only_if_it_is_down(
    monkeypatch: pytest.MonkeyPatch, available: bool, retries: int,
) -> None:
    from fastapi.testclient import TestClient

    import kavach.main as main

    calls: list[str] = []

    class Stub:
        store = SimpleNamespace(available=lambda: available,
                                save_event=lambda _event: None)

        def init_store(self) -> bool:
            calls.append("init_store")
            return available

        def recover(self) -> None:
            calls.append("recover")

    async def retry(_runner: Any) -> None:
        calls.append("retry")

    monkeypatch.setattr(routes, "get_runner", lambda _settings: Stub())
    monkeypatch.setattr(main, "connect_when_ready", retry)
    with TestClient(main.create_app()):
        pass
    assert calls[:2] == ["init_store", "recover"]
    assert calls.count("retry") == retries


# --- incident IDs -------------------------------------------------------------


def test_an_incident_id_does_not_repeat_on_another_day() -> None:
    """INC-HHMMSS repeated daily, and the store upserts on the ID."""
    from datetime import UTC, datetime

    from kavach.api.runner import new_incident_id

    monday = new_incident_id(datetime(2026, 11, 16, 20, 46, 36, tzinfo=UTC))
    tuesday = new_incident_id(datetime(2026, 11, 17, 20, 46, 36, tzinfo=UTC))
    assert monday == "INC-20261116-204636"
    assert monday != tuesday
