"""Append-only audit log with a hash chain.

AGENTS.md rule 8 names this a core guarantee; until now it did not exist in any
form. Each row carries the previous row's hash, so a row that is altered or
removed breaks the chain and `verify_chain` says where. The table also refuses
UPDATE, DELETE and TRUNCATE by trigger (migration 0005): the guarantee lives in
the database, not in the discipline of the callers.

What is recorded, and what deliberately is not. A row is written at each point
where the system decided or changed something: the gate's verdict, an execution,
a verification result, an unwind, the final outcome. Payloads carry action names,
parameters, risk tiers and measured deltas. They never carry evidence, prompts,
log lines, environment or anything read out of the managed application, because
that is where secrets and user data live (AGENTS.md rule 9) and this table is the
one place in the system that can never be redacted after the fact.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kavach.api.models import AuditLog

logger = logging.getLogger(__name__)

GENESIS = ""


class AuditChainError(Exception):
    pass


def _row_hash(
    prev_hash: str,
    actor: str,
    event: str,
    incident_id: str | None,
    payload: dict[str, Any],
    ts: str,
) -> str:
    """Hash over the row's content and its predecessor's hash.

    sort_keys, because a dict that serialises two ways hashes two ways and the
    chain would break on a re-read rather than on tampering.
    """
    body = json.dumps(
        {
            "prev": prev_hash,
            "incident_id": incident_id,
            "actor": actor,
            "event": event,
            "payload": payload,
            "ts": ts,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


async def append(
    session: AsyncSession,
    *,
    event: str,
    actor: str,
    incident_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    """Append one event and return its hash.

    The predecessor is read under a row lock in this transaction, so two
    concurrent appends serialise instead of chaining off the same parent.
    """
    payload = payload or {}
    await session.execute(text("LOCK TABLE audit_log IN SHARE ROW EXCLUSIVE MODE"))
    prev = (
        await session.execute(
            select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    prev_hash = prev or GENESIS

    ts = datetime.now(UTC)
    row_hash = _row_hash(prev_hash, actor, event, incident_id, payload, ts.isoformat())
    session.add(
        AuditLog(
            incident_id=incident_id,
            ts=ts,
            actor=actor,
            event=event,
            payload=payload,
            prev_hash=prev or None,
            hash=row_hash,
        )
    )
    await session.commit()
    return row_hash


async def read_log(
    session: AsyncSession, incident_id: str | None = None, limit: int = 200
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.id)
    if incident_id:
        stmt = stmt.where(AuditLog.incident_id == incident_id)
    return list((await session.execute(stmt.limit(limit))).scalars())


async def verify_chain(session: AsyncSession) -> tuple[bool, str | None]:
    """Recompute every hash in order. Returns (intact, first broken row's id)."""
    rows = list(
        (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars()
    )
    prev_hash = GENESIS
    # cast, not ignore: api/models.py uses the legacy Column() style, under which
    # mypy types an *instance* attribute as Column[T] rather than T.
    for row in rows:
        expected = _row_hash(
            prev_hash,
            cast(str, row.actor),
            cast(str, row.event),
            cast("str | None", row.incident_id),
            cast("dict[str, Any]", row.payload),
            cast(datetime, row.ts).isoformat(),
        )
        if (cast(str, row.prev_hash) or GENESIS) != prev_hash or row.hash != expected:
            return False, str(row.id)
        prev_hash = cast(str, row.hash)
    return True, None


def record(
    event: str,
    actor: str,
    incident_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append from synchronous code, which is where the graph nodes live.

    ponytail: one event loop per call, the same shape as the knowledge-base
    writes in graph/nodes.py and the reason api/db.py runs NullPool. The upgrade
    path is the same for both -- async graph nodes -- and is not worth doing for
    the audit log alone.

    A failure to write is logged at error and does not propagate: losing an audit
    row is bad, abandoning a repair half-applied because the audit database is
    down is worse.
    """
    import asyncio

    async def _go() -> None:
        from kavach.api.db import get_db_session

        async with get_db_session() as session:
            await append(
                session,
                event=event,
                actor=actor,
                incident_id=incident_id,
                payload=payload,
            )

    try:
        asyncio.run(_go())
    except Exception as e:  # noqa: BLE001 -- see docstring
        logger.error(
            "audit append failed for event=%s incident=%s: %s", event, incident_id, e
        )
