"""The diagnosis contract (FR-10, FR-11).

Pydantic v2 with `extra="forbid"`, so a model that invents a field is rejected
rather than silently partially understood. The same models generate the JSON
Schema handed to Ollama, so the constraint the decoder enforces and the
constraint validation enforces cannot drift apart.

What the model is allowed to say is deliberately narrow. It selects from a
closed set of fault classes, cites evidence by ID, and states a confidence. It
does not get a free-text field that anything downstream reads as an
instruction, and it cannot name an action outside the known repair vocabulary.
`reasoning` exists for a human to audit, and nothing branches on it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The eight catalogue IDs, plus the two non-fault outcomes. No F04 - retired
# (PRD §6.1). Offering the full catalogue rather than only F06 is deliberate:
# a model given one choice will always pick it, which would make the diagnosis
# meaningless and the validation untestable.
FaultClass = Literal[
    "F01", "F02", "F03", "F05", "F06", "F07", "F08", "F09",
    "UNKNOWN", "INSUFFICIENT_EVIDENCE",
]

# Repairs Kavach can actually perform today. The model may not propose anything
# else, so it cannot ask for an action with no implementation or no inverse.
CandidateRepair = Literal["rollback_config", "none"]


class RejectedAlternative(BaseModel):
    """A fault class considered and ruled out, with the reason (FR-10)."""

    model_config = ConfigDict(extra="forbid")

    fault_class: FaultClass
    reason: str = Field(min_length=1, max_length=500)


class Diagnosis(BaseModel):
    """A structured root-cause claim. Proposal only - it executes nothing."""

    model_config = ConfigDict(extra="forbid")

    fault_class: FaultClass
    fault_name: str = Field(min_length=1, max_length=80)
    service: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0.0, le=1.0)
    # REQUIRED, with a minimum of two, and deliberately no default.
    #
    # It was optional at first, and a real llama3.2 run cited EV-M01/EV-M02/
    # EV-M06 inside `reasoning` while leaving this array empty - every other
    # field correct. A constrained decoder is free to skip an optional field,
    # and no amount of prompting reliably fixes that. Making it required with
    # minItems=2 puts the requirement in the grammar, so the decoder must emit
    # citations rather than be asked nicely to.
    evidence_ids: list[str] = Field(min_length=2, max_length=20)
    reasoning: str = Field(min_length=1, max_length=2000)
    candidate_repair: CandidateRepair
    rejected_alternatives: list[RejectedAlternative] = Field(
        default_factory=list, max_length=9
    )

    @field_validator("evidence_ids")
    @classmethod
    def ids_are_unique(cls, v: list[str]) -> list[str]:
        """Citing the same item three times is not three pieces of evidence."""
        if len(set(v)) != len(v):
            raise ValueError("evidence_ids contains duplicates")
        return v

    @field_validator("service")
    @classmethod
    def service_is_a_bare_name(cls, v: str) -> str:
        s = v.strip()
        if not s or any(c.isspace() for c in s):
            raise ValueError("service must be a single service name")
        return s

    @property
    def is_actionable_claim(self) -> bool:
        """True only for a real fault class. UNKNOWN and INSUFFICIENT_EVIDENCE
        are honest non-answers and must never reach execution (FR-29)."""
        return self.fault_class not in ("UNKNOWN", "INSUFFICIENT_EVIDENCE")


def ollama_schema() -> dict[str, Any]:
    """JSON Schema for Ollama's `format`, generated from the model itself.

    Generated rather than hand-written so the decoder constraint and the
    validation constraint cannot diverge.
    """
    schema = Diagnosis.model_json_schema()
    # Ollama wants a self-contained schema; Pydantic emits $defs references,
    # which it handles, but required/additionalProperties must be explicit for
    # the constraint to actually bind.
    schema["additionalProperties"] = False
    return schema
