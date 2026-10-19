"""The dumb closed loop — one fault, no intelligence.

    detect -> known-fault lookup -> prepare action -> execute -> verify
           -> resolved, or escalated

No LLM, no LangGraph, no decision model, no allow-list engine, no sandbox. The
plan step is a literal dict. That is deliberate: closing the loop cheaply
proves the mechanism, and it is also the non-LLM baseline that P4's RCA engine
has to beat on the same injections.

It lives here rather than in `graph/` because `graph/` is reserved for the
LangGraph implementation in P4, and putting a hand-rolled orchestrator there
would misrepresent what it is.

THE ONE RULE THIS FILE EXISTS TO ENFORCE
An incident is only `RESOLVED` if verification passed AND the corpus fingerprint
is unchanged. Anything else escalates. A loop that reports success on a failed
verification is a false-healing machine, which is the single worst outcome in
the whole design.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from kavach.audit.log import AuditLog
from kavach.detection import base as det
from kavach.detection import catalogue as detector_catalogue  # noqa: F401
from kavach.executor import catalogue  # noqa: F401 - registers the catalogue
from kavach.executor.base import Action, ActionError, registry
from kavach.executor.undo_stack import UndoStack
from kavach.rca.engine import RcaResult
from kavach.safety.engine import (
    ActionRequest,
    Decision,
    ProjectPolicy,
    SafetyEngine,
    Verdict,
)
from kavach.safety.writer_lock import LockBusyError, writer_lock
from kavach.target import TargetClient
from kavach.verification import fast

# The RCA stage the loop may be given: a callable taking the fast-verification
# result, the deterministic detection and the known-good baseline, and
# returning a diagnosis that has already been through validation.
#
# A plain Callable rather than a Protocol: the loop only ever calls it
# positionally, and a Protocol here would match on parameter NAMES, which makes
# every caller and test fixture restate them for no benefit.
RcaStage = Callable[
    [fast.FastVerificationResult, det.Detection, float | None], RcaResult
]

# An OPTIONAL progress sink: (stage, status, message). Added in P4 so the
# console can watch a run while it happens, because `run_once` is synchronous
# and otherwise reveals nothing until it returns.
#
# It is strictly a notification. Nothing in this module reads a return value,
# no branch depends on it, and `None` - the default - leaves the P2/P3 loop
# byte-identical. A callback that raises would take the healing path down with
# it, so every call site goes through `_notify`, which swallows.
LoopEvent = Callable[[str, str, str], None]

STAGES: tuple[str, ...] = (
    "detect", "evidence", "diagnose", "validate",
    "plan", "repair", "verify", "resolve",
)


def _notify(sink: LoopEvent | None, stage: str, status: str, message: str) -> None:
    """Fire one progress event. A broken sink must never break a heal.

    The suppression is deliberately total: observation is not the job, and a
    console that has gone away must not take an in-flight repair with it.
    """
    if sink is None:
        return
    with contextlib.suppress(Exception):
        sink(stage, status, message)


class IncidentStatus(StrEnum):
    DETECTED = "DETECTED"
    NO_FAULT = "NO_FAULT"
    HEALING = "HEALING"
    # The gate permitted the action but not unattended: SIMULATION, APPROVAL,
    # a HIGH tier, or a sandbox requirement. A plan exists and nothing was
    # written, which is a different outcome from both success and escalation.
    AWAITING = "AWAITING_APPROVAL"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


# The plan step. A literal mapping from fault class to repair, with no reasoning
# involved. P4 replaces the lookup, not the executor.
def known_faults() -> dict[str, str]:
    """Fault class -> repair action, asked of the detector registry.

    This used to be a module-level dict literal naming one RAG fault and one
    RAG repair, which is what made the generic orchestrator a RAG orchestrator
    (`ARCHITECTURE.md` §1.4). It is now derived, so adding a fault class is a
    line in `detection/catalogue.py` and nothing here changes.
    """
    return det.registry.known_faults()


@dataclass
class Incident:
    incident_id: str
    project: str
    detected_at: str = ""
    resolved_at: str = ""
    status: IncidentStatus = IncidentStatus.DETECTED
    fault_class: str | None = None
    fault_name: str | None = None
    service: str | None = None
    detection: dict[str, Any] = field(default_factory=dict)
    diagnosed_by: str = ""            # "deterministic" | "llm_rca"
    rca: dict[str, Any] = field(default_factory=dict)
    planned_action: str | None = None
    decision: dict[str, Any] = field(default_factory=dict)
    action: dict[str, Any] = field(default_factory=dict)
    unwind: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)
    corpus_before: dict[str, Any] = field(default_factory=dict)
    corpus_after: dict[str, Any] = field(default_factory=dict)
    outcome: str = ""
    escalation_reason: str = ""

    @property
    def resolved(self) -> bool:
        return self.status is IncidentStatus.RESOLVED

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["status"] = str(self.status)
        return d

    def render(self) -> str:
        lines = [
            f"Incident {self.incident_id}  [{self.status}]",
            f"  project    {self.project}",
            f"  detected   {self.detected_at}",
        ]
        if self.fault_class:
            lines.append(f"  fault      {self.fault_class} {self.fault_name} "
                         f"on {self.service}")
        if self.diagnosed_by:
            lines.append(f"  diagnosed  {self.diagnosed_by}")
        if self.rca:
            d = self.rca.get("diagnosis") or {}
            lines.append(
                f"  rca        {d.get('fault_class')} conf={d.get('confidence')} "
                f"cited={d.get('evidence_ids')} "
                f"({self.rca.get('latency_s')}s, {self.rca.get('model')})"
            )
            lines.append(f"  validation {(self.rca.get('validation') or {}).get('outcome')}")
        if self.decision:
            lines.append(f"  permit     {self.decision.get('verdict')} "
                         f"({self.decision.get('risk_tier')}, "
                         f"{self.decision.get('mode')})")
        if self.planned_action:
            lines.append(f"  action     {self.planned_action} "
                         f"(risk {self.action.get('risk_tier', '?')})")
            lines.append(f"  inverse    {self.action.get('inverse_settings')}")
            lines.append(f"  idem key   {self.action.get('idempotency_key')}")
            lines.append(f"  cfg hash   {self.action.get('config_hash_before')} -> "
                         f"{self.action.get('config_hash_after')}")
        if self.verification:
            lines.append(f"  verified   {'PASS' if self.verification.get('passed') else 'FAIL'}"
                         f"  ({self.verification.get('pass_rate', 0):.0%} quality, "
                         f"{self.verification.get('total_s', 0)}s)")
        lines.append(f"  corpus     {self.corpus_before} -> {self.corpus_after}")
        if self.outcome:
            lines.append(f"  outcome    {self.outcome}")
        if self.escalation_reason:
            lines.append(f"  escalated  {self.escalation_reason}")
        return "\n".join(lines)


def _corpus(promql: Callable[[str, str], float | None], prometheus_url: str) -> dict[str, Any]:
    return {
        "chunks": promql(prometheus_url, "ragapp_corpus_chunks"),
        "files": promql(prometheus_url, "ragapp_corpus_files"),
    }


def run_once(
    client: TargetClient,
    prometheus_url: str,
    fast_set_path: str | Path,
    promql: Callable[[str, str], float | None],
    baseline_value: float | None,
    project: str = "simple-rag",
    incident_id: str | None = None,
    rca: RcaStage | None = None,
    on_event: LoopEvent | None = None,
    safety: SafetyEngine | None = None,
    policy: ProjectPolicy | None = None,
    audit: AuditLog | None = None,
    approved_from: str = "",
    repair_values: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
) -> Incident:
    """One pass of detect -> heal -> verify.

    `promql` is injected so the loop can be exercised without Prometheus.

    `on_event` is OPTIONAL and observation-only (see `LoopEvent`). It changes no
    decision and no return value; omitted, this function behaves exactly as it
    did in P2/P3.

    `safety` and `policy` are the P5 gate. Supplied, every mutation passes
    `permit()` first and the mode decides whether it may run unattended.
    Omitted, the loop runs with the P2/P3 posture: one known action, invoked
    explicitly, which is what it did before the gate existed. `audit` records
    the decision and the outcome to the hash-chained log.

    `approved_from` is the incident a human approved. It re-detects and
    re-prepares from scratch — the world may have moved — and the approval
    travels into `permit()` as evidence, not as a mode override. Everything
    except the mode and confidence gates is therefore evaluated again.

    `repair_values` maps an action name to the one declared value its builder
    needs: the captured baseline threshold for `rollback_config`, the declared
    backup endpoint for `switch_llm_endpoint`. It exists because that value is
    workload configuration, not something the orchestrator can derive — and
    because a second repair made `baseline_value` alone wrong as a parameter
    name for "the thing this repair aims at". `baseline_value` remains the
    fallback so every P2/P3 caller still works unchanged.

    `baseline` is the whole newest baseline capture, handed to the detectors.
    `F08` compares the live control-interface settings against the `settings`
    snapshot in it, which is a source no metric can supply. Omitted, F08
    reports INSUFFICIENT_EVIDENCE rather than clearing a system it cannot see.

    `rca` is OPTIONAL. Omitted, this is the P2 deterministic loop unchanged -
    the reference baseline, and the fallback if RCA is unavailable. Supplied, an
    LLM diagnosis is produced and must additionally survive deterministic
    validation before the same repair runs.

    Note what RCA does NOT do: it never widens what can execute. Deterministic
    detection still has to find the fault, the plan still comes from the same
    literal dict, and the repair is still the same single action. RCA adds a
    gate and an explanation; it cannot authorise anything on its own.
    """
    inc = Incident(
        incident_id=incident_id or f"INC-{uuid.uuid4().hex[:8].upper()}",
        project=project,
        detected_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )

    # Corpus fingerprint FIRST, before detection even runs, so the
    # unchanged-corpus guarantee covers the whole incident and not merely the
    # execute-to-verify window. A corpus that moved during detection would
    # otherwise slip through.
    inc.corpus_before = _corpus(promql, prometheus_url)

    # --- DETECT: metrics plus the fast set, no LLM
    _notify(on_event, "detect", "started",
            f"detection started for {project}; running the 3-case fast set and "
            f"reading retrieval metrics")
    pre_fast = fast.run(client, fast_set_path)
    # Every registered detector, not one imported by name. `run_all` returns a
    # single verdict and refuses to choose when two detectors claim at once.
    #
    # `Signals` carries the target and the baseline as well as Prometheus,
    # because F08's signal is a config comparison rather than a metric. A
    # detector given a source it does not need simply ignores it.
    detection = det.run_all(
        det.registry.specs(),
        det.Signals(
            prometheus_url=prometheus_url,
            promql=promql,
            client=client,
            baseline=baseline or {},
        ),
        pre_fast.passed,
        pre_fast.pass_rate,
    )
    inc.detection = detection.to_dict()
    inc.detection["pre_verification"] = pre_fast.to_dict()

    if detection.verdict is det.Verdict.NO_FAULT:
        _notify(on_event, "detect", "ok",
                f"no fault: fast set {pre_fast.pass_rate:.0%}, "
                f"verdict {detection.verdict}")
        inc.status = IncidentStatus.NO_FAULT
        inc.outcome = "no fault detected; nothing to do"
        return inc

    if detection.verdict is det.Verdict.INSUFFICIENT_EVIDENCE:
        _notify(on_event, "detect", "failed",
                "detection returned INSUFFICIENT_EVIDENCE; escalating without "
                "proposing a repair")
        inc.status = IncidentStatus.ESCALATED
        inc.escalation_reason = (
            "detection returned INSUFFICIENT_EVIDENCE; no repair is proposed from "
            "an undiagnosed fault: " + "; ".join(detection.reasons)
        )
        inc.outcome = "escalated without acting"
        return inc

    inc.fault_class = detection.fault_class
    inc.fault_name = detection.fault_name
    inc.service = detection.service
    _notify(on_event, "detect", "ok",
            f"detected {detection.fault_class} {detection.fault_name} on "
            f"{detection.service}; fast set {pre_fast.pass_rate:.0%}")

    # --- DIAGNOSE (optional): LLM RCA, gated by deterministic validation.
    # The LLM proposes; validate.py decides. A rejected diagnosis escalates
    # rather than falling back to the deterministic plan, because silently
    # ignoring a refused diagnosis would make the gate decorative.
    if rca is not None:
        _notify(on_event, "diagnose", "started",
                "collecting evidence and requesting an LLM diagnosis")
        rca_result = rca(pre_fast, detection, baseline_value)
        if rca_result.diagnosis is not None:
            d = rca_result.diagnosis
            _notify(on_event, "diagnose", "ok",
                    f"diagnosis returned: {d.fault_class} {d.fault_name} on "
                    f"{d.service}, confidence {d.confidence:.2f} (uncalibrated), "
                    f"citing {len(d.evidence_ids)} evidence items")
        else:
            _notify(on_event, "diagnose", "failed",
                    f"no usable diagnosis: {rca_result.error or 'unparseable output'}")
        inc.rca = rca_result.to_dict()
        inc.diagnosed_by = "llm_rca"
        if audit:
            # BEFORE the rejection branch below, which returns early.
            #
            # Until 2026-10-19 the first audit row any incident wrote was
            # `permit`, so an incident the cross-check refused reached the
            # log not at all - and those are precisely the incidents this
            # project's central claim is made of. "No wrong diagnosis has
            # ever driven a repair" was evidenced by harness JSON while the
            # append-only hash-chained log, which exists to evidence exactly
            # that kind of claim, said nothing. Found when an API rebuild
            # discarded the in-memory incident records and the refusals had
            # left no other trace.
            answer = rca_result.diagnosis
            audit.append(
                "diagnose", incident_id=inc.incident_id,
                deterministic_class=detection.fault_class or "",
                model=rca_result.model or "",
                model_class=(answer.fault_class if answer else ""),
                confidence=(answer.confidence if answer else None),
                approved=bool(rca_result.approved),
                detail="; ".join(rca_result.rejection_reasons)
                       or rca_result.error or "accepted",
            )
        n_checks = len(rca_result.validation.checks) if rca_result.validation else 0
        if not rca_result.approved:
            _notify(on_event, "validate", "failed",
                    f"validation REJECTED the diagnosis ({n_checks} checks run): "
                    + ("; ".join(rca_result.rejection_reasons)
                       or rca_result.error or "no reason recorded"))
            inc.status = IncidentStatus.ESCALATED
            reasons = rca_result.rejection_reasons
            inc.escalation_reason = (
                "LLM diagnosis rejected by deterministic validation: "
                + ("; ".join(reasons) if reasons else rca_result.error)
            )
            inc.outcome = "escalated without acting; target left as found"
            # Complete the record even on the early return; an empty
            # corpus_after reads like a mutation when nothing happened.
            inc.corpus_after = inc.corpus_before
            return inc
        _notify(on_event, "validate", "ok",
                f"validation ACCEPTED the diagnosis; all {n_checks} deterministic "
                f"checks passed, approved action "
                f"{rca_result.approved_action!r}")
        # Use the validator's approved action, never the model's raw proposal.
        inc.planned_action = rca_result.approved_action
        if rca_result.diagnosis is not None:
            inc.fault_class = rca_result.diagnosis.fault_class
            inc.fault_name = rca_result.diagnosis.fault_name
            inc.service = rca_result.diagnosis.service
    else:
        # --- PLAN: dict lookup, no reasoning
        inc.diagnosed_by = "deterministic"
        planned = known_faults().get(detection.fault_class or "")
        if planned is None:
            _notify(on_event, "plan", "failed",
                    f"no known repair for {detection.fault_class}")
            inc.status = IncidentStatus.ESCALATED
            inc.escalation_reason = f"no known repair for {detection.fault_class}"
            return inc
        inc.planned_action = planned

    _notify(on_event, "plan", "ok",
            f"repair proposed: {inc.planned_action}")

    # Whichever path chose it, the action must be one the registry knows.
    # Asking the registry rather than comparing against a RAG constant is what
    # stops this orchestrator being a RAG orchestrator (ARCHITECTURE.md §1.4).
    if not inc.planned_action or not registry.knows(inc.planned_action):
        _notify(on_event, "plan", "failed",
                f"planned action {inc.planned_action!r} is not registered")
        inc.status = IncidentStatus.ESCALATED
        inc.escalation_reason = (
            f"planned action {inc.planned_action!r} is not registered; "
            f"known actions: {registry.names()}"
        )
        return inc

    # --- PREPARE: build the action and capture its pre-state. No writes yet.
    inc.status = IncidentStatus.HEALING
    _notify(on_event, "repair", "started",
            f"capturing pre-state for {inc.planned_action}")
    try:
        # The value this specific repair aims at, in order of authority:
        #   1. the detector's own `repair_target`, when only it can know -
        #      F08's rollback restores exactly the settings IT diagnosed as
        #      drifted, which nothing before detection could have resolved
        #   2. the manifest/baseline value for this action, resolved up front
        #   3. the baseline threshold, which is what every pre-P6 caller passes
        target_value: Any = detection.repair_target
        if target_value is None:
            target_value = (repair_values or {}).get(
                inc.planned_action, baseline_value
            )
        action: Action = registry.build(
            inc.planned_action, inc.incident_id, client, target_value
        )
    except ActionError as exc:
        _notify(on_event, "repair", "failed", f"action could not be prepared: {exc}")
        inc.status = IncidentStatus.ESCALATED
        inc.escalation_reason = f"action could not be prepared: {exc}"
        inc.outcome = "escalated; target left as found"
        return inc

    # --- GATE: permit() decides. The loop proposes, it does not authorise.
    if safety is not None and policy is not None:
        diagnosis = (inc.rca.get("diagnosis") or {}) if inc.rca else {}
        request = ActionRequest(
            action=action.name,
            incident_id=inc.incident_id,
            service=inc.service or "",
            fault_class=inc.fault_class or "",
            params=dict(getattr(action, "target_settings", {}) or {}),
            compose_project=policy.compose_project,
            has_inverse=bool(getattr(action, "inverse_settings", None)),
            confidence=diagnosis.get("confidence"),
            diagnosis_class=str(diagnosis.get("fault_class") or ""),
            operator_approved=approved_from,
        )
        decision: Decision = safety.permit(request, policy)
        inc.decision = decision.to_dict()
        if audit:
            audit.append("permit", incident_id=inc.incident_id,
                         **decision.to_dict())

        if decision.denied:
            _notify(on_event, "gate", "failed",
                    f"permit DENIED {action.name}: {'; '.join(decision.reasons)}")
            inc.status = IncidentStatus.ESCALATED
            inc.escalation_reason = (
                f"denied by the safety engine: {'; '.join(decision.reasons)}"
            )
            inc.outcome = "escalated without acting; target left as found"
            inc.corpus_after = inc.corpus_before
            return inc

        # A sandbox verdict whose sandbox has ALREADY run and passed.
        #
        # `permit()` returns REQUIRE_SANDBOX to mean "this may not go to
        # production until a clone has agreed". For `apply_patch` the clone
        # ran during `prepare()`, because `ARCHITECTURE.md` §6.2.1
        # constraint 4 makes a sandbox result a precondition of the proposal
        # rather than a later step - no human should be asked to approve an
        # untested diff. So by the time the verdict is read, the condition
        # it names is already satisfied, and stopping here would mean a
        # patch could never reach production however many times it passed.
        #
        # Asked of the ACTION, not of its name. An action that ran no
        # sandbox has no `sandbox_passed`, reads as None, and falls through
        # to the await below exactly as before - which is every MEDIUM
        # action in AUTONOMOUS, so this adds no path for them.
        #
        # For HIGH this is reachable only after a human approval, because
        # an unapproved HIGH action returns REQUIRE_APPROVAL in every mode
        # including AUTONOMOUS (`safety/engine.py`). Approval plus a passing
        # clone, and nothing less, is what writes a generated patch.
        if (decision.verdict is Verdict.REQUIRE_SANDBOX
                and getattr(action, "sandbox_passed", None) is True):
            _notify(on_event, "gate", "ok",
                    f"{action.name} passed its sandbox before the gate saw "
                    f"it; promoting to production")
        elif decision.verdict is not Verdict.ALLOW_AUTO:
            # SIMULATION, APPROVAL, a HIGH tier, a below-threshold confidence,
            # or a MEDIUM action needing the sandbox. All of them stop here:
            # the plan and its dry-run diff are the output, and nothing is
            # written. This is what makes SIMULATION the safe default rather
            # than a label (docs/decisions/0006).
            _notify(on_event, "gate", "ok",
                    f"permit returned {decision.verdict} for {action.name}; "
                    f"no write performed")
            inc.status = IncidentStatus.AWAITING
            proposal = action.to_dict()
            inc.outcome = (
                f"{decision.verdict}: planned {action.name} "
                f"{proposal.get('inverse_settings', {})} -> "
                f"{proposal.get('requested_settings', {})}, not executed"
            )
            inc.action = action.to_dict()
            inc.corpus_after = inc.corpus_before
            return inc

        _notify(on_event, "gate", "ok",
                f"permit ALLOW_AUTO for {action.name} "
                f"({decision.risk_tier}, {policy.mode})")

    # --- EXECUTE: one writer, inverse on the stack BEFORE the mutation.
    stack = UndoStack(inc.incident_id)
    lock_project = policy.name if policy else project
    try:
        with writer_lock.hold(lock_project, inc.incident_id):
            stack.push(action)
            if audit:
                # The payload ALREADY carries incident_id and action - the
                # protocol calls to_dict() "the audit record", so it is the
                # whole row. Naming them again collided on both keys and raised
                # TypeError, and it went unnoticed because nothing reached this
                # line until permit() first returned ALLOW_AUTO.
                audit.append("execute_start", **action.to_dict())
            action.execute(client)
    except LockBusyError as exc:
        _notify(on_event, "repair", "failed", str(exc))
        inc.status = IncidentStatus.ESCALATED
        inc.escalation_reason = str(exc)
        inc.outcome = "escalated without acting; another writer holds the target"
        inc.corpus_after = inc.corpus_before
        return inc
    except ActionError as exc:
        _notify(on_event, "repair", "failed", f"action failed: {exc}")
        inc.status = IncidentStatus.ESCALATED
        inc.escalation_reason = f"action failed: {exc}"
        inc.outcome = "escalated; target left as found"
        return inc

    if safety is not None:
        safety.record_execution(
            ActionRequest(action=action.name, incident_id=inc.incident_id,
                          service=inc.service or "",
                          fault_class=inc.fault_class or "")
        )
    inc.action = action.to_dict()
    if audit:
        audit.append("execute_done", **action.to_dict())
    _notify(on_event, "repair", "ok",
            f"{action.name} executed; inverse recorded and on the undo stack")

    # --- VERIFY: the approved fast path only. Never the 40-case evaluator.
    _notify(on_event, "verify", "started",
            "verification started: health probe and the 3 fast-set cases")
    post_fast = fast.run(client, fast_set_path)
    inc.verification = post_fast.to_dict()
    inc.corpus_after = _corpus(promql, prometheus_url)

    applied_ok, applied_detail = action.verify_applied(client)
    scope_ok, scope_detail = action.unchanged_elsewhere(client)
    inc.verification["repair_applied"] = {"ok": applied_ok, "detail": applied_detail}
    inc.verification["scope_respected"] = {"ok": scope_ok, "detail": scope_detail}

    corpus_ok = inc.corpus_before == inc.corpus_after

    problems: list[str] = []
    if not post_fast.passed:
        problems.append("fast verification did not pass after the repair")
    if not applied_ok:
        problems.append(applied_detail)
    if not scope_ok:
        problems.append(scope_detail)
    if not corpus_ok:
        problems.append(
            f"corpus fingerprint changed: {inc.corpus_before} -> {inc.corpus_after}"
        )

    if problems:
        _notify(on_event, "verify", "failed", "; ".join(problems))
        # The repair ran and did not work, so the undo stack unwinds in reverse
        # and every inverse is VERIFIED against its pre-state witness. Applying
        # an inverse is not the same as the prior state being back, and
        # reporting a clean rollback over a target left in a third state would
        # be worse than not rolling back at all.
        _notify(on_event, "rollback", "started",
                f"verification failed; unwinding {stack.depth} action(s)")
        report = stack.unwind(client)
        inc.unwind = report.to_dict()
        if audit:
            audit.append("unwind", incident_id=inc.incident_id, **report.to_dict())
        _notify(on_event, "rollback", "ok" if report.clean else "failed",
                f"unwound {report.restored}/{report.attempted}, "
                f"verified against the pre-state witness"
                + ("" if report.clean else f"; FAILURES: {'; '.join(report.failures)}"))

        inc.status = IncidentStatus.ESCALATED
        inc.escalation_reason = "; ".join(problems)
        inc.outcome = (
            "NOT resolved - repair executed, verification failed, prior state "
            + ("restored and verified" if report.clean
               else "NOT fully restored: " + "; ".join(report.failures))
        )
        return inc

    _notify(on_event, "verify", "ok",
            f"verification passed: health ok, fast set {post_fast.pass_rate:.0%} "
            f"in {post_fast.total_s:.1f}s, repair applied, scope respected, "
            f"corpus unchanged")
    inc.status = IncidentStatus.RESOLVED
    inc.resolved_at = datetime.now(UTC).isoformat(timespec="seconds")
    if audit:
        audit.append("resolved", incident_id=inc.incident_id,
                     action=action.name, verification=inc.verification)
    record = action.to_dict()
    requested = record.get("requested_settings") or {}
    inverse = record.get("inverse_settings") or {}
    inc.outcome = (
        f"resolved: {action.name} applied {inverse} -> {requested}"
        if requested else f"resolved: {action.name} applied"
    )
    return inc
