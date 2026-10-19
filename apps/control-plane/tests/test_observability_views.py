"""The three read-only views: logs, LLM calls, alerts.

What is worth pinning here is not that a list comes back. It is the three
properties that would make these views actively harmful if they broke:

  - a secret must never reach the log buffer,
  - an alert must never consume the budget it reports on,
  - a refused diagnosis must still appear, with the refusal attached.

The third is the one that matters for the report. `REPORT_DRAFT.md` rests on
the model being wrong three times and acting zero times; a view that quietly
dropped refused diagnoses would show a cleaner system than the one that was
measured.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from kavach import telemetry
from kavach.api import alerts as alert_rules
from kavach.api.routes import incident_out, llm_calls
from kavach.api.runner import LoopRunner
from kavach.config import Settings
from kavach.executor import catalogue  # noqa: F401 - registers the actions
from kavach.executor.base import registry
from kavach.loop import Incident, IncidentStatus
from kavach.safety.engine import SafetyEngine


def _engine() -> SafetyEngine:
    """A gate with its own fresh limiters, so one test cannot spend
    another's blast radius."""
    return SafetyEngine(registry)


# --- logs -------------------------------------------------------------------


def test_a_credential_never_reaches_the_log_buffer() -> None:
    """AGENTS.md forbids logging secrets. Redaction happens on the way IN, so
    a secret is not merely hidden from the endpoint - it was never stored."""
    telemetry.configure_logging(Settings(log_level="DEBUG"))
    structlog.get_logger("test").warning(
        "target refused",
        admin_token="super-secret-value",
        api_key="sk-live-abcdef",
        incident_id="INC-000900",
        status_code=401,
    )
    rows = telemetry.recent_logs(limit=5)
    assert rows, "the buffer took nothing"
    row = rows[0]
    assert "super-secret-value" not in row.detail
    assert "sk-live-abcdef" not in row.detail
    assert row.detail.count("<redacted>") == 2
    # The non-secret context survives, or redaction would have cost the point
    # of structured logging.
    assert "status_code=401" in row.detail
    assert row.incident_id == "INC-000900"


def test_the_level_filter_is_a_floor_so_errors_show_in_the_warning_view() -> None:
    telemetry.configure_logging(Settings(log_level="DEBUG"))
    log = structlog.get_logger("test")
    log.info("a quiet thing", marker="obs-info")
    log.error("a loud thing", marker="obs-error")

    warnings = telemetry.recent_logs(level="warning", limit=50)
    events = [r.event for r in warnings]
    assert "a loud thing" in events
    assert "a quiet thing" not in events
    assert all(r.level in ("warning", "error", "critical") for r in warnings)


def test_the_buffer_is_bounded_and_newest_first() -> None:
    telemetry.configure_logging(Settings(log_level="DEBUG"))
    log = structlog.get_logger("test")
    for n in range(telemetry.LOG_BUFFER_MAX + 25):
        log.info("filler", n=n)
    rows = telemetry.recent_logs(limit=telemetry.LOG_BUFFER_MAX * 2)
    assert len(rows) <= telemetry.LOG_BUFFER_MAX
    assert "n=524" in rows[0].detail, "newest line is not first"


# --- alerts -----------------------------------------------------------------


def _incident(
    incident_id: str = "INC-000001",
    status: IncidentStatus = IncidentStatus.DETECTED,
    service: str | None = None,
    fault_class: str | None = None,
    escalation_reason: str = "",
) -> Incident:
    """Explicit parameters rather than **kwargs: a typed helper is what
    lets this file stay free of a , which AGENTS.md forbids
    for exactly the reason it would apply here - silencing the checker
    over a constructor whose signature the test should be pinned to."""
    return Incident(
        incident_id=incident_id,
        project="simple-rag",
        detected_at=datetime.now(UTC).isoformat(timespec="seconds"),
        status=status,
        service=service,
        fault_class=fault_class,
        escalation_reason=escalation_reason,
    )


def test_evaluating_alerts_does_not_spend_the_blast_radius_it_reports() -> None:
    """The rule that would be worst to get wrong.

    `evaluate` probes BlastRadius to say how much of the hour is left. If that
    probe recorded, then opening the console would consume the budget - and
    the limiter would refuse a real repair because somebody looked at a page.
    """
    safety = _engine()
    before, before_detail = safety.blast.check("INC-REAL")
    for _ in range(10):
        alert_rules.evaluate(safety, [], [], audit_intact=True)
    after, after_detail = safety.blast.check("INC-REAL")

    assert (before, before_detail) == (after, after_detail), (
        "looking at the alerts view changed what permit() would decide")


def test_a_broken_audit_chain_is_critical_and_says_not_to_repair_it() -> None:
    rows = alert_rules.evaluate(
        _engine(), [], [], audit_intact=False, audit_broken_at=42)
    broken = [a for a in rows if a.id == "audit_chain_broken"]
    assert broken, "a chain that does not verify raised nothing"
    assert broken[0].severity == "critical"
    assert "42" in broken[0].detail
    assert broken[0].action, "an alert with no action is a notification"


def test_a_dependency_that_is_down_is_reported_with_its_own_detail() -> None:
    rows = alert_rules.evaluate(
        _engine(), [],
        [("Prometheus", False, "connection refused"), ("Target application", True, "ok")],
        audit_intact=True)
    down = [a for a in rows if a.id == "dependency_down:Prometheus"]
    assert down and down[0].severity == "critical"
    assert "connection refused" in down[0].detail
    assert not [a for a in rows if "Target application" in a.id]


def test_three_escalations_in_a_row_are_noted_but_not_called_a_failure() -> None:
    """ESCALATED is the correct outcome on a fault outside the catalogue, so
    this fires at `info`. Ranking it higher would train an operator to treat
    the system's own safety behaviour as an incident."""
    incs = [_incident(incident_id=f"INC-00000{n}",
                      status=IncidentStatus.ESCALATED,
                      escalation_reason="not in the catalogue") for n in range(3)]
    rows = alert_rules.evaluate(_engine(), incs, [], audit_intact=True)
    streak = [a for a in rows if a.id == "escalation_streak"]
    assert streak and streak[0].severity == "info"


def test_the_most_severe_alert_comes_first() -> None:
    incs = [_incident(incident_id=f"INC-00000{n}",
                      status=IncidentStatus.ESCALATED) for n in range(3)]
    rows = alert_rules.evaluate(
        _engine(), incs, [("Prometheus", False, "down")],
        audit_intact=False)
    assert [a.severity for a in rows] == sorted(
        [a.severity for a in rows],
        key=lambda s: {"critical": 0, "warning": 1, "info": 2}[s])
    assert rows[0].severity == "critical"


def test_a_healthy_system_raises_nothing() -> None:
    assert alert_rules.evaluate(
        _engine(), [_incident(status=IncidentStatus.RESOLVED)],
        [("Prometheus", True, "ok")], audit_intact=True) == []


def test_an_open_breaker_is_reported_for_the_pair_that_opened_it() -> None:
    safety = _engine()
    now = datetime.now(UTC)
    for n in range(safety.breaker.limits.heals_per_pair):
        safety.breaker.record("backend", "F01", now=now - timedelta(seconds=n))
    rows = alert_rules.evaluate(
        safety,
        [_incident(service="backend", fault_class="F01"),
         _incident(incident_id="INC-000002", service="backend", fault_class="F06")],
        [], audit_intact=True)
    ids = [a.id for a in rows]
    assert "circuit_breaker_open:F01:backend" in ids
    assert "circuit_breaker_open:F06:backend" not in ids, (
        "the breaker is per (service, fault class), not per service")


# --- AI calls ---------------------------------------------------------------


def _runner_with(*incidents: Incident) -> LoopRunner:
    """A REAL runner, not a stub.

    A hand-rolled double would need a `type: ignore` at every call site,
    which AGENTS.md forbids and which would also stop the test noticing if
    the route started reading some other part of the runner. The
    constructor opens nothing - the store connects separately - so this is
    cheap, and an unconnected store is a supported state.
    """
    runner = LoopRunner(Settings())
    for inc in incidents:
        runner._remember(inc)
    return runner


def _rca_incident(approved: bool, fault_class: str = "F06") -> Incident:
    inc = _incident(incident_id="INC-000700", fault_class=fault_class)
    inc.rca = {
        "at": "2026-10-19T12:00:00+00:00",
        "model": "qwen2.5:7b-instruct",
        "provider": "ollama",
        "latency_s": 16.8,
        "prompt_tokens": 742,
        "completion_tokens": 118,
        "approved": approved,
        "approved_action": "rollback_config" if approved else None,
        "diagnosis": {"fault_class": fault_class, "confidence": 0.91,
                      "evidence_ids": ["EV-M02", "EV-C08"]},
        "validation": {"accepted": approved,
                       "reasons": [] if approved else
                       ["fault_class F06 does not match detection F07"]},
    }
    return inc


def test_a_refused_diagnosis_is_shown_with_the_reason_it_was_refused() -> None:
    """The row the report depends on.

    `REPORT_DRAFT.md` rests on the model being wrong and the system acting
    anyway zero times. A view that dropped refused diagnoses - or showed them
    without the refusal - would present a cleaner system than the measured one,
    which is the same class of error as ADR 0014.
    """
    import asyncio

    rows = asyncio.run(llm_calls(_runner_with(_rca_incident(approved=False))))
    assert len(rows) == 1
    row = rows[0]
    assert row.fault_class == "F06", "the model's own claim must survive"
    assert row.confidence == 0.91, "a refused diagnosis was still confident"
    assert row.approved is False
    assert row.approved_action is None
    assert row.rejection_reasons == [
        "fault_class F06 does not match detection F07"]
    assert row.evidence_cited == ["EV-M02", "EV-C08"]
    assert row.confidence_is_calibrated is False


def test_an_accepted_diagnosis_carries_the_action_it_authorised() -> None:
    import asyncio

    row = asyncio.run(llm_calls(_runner_with(_rca_incident(approved=True))))[0]
    assert row.approved is True
    assert row.approved_action == "rollback_config"
    assert row.model == "qwen2.5:7b-instruct"
    assert row.latency_s == 16.8
    assert (row.prompt_tokens, row.completion_tokens) == (742, 118)


def test_incidents_that_never_reached_the_model_are_not_listed() -> None:
    """A deterministic NO_FAULT run has no rca. Listing it as an LLM call with
    empty fields would inflate the denominator every accuracy figure uses."""
    import asyncio

    rows = asyncio.run(llm_calls(_runner_with(_incident(), _rca_incident(approved=True))))
    assert [r.incident_id for r in rows] == ["INC-000700"]


# --- the wire carries what the instrument stamped -------------------------


def test_detection_concluded_at_survives_the_api_mapper() -> None:
    """MTTD is measured OUTSIDE the process, so the stamp has to reach the wire.

    `loop.py` stamps `detection.concluded_at`, Postgres stores it, and
    `DetectionOut` dropped it on the floor - so `make bench`, the only consumer
    that reports MTTD, read None for every repetition. Caught on 2026-10-20
    five minutes into an eight-hour overnight run that would have measured
    nothing.

    ADR 0014 withdrew MTTD because the metric measured four phases and was
    named after one. This is the same lesson one layer up: an instrument is
    only as good as the narrowest pipe between it and whoever reports it.
    """
    inc = _incident(fault_class="F01")
    inc.detection = {
        "verdict": "FAULT",
        "fault_class": "F01",
        "concluded_at": "2026-10-20T00:11:12.345+00:00",
        "reasons": [],
        "evidence": [],
    }
    out = incident_out(inc)
    assert out.detection is not None
    assert out.detection.concluded_at == "2026-10-20T00:11:12.345+00:00", (
        "the stamp did not survive the mapper, so MTTD is unmeasurable again")


def test_an_incident_detected_before_the_stamp_existed_still_maps() -> None:
    """Older rows have no `concluded_at`. Absent must stay absent rather than
    becoming a wrong number - the substitution ADR 0014 exists about."""
    inc = _incident()
    inc.detection = {"verdict": "NO_FAULT", "reasons": [], "evidence": []}
    out = incident_out(inc)
    assert out.detection is not None
    assert out.detection.concluded_at == ""
