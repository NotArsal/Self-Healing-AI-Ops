"""Kavach's own telemetry: what it records, and what it refuses to break.

The second property is the one that matters. These metrics observe a loop
whose job is to survive the target being broken, so the tests that earn their
place are the ones proving a telemetry failure cannot reach it: a malformed
timestamp, a junk incident, a collector that is not there. A metric that
raises into the healing path would be a worse bug than the missing dashboard
it was added to fix.

No network and no collector. `setup_tracing` is exercised only through the
disabled path, because asserting that OTLP export works would be testing the
exporter, not Kavach.
"""

from __future__ import annotations

from kavach import telemetry
from kavach.config import Settings
from kavach.loop import Incident, IncidentStatus


def _resolved() -> Incident:
    """A complete, well-formed incident, as the runner hands one over."""
    return Incident(
        incident_id="INC-000001",
        project="simple-rag",
        detected_at="2026-10-19T10:00:00+00:00",
        resolved_at="2026-10-19T10:02:00+00:00",
        status=IncidentStatus.RESOLVED,
        fault_class="F01",
        diagnosed_by="deterministic",
        detection={"concluded_at": "2026-10-19T10:00:12.500+00:00"},
        decision={"verdict": "ALLOW_AUTO", "risk_tier": "LOW"},
        rca={"latency_s": 16.8},
    )


def _sample(name: str, **labels: str) -> float:
    """One counter/histogram sample out of the live registry."""
    from prometheus_client import REGISTRY

    value = REGISTRY.get_sample_value(name, labels or None)
    return 0.0 if value is None else value


# --- what it records --------------------------------------------------------


def test_a_resolved_incident_lands_on_every_series() -> None:
    """One run should move the incident, verdict, RCA, MTTD and MTTR series."""
    before = _sample("kavach_incidents_total",
                     fault_class="F01", status="RESOLVED",
                     diagnosed_by="deterministic")
    telemetry.record_incident(_resolved())

    assert _sample("kavach_incidents_total", fault_class="F01",
                   status="RESOLVED", diagnosed_by="deterministic") == before + 1
    assert _sample("kavach_permit_verdicts_total",
                   verdict="ALLOW_AUTO", risk_tier="LOW") >= 1
    assert _sample("kavach_rca_latency_seconds_count") >= 1
    assert _sample("kavach_detection_seconds_count") >= 1
    assert _sample("kavach_incident_seconds_count", status="RESOLVED") >= 1


def test_detection_is_measured_from_the_stamp_and_not_from_the_end() -> None:
    """MTTD is incident-open to detection-concluded. ADR 0014.

    The incident above opens at 10:00:00, detection concludes 12.5s later and
    the whole thing resolves at 10:02:00. A detection histogram that observed
    120.0 would be `mttd_s` making its original mistake again, in a new place.
    """
    before = _sample("kavach_detection_seconds_sum")
    telemetry.record_incident(_resolved())
    assert _sample("kavach_detection_seconds_sum") - before == 12.5


def test_an_incident_that_never_concluded_detection_records_no_mttd() -> None:
    """Absent is reported as absent, never backfilled from a longer span."""
    inc = _resolved()
    inc.detection = {}
    before = _sample("kavach_detection_seconds_count")
    telemetry.record_incident(inc)
    assert _sample("kavach_detection_seconds_count") == before


# --- what it refuses to break -----------------------------------------------


def test_a_malformed_timestamp_is_dropped_rather_than_raising() -> None:
    inc = _resolved()
    inc.detection = {"concluded_at": "not a timestamp"}
    before = _sample("kavach_detection_seconds_count")
    telemetry.record_incident(inc)  # must not raise
    assert _sample("kavach_detection_seconds_count") == before


def test_a_clock_that_went_backwards_is_dropped() -> None:
    """A negative duration is a broken clock, not a fast detector."""
    inc = _resolved()
    inc.detection = {"concluded_at": "2026-10-19T09:59:00+00:00"}
    before = _sample("kavach_detection_seconds_count")
    telemetry.record_incident(inc)
    assert _sample("kavach_detection_seconds_count") == before


def test_an_incident_missing_everything_optional_still_records() -> None:
    """Escalations carry no verdict, no RCA and no resolved_at."""
    inc = Incident(incident_id="INC-000002", project="simple-rag",
                   detected_at="2026-10-19T10:00:00+00:00",
                   status=IncidentStatus.ESCALATED)
    telemetry.record_incident(inc)
    assert _sample("kavach_incidents_total", fault_class="none",
                   status="ESCALATED", diagnosed_by="none") >= 1


def test_recording_never_raises_whatever_it_is_handed() -> None:
    """The guarantee the module exists to make, stated as a test.

    `record_incident` is called from the runner's worker thread on both the
    success and the exception path. An escaping error there would turn a
    completed heal into a failed one.
    """

    class Hostile:
        def __getattr__(self, _: str) -> object:
            raise RuntimeError("telemetry read a field that exploded")

    telemetry.record_incident(Hostile())  # type: ignore[arg-type]


# --- exposition and tracing -------------------------------------------------


def test_the_metrics_body_is_prometheus_exposition() -> None:
    telemetry.record_incident(_resolved())
    body, content_type = telemetry.exposition()
    assert b"kavach_incidents_total" in body
    assert b"kavach_detection_seconds" in body
    assert "text/plain" in content_type


def test_no_collector_configured_means_tracing_stays_off() -> None:
    """Every test run and any bare `uvicorn` takes this path. PL-02 adjacent:
    nothing in the control plane may require a service that is not there."""
    from fastapi import FastAPI

    assert telemetry.setup_tracing(FastAPI(), Settings(otlp_endpoint="")) is False
    assert telemetry.tracing_enabled() is False


def test_the_span_helpers_are_inert_when_tracing_is_off() -> None:
    with telemetry.heal_span("INC-000003"):
        telemetry.stage_event("detect", "ok", "F01 on backend")


def test_a_run_produces_one_span_carrying_every_stage_as_an_event() -> None:
    """The shape Jaeger renders: one `kavach.heal` span, stages as marks on it.

    Exercised against an in-memory exporter rather than a live heal, because a
    real one costs 4 of the 5 incident starts `permit()` allows in an hour and
    this assertion does not need a broken target to be true.

    Child spans per stage were deliberately not used - see `telemetry.py` - so
    the thing worth pinning is that every stage still lands on the timeline and
    that an unpaired stage cannot leak a span.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    # `set_tracer_provider` is once-per-process and silently keeps the
    # first one, so attach to whatever provider is already global rather
    # than installing a second that would be ignored. Passing alone and
    # failing in the full suite is exactly that collision.
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    was = telemetry.tracing_enabled()
    telemetry._enabled = True
    try:
        with telemetry.heal_span("INC-000004"):
            telemetry.stage_event("detect", "started", "looking")
            telemetry.stage_event("detect", "ok", "F01 on backend")
            telemetry.stage_event("gate", "ok", "ALLOW_AUTO")
            # Never paired with an "ok": a stage that ends some other way must
            # not strand anything.
            telemetry.stage_event("repair", "started", "switch_llm_endpoint")
    finally:
        telemetry._enabled = was

    spans = exporter.get_finished_spans()
    assert len(spans) == 1, "one run is one span, whatever the stages did"
    span = spans[0]
    assert span.name == "kavach.heal"
    assert span.attributes is not None
    assert span.attributes["kavach.incident_id"] == "INC-000004"
    assert [e.name for e in span.events] == [
        "detect.started", "detect.ok", "gate.ok", "repair.started",
    ]


def test_a_stage_event_outside_a_run_is_discarded_not_an_error() -> None:
    """`publish` fires once before the worker thread starts its span."""
    was = telemetry.tracing_enabled()
    telemetry._enabled = True
    try:
        telemetry.stage_event("run", "started", "operator started a loop run")
    finally:
        telemetry._enabled = was
