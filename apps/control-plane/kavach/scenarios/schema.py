from typing import Any

from pydantic import BaseModel, Field

from kavach.preflight.schema import KavachManifest


class TargetBinding(BaseModel):
    """A live application this incident is about.

    Its presence on a Scenario is what switches the executor and the verifier
    from simulated state onto the real thing. Dispatch is on this field being
    set, never on the fault class.
    """

    manifest_path: str
    manifest: KavachManifest


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
    # Direction of "better". Defaults to higher-is-better, which is what the
    # hand-authored simulation scenarios assume; a manifest metric such as
    # http_requests_errors_ratio declares "<" and is compared the other way.
    comparator: str = ">="


class PermissionDef(BaseModel):
    allowed_actions: list[str] = Field(default_factory=list)
    max_risk_tier: str = "HIGH"
    forbidden_services: list[str] = Field(default_factory=list)


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
    debt_config: dict[str, Any] | None = Field(default=None, alias="debt")
    active_debt: dict[str, Any] | None = None
    # The debt entry owed by this incident, resolved from debt_config once the
    # fault is diagnosed. Declared rather than attached dynamically: assigning an
    # undeclared attribute to a Pydantic model raises, which is why the debt path
    # only ever appeared to work while the lookup above it was silently failing.
    active_debt_def: Any | None = None
    # Absent for the hand-authored simulation scenarios; set when the incident
    # concerns a real onboarded application.
    target: TargetBinding | None = None
