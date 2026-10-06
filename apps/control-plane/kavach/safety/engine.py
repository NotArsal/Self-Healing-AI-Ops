from datetime import UTC, datetime, timedelta
from typing import Any

from kavach.scenarios.schema import Scenario
from kavach.tnr.models import Action


class PermitResult:
    def __init__(self, is_allowed: bool, reason: str):
        self.is_allowed = is_allowed
        self.reason = reason


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
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts >= thirty_mins_ago:
                        recent_identical_faults += 1
                except Exception:
                    pass

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
