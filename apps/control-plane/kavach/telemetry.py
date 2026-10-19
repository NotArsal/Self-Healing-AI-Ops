"""Kavach's own telemetry: the metrics it exposes and the traces it emits.

Until 2026-10-19 Kavach watched the target and nothing watched Kavach.
`GET /metrics` was a 404, the `kavach-api` scrape job in `infra/prometheus.yml`
was commented out, and the OTel collector in compose received nothing at all
because no process ever exported to it. A platform whose thesis is
"observability drives healing" had no observability of itself, and said so
nowhere. `ADR 0016` records the decision to close that.

NOTHING HERE MAY REACH THE HEALING PATH
Every public function swallows. A Prometheus registry error, a malformed
timestamp, a collector that is down - none of them may raise into a loop whose
job is to survive the target being broken. The failure mode of this module is
a missing graph, never a missed repair. That is why the call sites are two
lines in `api/runner.py` and one route in `main.py`, and why `loop.py` and
`safety/engine.py` are untouched: telemetry observes the run, it is not part
of it.

THE METRIC SET IS THE REPORT'S OWN FIGURES
Deliberately not a generic RED dashboard. Every series here corresponds to a
number `REPORT_DRAFT.md` quotes - MTTD, MTTR, RCA latency, verdict
distribution, incidents by class and outcome - so the live dashboard and the
paper cannot disagree about what was measured. A metric nobody reports is a
metric nobody checks, and `ADR 0014` is what an unchecked metric costs.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

if TYPE_CHECKING:  # pragma: no cover - import cycle at runtime, not at type time
    from fastapi import FastAPI

    from kavach.config import Settings
    from kavach.loop import Incident

# Seconds. Tuned for a 7B model on local Ollama, where a diagnosis is tens of
# seconds rather than the sub-second a default bucket set assumes. The upper
# buckets exist because an overloaded host has produced two-minute calls.
_LLM_BUCKETS = (1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 120.0)
# Detection is bounded below by each detector's evaluation window - 2m for F01,
# 1m for F06, no PromQL at all for F07 and F08 (`ADR 0014`). Fine buckets at
# the short end so the two no-PromQL classes are distinguishable from the two
# that wait on a rate window.
_DETECT_BUCKETS = (0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 45.0, 60.0, 90.0, 120.0)
_INCIDENT_BUCKETS = (30.0, 60.0, 90.0, 120.0, 180.0, 240.0, 300.0, 600.0)

INCIDENTS = Counter(
    "kavach_incidents_total",
    "Incidents by fault class, terminal status and which path diagnosed them.",
    ["fault_class", "status", "diagnosed_by"],
)
VERDICTS = Counter(
    "kavach_permit_verdicts_total",
    "permit() verdicts by risk tier. Every side effect in Kavach is counted here.",
    ["verdict", "risk_tier"],
)
RCA_LATENCY = Histogram(
    "kavach_rca_latency_seconds",
    "Wall-clock of one LLM diagnosis, decode included.",
    buckets=_LLM_BUCKETS,
)
DETECTION_SECONDS = Histogram(
    "kavach_detection_seconds",
    "Incident open to detection concluded. THE MTTD denominator (ADR 0014).",
    buckets=_DETECT_BUCKETS,
)
INCIDENT_SECONDS = Histogram(
    "kavach_incident_seconds",
    "Incident open to terminal status, by that status. MTTR when RESOLVED.",
    ["status"],
    buckets=_INCIDENT_BUCKETS,
)


def _elapsed(start: str, end: str) -> float | None:
    """Seconds between two ISO stamps, or None if either is absent or junk.

    `detected_at` is stamped to the second and `concluded_at` to the
    millisecond, which `fromisoformat` handles; anything else returns None
    rather than guessing. A metric derived from a timestamp nobody parsed is
    how `mttd_s` came to measure four phases and be named after one.
    """
    if not start or not end:
        return None
    try:
        delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    except ValueError:
        return None
    seconds = delta.total_seconds()
    return seconds if seconds >= 0 else None


def record_incident(inc: Incident) -> None:
    """Count one finished run. Called once per terminal incident, and swallows.

    Reads the incident rather than being threaded through the loop as callbacks
    so that adding a metric never means editing `loop.py`.
    """
    try:
        INCIDENTS.labels(
            fault_class=inc.fault_class or "none",
            status=str(inc.status),
            diagnosed_by=inc.diagnosed_by or "none",
        ).inc()

        decision = inc.decision or {}
        verdict = decision.get("verdict")
        if verdict:
            VERDICTS.labels(
                verdict=str(verdict),
                risk_tier=str(decision.get("risk_tier") or "unknown"),
            ).inc()

        rca_latency = (inc.rca or {}).get("latency_s")
        if isinstance(rca_latency, int | float):
            RCA_LATENCY.observe(float(rca_latency))

        detect = _elapsed(inc.detected_at, (inc.detection or {}).get("concluded_at", ""))
        if detect is not None:
            DETECTION_SECONDS.observe(detect)

        total = _elapsed(inc.detected_at, inc.resolved_at)
        if total is not None:
            INCIDENT_SECONDS.labels(status=str(inc.status)).observe(total)
    except Exception:
        return


def exposition() -> tuple[bytes, str]:
    """The `/metrics` body and its content type. Empty on any failure."""
    try:
        return generate_latest(), CONTENT_TYPE_LATEST
    except Exception:
        return b"", CONTENT_TYPE_LATEST


# --- logs -------------------------------------------------------------------
#
# A RING BUFFER, NOT A LOG STACK. There are four log calls in the whole control
# plane, and `structlog.configure()` was never called - so the output format
# and level were whatever structlog defaulted to, and `log_level` in
# `config.py` was read by nothing. Loki for four lines would be a storage
# cluster around an empty table; a bounded deque the console can read gives an
# operator the same answer with no new container and no new failure mode.
#
# ponytail: in-memory and per-process, so a restart loses it and a second
# replica would keep its own. Both are fine while Kavach is one container, and
# neither is hidden - the audit log, not this, is the durable record of what
# Kavach did.

LOG_BUFFER_MAX = 500
_LEVELS = ("debug", "info", "warning", "error", "critical")
# Any key that LOOKS like a credential is replaced before it is stored.
# AGENTS.md forbids logging secrets. Nothing currently logs one; this is here
# so that staying true does not depend on everyone remembering.
_SECRET_HINTS = ("token", "key", "secret", "password", "authorization", "dsn")


@dataclass(frozen=True)
class LogRecord:
    at: str
    level: str
    event: str
    logger: str = ""
    incident_id: str = ""
    detail: str = ""
    exception: str = ""


_log_buffer: deque[LogRecord] = deque(maxlen=LOG_BUFFER_MAX)


def _redact(key: str, value: object) -> str:
    if any(h in key.lower() for h in _SECRET_HINTS):
        return "<redacted>"
    text = str(value)
    return text if len(text) <= 300 else text[:297] + "..."


def _buffer_processor(
    _logger: Any, name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Copy each event into the ring buffer, then hand it on untouched.

    A processor that raised would take down the log call that invoked it, and
    one of the four live calls is in the `except` branch of the healing loop -
    so a bug here would turn a failed run into a crashed worker thread.
    """
    try:
        skip = {"event", "level", "timestamp", "logger", "incident_id", "exception"}
        detail = ", ".join(
            f"{k}={_redact(k, v)}" for k, v in event_dict.items() if k not in skip
        )
        _log_buffer.append(LogRecord(
            at=str(event_dict.get("timestamp", "")),
            level=str(event_dict.get("level", name or "info")).lower(),
            event=str(event_dict.get("event", "")),
            logger=str(event_dict.get("logger", "")),
            incident_id=str(event_dict.get("incident_id", "") or ""),
            detail=detail,
            exception=str(event_dict.get("exception", "") or ""),
        ))
    except Exception:
        pass
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Make `log_level` mean something, and render JSON.

    `structlog.configure()` had never been called, so the setting declared in
    `config.py` and passed by compose was read by nothing - the same dead
    configuration as `otlp_endpoint` before `setup_tracing` (ADR 0016).
    """
    try:
        import structlog

        level = str(settings.log_level or "INFO").upper()
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                _buffer_processor,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, level, logging.INFO)),
            cache_logger_on_first_use=True,
        )
    except Exception:
        return


def recent_logs(level: str = "", limit: int = 200) -> list[LogRecord]:
    """Newest first. `level` is a FLOOR, so "warning" also returns errors."""
    try:
        rows = list(_log_buffer)
    except Exception:
        return []
    wanted = level.lower().strip()
    if wanted in _LEVELS:
        floor = _LEVELS.index(wanted)
        rows = [r for r in rows
                if r.level in _LEVELS and _LEVELS.index(r.level) >= floor]
    rows.reverse()
    return rows[:max(0, limit)]


# --- traces -----------------------------------------------------------------
#
# ONE SPAN PER RUN, WITH THE STAGES AS EVENTS ON IT, rather than a child span
# per stage. A child span has to be opened on "started" and closed on
# "ok"/"failed", which means pairing state held across a worker-thread boundary
# and a span that leaks whenever a stage ends in a way nobody anticipated.
# Events carry the same timestamps, need no pairing and cannot leak. Jaeger
# renders them as marks on the run's timeline, which is the stage decomposition
# the demo wants to show.
#
# ponytail: upgrade to child spans only if stage durations are needed
# programmatically rather than read off a timeline.

_enabled = False


def setup_tracing(app: FastAPI, settings: Settings) -> bool:
    """Export spans to the collector. Returns whether tracing came up.

    An empty `otlp_endpoint` disables it, which is what a bare `uvicorn` run and
    every test get. Export failures are the exporter's problem and are retried
    in its own background thread; they never surface here.
    """
    global _enabled
    if not settings.otlp_endpoint:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create({"service.name": "kavach-control-plane"})
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{settings.otlp_endpoint.rstrip('/')}/v1/traces")
            )
        )
        trace.set_tracer_provider(provider)
        # Excluded because Prometheus scrapes `/metrics` every 15s and the
        # console polls `/healthz`; tracing either buries the heal runs that
        # are the reason this exists.
        FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,metrics")
    except Exception:
        return False
    _enabled = True
    return True


@contextmanager
def heal_span(incident_id: str) -> Iterator[None]:
    """Wrap one loop run. A no-op when tracing is off, and never raises."""
    if not _enabled:
        yield
        return
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("kavach.loop")
        with tracer.start_as_current_span(
            "kavach.heal", attributes={"kavach.incident_id": incident_id}
        ):
            yield
        return
    except Exception:
        pass
    yield


def stage_event(stage: str, status: str, message: str) -> None:
    """Mark one loop stage on the active run's span.

    `message` is operator-facing prose the audit log already carries. It is
    truncated because a span attribute is not a log line, and because an
    escalation reason can run to several hundred characters.
    """
    if not _enabled:
        return
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        # An INVALID_SPAN - no active run - accepts add_event and discards it,
        # so a stray event outside a heal costs nothing.
        span.add_event(
            f"{stage}.{status}",
            attributes={"kavach.stage": stage, "kavach.status": status,
                        "kavach.message": message[:300]},
        )
    except Exception:
        return


def tracing_enabled() -> bool:
    return _enabled


__all__ = [
    "DETECTION_SECONDS",
    "INCIDENTS",
    "INCIDENT_SECONDS",
    "RCA_LATENCY",
    "VERDICTS",
    "exposition",
    "heal_span",
    "record_incident",
    "setup_tracing",
    "stage_event",
    "tracing_enabled",
]
