"""Deny cases for the forbidden-operation rule.

AGENTS.md requires a deny-case test per safety engine rule, and rule 7 says
no action may delete data, drop a database, scale to zero or run a migration,
and that these "must not become reachable". They were reachable: the allow-list
matches an action's *name*, so a scenario permitting `shell_command` permitted
any command string in its params, and the only thing reading that string was
shadow Laya -- which AGENTS.md forbids from gating and which disagrees with the
rule engine on 7 of 9 cases.
"""

import pytest

from kavach.safety.engine import permit
from kavach.scenarios.schema import PermissionDef, Scenario, ServiceDef
from kavach.tnr.models import Action


def _scenario() -> Scenario:
    """A scenario that explicitly permits shell_command. The point is that
    permitting the action must not permit everything the action can carry."""
    return Scenario(
        id="scen-shell",
        fault_class="F11",
        services={"api": ServiceDef(role="application")},
        health={"api": "unhealthy"},
        permissions=PermissionDef(
            allowed_actions=["shell_command"], max_risk_tier="HIGH"
        ),
    )


def _permit(cmd: str):  # type: ignore[no-untyped-def]
    return permit(Action(name="shell_command", params={"cmd": cmd}), _scenario(), [])


@pytest.mark.parametrize(
    "cmd,reason",
    [
        ("rm -rf /var/lib/mysql", "DELETES_DATA"),
        ("rm -f /etc/passwd", "DELETES_DATA"),
        ("psql -c 'DROP DATABASE kavach'", "DROPS_DATABASE"),
        ("psql -c 'TRUNCATE TABLE audit_log'", "DROPS_DATABASE"),
        ("mysql -e 'DELETE FROM incidents'", "DELETES_DATA"),
        ("mkfs.ext4 /dev/sdb1", "FORMATS_FILESYSTEM"),
        ("dd if=/dev/zero of=/dev/sda", "OVERWRITES_DEVICE"),
        ("shutdown -h now", "HALTS_HOST"),
        ("docker rm kavach-db", "DESTROYS_CONTAINER_STATE"),
        ("docker volume rm kavach_pgdata", "DESTROYS_CONTAINER_STATE"),
        ("kubectl delete deployment api", "DELETES_WORKLOAD"),
        ("kubectl scale deployment api --replicas=0", "SCALES_TO_ZERO"),
        ("alembic upgrade head", "RUNS_MIGRATION"),
        ("git push origin main", "WRITES_TO_A_REMOTE"),
    ],
)
def test_forbidden_operations_are_denied(cmd: str, reason: str) -> None:
    result = _permit(cmd)
    assert not result.is_allowed, f"{cmd!r} was permitted"
    assert result.reason == f"FORBIDDEN_OPERATION_{reason}", result.reason


@pytest.mark.parametrize(
    "cmd",
    [
        "systemctl restart api; rm -rf /data",
        "systemctl restart api && docker rm db",
        "echo ok | tee /etc/shadow",
        "echo $(cat /etc/passwd)",
        "echo `whoami`",
        "echo bad > /etc/hosts",
    ],
)
def test_a_second_command_hidden_behind_a_metacharacter_is_denied(cmd: str) -> None:
    """The gate is shown one command and must not be made to approve two."""
    result = _permit(cmd)
    assert not result.is_allowed, f"{cmd!r} was permitted"
    assert result.reason == "FORBIDDEN_OPERATION_SHELL_METACHARACTER"


def test_unparseable_command_is_denied() -> None:
    result = _permit("systemctl restart 'api")
    assert not result.is_allowed
    assert result.reason == "FORBIDDEN_OPERATION_UNPARSEABLE_COMMAND"


def test_an_ordinary_command_is_still_permitted() -> None:
    """The allow case, so the rule is not simply refusing everything."""
    result = _permit("systemctl restart api")
    assert result.is_allowed, result.reason


def test_an_action_carrying_no_command_is_unaffected() -> None:
    action = Action(name="shell_command", params={"target": "model_backup"})
    assert permit(action, _scenario(), []).is_allowed


def test_the_rule_runs_before_the_allow_list() -> None:
    """A destructive command is refused whether or not the action is permitted.

    Order matters: if the allow-list ran first, a scenario that did not permit
    `shell_command` would report UNAPPROVED_ACTION and the operation would never
    be examined -- which reads, in an audit, as a permissions problem rather
    than as an attempt to delete a database.
    """
    scenario = _scenario()
    scenario.permissions = PermissionDef(allowed_actions=[], max_risk_tier="HIGH")
    result = permit(
        Action(name="shell_command", params={"cmd": "rm -rf /var/lib/mysql"}),
        scenario,
        [],
    )
    assert not result.is_allowed
    assert result.reason == "FORBIDDEN_OPERATION_DELETES_DATA"
