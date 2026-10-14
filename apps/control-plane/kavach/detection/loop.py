"""The detection tick.

Mirrors the debt checker's shape: one asyncio task for the app's lifetime. It
probes the configured target and opens an incident when an objective breaches,
which is what makes a heal start with no human in the loop.
"""

import asyncio
import logging

from kavach.api.store import create_incident, get_all_incidents
from kavach.config import settings
from kavach.detection.monitor import build_incident_scenario, detect_breach
from kavach.scenarios.from_manifest import TargetLoadError, load_target

logger = logging.getLogger(__name__)

TERMINAL_OUTCOMES = {"RESOLVED", "ESCALATED", "UNRECOVERABLE"}


def _has_open_incident(manifest_path: str) -> bool:
    """True while an earlier breach of the same target is still being handled.

    Without this the 15s tick opens a second incident for a fault the first one
    is still repairing, and two incidents race for the same writer lock.
    """
    for state in get_all_incidents().values():
        scenario = state.get("scenario")
        target = getattr(scenario, "target", None)
        if target is None or target.manifest_path != manifest_path:
            continue
        if state.get("outcome") not in TERMINAL_OUTCOMES:
            return True
    return False


async def detection_tick() -> str | None:
    """One probe. Returns the new incident id, or None when nothing opened."""
    if not settings.target_manifest:
        return None

    try:
        target = load_target(settings.target_manifest)
    except TargetLoadError as e:
        logger.warning("detection: cannot load target manifest: %s", e)
        return None

    if _has_open_incident(target.manifest_path):
        return None

    # Probing is blocking HTTP; keep it off the event loop.
    breach = await asyncio.to_thread(detect_breach, target)
    if breach is None:
        return None

    incident_id = create_incident("pending", {})
    scenario = build_incident_scenario(target, breach, scenario_id=incident_id)
    initial_state = {
        "scenario": scenario,
        "simulation_state": {},
        "incident_id": incident_id,
        "mode": settings.execution_mode,
    }

    logger.info(
        "detection: breach on %s (%s) -> incident %s",
        target.manifest_path,
        ",".join(breach.breached),
        incident_id,
    )

    from kavach.api.routes.incidents import execute_graph_background

    get_all_incidents()[incident_id] = initial_state
    asyncio.create_task(execute_graph_background(incident_id, initial_state))
    return incident_id


async def detection_loop() -> None:
    while True:
        try:
            await asyncio.sleep(settings.detection_interval_s)
            await detection_tick()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("detection: tick failed")
