from typing import Literal

from pydantic import BaseModel, Field, model_validator


class HealthDef(BaseModel):
    type: Literal["http", "tcp", "exec"]
    target: str
    timeout_s: int
    expect_status: int | None = None


class ServiceDef(BaseModel):
    role: str
    depends_on: list[str] = Field(default_factory=list)
    health: HealthDef | None = None


class RunnerDef(BaseModel):
    type: Literal["http", "exec"]
    target: str


class QualityDef(BaseModel):
    golden_set: str
    min_cases: int
    scorers: list[str]
    schedule_s: int
    runner: RunnerDef


class ObjectiveMetric(BaseModel):
    metric: str
    comparator: Literal["<", "<=", ">", ">=", "=="]
    threshold: float
    window_s: int
    weight: float


class ObjectivesDef(BaseModel):
    availability: list[ObjectiveMetric] = Field(default_factory=list)
    latency: list[ObjectiveMetric] = Field(default_factory=list)
    quality: list[ObjectiveMetric] = Field(default_factory=list)
    cost: list[ObjectiveMetric] = Field(default_factory=list)


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
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_services: list[str] = Field(default_factory=list)
    max_risk_tier: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"


class TelemetryDef(BaseModel):
    otlp_endpoint: str
    semconv_version: str
    genai_instrumented: bool
    required_attributes: list[str]


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
    services: dict[str, ServiceDef]
    quality: QualityDef | None = None
    objectives: ObjectivesDef | None = None
    tolerance: ToleranceDef | None = None
    reversible_state: dict[str, ReversibleStateDef] | None = None
    permissions: PermissionDef = Field(default_factory=PermissionDef)
    telemetry: TelemetryDef | None = None
    dependencies: list[DependencyDef] = Field(default_factory=list)
    debt: dict[str, DebtItemDef] | None = None

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
