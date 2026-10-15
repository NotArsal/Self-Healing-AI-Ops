"""The catalogue overlays per-fault files onto core.yaml instead of replacing.

`load_catalogue` assigned each fault into the dict, so `f03.yaml` -- which
declares neither `risk` nor `detect` -- replaced `core.yaml`'s F03 wholesale.
Every fault loaded as LOW, `plan_node` never set `sandbox_required`, and the
F-SBX sandbox branch was unreachable for every real fault.
"""

import pytest

from kavach.catalogue.loader import load_catalogue, reset_catalogue
from kavach.graph.nodes import plan_node
from kavach.graph.state import IncidentState
from kavach.scenarios.loader import load_scenario


@pytest.fixture(autouse=True)
def _fresh_catalogue():
    reset_catalogue()
    yield
    reset_catalogue()


def test_per_fault_file_does_not_drop_core_fields() -> None:
    f03 = load_catalogue().faults["F03"]
    # Declared only in core.yaml.
    assert f03.risk == "MEDIUM"
    assert f03.detect is not None and f03.detect.signal == "container_status"
    assert f03.applies_to_roles == ["application"]
    # Declared in f03.yaml, which must still win.
    assert f03.name == "container crash-loop or OOM"


def test_risk_tiers_are_not_flat() -> None:
    risks = {fc: f.risk for fc, f in load_catalogue().faults.items()}
    assert risks["F03"] == "MEDIUM"
    assert risks["F07"] == "MEDIUM"
    assert risks["F01"] == "LOW"


def test_action_overlay_keeps_an_effect_binding() -> None:
    # switch_model's live binding lives in core.yaml only; an overlay of the same
    # action name elsewhere must not be able to silently un-bind it.
    assert load_catalogue().actions["switch_model"].effect is not None


@pytest.mark.parametrize("fault,expected_tier", [("F01", "LOW"), ("F03", "MEDIUM")])
def test_plan_node_reaches_the_sandbox_branch(fault, expected_tier) -> None:
    result = plan_node(IncidentState(scenario=load_scenario(fault), fault_class=fault))
    assert result["risk_tier"] == expected_tier
    assert result["sandbox_required"] is (expected_tier == "MEDIUM")
    assert result["plan"], "a declared repair must still produce a plan"


def test_declared_repair_params_resolve() -> None:
    """A repair must supply what its action's templates read.

    Forward mutations resolve from the repair's own params. An inverse mapping may
    also name a state key the forward action mutated, which the witness supplies
    (see simulation/executor.execute_action). Anything else resolves to "unknown"
    and is silently written as the repair or the undo.
    """
    cat = load_catalogue()
    for fc, f_def in cat.faults.items():
        if not f_def.repair:
            continue  # legacy recommended_actions carry no params at all
        act = cat.actions[f_def.repair.action]
        params = set(f_def.repair.params)
        forward = {v[1:] for v in act.mutations.values() if v.startswith("$")}
        assert not forward - params, (
            f"{fc} repair omits {forward - params} for {act.name}"
        )

        witnessed = set(act.mutations)
        inverse = {
            v[1:] for v in act.inverse.params_mapping.values() if v.startswith("$")
        }
        unresolvable = inverse - params - witnessed
        assert not unresolvable, (
            f"{fc}: {act.inverse.name} reads {unresolvable}, which is neither a "
            f"param of {act.name} nor a key it witnesses"
        )
