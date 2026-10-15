"""Describe an incident in words, for embedding and recall.

The knowledge base matches incidents by similarity, so the text it embeds has to
carry what actually distinguishes one incident from another: which services are
unhealthy and which objectives are breached by how much. The previous call sites
reached for `scenario.trigger`, which is not a field on Scenario, so both the
read and the write raised and the knowledge base stayed permanently empty.
"""

from kavach.scenarios.schema import Scenario
from kavach.verification.live import satisfies


def describe_symptoms(scenario: Scenario) -> str:
    """A stable one-line-per-fact description of what is wrong."""
    parts: list[str] = []

    unhealthy = sorted(
        name for name, status in (scenario.health or {}).items() if status != "healthy"
    )
    if unhealthy:
        parts.append("unhealthy services: " + ", ".join(unhealthy))

    breached: list[str] = []
    for category, objective in (scenario.objectives or {}).items():
        if not satisfies(objective.value, objective.comparator, objective.threshold):
            breached.append(
                f"{category}={objective.value:.3f} "
                f"(needs {objective.comparator} {objective.threshold:.3f})"
            )
    if breached:
        parts.append("breached objectives: " + "; ".join(sorted(breached)))

    if scenario.signals:
        signals = ", ".join(f"{k}={v}" for k, v in sorted(scenario.signals.items()))
        parts.append("signals: " + signals)

    if not parts:
        return "no symptoms recorded"
    return "\n".join(parts)


def describe_incident(scenario: Scenario, fault_class: str) -> str:
    """The text used to look up similar past incidents."""
    return f"Fault: {fault_class}\nSymptoms: {describe_symptoms(scenario)}"
