from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.0's declarative base.

    `declarative_base()` returns a value, and mypy cannot use a value as a base
    class, so every model here was an `Invalid base class` error. Same metadata,
    same mapping; alembic reads Base.metadata either way.
    """


class RemediationDebt(Base):
    __tablename__ = "remediation_debt"

    id = Column(String, primary_key=True)
    incident_id = Column(String, nullable=False)
    action_name = Column(String, nullable=False)
    action_params = Column(JSONB, nullable=False, server_default="{}")
    trigger_type = Column(String, nullable=False)
    trigger_condition = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    max_age_s = Column(Integer, nullable=False)
    status = Column(
        String, nullable=False, server_default="PENDING"
    )  # PENDING, REPAID, ESCALATED


from pgvector.sqlalchemy import Vector
from sqlalchemy import Text


class IncidentMemory(Base):
    __tablename__ = "incident_memory"

    id = Column(String, primary_key=True)
    fault_class = Column(String, nullable=False)
    symptoms = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    repair_action = Column(JSONB, nullable=False, server_default="{}")
    outcome = Column(String, nullable=False)
    embedding = Column(Vector(768), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


from sqlalchemy import BigInteger


class AuditLog(Base):
    """Append-only; migration 0005 installs a trigger that refuses UPDATE/DELETE.

    No ORM code may change a row here, and nothing should try: the chain in
    prev_hash/hash makes an alteration detectable, which is the point.
    """

    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    incident_id = Column(String, nullable=True, index=True)
    ts = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    actor = Column(String, nullable=False)
    event = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False, server_default="{}")
    prev_hash = Column(String(64), nullable=True)
    hash = Column(String(64), nullable=False, unique=True)
