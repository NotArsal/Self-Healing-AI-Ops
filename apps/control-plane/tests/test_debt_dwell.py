"""The debt trigger's dwell state machine.

Repaying the instant a flapping provider first looks healthy hands the
application straight back to the thing that just failed. The dwell is the guard,
and before it existed the checker passed value=0 and repaid immediately.

The health probe is stubbed so the state machine is asserted directly, with no
dependence on a live application or on test ordering.
"""

import pytest

from kavach.debt.triggers import evaluate_trigger, reset_dwell
from kavach.preflight.schema import KavachManifest, ServiceDef
from kavach.scenarios.schema import Scenario, TargetBinding
from kavach.scenarios.schema import ServiceDef as ScenarioServiceDef

INCIDENT = "inc-dwell-unit"


@pytest.fixture
def scenario() -> Scenario:
    manifest = KavachManifest(services={"api": ServiceDef(role="application")})
    return Scenario(
        id=INCIDENT,
        fault_class="F01",
        services={"api": ScenarioServiceDef(role="application")},
        health={"api": "healthy"},
        target=TargetBinding(manifest_path="kavach.yaml", manifest=manifest),
    )


@pytest.fixture(autouse=True)
def clean_dwell():
    reset_dwell(INCIDENT)
    yield
    reset_dwell(INCIDENT)


@pytest.fixture
def health(monkeypatch):
    """Control what the probe reports, and let the clock be moved."""
    state = {"health": {"api": "healthy"}, "now": 1000.0}
    monkeypatch.setattr(
        "kavach.debt.triggers.probe_health", lambda _target: state["health"]
    )
    monkeypatch.setattr("kavach.debt.triggers.time.time", lambda: state["now"])
    return state


def _trigger(scenario: Scenario, value: float) -> bool:
    return evaluate_trigger("healthy_for_s", value, {}, scenario, INCIDENT)


def test_unhealthy_never_triggers(scenario, health) -> None:
    health["health"] = {"api": "unhealthy"}
    assert _trigger(scenario, 0) is False


def test_dwell_must_elapse(scenario, health) -> None:
    assert _trigger(scenario, 30) is False, "first healthy observation starts the clock"

    health["now"] += 29
    assert _trigger(scenario, 30) is False, "29s of a 30s dwell is not enough"

    health["now"] += 1
    assert _trigger(scenario, 30) is True, "30s elapsed, repayable"


def test_a_dip_restarts_the_clock(scenario, health) -> None:
    assert _trigger(scenario, 30) is False
    health["now"] += 29

    # Flap.
    health["health"] = {"api": "unhealthy"}
    assert _trigger(scenario, 30) is False

    # Healthy again, but the 29s already served must not carry forward.
    health["health"] = {"api": "healthy"}
    health["now"] += 1
    assert _trigger(scenario, 30) is False, "the dwell must restart, not resume"

    health["now"] += 30
    assert _trigger(scenario, 30) is True


def test_unknown_health_is_not_healthy(scenario, health) -> None:
    """A service we cannot probe must not satisfy the precondition."""
    health["health"] = {"api": "unknown"}
    assert _trigger(scenario, 0) is False


def test_unsupported_condition_denies(scenario, health) -> None:
    assert evaluate_trigger("some_future_condition", 0, {}, scenario, INCIDENT) is False
