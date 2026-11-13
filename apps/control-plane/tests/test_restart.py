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


# --- wiring -----------------------------------------------------------------


def test_the_api_recovers_at_startup_after_connecting_the_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from kavach.main import create_app

    calls: list[str] = []

    class Stub:
        def init_store(self) -> bool:
            calls.append("init_store")
            return False

        def recover(self) -> None:
            calls.append("recover")

    monkeypatch.setattr(routes, "get_runner", lambda _settings: Stub())
    with TestClient(create_app()):
        pass
    assert calls == ["init_store", "recover"]
