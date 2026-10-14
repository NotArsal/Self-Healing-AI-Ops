"""Objective-driven detection against a live application.

Detection reports a *breach*, never a fault class: naming the cause is the
diagnosis node's job, and a detector that also classifies is a detector that
quietly becomes the symptom-matching baseline P4 is supposed to beat.

Evidence attached here is measured from the application, so the IDs the LLM cites
resolve to something that was actually observed.
"""

import logging

from pydantic import BaseModel

from kavach.scenarios.from_manifest import scenario_from_target
from kavach.scenarios.schema import EvidenceItem, Scenario, TargetBinding
from kavach.verification.live import measure_objectives, probe_health, satisfies

logger = logging.getLogger(__name__)

# Diagnosis assigns the real class; detection must not pretend to know it.
UNCLASSIFIED = "UNKNOWN"


class Breach(BaseModel):
    health: dict[str, str]
    measured: dict[str, float]
    breached: list[str]


def detect_breach(target: TargetBinding) -> Breach | None:
    """Probe the application once. None when every declared objective holds."""
    health = probe_health(target)
    measured = measure_objectives(target)

    breached: list[str] = []
    objectives = target.manifest.objectives
    if objectives:
        for category in ("availability", "latency", "quality", "cost"):
            metrics = getattr(objectives, category)
            if not metrics or category not in measured:
                continue
            metric = metrics[0]
            if not satisfies(measured[category], metric.comparator, metric.threshold):
                breached.append(category)

    if not breached:
        return None
    return Breach(health=health, measured=measured, breached=breached)


def build_incident_scenario(
    target: TargetBinding, breach: Breach, scenario_id: str
) -> Scenario:
    """Turn an observed breach into an incident the graph can run."""
    scenario = scenario_from_target(
        target=target,
        fault_class=UNCLASSIFIED,
        measured=breach.measured,
        health=breach.health,
        scenario_id=scenario_id,
    )

    evidence: list[EvidenceItem] = []
    for category in breach.breached:
        metric = getattr(target.manifest.objectives, category)[0].metric
        evidence.append(
            EvidenceItem(
                id=f"ev-objective-{category}",
                kind="metric",
                source=metric,
                value=breach.measured[category],
                payload={"breached": True, "category": category},
            )
        )
    for name, status in breach.health.items():
        if status == "healthy":
            continue
        evidence.append(
            EvidenceItem(
                id=f"ev-health-{name}",
                kind="state",
                source=name,
                payload={
                    "health": status,
                    "role": target.manifest.services[name].role,
                },
            )
        )

    scenario.evidence = evidence
    return scenario
