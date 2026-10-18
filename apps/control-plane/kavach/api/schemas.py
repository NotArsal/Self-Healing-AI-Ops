"""Typed response models — the contract the console's client is generated from.

These exist for one reason: the control plane's internals are dataclasses whose
`to_dict()` returns `dict[str, Any]`, and a route typed as `dict[str, Any]`
generates a useless TypeScript type. With real models, `make gen-client`
produces types that break `tsc` when a field changes, which is the whole point
of generating rather than hand-writing the client.

They mirror the existing `to_dict()` shapes and add nothing. Every model is
built with `model_validate` over the dict the dataclass already produced, so a
field added upstream appears here by changing one model and nothing else.

WHAT IS DELIBERATELY NOT HERE
`RcaResult.raw_response` - the unparsed model output. It is already absent from
`RcaResult.to_dict()`, and it stays out of the browser: the structured
`diagnosis` carries everything a human needs to audit, and shipping raw
generations to a UI is how prompt text and half-formed reasoning leak into a
screenshot. `reasoning` IS included - it is a bounded, schema-validated audit
field, not chain-of-thought.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from kavach.config import Mode


class Probe(BaseModel):
    """A named boolean outcome with its explanation. Never colour alone: the
    console renders `ok` as text and an icon, never as a hue by itself."""

    ok: bool
    detail: str = ""


# --- verification -----------------------------------------------------------


class CaseOut(BaseModel):
    case_id: str
    passed: bool
    keyword_present: bool
    non_refusal: bool
    sources_block: bool
    latency_s: float
    error: str = ""


class VerificationOut(BaseModel):
    passed: bool
    health_ok: bool
    health_detail: str = ""
    quality_ok: bool
    within_budget: bool
    pass_rate: float
    total_s: float
    budget_s: int
    cases: list[CaseOut]
    # Present only after a repair; absent on the pre-repair detection run.
    repair_applied: Probe | None = None
    scope_respected: Probe | None = None


# --- detection --------------------------------------------------------------


class DetectionEvidenceOut(BaseModel):
    kind: str
    source: str
    value: str
    expected: str = ""
    supports_fault: bool


class DetectionOut(BaseModel):
    verdict: str
    fault_class: str | None = None
    fault_name: str | None = None
    service: str | None = None
    reasons: list[str]
    evidence: list[DetectionEvidenceOut]
    pre_verification: VerificationOut | None = None


# --- RCA --------------------------------------------------------------------


class EvidenceItemOut(BaseModel):
    """One citable evidence item. `value` is stringified on the way out so the
    generated TypeScript type is `string` rather than `unknown` - the console
    renders every payload as mono text anyway (`DESIGN_SYSTEM.md` §7.4)."""

    eid: str
    kind: str
    name: str
    value: str
    expected: str = ""
    note: str = ""


class RejectedAlternativeOut(BaseModel):
    fault_class: str
    reason: str


class DiagnosisOut(BaseModel):
    fault_class: str
    fault_name: str
    service: str
    confidence: float
    evidence_ids: list[str]
    reasoning: str = ""
    candidate_repair: str
    rejected_alternatives: list[RejectedAlternativeOut]


class ValidationCheckOut(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class ValidationOut(BaseModel):
    outcome: str
    approved_action: str | None = None
    rejection_reasons: list[str]
    checks: list[ValidationCheckOut]


class RcaOut(BaseModel):
    at: str
    model: str
    latency_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    approved: bool
    approved_action: str | None = None
    error: str = ""
    diagnosis: DiagnosisOut | None = None
    validation: ValidationOut | None = None
    evidence: list[EvidenceItemOut]
    evidence_problems: list[str]
    evidence_collected_at: str = ""
    # Stated on the wire, not left to the frontend to remember. The console
    # labels the number uncalibrated; the backend says so too, so a second
    # client cannot quietly present it as a probability.
    confidence_is_calibrated: Literal[False] = False


# --- action -----------------------------------------------------------------


class ActionOut(BaseModel):
    incident_id: str
    action: str
    risk_tier: str
    idempotency_key: str
    # For a config repair these are setting names and values; for
    # `rollback_prompt` they are filenames and content DIGESTS, never prompt
    # text. Both shapes fit because both are "what this action writes" and
    # "what undoes it", which is the only thing the gate and the console need.
    requested_settings: dict[str, float | int | str | bool | None]
    inverse_settings: dict[str, float | int | str | bool | None]
    config_hash_before: str = ""
    config_hash_after: str = ""
    # Added 2026-10-17 with F07, and the reason is worth recording: this
    # schema was shaped entirely around `ConfigRollback`, so the first action
    # that was not one had its whole record silently truncated on the wire.
    # The live harness caught it because it asserts on what the API returns
    # rather than on what the action object holds.
    #
    # `ROADMAP.md` P6 asks that a new fault class change nothing in the core.
    # F07 needed no change to the loop, the detector seam, the safety engine
    # or the schema the model answers in - and needed this one. The seam held
    # where it was built and was missing here, which is a more useful result
    # than claiming zero.
    #
    # Optional with defaults, so a `ConfigRollback` record is unchanged.
    restored_files: list[str] = Field(default_factory=list)
    bytes_written: dict[str, int] = Field(default_factory=dict)
    prompts_dir: str = ""
    executed: bool = False
    reverted: bool = False
    prepared_at: str = ""
    executed_at: str = ""
    error: str = ""


# --- incident ---------------------------------------------------------------


class CorpusOut(BaseModel):
    chunks: float | None = None
    files: float | None = None


class IncidentSummary(BaseModel):
    """The history table row (`DESIGN_SYSTEM.md` §7.3)."""

    incident_id: str
    project: str
    status: str
    detected_at: str = ""
    resolved_at: str = ""
    fault_class: str | None = None
    fault_name: str | None = None
    service: str | None = None
    diagnosed_by: str = ""
    outcome: str = ""


class SafetyCheckOut(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class DecisionOut(BaseModel):
    """What `permit()` decided, and why. The approval dialog reads this."""

    verdict: str
    action: str = ""
    risk_tier: str = ""
    mode: str = ""
    reasons: list[str]
    checks: list[SafetyCheckOut]
    at: str = ""


class UnwindOut(BaseModel):
    """What happened when the undo stack unwound. `clean` is the one that
    matters: an inverse that ran is not the same as prior state restored."""

    attempted: int
    restored: int
    clean: bool
    failures: list[str]


class IncidentOut(IncidentSummary):
    model_config = ConfigDict(extra="ignore")

    escalation_reason: str = ""
    planned_action: str | None = None
    detection: DetectionOut | None = None
    rca: RcaOut | None = None
    decision: DecisionOut | None = None
    action: ActionOut | None = None
    unwind: UnwindOut | None = None
    awaiting_approval: bool = False
    verification: VerificationOut | None = None
    corpus_before: CorpusOut | None = None
    corpus_after: CorpusOut | None = None
    corpus_unchanged: bool | None = None


# --- system health ----------------------------------------------------------


class Dependency(BaseModel):
    name: str
    ok: bool
    detail: str = ""
    # Shown so the operator can tell Kavach's direct Ollama path from the
    # target's proxied one. Confusing the two is how an F01 injection looks
    # like a broken diagnostician.
    endpoint: str = ""


class SystemOut(BaseModel):
    kavach_version: str
    # The mode `permit()` will actually apply, read from the target's manifest
    # - NOT `settings.default_mode`, which is only the fallback for a project
    # with no readable manifest. Reporting the default here was a P4 leftover
    # that showed SIMULATION on a project whose manifest says APPROVAL.
    mode: Mode
    # True since P5: `permit()` exists and reads the mode before anything is
    # written. The dependency row below says so when the manifest is readable,
    # and says the opposite when it is not.
    mode_is_enforced: bool = True
    project: str
    target_path: str = ""
    compose_project: str = ""
    rerank_threshold: float | None = None
    config_hash: str = ""
    corpus: CorpusOut | None = None
    dependencies: list[Dependency]
    loop_running: bool = False
    running_incident_id: str = ""


# --- preflight --------------------------------------------------------------


class PreflightCheckOut(BaseModel):
    name: str
    passed: bool
    skipped: bool
    status: str
    detail: str = ""
    remediation: str = ""


class PreflightOut(BaseModel):
    project: str
    passed: bool
    blocking_count: int
    checks: list[PreflightCheckOut]
    ran_at: str = ""
    error: str = ""


# --- events -----------------------------------------------------------------


class EventOut(BaseModel):
    seq: int
    at: str
    incident_id: str = ""
    stage: str
    status: str
    message: str


class RunStarted(BaseModel):
    incident_id: str
    started_at: str
    mode: Mode
    rca_enabled: bool
    approved_from: str = ""


class ModeOut(BaseModel):
    """The operating mode, and whether it is now actually enforced."""

    mode: Mode
    enforced: bool
    manifest_mode: Mode
    overridden: bool
    allowed_actions: list[str]
    denied_mutations: list[str]
    confidence_threshold: float


class ModeChange(BaseModel):
    mode: Mode


class RejectRequest(BaseModel):
    # Required, and non-empty: a rejection without a reason teaches nobody
    # anything, and the knowledge base is built from exactly these.
    reason: str = Field(min_length=3, max_length=2000)


class FleetMetrics(BaseModel):
    """The aggregates the console cannot compute from memory.

    Every rate is nullable on purpose. A zero MTTR reads as "instant", which is
    the opposite of "no data", and a dashboard must be able to tell them apart.
    """

    available: bool
    incidents: int
    resolved: int
    escalated: int
    awaiting: int
    auto_healed: int
    mttr_seconds: float | None = None
    repair_success_rate: float | None = None
    unavailable_reason: str = ""


class AuditRow(BaseModel):
    at: str = ""
    incident_id: str = ""
    actor: str = ""
    event: str = ""
    hash: str = ""
    prev: str = ""


class AuditOut(BaseModel):
    rows: list[AuditRow]
    chain_intact: bool
    broken_at: int | None = None
    detail: str = ""


def to_evidence_value(value: Any) -> str:
    """One stringifier, so every evidence payload renders the same way."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return str(value)
