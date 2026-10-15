"""Session handling and the incident store.

DEGRADES, NEVER BLOCKS
Persistence is how an approval survives a restart and how MTTR gets a series.
It is not how the loop heals. If Postgres is down, `available()` is False, the
store no-ops, and detection, diagnosis, repair and verification all still run —
the console's history empties and MTTR is unavailable, and that is the right
trade. A control plane that refuses to fix a broken service because its own
bookkeeping database is unreachable has the priorities backwards.

Every method therefore swallows and logs rather than raising into the healing
path. The one exception is `init()`, which a caller may legitimately want to
fail loudly at startup.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from kavach.db.models import Base, Hypothesis, Incident, RiskDecision

logger = structlog.get_logger(__name__)


def _as_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def sync_url(url: str) -> str:
    """Normalise a configured URL to the sync psycopg driver.

    `KAVACH_DATABASE_URL` is declared with `+asyncpg` from Phase 0, and compose
    still supplies it. The loop is synchronous, so rather than ask every
    deployment to change its environment, the driver is corrected here.
    """
    for wrong, right in (
        ("postgresql+asyncpg://", "postgresql+psycopg://"),
        ("postgres://", "postgresql+psycopg://"),
    ):
        if url.startswith(wrong):
            return right + url[len(wrong):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class IncidentStore:
    """Incidents, risk decisions and hypotheses. Best-effort by design."""

    def __init__(self, url: str, echo: bool = False, connect_timeout: int = 5) -> None:
        self.url = sync_url(url)
        self.connect_timeout = connect_timeout
        self._engine: Engine | None = None
        self._sessions: sessionmaker[Session] | None = None
        self._echo = echo
        self._reason = "not initialised"

    # --- lifecycle ----------------------------------------------------------

    def init(self, create: bool = True) -> bool:
        """Connect and create tables. Returns False instead of raising."""
        try:
            engine = create_engine(
                self.url,
                echo=self._echo,
                pool_pre_ping=True,
                pool_size=5,
                # Bookkeeping must fail FAST. Without this, libpq retries every
                # address the host resolves to with its own long default, and
                # an unreachable database blocked app startup for 135 seconds -
                # the API appearing hung because its audit store was down.
                connect_args={"connect_timeout": self.connect_timeout},
                pool_timeout=self.connect_timeout,
            )
            if create:
                Base.metadata.create_all(engine)
            self._engine = engine
            self._sessions = sessionmaker(engine, expire_on_commit=False)
            self._reason = ""
            return True
        except Exception as exc:
            self._reason = f"{type(exc).__name__}: {exc}"
            logger.warning("incident store unavailable", error=self._reason)
            return False

    def available(self) -> bool:
        return self._sessions is not None

    @property
    def unavailable_reason(self) -> str:
        return self._reason

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
        self._engine = None
        self._sessions = None

    @contextlib.contextmanager
    def _session(self) -> Iterator[Session | None]:
        if self._sessions is None:
            yield None
            return
        session = self._sessions()
        try:
            yield session
            session.commit()
        except Exception as exc:
            # Never raises into the healing path. A read that fails this way
            # falls through to its caller's fallback value, which is why every
            # reader below assigns a result rather than returning inside the
            # `with` - mypy sees the block as always-returning, the runtime
            # does not, and only one of those is right.
            session.rollback()
            logger.warning("incident store write failed", error=str(exc))
        finally:
            session.close()

    # --- writing ------------------------------------------------------------

    def save(self, record: dict[str, Any]) -> None:
        """Upsert one incident from its `to_dict()`."""
        incident_id = str(record.get("incident_id") or "")
        if not incident_id:
            return
        detected = _as_dt(record.get("detected_at"))
        resolved = _as_dt(record.get("resolved_at"))
        mttr = (resolved - detected).total_seconds() if detected and resolved else None

        with self._session() as session:
            if session is None:
                return
            row = session.get(Incident, incident_id)
            if row is None:
                row = Incident(incident_id=incident_id)
                session.add(row)
            row.project = str(record.get("project") or "")
            row.status = str(record.get("status") or "")
            row.detected_at = detected
            row.resolved_at = resolved
            row.fault_class = record.get("fault_class")
            row.fault_name = record.get("fault_name")
            row.service = record.get("service")
            row.diagnosed_by = str(record.get("diagnosed_by") or "")
            row.planned_action = record.get("planned_action")
            row.outcome = str(record.get("outcome") or "")
            row.escalation_reason = str(record.get("escalation_reason") or "")
            row.mttr_seconds = mttr
            row.payload = record

    def save_decision(self, incident_id: str, decision: dict[str, Any]) -> None:
        with self._session() as session:
            if session is None:
                return
            session.add(RiskDecision(
                incident_id=incident_id,
                action=str(decision.get("action") or ""),
                verdict=str(decision.get("verdict") or ""),
                risk_tier=str(decision.get("risk_tier") or ""),
                mode=str(decision.get("mode") or ""),
                reasons=list(decision.get("reasons") or []),
                checks=list(decision.get("checks") or []),
                typed_decision_frame=dict(decision.get("typed_decision_frame") or {}),
            ))

    def save_hypotheses(self, incident_id: str, items: list[dict[str, Any]]) -> None:
        with self._session() as session:
            if session is None:
                return
            for item in items:
                session.add(Hypothesis(
                    incident_id=incident_id,
                    rank=int(item.get("rank", 0)),
                    description=str(item.get("description") or ""),
                    confidence=float(item.get("confidence") or 0.0),
                    evidence_ids=list(item.get("evidence_ids") or []),
                    tested=bool(item.get("tested")),
                    outcome=str(item.get("outcome") or ""),
                ))

    # --- reading ------------------------------------------------------------

    def get(self, incident_id: str) -> dict[str, Any] | None:
        found: dict[str, Any] | None = None
        with self._session() as session:
            if session is not None:
                row = session.get(Incident, incident_id)
                found = dict(row.payload) if row else None
        return found

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Newest first."""
        out: list[dict[str, Any]] = []
        with self._session() as session:
            if session is not None:
                rows = session.execute(
                    select(Incident)
                    .order_by(Incident.detected_at.desc().nullslast())
                    .limit(limit)
                ).scalars().all()
                out = [dict(r.payload) for r in rows]
        return out

    def hypotheses(self, incident_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        with self._session() as session:
            if session is not None:
                rows = session.execute(
                    select(Hypothesis)
                    .where(Hypothesis.incident_id == incident_id)
                    .order_by(Hypothesis.rank)
                ).scalars().all()
                out = [
                    {"rank": r.rank, "description": r.description,
                     "confidence": r.confidence, "evidence_ids": r.evidence_ids,
                     "tested": r.tested, "outcome": r.outcome}
                    for r in rows
                ]
        return out

    def fleet_metrics(self) -> dict[str, Any]:
        """The aggregates the console cannot compute from memory.

        Returned as `None` where there is nothing to measure rather than `0`.
        A zero MTTR reads as "instant", which is the opposite of "no data", and
        the console must be able to tell them apart.
        """
        empty: dict[str, Any] = {
            "incidents": 0, "resolved": 0, "escalated": 0, "awaiting": 0,
            "auto_healed": 0, "mttr_seconds": None, "repair_success_rate": None,
            "available": self.available(),
        }
        metrics = empty
        with self._session() as session:
            if session is None:
                return metrics
            counts = dict(session.execute(
                select(Incident.status, func.count()).group_by(Incident.status)
            ).all())
            resolved = int(counts.get("RESOLVED", 0))
            escalated = int(counts.get("ESCALATED", 0))
            awaiting = int(counts.get("AWAITING_APPROVAL", 0))
            total = sum(int(v) for v in counts.values())

            mttr = session.execute(
                select(func.avg(Incident.mttr_seconds))
                .where(Incident.mttr_seconds.is_not(None))
            ).scalar()

            # Success over incidents that reached a repair outcome. Incidents
            # that found no fault are not attempts and must not inflate it.
            attempts = resolved + escalated
            metrics = {
                "incidents": total,
                "resolved": resolved,
                "escalated": escalated,
                "awaiting": awaiting,
                "auto_healed": resolved,
                "mttr_seconds": round(float(mttr), 1) if mttr is not None else None,
                "repair_success_rate": (
                    round(resolved / attempts, 3) if attempts else None
                ),
                "available": True,
            }
        return metrics
