"""The shape a generated repair must arrive in.

`apply_patch` is the one action where the model supplies content, so this
is the one schema where the decoder constraint carries real weight. The
lesson `rca/schema.py` records twice over applies with more force here:
asking a small model nicely does not work, constraining the decoder does.

WHAT IS CONSTRAINED AT THE DECODER, AND WHY EACH ONE
`target_path` is an ENUM of the files the manifest actually declares as
versioned. Not a string the model fills in. `patch_checks.check_paths`
would refuse an undeclared path anyway, but refusing a bad answer and
preventing one are different things, and the second is cheaper - this
project already spent ten runs on a model inventing `application_service`
for a field whose valid values were in the prompt.

`diff` stays a free string because a unified diff cannot be expressed in
JSON Schema. Everything about it is checked afterwards, deterministically,
by `patch_checks.evaluate`, and nothing is applied before `git apply
--check` agrees it still fits the file.

A FIELD `description` IS NOT A DECODER CONSTRAINT, AND WAS MEASURED NOT TO BE
The obvious move when a model gets a field wrong is to describe the field
better in the schema. It does nothing here. Ollama compiles `format` into a
GBNF grammar, and a grammar encodes which TOKENS are legal, not prose about
them - so a `description` never reaches the model at all. Measured on
2026-10-18: adding one telling the model the `--- a/` header was mandatory
changed the rate at which qwen2.5:7b-instruct emitted it from 1 in 3 to 0 in
5. The enum on `target_path` works because an enum IS expressible as a
grammar. The distinction is the whole reason this file calls out which
constraint lives where.

`rationale` is required and bounded. A patch an operator cannot read a
reason for is one they cannot approve, and `apply_patch` is HIGH tier so a
human always sees it.

WHAT IS DELIBERATELY NOT A FIELD
There is no `confidence` here. `rca/schema.py` has one because a diagnosis
is a claim about the world that can be more or less certain; a patch is a
proposal, and a model's confidence in its own prose is not evidence of
anything. The gate on this action is the six checks and the sandbox, not a
number the model chose.

There is no `apply_immediately`, no `skip_sandbox`, no severity - nothing
the model can set that influences whether its own output runs. Every such
decision is the deterministic layer's, which is the whole safety argument.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PatchProposal(BaseModel):
    """An LLM-authored unified diff against one declared file."""

    model_config = ConfigDict(extra="forbid")

    # A plain `str` on the model because the valid set is runtime data from
    # the manifest; narrowed to an enum at the DECODER by `ollama_schema`.
    target_path: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=600)
    diff: str = Field(min_length=1, max_length=4000)


def ollama_schema(declared_files: list[str]) -> dict[str, Any]:
    """JSON Schema for Ollama's `format`, with the path narrowed to an enum.

    `declared_files` are the versioned files that currently exist and have a
    pre-state witness. An empty list is a programming error rather than a
    permissive case: generating a patch with nowhere to write it is asking
    the model to produce something that cannot possibly be applied, and a
    schema with an empty enum would fail at the decoder anyway.
    """
    if not declared_files:
        raise ValueError(
            "no declared versioned files with a witness, so there is nothing "
            "a patch could target. Refusing to build a schema whose only "
            "valid answers are invalid"
        )
    schema = PatchProposal.model_json_schema()
    props = schema.get("properties", {})
    props["target_path"] = {
        "type": "string",
        "enum": sorted(declared_files),
        "description": "the file to patch; one of the declared versioned files",
    }
    schema["required"] = ["target_path", "rationale", "diff"]
    schema["additionalProperties"] = False
    return schema
