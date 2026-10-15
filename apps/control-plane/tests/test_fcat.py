import os

import pytest
from pydantic import ValidationError

from kavach.catalogue.loader import load_catalogue, reset_catalogue
from kavach.catalogue.schema import FaultDef
from kavach.graph.nodes import gate_node, plan_node
from kavach.graph.state import IncidentState
from kavach.tnr.models import Action


@pytest.fixture(autouse=True)
def setup_teardown():
    # Make sure we use test fixtures
    os.environ["KAVACH_CATALOGUE_DIR"] = "catalogue_data,tests/fixtures"
    reset_catalogue()
    yield
    reset_catalogue()
    del os.environ["KAVACH_CATALOGUE_DIR"]


def test_loader_parses_builtin_and_fixtures() -> None:
    # Test loader successfully loads builtin and test fixtures
    cat = load_catalogue()

    assert "F01" in cat.faults
    assert "F03" in cat.faults

    f01 = cat.faults["F01"]
    assert f01.name == "provider_outage"
    assert f01.detect.signal == "gen_ai_error_rate"
    assert f01.repair.action == "switch_model"
    assert f01.repair.params["target"] == "model_backup"


def test_loader_maps_id_to_fault_class() -> None:
    cat = load_catalogue()
    assert "F10" in cat.faults
    f10 = cat.faults["F10"]
    assert f10.fault_class == "F10"
    assert f10.repair.action == "shell_command"


def test_plan_node_extracts_declarative_repair() -> None:
    state = IncidentState(fault_class="F01", scenario=None)
    new_state = plan_node(state)

    plan = new_state.get("plan", [])
    assert len(plan) == 1
    assert plan[0].name == "switch_model"
    assert plan[0].params["target"] == "model_backup"


def test_plan_node_extracts_destructive_repair_from_fixture() -> None:
    # F11 is a destructive command, but plan_node just plans it.
    # The safety engine (gate_node) is what blocks it in production.
    state = IncidentState(fault_class="F11", scenario=None)
    new_state = plan_node(state)

    plan = new_state.get("plan", [])
    assert len(plan) == 1
    assert plan[0].name == "shell_command"
    assert plan[0].params["cmd"] == "rm -rf /var/lib/mysql"


def test_invalid_yaml_fails_fast() -> None:
    # We can test validation error directly
    with pytest.raises(ValidationError):
        FaultDef(
            fault_class="F99",
            # missing detect, etc but wait, they are Optional except fault_class.
            # let's pass a bad type to detect
            detect="invalid_string_not_dict",
        )


def test_gate_node_blocks_f11_destructive_command() -> None:
    """The command is refused, and for the reason it should be.

    This used to build the scenario with a MagicMock, whose `permissions
    .allowed_actions` contains nothing, so the gate denied with
    UNAPPROVED_ACTION and the command string was never examined. It passed
    without testing anything about destructiveness. The scenario below permits
    `shell_command` explicitly, which is the case that matters: permitting the
    action must not permit everything the action can carry.
    """
    from kavach.scenarios.schema import PermissionDef, Scenario, ServiceDef

    scenario = Scenario(
        id="test_scen",
        fault_class="F11",
        services={"api": ServiceDef(role="application")},
        health={"api": "unhealthy"},
        permissions=PermissionDef(
            allowed_actions=["shell_command"], max_risk_tier="HIGH"
        ),
    )

    state = IncidentState(
        incident_id="inc_test",
        fault_class="F11",
        scenario=scenario,
        plan=[Action(name="shell_command", params={"cmd": "rm -rf /var/lib/mysql"})],
    )

    new_state = gate_node(state)
    assert new_state.get("gate_verdict") == "DENY"
    assert new_state.get("gate_reason") == "FORBIDDEN_OPERATION_DELETES_DATA"
    assert new_state.get("approved_actions") == []
