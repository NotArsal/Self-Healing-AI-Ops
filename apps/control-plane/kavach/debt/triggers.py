import logging
import time
from typing import Any

from kavach.scenarios.schema import Scenario
from kavach.verification.live import probe_health

logger = logging.getLogger(__name__)

# First moment each incident's application was observed fully healthy again.
# ponytail: in-memory, so a control-plane restart restarts the dwell clock. The
# debt row itself survives in Postgres; only the dwell does not. Persist it on
# the row if that matters.
_FIRST_HEALTHY: dict[str, float] = {}


def reset_dwell(incident_id: str) -> None:
    _FIRST_HEALTHY.pop(incident_id, None)


def evaluate_trigger(
    condition: str,
    value: float,
    current_signals: dict[str, Any],
    scenario: Scenario | None = None,
    incident_id: str | None = None,
) -> bool:
    """Has the condition that makes this debt repayable held for long enough?

    For a live application, `healthy_for_s` means every declared health endpoint
    reports healthy and has done so continuously for `value` seconds. The dwell
    matters: repaying the instant a flapping provider looks healthy puts the
    application straight back onto the thing that just failed.
    """
    if scenario is not None and scenario.target is not None:
        return _evaluate_live(condition, value, scenario, incident_id)

    if condition == "primary_healthy_for_s":
        return current_signals.get("model_primary") == "healthy"

    if condition == "healthy_for_s":
        return current_signals.get("llm_proxy_health") == "healthy"

    return False


def _evaluate_live(
    condition: str,
    value: float,
    scenario: Scenario,
    incident_id: str | None,
) -> bool:
    if condition not in ("healthy_for_s", "primary_healthy_for_s"):
        logger.warning("debt trigger: unsupported condition %r", condition)
        return False

    assert scenario.target is not None
    health = probe_health(scenario.target)
    # "unknown" is not "healthy": a service we cannot probe must not satisfy the
    # precondition for handing the application back to it.
    all_healthy = bool(health) and all(v == "healthy" for v in health.values())

    key = incident_id or scenario.id
    if not all_healthy:
        _FIRST_HEALTHY.pop(key, None)
        return False

    now = time.time()
    first_seen = _FIRST_HEALTHY.setdefault(key, now)
    held_for = now - first_seen
    if held_for < value:
        logger.info(
            "debt trigger: application healthy for %.0fs of %.0fs required",
            held_for,
            value,
        )
        return False
    return True
