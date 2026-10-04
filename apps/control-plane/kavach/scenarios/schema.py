from typing import Any

from pydantic import BaseModel, Field


class ServiceDef(BaseModel):
    role: str
    depends_on: list[str] | None = None


class QualityDef(BaseModel):
    golden_set: str
    min_cases: int
    scorers: list[str]


class ObjectiveDef(BaseModel):
    value: float
    threshold: float
    weight: float


class PermissionDef(BaseModel):
    allowed_actions: list[str] = Field(default_factory=list)
    max_risk_tier: str = "HIGH"


class EvidenceItem(BaseModel):
    id: str
    kind: str
    source: str
    value: float | None = None
    payload: dict[str, Any] | None = None


class TriggerDef(BaseModel):
    condition: str
    value: float


class DebtDef(BaseModel):
    repayment_action: str
    trigger: TriggerDef
    max_age_s: int


class Scenario(BaseModel):
    id: str
    fault_class: str
    services: dict[str, ServiceDef]
    health: dict[str, str]
    quality: QualityDef | None = None
    objectives: dict[str, ObjectiveDef] | None = None
    tolerance: dict[str, float] | None = None
    reversible_state: dict[str, dict[str, Any]] | None = None
    permissions: PermissionDef | None = Field(default_factory=PermissionDef)
    signals: dict[str, float] | None = None
    evidence: list[EvidenceItem] | None = None
    state: dict[str, str] | None = None
    debt: dict[str, Any] | None = None
