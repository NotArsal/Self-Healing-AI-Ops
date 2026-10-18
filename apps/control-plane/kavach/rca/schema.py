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
#
# THIS IS THE OUTPUT VOCABULARY, SO AN OMISSION HERE IS A GAG, NOT A TYPO.
# Ollama's structured-output schema is generated from this model, so a repair
# missing from this list is one the model is PHYSICALLY UNABLE to name. When
# F01 landed, `switch_llm_endpoint` was registered in the executor, allowed in
# the manifest, and named in the prompt's repair table - but absent here. Over
# ten live runs the model diagnosed F01 correctly every time, cited real
# evidence, and proposed "none" in all ten, because "none" was the only legal
# value left to it. 0 of 10 usable diagnoses, and nothing in the prompt could
# have fixed it.
#
# Kept as an explicit Literal rather than generated from the registry so that
# mypy and the published JSON schema stay readable. `tests/test_rca.py`
# asserts it equals the executor registry plus "none", so adding an action
# without widening this fails the suite loudly instead of silently gagging the
# model.
CandidateRepair = Literal[
    "rollback_config", "switch_llm_endpoint", "rollback_prompt", "none",
]

# Registered actions the model is deliberately NOT allowed to name.
#
# `apply_patch` is registered and buildable, so the invariant above would
# normally demand it appear in `CandidateRepair`. It must not, and the reason
# is `validate.py` rule 7: a diagnosis's repair must be the ONE repair
# permitted for the class it named. `apply_patch` is the permitted repair for
# no class - F01, F06, F07 and F08 each have a deterministic repair that
# works. Listing it would therefore add a value the validator rejects for
# every possible class: a trap rather than a capability, and exactly the kind
# of "sound diagnosis that can never authorise a repair" this file already
# has scar tissue about.
#
# `apply_patch` is reached a different way. The diagnosis names a class; the
# operator or the engine then asks `rca/patch_engine.py` for a patch FOR that
# class. The model never chooses to patch; it is asked to write one.
#
# This set is not an escape hatch for the invariant. Anything in it is an
# action no diagnosis can propose, which has to be true by design rather than
# by oversight, and `tests/test_rca.py` still fails for any registered action
# that is neither nameable nor listed here.
NOT_MODEL_PROPOSABLE: frozenset[str] = frozenset({"apply_patch"})


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


def ollama_schema(declared_services: set[str] | None = None) -> dict[str, Any]:
    """JSON Schema for Ollama's `format`, generated from the model itself.

    Generated rather than hand-written so the decoder constraint and the
    validation constraint cannot diverge.

    `declared_services` narrows the `service` property to an enum of the names
    this project actually declares. The field stays a plain `str` on the model
    because the valid set is runtime data from the manifest, not something a
    static type can know - but the DECODER can be told, and telling it is the
    difference between refusing a bad answer and preventing one.

    This was learned the hard way twice. `candidate_repair` was a Literal
    missing `switch_llm_endpoint`, so the model was unable to name F01's repair
    and proposed "none" in ten of ten runs. Then with that fixed it returned
    `service: "application_service"` in ten of ten - an invented name that
    rule 2 of the prompt explicitly forbids and that the validator duly
    rejected, for 0 usable diagnoses out of 10. Asking a 3B model nicely does
    not work; constraining the decoder does.
    """
    schema = Diagnosis.model_json_schema()
    # Ollama wants a self-contained schema; Pydantic emits $defs references,
    # which it handles, but required/additionalProperties must be explicit for
    # the constraint to actually bind.
    schema["additionalProperties"] = False
    if declared_services:
        props = schema.get("properties", {})
        if "service" in props:
            # Replace rather than add: a string with both maxLength and enum
            # is satisfiable, but the enum alone is the whole constraint.
            props["service"] = {
                "type": "string",
                "enum": sorted(declared_services),
                "description": "The service that owns the fault. Must be one "
                               "of these exact names.",
            }
    return schema
