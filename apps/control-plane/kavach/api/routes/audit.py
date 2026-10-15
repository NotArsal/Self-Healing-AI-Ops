"""Read-only audit routes.

Read-only is the whole design. AGENTS.md rule 8 forbids an update or delete
route, and `DESIGN_SYSTEM.md` §7.12 says of the audit view that "no edit control
exists anywhere on this view — the absence is the point". Appending happens
inside the healing loop (`kavach/audit/log.py`), never over HTTP, because an
event the API can inject is not evidence of what the system did.
"""

from typing import Any

from fastapi import APIRouter

from kavach.api.db import get_db_session
from kavach.audit.log import read_log, verify_chain

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/")
async def get_audit_log(
    incident_id: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    async with get_db_session() as session:
        rows = await read_log(session, incident_id=incident_id, limit=limit)
    return [
        {
            "id": r.id,
            "incident_id": r.incident_id,
            "ts": r.ts.isoformat(),
            "actor": r.actor,
            "event": r.event,
            "payload": r.payload,
            "prev_hash": r.prev_hash,
            "hash": r.hash,
        }
        for r in rows
    ]


@router.get("/integrity")
async def get_audit_integrity() -> dict[str, Any]:
    """Recompute the chain. A broken link names the first row that does not fit."""
    async with get_db_session() as session:
        intact, broken_at = await verify_chain(session)
    return {"intact": intact, "broken_at": broken_at}
