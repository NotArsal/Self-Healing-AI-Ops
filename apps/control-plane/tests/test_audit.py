"""The audit log: hash chain, and append-only enforced by the database.

AGENTS.md rule 8 calls this a core guarantee and forbids an update or delete
route. A guarantee that rests on no caller writing the wrong statement is a
convention, so the tests that matter here are the ones that *try* to break it:
an UPDATE, a DELETE and a TRUNCATE must all be refused by Postgres itself.

The chain tests need a real database (JSONB, a plpgsql trigger and a row lock),
so they carry the `live` marker and run under `make test-integration`.
"""

import pytest
from sqlalchemy import text

from kavach.audit.log import _row_hash, append, read_log, verify_chain


def test_row_hash_is_stable_across_dict_ordering() -> None:
    """A payload that serialises two ways would break the chain on a re-read."""
    a = _row_hash("prev", "kavach.gate", "gate_verdict", "inc-1",
                  {"verdict": "ALLOW", "risk_tier": "LOW"}, "2026-10-15T00:00:00+00:00")
    b = _row_hash("prev", "kavach.gate", "gate_verdict", "inc-1",
                  {"risk_tier": "LOW", "verdict": "ALLOW"}, "2026-10-15T00:00:00+00:00")
    assert a == b


def test_row_hash_changes_with_every_field() -> None:
    base = {
        "prev_hash": "p", "actor": "a", "event": "e", "incident_id": "i",
        "payload": {"x": 1}, "ts": "2026-10-15T00:00:00+00:00",
    }
    original = _row_hash(**base)  # type: ignore[arg-type]
    for field, altered in [
        ("prev_hash", "p2"),
        ("actor", "a2"),
        ("event", "e2"),
        ("incident_id", "i2"),
        ("payload", {"x": 2}),
        ("ts", "2026-10-15T00:00:01+00:00"),
    ]:
        assert _row_hash(**{**base, field: altered}) != original, field  # type: ignore[arg-type]


def _run(coro):  # type: ignore[no-untyped-def]
    """asyncio.run per test, matching how the graph nodes reach the database.

    ponytail: no pytest-asyncio, because adding a dependency for three tests is
    worse than four lines. See kavach/api/db.py for why the engine is unpooled.
    """
    import asyncio

    async def _with_session():  # type: ignore[no-untyped-def]
        from kavach.api.db import get_db_session

        async with get_db_session() as session:
            return await coro(session)

    return asyncio.run(_with_session())


@pytest.mark.live
def test_chain_links_and_verifies() -> None:
    async def body(session):  # type: ignore[no-untyped-def]
        first = await append(
            session, event="gate_verdict", actor="kavach.gate",
            incident_id="inc-audit-test", payload={"verdict": "ALLOW"},
        )
        second = await append(
            session, event="executed", actor="kavach.executor",
            incident_id="inc-audit-test", payload={"actions": ["switch_model"]},
        )
        assert first != second

        rows = await read_log(session, incident_id="inc-audit-test")
        assert [r.event for r in rows[-2:]] == ["gate_verdict", "executed"]
        assert rows[-1].prev_hash == rows[-2].hash

        intact, broken_at = await verify_chain(session)
        assert intact, f"chain broken at row {broken_at}"

    _run(body)


@pytest.mark.live
@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_log SET event = 'tampered'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ],
)
def test_database_refuses_to_mutate_the_log(statement: str) -> None:
    async def body(session):  # type: ignore[no-untyped-def]
        await append(
            session, event="outcome", actor="kavach.graph",
            incident_id="inc-audit-immutable", payload={"outcome": "MITIGATED"},
        )
        with pytest.raises(Exception) as excinfo:
            await session.execute(text(statement))
            await session.commit()
        assert "append-only" in str(excinfo.value), str(excinfo.value)
        await session.rollback()

    _run(body)
