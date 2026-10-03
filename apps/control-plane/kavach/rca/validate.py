"""Deterministic validation of an LLM diagnosis. Fails closed.

The LLM proposes; this module decides whether the proposal may reach the
executor. Nothing here calls a model, and every rule is a plain comparison, so
the same diagnosis against the same evidence always produces the same verdict.

THE RULE THAT MATTERS MOST
The deterministic detector remains authoritative on whether the conditions for
a fault actually hold. The LLM's contribution is a cited, explained diagnosis -
not permission to act. If the model claims F06 while the deterministic evidence
says otherwise, the claim is rejected.

That is the whole defence against the failure mode the project is about:
SREGym found mitigation succeeds 22-62% of the time even when the diagnosis is
WRONG, because agents pattern-match a symptom to a fix that happens to work. A
confident wrong diagnosis that passes straight to a repair is how that happens.
Requiring the model to agree with independent deterministic evidence means a
plausible-but-wrong diagnosis cannot drive a write.

FAIL CLOSED, EVERY TIME
Any rule that cannot be evaluated - missing evidence, unparseable output, an
absent baseline - rejects. There is no path where uncertainty permits action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from kavach.detection import retrieval_collapse as rc
from kavach.rca.evidence import EvidenceFrame
from kavach.rca.schema import Diagnosis

# Repairs this slice can perform, per fault class. A diagnosis proposing
# anything else is rejected: the model may not name an action with no
# implementation, no inverse, or no tested rollback.
PERMITTED_REPAIR: dict[str, str] = {
    rc.FAULT_CLASS: "rollback_config",
}

# Only F06 is implemented. Every other catalogue class is a legitimate thing
# for the model to SAY - and an illegitimate thing to act on yet.
SUPPORTED_FAULT_CLASSES: frozenset[str] = frozenset({rc.FAULT_CLASS})

MIN_CITED_EVIDENCE = 2


class Outcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""

    def render(self) -> str:
        return f"  [{'ok' if self.passed else 'REJECT'}] {self.name}: {self.detail}"


@dataclass
class ValidationResult:
    outcome: Outcome
    checks: list[Check] = field(default_factory=list)
    approved_action: str | None = None
    rejection_reasons: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.outcome is Outcome.ACCEPTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": str(self.outcome),
            "approved_action": self.approved_action,
            "rejection_reasons": self.rejection_reasons,
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail}
                       for c in self.checks],
        }

    def render(self) -> str:
        head = f"Validation: {self.outcome}"
        if self.approved_action:
            head += f" -> {self.approved_action}"
        return "\n".join([head] + [c.render() for c in self.checks])


def validate(
    diagnosis: Diagnosis | None,
    frame: EvidenceFrame,
    deterministic: rc.Detection,
    confidence_threshold: float,
    declared_services: set[str] | None = None,
    parse_error: str = "",
) -> ValidationResult:
    """Decide whether a diagnosis may drive a repair. Pure function."""
    res = ValidationResult(outcome=Outcome.REJECTED)

    def reject(name: str, detail: str) -> None:
        res.checks.append(Check(name, False, detail))
        res.rejection_reasons.append(f"{name}: {detail}")

    def ok(name: str, detail: str = "") -> None:
        res.checks.append(Check(name, True, detail))

    # --- 1. the output parsed and validated at all
    if diagnosis is None:
        reject("schema_valid",
               parse_error or "LLM output was missing or failed schema validation")
        return res
    ok("schema_valid", "parsed and schema-validated")

    # --- 2. an honest non-answer is respected, not overridden
    if not diagnosis.is_actionable_claim:
        reject("actionable_claim",
               f"fault_class is {diagnosis.fault_class}, which is an honest "
               f"non-answer and must never reach execution (FR-11, FR-29)")
        return res
    ok("actionable_claim", f"fault_class {diagnosis.fault_class}")

    # --- 3. the class is one we can actually repair
    if diagnosis.fault_class not in SUPPORTED_FAULT_CLASSES:
        reject("fault_class_supported",
               f"{diagnosis.fault_class} has no implementation in this slice; "
               f"supported: {sorted(SUPPORTED_FAULT_CLASSES)}")
        return res
    ok("fault_class_supported", diagnosis.fault_class)

    # --- 4. confidence (FR-12)
    if diagnosis.confidence < confidence_threshold:
        reject("confidence_threshold",
               f"{diagnosis.confidence:.2f} < required {confidence_threshold:.2f}")
    else:
        ok("confidence_threshold",
           f"{diagnosis.confidence:.2f} >= {confidence_threshold:.2f}")

    # --- 5. every cited ID resolves to real collected evidence (FR-10)
    unknown = [e for e in diagnosis.evidence_ids if e not in frame.ids]
    if unknown:
        reject("citations_resolve",
               f"cited evidence that does not exist: {unknown}. A citation that "
               f"resolves to nothing is a fabricated justification")
    elif len(diagnosis.evidence_ids) < MIN_CITED_EVIDENCE:
        reject("citations_resolve",
               f"only {len(diagnosis.evidence_ids)} cited; at least "
               f"{MIN_CITED_EVIDENCE} required")
    else:
        ok("citations_resolve",
           f"{len(diagnosis.evidence_ids)} cited, all resolve: "
           f"{diagnosis.evidence_ids}")

    # --- 6. the service must be one the manifest declares
    if declared_services:
        if diagnosis.service not in declared_services:
            reject("service_declared",
                   f"{diagnosis.service!r} is not a declared service: "
                   f"{sorted(declared_services)}")
        else:
            ok("service_declared", diagnosis.service)

    # --- 7. the proposed repair must be the permitted one for this class
    expected_repair = PERMITTED_REPAIR.get(diagnosis.fault_class)
    if diagnosis.candidate_repair != expected_repair:
        reject("repair_permitted",
               f"proposed {diagnosis.candidate_repair!r}, but "
               f"{diagnosis.fault_class} may only use {expected_repair!r}")
    else:
        ok("repair_permitted", diagnosis.candidate_repair)

    # --- 8. THE CROSS-CHECK: the deterministic detector is authoritative
    if not deterministic.detected:
        reject("deterministic_agreement",
               f"the LLM claims {diagnosis.fault_class} but deterministic "
               f"detection returned {deterministic.verdict}. Independent "
               f"evidence does not support the claim, so it cannot drive a "
               f"repair")
    elif deterministic.fault_class != diagnosis.fault_class:
        reject("deterministic_agreement",
               f"LLM says {diagnosis.fault_class}, deterministic detection says "
               f"{deterministic.fault_class}")
    elif deterministic.service != diagnosis.service:
        reject("deterministic_agreement",
               f"LLM blames {diagnosis.service!r}, deterministic detection "
               f"blames {deterministic.service!r}")
    else:
        ok("deterministic_agreement",
           f"both agree: {diagnosis.fault_class} on {diagnosis.service}")

    # --- 9. the repair needs something to roll back TO
    baseline = frame.by_id("EV-B01")
    if baseline is None or baseline.value is None:
        reject("baseline_available",
               "no captured known-good value; a rollback with no recorded "
               "target would be a guess, not a rollback")
    else:
        ok("baseline_available", f"rerank_threshold {baseline.value}")

    # --- 10. the corpus must be intact; an empty corpus is a different fault
    corpus = frame.metric("corpus_chunks")
    if corpus is None:
        reject("corpus_intact", "corpus size unknown; cannot rule out a corpus fault")
    elif corpus <= 0:
        reject("corpus_intact",
               f"corpus is empty ({corpus}); a config rollback is the wrong repair")
    else:
        ok("corpus_intact", f"{int(corpus)} chunks")

    if res.rejection_reasons:
        return res

    res.outcome = Outcome.ACCEPTED
    res.approved_action = expected_repair
    return res
