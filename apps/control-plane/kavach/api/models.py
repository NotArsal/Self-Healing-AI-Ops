from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class RemediationDebt(Base):
    __tablename__ = "remediation_debt"

    id = Column(String, primary_key=True)
    incident_id = Column(String, nullable=False)
    action_name = Column(String, nullable=False)
    action_params = Column(JSONB, nullable=False, server_default='{}')
    trigger_type = Column(String, nullable=False)
    trigger_condition = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    max_age_s = Column(Integer, nullable=False)
    status = Column(String, nullable=False, server_default='PENDING')  # PENDING, REPAID, ESCALATED

from pgvector.sqlalchemy import Vector
from sqlalchemy import Text

class IncidentMemory(Base):
    __tablename__ = "incident_memory"

    id = Column(String, primary_key=True)
    fault_class = Column(String, nullable=False)
    symptoms = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    repair_action = Column(JSONB, nullable=False, server_default='{}')
    outcome = Column(String, nullable=False)
    embedding = Column(Vector(768), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
