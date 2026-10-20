"""Reading an incident back out of the store.

Incidents were always persisted. Both incident routes read the in-process
ring anyway, so an API restart emptied the console's history and
`make postmortem` printed "no incidents recorded yet" with 137 rows sitting
in Postgres (`RESEARCH_NOTES.md` section 7.2).

Three properties are worth pinning, and only one of them is "the list is
longer":

  - a stored record round-trips into a real `Incident`, so the API's
    existing mappers serve a restored one unchanged,
  - memory wins a collision, because `_remember` writes to the store
    best-effort and the memory copy can be the newer one,
  - a restored incident CANNOT be approved. `approve()` gates on
    `_awaiting`, which is memory and is never repopulated. If that ever
    changed, a plan derived from a world that has since moved could be
    executed after a restart.

The third is the one that would be dangerous to get wrong, so it is tested
against the real `approve()` rather than by reading the code.
"""

from __future__ import annotations

from typing import Any

import pytest

from kavach.api.runner import LoopRunner
from kavach.config import Settings
from kavach.db.store import IncidentStore
from kavach.executor import catalogue  # noqa: F401 - registers the actions
from kavach.loop import Incident, IncidentStatus


class FakeStore(IncidentStore):
    """The store's read surface, with a list behind it instead of Postgres.

    A real subclass rather than a hand-rolled double, so no call site needs a
    `type: ignore` - AGENTS.md forbids those, and one here would also stop
    the test noticing if `history()` started calling some other store method.
    `IncidentStore.__init__` opens no socket (see `LoopRunner.__init__`), so
    this costs nothing, and `PL-02` plus the offline rehearsal both require
    the suite to run with nothing external up.
    """

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        super().__init__("postgresql+psycopg://unused/unused")
        self.rows: list[dict[str, Any]] = rows or []
        self.saved: list[dict[str, Any]] = []

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.rows[:limit]

    def get(self, incident_id: str) -> dict[str, Any] | None:
        return next((r for r in self.rows
                     if r.get("incident_id") == incident_id), None)

    def save(self, record: dict[str, Any]) -> None:
        self.saved.append(record)

    def available(self) -> bool:
        return True


def _incident(incident_id: str, detected_at: str,
              status: IncidentStatus = IncidentStatus.RESOLVED,
              fault_class: str = "F06") -> Incident:
    return Incident(
        incident_id=incident_id,
        project="simple-rag",
        detected_at=detected_at,
        status=status,
        fault_class=fault_class,
        fault_name="retrieval_collapse",
        service="backend",
    )


@pytest.fixture
def runner() -> LoopRunner:
    r = LoopRunner(Settings())
    r.store = FakeStore()
    return r


def _rows(runner: LoopRunner) -> list[dict[str, Any]]:
    """The fake's backing list, typed, so no test needs a cast."""
    store = runner.store
    assert isinstance(store, FakeStore)
    return store.rows


# --- the round trip ---------------------------------------------------------


def test_a_stored_record_round_trips_into_a_real_incident() -> None:
    """`to_dict` is what the store persists, so `from_dict` has to invert it
    exactly - otherwise the API needs a second reconstruction layer and the
    two can disagree."""
    original = _incident("INC-000101", "2026-10-20T01:02:03+00:00")
    original.rca = {"model": "qwen2.5:7b-instruct",
                    "diagnosis": {"fault_class": "F06", "confidence": 0.95}}
    original.detection = {"verdict": "FAULT",
                          "concluded_at": "2026-10-20T01:02:21.500+00:00"}

    restored = Incident.from_dict(original.to_dict())

    assert restored == original
    assert restored.status is IncidentStatus.RESOLVED, "status came back a str"
    assert restored.detection["concluded_at"] == "2026-10-20T01:02:21.500+00:00"


def test_a_record_written_by_an_older_image_still_loads() -> None:
    """`detection.concluded_at` arrived mid-bench. A reader that required
    every current field would 500 on every row written before today."""
    restored = Incident.from_dict({
        "incident_id": "INC-000001",
        "project": "simple-rag",
        "status": "ESCALATED",
        "detected_at": "2026-10-01T00:00:00+00:00",
        "a_field_that_no_longer_exists": "ignored",
    })
    assert restored.incident_id == "INC-000001"
    assert restored.status is IncidentStatus.ESCALATED
    assert restored.fault_class is None, "an absent field was invented"
    assert restored.rca == {}


def test_a_record_with_no_status_does_not_invent_one() -> None:
    restored = Incident.from_dict(
        {"incident_id": "INC-000002", "project": "simple-rag"})
    assert restored.status is IncidentStatus.DETECTED


# --- the merge --------------------------------------------------------------


def test_history_returns_what_memory_lost(runner: LoopRunner) -> None:
    stored = _incident("INC-000050", "2026-10-19T23:00:00+00:00")
    _rows(runner).append(stored.to_dict())

    assert runner.incidents() == [], "nothing is in memory yet"
    assert [i.incident_id for i in runner.history()] == ["INC-000050"]


def test_memory_wins_a_collision_because_the_store_write_is_best_effort(
        runner: LoopRunner) -> None:
    """`_remember` saves best-effort, so a database that blinked mid-incident
    leaves a stale row. Preferring it would show RESOLVED as DETECTED, or
    worse, the reverse."""
    live = _incident("INC-000060", "2026-10-20T02:00:00+00:00",
                     status=IncidentStatus.RESOLVED)
    stale = _incident("INC-000060", "2026-10-20T02:00:00+00:00",
                      status=IncidentStatus.DETECTED)
    _rows(runner).append(stale.to_dict())
    runner._remember(live)

    rows = runner.history()
    assert len(rows) == 1, "the same incident came back twice"
    assert rows[0].status is IncidentStatus.RESOLVED


def test_history_is_newest_first_across_both_sources(
        runner: LoopRunner) -> None:
    _rows(runner).extend([
        _incident("INC-000003", "2026-10-20T03:00:00+00:00").to_dict(),
        _incident("INC-000001", "2026-10-20T01:00:00+00:00").to_dict(),
    ])
    runner._remember(_incident("INC-000002", "2026-10-20T02:00:00+00:00"))

    assert [i.incident_id for i in runner.history()] == [
        "INC-000003", "INC-000002", "INC-000001"]


def test_an_unreachable_store_degrades_to_the_old_behaviour() -> None:
    """A database that is down must never cost a read, as it must never stop
    a heal. A real `IncidentStore` that was never `init()`ed returns [] from
    `recent()` rather than raising, and this pins that the merge adds no
    failure mode on top of it."""
    r = LoopRunner(Settings())           # a REAL store, deliberately unconnected
    r._remember(_incident("INC-000070", "2026-10-20T04:00:00+00:00"))
    assert [i.incident_id for i in r.history()] == ["INC-000070"]
    assert r.find("INC-000070") is not None


def test_find_falls_back_to_the_store(runner: LoopRunner) -> None:
    _rows(runner).append(
        _incident("INC-000080", "2026-10-20T05:00:00+00:00").to_dict())
    found = runner.find("INC-000080")
    assert found is not None and found.incident_id == "INC-000080"
    assert runner.find("INC-999999") is None


# --- the one that matters ---------------------------------------------------


@pytest.mark.asyncio
async def test_a_restored_incident_cannot_be_approved(
        runner: LoopRunner) -> None:
    """THE safety property of this change.

    An incident parked AWAITING_APPROVAL before a restart is readable
    afterwards and must not be actionable: the plan it was parked with was
    derived from a world that has since moved, which is the same reason
    `approve()` re-detects rather than replaying (`runner.approve`).

    `_awaiting` is memory and `history()` never repopulates it. Tested
    against the real `approve()`, because a comment asserting this would not
    notice if the gate moved.

    The reads below are in the order the API performs them, and that is the
    point rather than tidiness. An earlier version of this test asserted on
    `awaiting()` without calling `history()` first, so a mutant that pushed
    restored AWAITING incidents straight into `_awaiting` passed it - the
    mutated line never ran. `GET /v1/incidents` calls `history()`, so the
    test has to.
    """
    parked = _incident("INC-000090", "2026-10-20T06:00:00+00:00",
                       status=IncidentStatus.AWAITING)
    _rows(runner).append(parked.to_dict())

    listed = runner.history()
    assert [i.incident_id for i in listed] == ["INC-000090"], "not readable"
    assert listed[0].status is IncidentStatus.AWAITING
    assert runner.find("INC-000090") is not None

    assert runner.awaiting() == [], (
        "a restored incident entered the approval set - its parked plan was "
        "derived from a world that has since moved")

    with pytest.raises(Exception) as excinfo:
        await runner.approve("INC-000090")
    assert "INC-000090" in str(excinfo.value)
