"""Alert rules over Kavach's own state.

DISPLAYED, NOT DELIVERED. Nothing here emails, pages or posts anywhere, and
that is a decision rather than an omission: an alert exists to interrupt a
human who is not looking, and this project has no on-call rotation to
interrupt. What an operator in front of the console actually needs is to know
*why the system will refuse the next repair* before they ask it to try.

So every rule below reads a limit `permit()` itself enforces, or an invariant
the system claims to hold. None of them is a threshold invented for a
dashboard - a rule that fires on something no gate consults would be telling
an operator about a number nobody acts on.

PURE, AND READ-ONLY. `evaluate` takes state and returns findings; it holds no
timers, mutates nothing, and calls no limiter's `record`. `BlastRadius.check`
and `CircuitBreaker.check` are read-only by construction - only `record`
mutates - so probing them here cannot consume the budget it reports on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from kavach.loop import Incident, IncidentStatus
from kavach.safety.engine import SafetyEngine

Severity = Literal["critical", "warning", "info"]

# The id used to ask BlastRadius what the hour looks like without claiming a
# slot. `check` never writes, but an id that could collide with a real
# incident would make the projection wrong by one.
_PROBE_ID = "__alert_probe__"


@dataclass(frozen=True)
class Alert:
    id: str
    severity: Severity
    title: str
    detail: str
    # What an operator should do about it. An alert with no action is a
    # notification, and notifications are what people learn to ignore.
    action: str = ""


def evaluate(
    safety: SafetyEngine,
    incidents: list[Incident],
    dependencies: list[tuple[str, bool, str]],
    audit_intact: bool,
    audit_broken_at: int | None = None,
) -> list[Alert]:
    """Every rule, most severe first. Never raises.

    `dependencies` is (name, ok, detail) as `/v1/system` already computes it,
    passed in rather than recomputed so the console cannot be shown a health
    state that disagrees with the one on the same page.
    """
    found: list[Alert] = []

    # --- invariants the system claims --------------------------------------
    if not audit_intact:
        where = f" first break at row {audit_broken_at}" if audit_broken_at else ""
        found.append(Alert(
            id="audit_chain_broken",
            severity="critical",
            title="The audit chain does not verify",
            detail=(f"A row's digest does not match its payload.{where} Every "
                    f"claim about what Kavach did rests on this chain."),
            action="Stop. Treat the trail as evidence, not as a log to repair.",
        ))

    # --- limits permit() will enforce on the next request -------------------
    within, blast_detail = safety.blast.check(_PROBE_ID)
    if not within:
        found.append(Alert(
            id="blast_radius_exhausted",
            severity="warning",
            title="Blast radius is spent for this hour",
            detail=blast_detail,
            action=("Wait for the window to roll. A run started now parks on "
                    "the limiter, which is correct behaviour, not a fault."),
        ))

    for service, fault_class in sorted(
        {(i.service or "", i.fault_class or "") for i in incidents
         if i.service and i.fault_class}
    ):
        closed, breaker_detail = safety.breaker.check(service, fault_class)
        if not closed:
            found.append(Alert(
                id=f"circuit_breaker_open:{fault_class}:{service}",
                severity="warning",
                title=f"Circuit breaker open for {fault_class} on {service}",
                detail=breaker_detail,
                action=("Investigate the cause rather than re-running. A "
                        "repair that keeps being needed is not repairing."),
            ))

    # --- the things the loop depends on ------------------------------------
    for name, ok, detail in dependencies:
        if not ok:
            found.append(Alert(
                id=f"dependency_down:{name}",
                severity="critical",
                title=f"{name} is not answering",
                detail=detail or "reported not ok by /v1/system",
                action="Detection reads this. A heal attempted now is blind.",
            ))

    # --- patterns in recent outcomes ---------------------------------------
    # Not a tuned threshold: three consecutive escalations means the last three
    # things Kavach saw, it declined to act on. That is the system working, and
    # it is also the shape of a target that has drifted out of its baseline.
    recent = incidents[:3]
    if len(recent) == 3 and all(
        i.status is IncidentStatus.ESCALATED for i in recent
    ):
        found.append(Alert(
            id="escalation_streak",
            severity="info",
            title="The last three incidents all escalated",
            detail="; ".join(
                f"{i.incident_id}: {i.escalation_reason or 'no reason recorded'}"
                for i in recent),
            action=("Expected on faults outside the catalogue. If they were "
                    "inside it, the baseline is probably stale."),
        ))

    llm_errors = [i for i in incidents[:10] if (i.rca or {}).get("error")]
    if len(llm_errors) >= 3:
        found.append(Alert(
            id="llm_unreliable",
            severity="warning",
            title="The RCA model is failing to answer",
            detail=(f"{len(llm_errors)} of the last {min(len(incidents), 10)} "
                    f"incidents recorded an LLM error. Most recent: "
                    f"{(llm_errors[0].rca or {}).get('error', '')[:160]}"),
            action=("Deterministic detection and repair are unaffected; only "
                    "the diagnosis path is. Check Ollama on the Kavach path."),
        ))

    order: dict[str, int] = {"critical": 0, "warning": 1, "info": 2}
    found.sort(key=lambda a: order[a.severity])
    return found


__all__ = ["Alert", "Severity", "evaluate"]
