"""What the knowledge base embeds and recalls on.

Both call sites previously read `scenario.trigger`, which Scenario does not
define, so every read and write raised into a bare except and the knowledge base
was permanently empty. These assert the description is built from real incident
data, so the failure cannot return silently.
"""

from kavach.knowledge.summary import describe_incident, describe_symptoms
from kavach.scenarios.schema import ObjectiveDef, Scenario, ServiceDef


def _scenario(**kwargs) -> Scenario:
    defaults = dict(
        id="inc-1",
        fault_class="F01",
        services={"api": ServiceDef(role="application")},
        health={"api": "healthy"},
    )
    defaults.update(kwargs)
    return Scenario(**defaults)


def test_names_unhealthy_services():
    scenario = _scenario(health={"api": "healthy", "llm-proxy": "unhealthy"})
    assert "llm-proxy" in describe_symptoms(scenario)
    assert "unhealthy services" in describe_symptoms(scenario)


def test_healthy_services_are_not_listed():
    scenario = _scenario(health={"api": "healthy", "llm-proxy": "healthy"})
    assert "unhealthy services" not in describe_symptoms(scenario)


def test_reports_a_breached_objective_with_its_threshold():
    scenario = _scenario(
        objectives={
            # An error ratio: lower is better, so "<" is the direction.
            "availability": ObjectiveDef(
                value=1.0, threshold=0.01, weight=1.0, comparator="<"
            )
        }
    )
    described = describe_symptoms(scenario)
    assert "breached objectives" in described
    assert "availability=1.000" in described
    assert "< 0.010" in described


def test_a_satisfied_objective_is_not_a_symptom():
    scenario = _scenario(
        objectives={
            "availability": ObjectiveDef(
                value=0.0, threshold=0.01, weight=1.0, comparator="<"
            )
        }
    )
    assert "breached objectives" not in describe_symptoms(scenario)


def test_comparator_direction_is_respected():
    """A pass rate of 0.9 against ">= 0.85" is fine, not a breach."""
    scenario = _scenario(
        objectives={
            "quality": ObjectiveDef(
                value=0.90, threshold=0.85, weight=1.0, comparator=">="
            )
        }
    )
    assert "breached objectives" not in describe_symptoms(scenario)


def test_description_is_stable_across_dict_ordering():
    """Embeddings are matched by similarity; the same incident must read the same."""
    a = _scenario(health={"api": "unhealthy", "llm-proxy": "unhealthy"})
    b = _scenario(health={"llm-proxy": "unhealthy", "api": "unhealthy"})
    assert describe_symptoms(a) == describe_symptoms(b)


def test_empty_scenario_says_so_rather_than_returning_blank():
    assert describe_symptoms(_scenario()) == "no symptoms recorded"


def test_describe_incident_carries_the_fault_class():
    described = describe_incident(_scenario(), "F07")
    assert "F07" in described
