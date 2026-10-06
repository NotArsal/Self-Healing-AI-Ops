from datetime import UTC, datetime, timedelta

import pytest

from kavach.safety.engine import permit
from kavach.scenarios.schema import PermissionDef, Scenario
from kavach.tnr.models import Action


@pytest.fixture
def base_scenario():
    return Scenario(
        id="test-scen-1",
        fault_class="F01",
        services={},
        health={},
        permissions=PermissionDef(
            allowed_actions=["restart_service", "scale_up"],
            forbidden_services=["billing-db", "auth-service"],
        ),
    )


def test_permit_allowed_action(base_scenario):
    action = Action(name="restart_service", params={"target": "api"})
    res = permit(action, base_scenario, [])
    assert res.is_allowed is True
    assert res.reason == "PASSED"


def test_permit_deny_unapproved_action(base_scenario):
    action = Action(name="drop_table", params={})
    res = permit(action, base_scenario, [])
    assert res.is_allowed is False
    assert "UNAPPROVED_ACTION" in res.reason


def test_permit_deny_forbidden_service_in_name(base_scenario):
    action = Action(name="restart_service_billing-db", params={})
    res = permit(action, base_scenario, [])
    assert res.is_allowed is False
    assert "FORBIDDEN_SERVICE" in res.reason


def test_permit_deny_forbidden_service_in_params(base_scenario):
    action = Action(name="restart_service", params={"target": "auth-service"})
    res = permit(action, base_scenario, [])
    assert res.is_allowed is False
    assert "FORBIDDEN_SERVICE" in res.reason


def test_permit_circuit_breaker(base_scenario):
    now = datetime.now(UTC)
    # Simulate 4 previous identical faults in the last 30 minutes
    history = [
        {
            "scenario": base_scenario,
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "outcome": "RESOLVED",
        },
        {
            "scenario": base_scenario,
            "timestamp": (now - timedelta(minutes=10)).isoformat(),
            "outcome": "RESOLVED",
        },
        {
            "scenario": base_scenario,
            "timestamp": (now - timedelta(minutes=15)).isoformat(),
            "outcome": "RESOLVED",
        },
        {
            "scenario": base_scenario,
            "timestamp": (now - timedelta(minutes=20)).isoformat(),
            "outcome": "RESOLVED",
        },
    ]

    action = Action(name="restart_service", params={"target": "api"})
    res = permit(action, base_scenario, history)
    assert res.is_allowed is False
    assert "CIRCUIT_BREAKER_TRIPPED" in res.reason


def test_permit_blast_radius(base_scenario):
    # Simulate 4 currently active incidents (globally)
    other_scenario = Scenario(id="other", fault_class="F02", services={}, health={})
    history = [
        {"scenario": other_scenario, "outcome": "ACTIVE"},
        {"scenario": other_scenario, "outcome": "ACTIVE"},
        {"scenario": other_scenario, "outcome": "ACTIVE"},
        {"scenario": other_scenario, "outcome": "ACTIVE"},
    ]

    action = Action(name="restart_service", params={"target": "api"})
    res = permit(action, base_scenario, history)
    assert res.is_allowed is False
    assert "BLAST_RADIUS_EXCEEDED" in res.reason
