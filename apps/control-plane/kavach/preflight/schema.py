from typing import Any, Literal, List, Dict, Optional
from pydantic import BaseModel, Field, model_validator


class HealthDef(BaseModel):
    type: Literal["http", "tcp", "exec"]
    target: str
    timeout_s: int
    expect_status: int | None = None


class ServiceDef(BaseModel):
    role: str
    depends_on: List[str] = Field(default_factory=list)
    health: HealthDef | None = None


class RunnerDef(BaseModel):
    type: Literal["http", "exec"]
    target: str


class QualityDef(BaseModel):
    golden_set: str
    min_cases: int
    scorers: List[str]
    schedule_s: int
    runner: RunnerDef


class ObjectiveMetric(BaseModel):
    metric: str
    comparator: Literal["<", "<=", ">", ">=", "=="]
    threshold: float
    window_s: int
    weight: float


class ObjectivesDef(BaseModel):
    availability: List[ObjectiveMetric] = Field(default_factory=list)
    latency: List[ObjectiveMetric] = Field(default_factory=list)
    quality: List[ObjectiveMetric] = Field(default_factory=list)
    cost: List[ObjectiveMetric] = Field(default_factory=list)


class ToleranceDef(BaseModel):
    quality_drop_pct: float | None = None
    latency_increase_pct: float | None = None
    cost_increase_pct: float | None = None


class ReversibleStateDef(BaseModel):
    kind: Literal["git_directory", "git_file", "snapshot", "runtime_config"]
    path: str | None = None
    snapshot_cmd: str | None = None
    restore_cmd: str | None = None
    read: str | None = None
    write: str | None = None


class PermissionDef(BaseModel):
    allowed_actions: List[str] = Field(default_factory=list)
    forbidden_services: List[str] = Field(default_factory=list)
    max_risk_tier: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"


class TelemetryDef(BaseModel):
    otlp_endpoint: str
    semconv_version: str
    genai_instrumented: bool
    required_attributes: List[str]


class DependencyDef(BaseModel):
    id: str
    name: str
    version: str
    role_hint: str | None = None


class DebtTriggerDef(BaseModel):
    metric: str
    condition: str
    value: float


class DebtItemDef(BaseModel):
    repayment_action: str
    trigger: DebtTriggerDef
    max_age_s: int


class KavachManifest(BaseModel):
    services: Dict[str, ServiceDef]
    quality: QualityDef | None = None
    objectives: ObjectivesDef | None = None
    tolerance: ToleranceDef | None = None
    reversible_state: Dict[str, ReversibleStateDef] | None = None
    permissions: PermissionDef = Field(default_factory=PermissionDef)
    telemetry: TelemetryDef | None = None
    dependencies: List[DependencyDef] = Field(default_factory=list)
    debt: Dict[str, DebtItemDef] | None = None

    @model_validator(mode="after")
    def validate_objectives(self) -> 'KavachManifest':
        if self.objectives:
            if not self.objectives.availability and not self.objectives.quality:
                # Actually, CONTRACT C4 says: "At least one objective in availability and one in quality. 
                # An application declaring only availability objectives is conformant but cannot be protected 
                # against silent degradation, and the platform must say so at onboarding."
                # So we won't error here, but the checker will handle level assignment.
                pass
        return self
