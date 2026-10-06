import asyncio
from typing import Any
from uuid import uuid4

# In-memory store for incidents
# Key: incident_id -> Value: IncidentState (dict)
INCIDENTS_STORE: dict[str, dict[str, Any]] = {}

# In-memory queues for SSE clients
# List of asyncio queues
EVENT_QUEUES: list[asyncio.Queue[dict[str, Any]]] = []


async def broadcast_event(event_data: dict[str, Any]) -> None:
    """Push event to all connected SSE clients."""
    for q in EVENT_QUEUES:
        await q.put(event_data)


def create_incident(scenario_id: str, state_data: dict[str, Any]) -> str:
    incident_id = f"inc-{uuid4().hex[:8]}"
    INCIDENTS_STORE[incident_id] = state_data
    return incident_id


def update_incident(incident_id: str, state_data: dict[str, Any] | None) -> None:
    if incident_id in INCIDENTS_STORE and state_data:
        INCIDENTS_STORE[incident_id].update(state_data)


def get_incident(incident_id: str) -> dict[str, Any] | None:
    return INCIDENTS_STORE.get(incident_id)


def get_all_incidents() -> dict[str, dict[str, Any]]:
    return INCIDENTS_STORE
