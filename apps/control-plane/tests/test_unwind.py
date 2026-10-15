"""The undo stack's guarantee, made falsifiable.

AGENTS.md 4a calls the undo stack the system's core guarantee and the testing
section requires, per adapter, a test that proves its inverse restores the prior
state. Neither existed. The undo ablation (docs/MEASUREMENTS.md) measured a
working rollback and no rollback at all reporting the same outcome, because
nothing read the state back: `UNRECOVERABLE` was raised only by a test flag.

Two properties are checked here:

1. Every catalogue inverse restores the configuration its forward action wrote.
   Scoped to mutations written from a `$param` template -- a constant mutation
   like `api_health: healthy` is the simulator asserting an outcome, not a
   configuration write, and no inverse can or should undo it.
2. An unwind that cannot confirm the restore reports UNRECOVERABLE rather than
   passing quietly.
"""

import pytest

from kavach.catalogue.loader import load_catalogue
from kavach.graph.nodes import outcome_node, unwind_node
from kavach.graph.state import IncidentState
from kavach.scenarios.loader import load_scenario
from kavach.simulation.executor import execute_action
from kavach.tnr.models import Action, UndoRecord

FAULTS = [f"F0{i}" for i in range(1, 10)]


def _repair_for(fault: str) -> Action:
    f_def = load_catalogue().faults[fault]
    if f_def.repair:
        return Action(name=f_def.repair.action, params=dict(f_def.repair.params))
    return Action(name=f_def.recommended_actions[0], params={})


def _configuration_keys(action_name: str) -> set[str]:
    """Mutations written from a param, i.e. the ones an inverse is answerable for."""
    act_def = load_catalogue().actions[action_name]
    return {k for k, v in act_def.mutations.items() if v.startswith("$")}


@pytest.mark.parametrize("fault", FAULTS)
def test_catalogue_inverse_restores_the_configuration_it_wrote(fault: str) -> None:
    scenario = load_scenario(fault)
    before = (scenario.state or {}).copy()
    action = _repair_for(fault)

    state = before.copy()
    record = execute_action(action, state)
    keys = _configuration_keys(action.name)
    if not keys:
        pytest.skip(f"{action.name} writes no configuration, only asserted health")

    assert any(state.get(k) != before.get(k) for k in keys), (
        f"{action.name} changed none of {keys}; the test proves nothing"
    )

    execute_action(record.inverse_action, state)
    for k in keys:
        assert state.get(k) == before.get(k), (
            f"{action.name}'s inverse {record.inverse_action.name} left "
            f"{k}={state.get(k)!r}, prior value was {before.get(k)!r}"
        )


@pytest.mark.parametrize("fault", FAULTS)
def test_unwind_node_restores_every_witnessed_key(fault: str) -> None:
    scenario = load_scenario(fault)
    before = (scenario.state or {}).copy()
    action = _repair_for(fault)

    state = before.copy()
    record = execute_action(action, state)

    result = unwind_node(
        IncidentState(
            scenario=scenario,
            mode="SIMULATION",
            simulation_state=state,
            undo_stack=[record],
        )
    )
    after = result["simulation_state"]
    for k, v in record.pre_state_witness.items():
        assert after.get(k) == v, f"{fault}: {k} is {after.get(k)!r}, witnessed {v!r}"
    assert result["unwind_unrestored"] == []


def test_unrestored_key_reports_unrecoverable() -> None:
    scenario = load_scenario("F01")
    result = outcome_node(
        IncidentState(
            scenario=scenario,
            incident_id="inc-test",
            verification_passed=False,
            unwind_unrestored=["model_selection"],
        )
    )
    assert result["outcome"] == "UNRECOVERABLE"


def test_unwind_with_nothing_unrestored_does_not_report_unrecoverable() -> None:
    """The deny case's twin: a clean unwind must not be reported as a disaster."""
    scenario = load_scenario("F01")
    result = outcome_node(
        IncidentState(
            scenario=scenario,
            incident_id="inc-test",
            verification_passed=False,
            unwind_unrestored=[],
        )
    )
    assert result["outcome"] == "ESCALATED"


def test_live_revert_reports_failure_when_the_app_does_not_take_the_write() -> None:
    """A 2xx on the write is not evidence the state moved."""
    from kavach.catalogue.schema import EffectDef
    from kavach.preflight.schema import ReversibleStateDef
    from kavach.remediation import runtime_config

    effect = EffectDef(kind="reversible_state", key="model_selection", value="$target")
    rs_def = ReversibleStateDef(
        kind="runtime_config",
        read="http://localhost:1/model",
        write="http://localhost:1/model",
        field="model",
    )
    record = UndoRecord(
        original_action=Action(name="switch_model", params={"target": "model_backup"}),
        inverse_action=Action(name="switch_model", params={"target": "model_primary"}),
        pre_state_witness={"model_selection": "primary"},
        applied=True,
    )

    writes: list[str] = []
    runtime_config.write_value = lambda rs, v: writes.append(v)  # type: ignore[assignment]
    runtime_config.read_value = lambda rs: "backup"  # type: ignore[assignment]
    try:
        assert (
            runtime_config.revert_effect(effect, record, rs_def, "AUTONOMOUS") is False
        )
        runtime_config.read_value = lambda rs: "primary"  # type: ignore[assignment]
        assert (
            runtime_config.revert_effect(effect, record, rs_def, "AUTONOMOUS") is True
        )
    finally:
        import importlib

        importlib.reload(runtime_config)
    assert writes == ["primary", "primary"]
