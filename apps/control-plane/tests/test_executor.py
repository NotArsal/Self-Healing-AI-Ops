"""The executor runs what the gate permitted, and asks nothing of Laya.

These tests used to assert the opposite: that `execute_command` consults
`evaluate_safety` -- shadow Laya -- and raises `RequiresHumanApprovalError` when
it disapproves. That made the decision model a gate in everything but name,
which AGENTS.md forbids for v1, and the measurement shows the cost: Laya judges
7 of 9 legitimate repairs unsafe at confidence 0.01-0.16, so gating on it would
have blocked 78% of correct repairs (docs/MEASUREMENTS.md).

Permission is `safety.engine.permit()`'s decision and has already been made by
the time anything here runs; the deny cases live in tests/test_safety_commands.py.
"""

import sys
from unittest.mock import patch

from kavach.remediation.executor import execute_command

# A real executable, because the executor no longer runs commands through a
# shell: `echo` is a shell builtin on Windows and would not be found.
HELLO = f'"{sys.executable}" -c "print(\'hello\')"'


def test_a_permitted_command_runs() -> None:
    success, output = execute_command(HELLO, "Context")

    assert success is True, output
    assert "hello" in output


def test_laya_is_not_consulted() -> None:
    """Shadow means shadow. The executor must not call it at all."""
    with patch("kavach.remediation.tnr_gate.evaluate_safety") as mock_evaluate:
        success, output = execute_command(HELLO, "Context")

    assert success is True, output
    mock_evaluate.assert_not_called()


def test_a_second_command_after_a_semicolon_does_not_run() -> None:
    """No shell, so a chained command is an argument rather than a command.

    `permit()` refuses a metacharacter outright, so this is the second line of
    defence: even reached directly, the shell that would have interpreted the
    `;` is not there.
    """
    marker = "SHOULD-NOT-RUN"
    success, output = execute_command(
        f'"{sys.executable}" -c "print(\'first\')" ; echo {marker}', "Context"
    )

    assert marker not in output
    # python receives the rest as arguments and ignores them, or exits non-zero.
    assert "first" in output or success is False


def test_an_unparseable_command_fails_without_executing() -> None:
    success, output = execute_command("systemctl restart 'api", "Context")

    assert success is False
    assert "could not be parsed" in output


def test_an_empty_command_fails() -> None:
    success, output = execute_command("   ", "Context")

    assert success is False
    assert "Empty command" in output


def test_a_missing_executable_reports_rather_than_raises() -> None:
    success, output = execute_command("kavach-no-such-binary --now", "Context")

    assert success is False
    assert "Execution failed" in output
