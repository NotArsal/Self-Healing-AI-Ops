import logging
import re
import shlex
from datetime import UTC, datetime, timedelta
from typing import Any

from kavach.scenarios.schema import Scenario
from kavach.tnr.models import Action


class PermitResult:
    def __init__(self, is_allowed: bool, reason: str):
        self.is_allowed = is_allowed
        self.reason = reason


# AGENTS.md rule 7: no action may delete data, drop a database, scale to zero or
# run a migration, and these "must not become reachable". An action carrying a
# free-text command makes every one of them reachable, because the allow-list
# matches the action's *name*: a scenario permitting `shell_command` permitted
# `rm -rf /var/lib/mysql` with it.
#
# A deny-list is the weaker half of a security model and is deliberately second
# best here. The structural fix is for a manifest to declare which commands it
# permits, so the gate can require a positive match instead of guessing at
# negatives -- that needs a `kavach.yaml` schema change, which is not a decision
# to take unilaterally. Until then this is the floor, not the ceiling.
FORBIDDEN_COMMAND_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\brm\s+(-\w+\s+)*-?\w*[rf]", "DELETES_DATA"),
    (r"\b(drop|truncate)\s+(database|schema|table)\b", "DROPS_DATABASE"),
    (r"\bdelete\s+from\b", "DELETES_DATA"),
    (r"\bmkfs(\.\w+)?\b", "FORMATS_FILESYSTEM"),
    (r"\bdd\s+.*\bof=", "OVERWRITES_DEVICE"),
    (r"\b(shutdown|reboot|halt|poweroff)\b", "HALTS_HOST"),
    (r"\bdocker\s+(rm|rmi|volume\s+rm|system\s+prune)\b", "DESTROYS_CONTAINER_STATE"),
    (r"\bkubectl\s+delete\b", "DELETES_WORKLOAD"),
    (r"--replicas[= ]+0\b", "SCALES_TO_ZERO"),
    (r"\bscale\b.*\b(--replicas[= ]+)?0\b", "SCALES_TO_ZERO"),
    (r"\b(alembic|flyway|liquibase)\b|\bmanage\.py\s+migrate\b", "RUNS_MIGRATION"),
    (r"\bgit\s+push\b", "WRITES_TO_A_REMOTE"),
    (r":\s*\(\s*\)\s*\{.*\};\s*:", "FORK_BOMB"),
)

# Anything that lets one approved command become two. The command is executed
# without a shell, so these cannot chain -- but a value carrying them is not
# the command the gate was shown, and it is refused rather than silently split.
SHELL_METACHARACTERS = (";", "&&", "||", "|", "`", "$(", ">", ">>", "\n")

# Params whose value is executed rather than compared.
COMMAND_PARAMS = ("cmd", "command", "script")


def _command_values(action: Action) -> list[str]:
    return [
        v
        for k, v in action.params.items()
        if k in COMMAND_PARAMS and isinstance(v, str) and v.strip()
    ]


def forbidden_operation(action: Action) -> str | None:
    """The rule-7 reason this action must not run, or None.

    Returns a verdict's reason, never a score: `permit()` decides, and nothing
    about a confidence or a risk tier may reach past this (AGENTS.md 4b).
    """
    for command in _command_values(action):
        lowered = command.lower()
        for meta in SHELL_METACHARACTERS:
            if meta in command:
                return "SHELL_METACHARACTER"
        for pattern, reason in FORBIDDEN_COMMAND_PATTERNS:
            if re.search(pattern, lowered):
                return reason
        try:
            if not shlex.split(command):
                return "EMPTY_COMMAND"
        except ValueError:
            # Unbalanced quoting. The gate cannot read what it is approving.
            return "UNPARSEABLE_COMMAND"
    return None


def permit(
    action: Action, scenario: Scenario, incident_history: list[dict[str, Any]]
) -> PermitResult:
    """
    Core safety gate. Evaluates an action against strict safety rules.
    This must NEVER return True based on an LLM score alone.
    """

    # 1. Forbidden services check (must run before any other check)
    forbidden = scenario.permissions.forbidden_services if scenario.permissions else []
    for f_service in forbidden:
        # Check action name
        if f_service.lower() in action.name.lower():
            return PermitResult(
                False, f"FORBIDDEN_SERVICE_TARGETED_{f_service.upper()}"
            )
        # Check all string parameters
        for v in action.params.values():
            if isinstance(v, str) and f_service.lower() in v.lower():
                return PermitResult(
                    False, f"FORBIDDEN_SERVICE_TARGETED_{f_service.upper()}"
                )

    # 1b. Forbidden operations, by what the action actually does. The allow-list
    # below matches an action's name, so without this a scenario that permits
    # `shell_command` permits every command string anyone can put in its params.
    operation = forbidden_operation(action)
    if operation is not None:
        return PermitResult(False, f"FORBIDDEN_OPERATION_{operation}")

    # 2. Allow-list check (empty by default)
    allowed = scenario.permissions.allowed_actions if scenario.permissions else []
    if action.name not in allowed:
        return PermitResult(False, f"UNAPPROVED_ACTION_{action.name.upper()}")

    # 3. Circuit breaker (4 identical faults in 30 mins -> deny)
    now = datetime.now(UTC)
    thirty_mins_ago = now - timedelta(minutes=30)

    recent_identical_faults = 0
    for inc in incident_history:
        # Ensure the incident belongs to the same target/fault_class
        inc_scenario = inc.get("scenario")
        if not inc_scenario:
            continue

        if inc_scenario.fault_class == scenario.fault_class:
            # Check timestamps
            ts_str = inc.get("timestamp")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                except ValueError:
                    # An unparseable timestamp silently lowered the count the
                    # circuit breaker compares against, which makes the breaker
                    # harder to trip rather than easier.
                    logging.getLogger(__name__).warning(
                        "incident timestamp %r is unparseable; it is not counted "
                        "towards the circuit breaker",
                        ts_str,
                    )
                else:
                    if ts >= thirty_mins_ago:
                        recent_identical_faults += 1

    if recent_identical_faults >= 4:
        return PermitResult(False, "CIRCUIT_BREAKER_TRIPPED")

    # 4. Blast radius
    # Find active incidents globally (status != RESOLVED/ESCALATED)
    active_incidents = 0
    for inc in incident_history:
        status = inc.get("outcome", "ACTIVE")
        if status not in ["RESOLVED", "ESCALATED", "UNRECOVERABLE"]:
            active_incidents += 1

    # Assuming blast radius limit of 3 concurrent active global incidents
    if active_incidents > 3:
        return PermitResult(False, "BLAST_RADIUS_EXCEEDED")

    return PermitResult(True, "PASSED")
