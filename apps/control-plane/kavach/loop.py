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

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from kavach.detection import retrieval_collapse as rc
from kavach.executor.config_rollback import (
    ActionError,
    ConfigRollback,
    build_rollback_for_retrieval_collapse,
)
from kavach.target import TargetClient
from kavach.verification import fast


class IncidentStatus(StrEnum):
    DETECTED = "DETECTED"
    NO_FAULT = "NO_FAULT"
    HEALING = "HEALING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


# The plan step. A literal mapping from fault class to repair, with no reasoning
# involved. P4 replaces the lookup, not the executor.
KNOWN_FAULTS: dict[str, str] = {
    rc.FAULT_CLASS: "rollback_config",
}


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
    planned_action: str | None = None
    action: dict[str, Any] = field(default_factory=dict)
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
    baseline_rerank_threshold: float | None,
    project: str = "simple-rag",
    incident_id: str | None = None,
) -> Incident:
    """One pass of detect -> heal -> verify.

    `promql` is injected so the loop can be exercised without Prometheus.
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
    pre_fast = fast.run(client, fast_set_path)
    metrics = rc.collect(prometheus_url, promql)
    detection = rc.evaluate(metrics, pre_fast.passed, pre_fast.pass_rate)
    inc.detection = detection.to_dict()
    inc.detection["pre_verification"] = pre_fast.to_dict()

    if detection.verdict is rc.Verdict.NO_FAULT:
        inc.status = IncidentStatus.NO_FAULT
        inc.outcome = "no fault detected; nothing to do"
        return inc

    if detection.verdict is rc.Verdict.INSUFFICIENT_EVIDENCE:
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

    # --- PLAN: dict lookup, no reasoning
    planned = KNOWN_FAULTS.get(detection.fault_class or "")
    if planned is None:
        inc.status = IncidentStatus.ESCALATED
        inc.escalation_reason = f"no known repair for {detection.fault_class}"
        return inc
    inc.planned_action = planned

    # --- EXECUTE
    inc.status = IncidentStatus.HEALING
    try:
        action: ConfigRollback = build_rollback_for_retrieval_collapse(
            inc.incident_id, client, baseline_rerank_threshold
        )
        action.execute(client)
    except ActionError as exc:
        inc.status = IncidentStatus.ESCALATED
        inc.escalation_reason = f"action failed: {exc}"
        inc.outcome = "escalated; target left as found"
        return inc
    inc.action = action.to_dict()

    # --- VERIFY: the approved fast path only. Never the 40-case evaluator.
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
        # The repair ran but did not work. The honest outcome is escalation, and
        # the inverse is left recorded so the state can be unwound deliberately.
        inc.status = IncidentStatus.ESCALATED
        inc.escalation_reason = "; ".join(problems)
        inc.outcome = "NOT resolved - repair executed but verification failed"
        return inc

    inc.status = IncidentStatus.RESOLVED
    inc.resolved_at = datetime.now(UTC).isoformat(timespec="seconds")
    restored = action.target_settings.get("rerank_threshold")
    was = action.inverse_settings.get("rerank_threshold")
    inc.outcome = (
        f"resolved: rerank_threshold {was} -> {restored} (restored from baseline)"
        if restored is not None else "resolved"
    )
    return inc
