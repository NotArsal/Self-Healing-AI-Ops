"""Side-effecting adapters. Permission is decided before anything gets here.

`safety.engine.permit()` is the only authority, and it has already run in
`gate_node` by the time these are called. Both functions used to call
`evaluate_safety` -- shadow Laya -- and raise if it disapproved, which made the
decision model a gate in everything but name. AGENTS.md is explicit that Laya is
shadow-only in v1 and must not gate an action, and the measurement says why:
Laya judges 7 of 9 legitimate repairs unsafe at confidence 0.01-0.16
(docs/MEASUREMENTS.md), so it would have blocked 78% of correct repairs while
offering no evidence it blocks the dangerous ones.
"""

import shlex
import subprocess

import httpx


class RequiresHumanApprovalError(Exception):
    """Kept for callers that still catch it; nothing in this module raises it.

    Approval is requested by the graph (`_request_approval` interrupts in
    `gate_node`), not by an adapter discovering mid-execution that it should not
    have been called.
    """

    def __init__(self, reason: str, command: str):
        self.reason = reason
        self.command = command
        super().__init__(f"Action requires human approval. Reason: {reason}")


def execute_command(command: str, incident_context: str = "") -> tuple[bool, str]:
    """Run a command the gate has already permitted.

    No shell. `shell=True` handed an uninspected string to a shell, so a command
    the gate approved could carry a second one after a `;` -- and the gate was
    only ever shown the action's *name*. permit() now reads the command and
    refuses shell metacharacters outright, and this runs the argv it parsed.

    ponytail: shlex.split is POSIX, so a Windows path with backslashes needs
    quoting. The catalogue's commands are container and process operations, so
    that has not bitten; a manifest-declared command allow-list is the real fix.
    """
    try:
        argv = shlex.split(command)
    except ValueError as e:
        return False, f"Command could not be parsed: {e}"
    if not argv:
        return False, "Empty command."

    try:
        result = subprocess.run(
            argv, shell=False, check=False, capture_output=True, text=True, timeout=30
        )
        output = result.stdout + "\n" + result.stderr
        success = result.returncode == 0
        return success, output.strip()
    except subprocess.TimeoutExpired:
        return False, "Command timed out after 30 seconds."
    except OSError as e:
        return False, f"Execution failed: {e!s}"


def execute_http(
    method: str, url: str, payload: dict[str, str], incident_context: str = ""
) -> tuple[bool, str]:
    """Issue a request the gate has already permitted."""
    try:
        from opentelemetry import propagate

        headers: dict[str, str] = {}
        propagate.inject(headers)

        with httpx.Client(timeout=30) as client:
            req = client.build_request(method, url, json=payload, headers=headers)
            res = client.send(req)
            success = res.is_success
            return success, res.text
    except Exception as e:
        return False, f"HTTP Execution failed: {e!s}"


# verify_execution() lived here: a Laya choice question over a command's stdout,
# asked by verify_node to decide whether a shell repair had worked, and from
# there whether to unwind. It had no access to the exit status, which
# execute_command returns and execute_node was discarding. Removed along with
# its only caller; the exit status is the verdict.
