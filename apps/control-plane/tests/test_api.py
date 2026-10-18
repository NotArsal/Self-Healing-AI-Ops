"""The console API: serialisation, the single-flight slot, and the event bus.

The live demo found a 500 here that the console's own tests could not: the
frontend fixture carried an empty `detection.evidence`, so nothing exercised
the real `Detection.to_dict()` shape, whose values are floats and ints rather
than strings. These tests use the real dataclasses and their real `to_dict()`
output, which is the only way the wire contract gets checked against what the
loop actually produces.

Zero network calls. Nothing here touches the target, Prometheus or Ollama.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from kavach import loop
from kavach.api import routes, schemas
from kavach.api.events import EventBus
from kavach.api.runner import LoopBusyError, LoopRunner, NoBaselineError, newest_baseline
from kavach.config import Settings
from kavach.detection import base as det
from kavach.detection import retrieval_collapse as rc
from kavach.verification import fast

# --- helpers ----------------------------------------------------------------


def a_detection() -> rc.Detection:
    """A real detection, built through the real collector and evaluator."""
    metrics = rc.collect(
        det.Signals(prometheus_url="http://unused", promql=lambda _url, _q: None)
    )
    return rc.evaluate(metrics, fast_set_passed=False, fast_set_pass_rate=0.0)


def an_incident() -> loop.Incident:
    inc = loop.Incident(incident_id="INC-TEST", project="simple-rag")
    inc.detection = a_detection().to_dict()
    inc.detection["pre_verification"] = fast.FastVerificationResult().to_dict()
    inc.corpus_before = {"chunks": 30.0, "files": 2.0}
    inc.corpus_after = {"chunks": 30.0, "files": 2.0}
    return inc


# --- serialisation ----------------------------------------------------------


def test_incident_out_accepts_real_detection_evidence() -> None:
    """The regression the live demo caught: evidence values are not strings.

    `Detection.to_dict()` emits floats, ints and None depending on the signal.
    The response model types `value` as `str`, so every one of them has to go
    through the stringifier or the route returns a 500.
    """
    inc = an_incident()
    # Force the mixed-type values the real collector produces.
    inc.detection["evidence"] = [
        {"kind": "metric", "source": "retrieval_top_similarity", "value": 0.658,
         "expected": "0.4 to 0.9", "supports_fault": True},
        {"kind": "metric", "source": "retrieval_chunks_kept", "value": 0.0,
         "expected": 1, "supports_fault": True},
        {"kind": "metric", "source": "corpus_chunks", "value": 30,
         "expected": None, "supports_fault": False},
        {"kind": "config", "source": "rerank_threshold", "value": None,
         "expected": "", "supports_fault": False},
    ]

    out = routes.incident_out(inc)

    assert out.detection is not None
    values = [e.value for e in out.detection.evidence]
    assert values == ["0.658", "0.0", "30", "None"]
    assert all(isinstance(v, str) for v in values)
    # `None` is rendered, not dropped: no data is not zero and not healthy.
    assert out.detection.evidence[3].value == "None"


def test_incident_out_round_trips_a_bare_incident() -> None:
    out = routes.incident_out(loop.Incident(incident_id="INC-1", project="p"))
    assert out.incident_id == "INC-1"
    assert out.status == "DETECTED"
    assert out.rca is None
    assert out.action is None
    assert out.verification is None
    assert out.corpus_unchanged is None


def test_incident_out_reports_corpus_change() -> None:
    inc = an_incident()
    assert routes.incident_out(inc).corpus_unchanged is True
    inc.corpus_after = {"chunks": 29.0, "files": 2.0}
    assert routes.incident_out(inc).corpus_unchanged is False


def test_incident_out_carries_the_pre_verification_run() -> None:
    out = routes.incident_out(an_incident())
    assert out.detection is not None
    assert out.detection.pre_verification is not None
    assert out.detection.pre_verification.budget_s == 120


def test_evidence_value_stringifier_is_total() -> None:
    cases: list[tuple[Any, str]] = [
        (None, "None"), (True, "true"), (False, "false"),
        (0.0, "0.0"), (30, "30"), ("already", "already"),
        ({"a.txt": "ab12"}, "{'a.txt': 'ab12'}"),
    ]
    for value, expected in cases:
        assert schemas.to_evidence_value(value) == expected


def test_summary_omits_the_heavy_fields() -> None:
    """The history table must not pull a full evidence frame per row."""
    summary = routes.incident_summary(an_incident())
    assert not hasattr(summary, "rca")
    assert not hasattr(summary, "detection")


# --- the uncalibrated-confidence statement is on the wire -------------------


def test_rca_out_states_confidence_is_not_calibrated() -> None:
    """A second client must not be able to read the number as a probability."""
    out = schemas.RcaOut(
        at="", model="llama3.2", latency_s=2.2, approved=True,
        evidence=[], evidence_problems=[],
    )
    assert out.confidence_is_calibrated is False
    assert "confidence_is_calibrated" in schemas.RcaOut.model_fields


def test_system_out_defaults_to_the_mode_being_enforced() -> None:
    """Inverted at P5, not deleted: before the safety engine existed the mode
    was a label, and this asserted so. `permit()` now reads it, so the honest
    default is True - and the route still sends False when the manifest that
    carries the mode cannot be read, which the next test covers."""
    out = schemas.SystemOut(
        kavach_version="0.1.0", mode="SIMULATION", project="simple-rag",
        dependencies=[],
    )
    assert out.mode_is_enforced is True


def test_system_out_can_report_an_unenforced_mode() -> None:
    """No manifest means no policy, and the console must be able to say it."""
    out = schemas.SystemOut(
        kavach_version="0.1.0", mode="SIMULATION", project="simple-rag",
        mode_is_enforced=False, dependencies=[],
    )
    assert out.mode_is_enforced is False


def test_rca_out_has_no_raw_response_field() -> None:
    """Raw generations stay out of the browser (FR-28)."""
    assert "raw_response" not in schemas.RcaOut.model_fields


# --- the event bus ----------------------------------------------------------


def test_bus_assigns_monotonic_sequence_numbers() -> None:
    bus = EventBus()
    first = bus.publish("detect", "started", "a")
    second = bus.publish("detect", "ok", "b")
    assert second["seq"] == first["seq"] + 1


def test_bus_replays_only_events_after_the_given_seq() -> None:
    bus = EventBus()
    bus.publish("detect", "started", "a")
    second = bus.publish("detect", "ok", "b")
    assert [e["seq"] for e in bus.replay(after_seq=1)] == [second["seq"]]


def test_bus_replay_buffer_is_bounded() -> None:
    bus = EventBus(replay_max=3)
    for n in range(10):
        bus.publish("detect", "ok", str(n))
    assert len(bus.replay()) == 3


@pytest.mark.asyncio
async def test_bus_delivers_to_a_subscriber() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []

    async def reader() -> None:
        async for event in bus.subscribe():
            received.append(event)
            return

    task = asyncio.create_task(reader())
    await asyncio.sleep(0)
    bus.publish("verify", "ok", "verification passed", incident_id="INC-1")
    await asyncio.wait_for(task, timeout=2)

    assert received[0]["message"] == "verification passed"
    assert received[0]["incident_id"] == "INC-1"


@pytest.mark.asyncio
async def test_bus_unsubscribes_on_exit() -> None:
    bus = EventBus()

    stream = bus.subscribe()

    async def reader() -> None:
        async for _event in stream:
            break

    task = asyncio.create_task(reader())
    await asyncio.sleep(0)
    assert bus.subscriber_count == 1
    bus.publish("detect", "ok", "x")
    await asyncio.wait_for(task, timeout=2)

    # Breaking out of `async for` suspends the generator rather than finishing
    # it, so the `finally` that unsubscribes has not run yet. A real WebSocket
    # handler exits the generator, which is what `aclose` models here.
    await stream.aclose()
    assert bus.subscriber_count == 0


def test_a_full_queue_drops_for_that_subscriber_only() -> None:
    """A wedged browser must not slow a heal or starve another console."""
    bus = EventBus()
    wedged: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1)
    healthy: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=10)
    bus._subscribers.update({wedged, healthy})

    for n in range(5):
        bus.publish("detect", "ok", str(n))

    assert wedged.qsize() == 1
    assert healthy.qsize() == 5


# --- the loop runner --------------------------------------------------------


def a_runner(tmp_path: Path) -> LoopRunner:
    """A runner rooted at a temp directory, so no test reads the real captures."""
    return LoopRunner(Settings(kavach_root=str(tmp_path)))


def test_newest_baseline_returns_none_with_no_captures(tmp_path: Path) -> None:
    value, source = newest_baseline(tmp_path / "harness" / "baselines", "simple-rag")
    assert value is None
    assert source == ""


def test_newest_baseline_picks_the_latest_capture(tmp_path: Path) -> None:
    d = tmp_path / "harness" / "baselines"
    d.mkdir(parents=True)
    (d / "baseline-simple-rag-20261003T100000+0000.json").write_text(
        '{"rerank_threshold": 0.30}', encoding="utf-8")
    (d / "baseline-simple-rag-20261003T140000+0000.json").write_text(
        '{"rerank_threshold": 0.35}', encoding="utf-8")

    value, source = newest_baseline(d, "simple-rag")
    assert value == 0.35
    assert "140000" in source


def test_newest_baseline_skips_an_unreadable_capture(tmp_path: Path) -> None:
    """A corrupt newest file must not hide a good older one."""
    d = tmp_path / "harness" / "baselines"
    d.mkdir(parents=True)
    (d / "baseline-simple-rag-20261003T100000+0000.json").write_text(
        '{"rerank_threshold": 0.35}', encoding="utf-8")
    (d / "baseline-simple-rag-20261003T140000+0000.json").write_text(
        "not json at all", encoding="utf-8")

    value, _ = newest_baseline(d, "simple-rag")
    assert value == 0.35


def test_newest_baseline_ignores_another_project(tmp_path: Path) -> None:
    d = tmp_path / "harness" / "baselines"
    d.mkdir(parents=True)
    (d / "baseline-other-20261003T100000+0000.json").write_text(
        '{"rerank_threshold": 0.9}', encoding="utf-8")
    assert newest_baseline(d, "simple-rag")[0] is None


@pytest.mark.asyncio
async def test_run_is_refused_with_no_baseline(tmp_path: Path) -> None:
    """A rollback with no recorded known-good value would be a guess."""
    runner = a_runner(tmp_path)
    with pytest.raises(NoBaselineError, match="no baseline capture"):
        await runner.start()
    assert runner.busy is False


@pytest.mark.asyncio
async def test_a_second_run_is_refused_while_one_is_in_flight(tmp_path: Path) -> None:
    """One writer at a time: two runs would both capture a pre-state, and the
    second inverse would point at the first run's faulty value."""
    d = tmp_path / "harness" / "baselines"
    d.mkdir(parents=True)
    (d / "baseline-simple-rag-20261003T140000+0000.json").write_text(
        '{"rerank_threshold": 0.35}', encoding="utf-8")

    runner = a_runner(tmp_path)
    runner._running = "INC-EARLIER"
    with pytest.raises(LoopBusyError, match="already in flight"):
        await runner.start()


def test_history_is_capped(tmp_path: Path) -> None:
    runner = a_runner(tmp_path)
    for n in range(60):
        runner._remember(loop.Incident(incident_id=f"INC-{n:03d}", project="p"))
    assert len(runner.incidents()) == 50
    # Newest first, and the oldest were evicted.
    assert runner.incidents()[0].incident_id == "INC-059"
    assert runner.incident("INC-000") is None


def test_remembering_the_same_incident_twice_updates_it(tmp_path: Path) -> None:
    """The runner stores a placeholder, then the finished record."""
    runner = a_runner(tmp_path)
    runner._remember(loop.Incident(incident_id="INC-1", project="p"))
    done = loop.Incident(incident_id="INC-1", project="p")
    done.status = loop.IncidentStatus.RESOLVED
    runner._remember(done)

    assert len(runner.incidents()) == 1
    stored = runner.incident("INC-1")
    assert stored is not None
    assert stored.status is loop.IncidentStatus.RESOLVED


# --- configuration: the two P4 cleanup fixes --------------------------------


def test_root_is_explicit_when_set() -> None:
    """Compose sets KAVACH_ROOT=/app, because the container cannot derive it."""
    assert Settings(kavach_root="/app").root() == Path("/app")
    assert Settings(kavach_root="/app").baselines_dir() == Path("/app/harness/baselines")


def test_root_falls_back_without_a_repository_above_the_package() -> None:
    """The regression that 500'd the containerised API on its first request.

    `parents[4]` only exists on a host checkout. At `/app/kavach/config.py`
    there are three parents, so a fixed index raised IndexError. The fallback
    has to return the package parent instead of exploding.
    """
    deep = Path("/repo/apps/control-plane/kavach/config.py")
    flat = Path("/app/kavach/config.py")
    # Mirrors `Settings.root()`: index 3 when it exists, else index 1.
    for path, expected in ((deep, Path("/repo")), (flat, Path("/app"))):
        parents = path.parents
        assert (parents[3] if len(parents) > 3 else parents[1]) == expected


def test_root_resolves_on_this_checkout() -> None:
    root = Settings().root()
    assert (root / "harness").is_dir()
    assert (root / "apps" / "control-plane").is_dir()


def test_admin_token_has_no_source_default() -> None:
    """No credential literal in source, and none in git history going forward.

    Empty is a usable state: the target answers 401 and the loop escalates
    rather than writing, which is the correct failure for a missing secret.

    THE DECLARED DEFAULT IS THE CLAIM, NOT THE RESOLVED VALUE
    This also asserted `Settings().target_admin_token == ""`, which reads the
    ENVIRONMENT and so asserted something about the machine rather than about
    the source. It passed only because `.env` was being looked for relative to
    the working directory and was therefore invisible from here; it would have
    failed just as readily for anyone who exported the variable in their
    shell, which is a supported way to run this. Once `config.py` started
    finding the repository's `.env` wherever it was launched from, the
    accident ended.

    The field default IS the property the docstring names, it is a statement
    about source, and it is true on every machine.
    """
    field = Settings.model_fields["target_admin_token"]
    assert field.default == ""


def test_fast_set_resolves_in_both_layouts(tmp_path: Path) -> None:
    """One call covers the host checkout and the image.

    On a host checkout the set is under `apps/control-plane/`; in the image the
    package is at `/app/kavach` and the set is directly under the root.
    """
    declared = "kavach/verification/fast_set.yaml"

    container = tmp_path / "app"
    (container / "kavach" / "verification").mkdir(parents=True)
    (container / declared).write_text("cases: []", encoding="utf-8")
    assert fast.resolve_set(declared, container) == container / declared

    checkout = tmp_path / "repo"
    nested = checkout / "apps" / "control-plane" / "kavach" / "verification"
    nested.mkdir(parents=True)
    (nested / "fast_set.yaml").write_text("cases: []", encoding="utf-8")
    assert fast.resolve_set(declared, checkout) == nested / "fast_set.yaml"

    assert fast.resolve_set(declared, tmp_path / "nowhere") is None


def test_runner_reports_a_missing_fast_set_clearly(tmp_path: Path) -> None:
    runner = LoopRunner(Settings(kavach_root=str(tmp_path)))
    with pytest.raises(FileNotFoundError, match="KAVACH_ROOT"):
        runner.fast_set_path()


# --- the loop's event sink stays observation-only ----------------------------


def test_notify_swallows_a_broken_sink() -> None:
    """A console that has gone away must not take an in-flight repair with it."""
    def explode(_stage: str, _status: str, _message: str) -> None:
        raise RuntimeError("the browser closed")

    loop._notify(explode, "repair", "started", "executing")  # must not raise


def test_notify_with_no_sink_is_a_no_op() -> None:
    loop._notify(None, "repair", "started", "executing")


def test_stage_names_cover_the_loop() -> None:
    assert loop.STAGES == (
        "detect", "evidence", "diagnose", "validate",
        "plan", "repair", "verify", "resolve",
    )
