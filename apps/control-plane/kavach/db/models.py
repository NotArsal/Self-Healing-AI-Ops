"""Persisted state — incidents, risk decisions and hypotheses.

Three tables, each earning its place:

`incidents`     an approval must survive a control-plane restart, and MTTR
                over a series needs a series. In-memory history gave neither.
`risk_decisions` every `permit()` call, including the Laya-shaped typed frame,
                so the fine-tuning corpus accrues from the first decision long
                before any shadow engine reads it (`PRD.md` §7.1).
`hypotheses`    the unknown-failure flow ranks candidates and records which
                were tested and what happened. Without the table the flow has
                nowhere to put its work (`PRD.md` §8.4).

WHY THE PAYLOADS ARE JSON
The loop's records are already dataclasses with `to_dict()`, and their shape is
still moving. Normalising them into columns now would mean a migration for
every field the diagnosis gains. The columns that are queried — status, fault
class, service, timestamps — are real columns; the rest is a document. That is
a deliberate trade and the queries that matter stay indexable.

THE AUDIT LOG IS NOT HERE
It stays a hash-chained file (`audit/log.py`). A chain whose rows can be
updated by anything holding a database session is a weaker claim than one in an
append-only file, and the file's guarantee is already the honest one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)

    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    fault_class: Mapped[str | None] = mapped_column(String(32), index=True)
    fault_name: Mapped[str | None] = mapped_column(String(128))
    service: Mapped[str | None] = mapped_column(String(128), index=True)
    diagnosed_by: Mapped[str] = mapped_column(String(32), default="")
    planned_action: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(Text, default="")
    escalation_reason: Mapped[str] = mapped_column(Text, default="")

    # Seconds from detection to resolution. Stored rather than computed so a
    # dashboard can average it without reading every record.
    mttr_seconds: Mapped[float | None] = mapped_column(Float)

    # The full record. Shapes still move; the queried fields are columns above.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("ix_incidents_project_detected", "project", "detected_at"),
    )


class RiskDecision(Base):
    __tablename__ = "risk_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("incidents.incident_id", ondelete="CASCADE"), index=True
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    action: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[str] = mapped_column(String(32), index=True)
    risk_tier: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16))
    reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    # The Laya-format compression. Populated from the first decision.
    typed_decision_frame: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Filled when a shadow engine runs. Never read by permit() (PRD §7.1).
    shadow_engine: Mapped[str | None] = mapped_column(String(32))
    shadow_verdict: Mapped[str | None] = mapped_column(String(32))
    shadow_agreed: Mapped[bool | None] = mapped_column()


class Hypothesis(Base):
    """A candidate explanation for an unknown failure (`PRD.md` §8.4).

    Ranked, and marked as tested with an outcome. Nothing here executes: the
    unknown flow always ends at human escalation, and these rows are what the
    human reads.
    """

    __tablename__ = "hypotheses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("incidents.incident_id", ondelete="CASCADE"), index=True
    )
    rank: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    tested: Mapped[bool] = mapped_column(default=False)
    outcome: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
