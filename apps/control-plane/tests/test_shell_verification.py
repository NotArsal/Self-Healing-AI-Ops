"""A shell repair is verified by its exit status, not by reading its output.

tests/test_executor_verify.py asserted the old behaviour: `verify_execution`
asked Laya, over the command's stdout, whether the command had worked, and
verify_node turned that answer into `verification_passed` -- which decides
whether the system unwinds. The model had no access to the exit code, which
execute_command returns and execute_node was discarding into `_success`.
Deleted along with the function; this replaces it.
"""

from kavach.graph.nodes import verify_node
from kavach.graph.state import IncidentState
from kavach.scenarios.schema import PermissionDef, Scenario, ServiceDef
from kavach.tnr.models import Action


def _state(success: str | None, output: str) -> IncidentState:
    sim_state = {"last_shell_output": output}
    if success is not None:
        sim_state["last_shell_success"] = success
    return IncidentState(
        scenario=Scenario(
            id="scen-shell",
            fault_class="F10",
            services={"api": ServiceDef(role="application")},
            health={"api": "unhealthy"},
            permissions=PermissionDef(allowed_actions=["shell_command"]),
        ),
        simulation_state=sim_state,
        approved_actions=[Action(name="shell_command", params={"cmd": "true"})],
    )


def test_a_zero_exit_verifies() -> None:
    result = verify_node(_state("true", "deployment.apps/api restarted"))
    assert result["verification_passed"] is True
    assert result["verification_deltas"] == {"exit_ok": 1.0}


def test_a_nonzero_exit_does_not_verify() -> None:
    result = verify_node(_state("false", 'Error from server (NotFound)'))
    assert result["verification_passed"] is False
    assert result["verification_deltas"] == {"exit_ok": 0.0}


def test_output_that_reads_like_success_does_not_override_a_failure() -> None:
    """The case the model got to decide, and the reason it must not.

    A command can print a reassuring line and still exit non-zero.
    """
    result = verify_node(_state("false", "restarted successfully, all OK"))
    assert result["verification_passed"] is False


def test_a_missing_exit_status_does_not_verify() -> None:
    """Absent information is not a pass."""
    result = verify_node(_state(None, "something happened"))
    assert result["verification_passed"] is False
