"""Timeline events survive a restart (2026-11-13).

Events lived only in the API's memory, so after every restart the timeline of
every past incident was empty. They are now also written to the store, and
read back per incident. Zero network: the store is a stand-in.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from kavach.api import routes
from kavach.api.events import EventBus
from kavach.api.runner import LoopRunner
from kavach.config import Settings
from kavach.db.store import IncidentStore


def test_each_event_reaches_the_sink_exactly_as_published() -> None:
    """The console identifies an event by seq + at, so the stored copy must
    carry the same pair or the two would show as two lines."""
    bus = EventBus()
    kept: list[dict[str, Any]] = []
    bus.sink = kept.append

    event = bus.publish("detect", "ok", "fault found", incident_id="INC-1")

    assert kept == [event]


@pytest.mark.asyncio
async def test_on_the_event_loop_the_write_happens_off_it() -> None:
    bus = EventBus()
    kept: list[dict[str, Any]] = []
    bus.sink = kept.append

    event = bus.publish("detect", "ok", "fault found", incident_id="INC-1")
    await asyncio.sleep(0.05)  # the executor runs the write

    assert kept == [event]


def test_a_broken_sink_never_stops_publishing() -> None:
    bus = EventBus()

    def broken(_event: dict[str, Any]) -> None:
        raise RuntimeError("database gone")

    bus.sink = broken
    assert bus.publish("detect", "ok", "still published")["seq"] == 1


def test_a_store_that_is_down_keeps_nothing_and_never_raises() -> None:
    store = IncidentStore("postgresql+psycopg://nobody@127.0.0.1:1/none")
    store.save_event({"seq": 1, "at": "t", "incident_id": "INC-1",
                      "stage": "detect", "status": "ok", "message": "m"})
    assert store.events("INC-1") == []


@pytest.mark.asyncio
async def test_the_route_returns_the_stored_timeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = LoopRunner(Settings(kavach_root=str(tmp_path)))
    stored = [{"seq": 3, "at": "2026-11-13T05:44:30.000+00:00", "incident_id": "INC-1",
               "stage": "resolve", "status": "ok", "message": "resolved"}]
    monkeypatch.setattr(runner.store, "events",
                        lambda incident_id: stored if incident_id == "INC-1" else [])

    out = await routes.incident_events("INC-1", runner)

    assert [e.model_dump() for e in out] == stored
    assert await routes.incident_events("INC-2", runner) == []


def test_startup_points_the_bus_at_the_store_and_lets_go_at_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    import kavach.main as main
    from kavach.api.events import bus

    def save_event(_event: dict[str, Any]) -> None:
        return None

    class Stub:
        store = SimpleNamespace(available=lambda: True, save_event=save_event)

        def init_store(self) -> bool:
            return True

        def recover(self) -> None:
            return None

    monkeypatch.setattr(routes, "get_runner", lambda _settings: Stub())
    with TestClient(main.create_app()):
        assert bus.sink is save_event
    assert bus.sink is None


@pytest.mark.asyncio
async def test_the_incident_list_takes_a_limit_for_the_history_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = LoopRunner(Settings(kavach_root=str(tmp_path)))
    asked: list[int] = []

    def history(limit: int = 50) -> list[Any]:
        asked.append(limit)
        return []

    monkeypatch.setattr(runner, "history", history)
    await routes.list_incidents(runner)
    await routes.list_incidents(runner, limit=1000)
    assert asked == [50, 1000]


def test_a_nan_metric_no_longer_costs_the_whole_incident_row() -> None:
    """Postgres JSON has no NaN; one 0/0 rate from Prometheus made it refuse the
    finished result, and the row stayed DETECTED for good (2026-11-13)."""
    import json
    import math

    from kavach.db.store import json_safe

    record: dict[str, Any] = {"status": "ESCALATED",
              "detection": {"signals": [{"name": "retrieval_top_similarity",
                                         "value": math.nan},
                                        {"name": "ratio", "value": math.inf}],
                            "rate": 0.5}}
    safe = json_safe(record)

    assert safe["detection"]["signals"][0]["value"] is None
    assert safe["detection"]["signals"][1]["value"] is None
    assert safe["detection"]["rate"] == 0.5
    json.dumps(safe, allow_nan=False)  # what Postgres accepts
    assert math.isnan(record["detection"]["signals"][0]["value"]), "input untouched"
