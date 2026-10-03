"""The RCA engine: evidence -> LLM -> schema -> deterministic validation.

Orchestration only. It holds no judgement of its own: the LLM proposes, the
validator in `validate.py` decides, and this module just moves data between
them and records what happened.

Returns an RcaResult in every case, including every failure case. The engine
never raises for a bad model response, because a raise in the healing path
would be an unhandled fault in the component that handles faults - the failure
has to be data the loop can act on.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from kavach.detection import retrieval_collapse as rc
from kavach.llm.client import LlmError, LlmResponse, OllamaClient
from kavach.rca import validate as policy
from kavach.rca.evidence import EvidenceFrame
from kavach.rca.schema import Diagnosis, ollama_schema

PROMPT_PATH = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "diagnose.txt"

SYSTEM = (
    "You are a precise reliability diagnostician. You answer only with a JSON "
    "object matching the schema you are given. You never execute anything. "
    "Returning INSUFFICIENT_EVIDENCE when the evidence is inconclusive is a "
    "correct answer, not a failure."
)


@dataclass
class RcaResult:
    """What RCA concluded, and whether it is allowed to drive a repair."""

    diagnosis: Diagnosis | None = None
    validation: policy.ValidationResult | None = None
    evidence: EvidenceFrame | None = None
    deterministic: rc.Detection | None = None
    model: str = ""
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_response: str = ""
    error: str = ""
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    @property
    def approved(self) -> bool:
        """True only if a diagnosis survived every deterministic check."""
        return bool(self.validation and self.validation.accepted)

    @property
    def approved_action(self) -> str | None:
        return self.validation.approved_action if self.validation else None

    @property
    def rejection_reasons(self) -> list[str]:
        """Why it was refused. Empty when approved, never None."""
        return list(self.validation.rejection_reasons) if self.validation else []

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "model": self.model,
            "latency_s": round(self.latency_s, 2),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "approved": self.approved,
            "approved_action": self.approved_action,
            "error": self.error,
            "diagnosis": self.diagnosis.model_dump() if self.diagnosis else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "deterministic": self.deterministic.to_dict() if self.deterministic else None,
        }

    def render(self) -> str:
        lines = [f"RCA ({self.model}, {self.latency_s:.1f}s)"]
        if self.error:
            lines.append(f"  ERROR {self.error}")
        if self.diagnosis:
            d = self.diagnosis
            lines += [
                f"  fault_class       {d.fault_class} ({d.fault_name})",
                f"  service           {d.service}",
                f"  confidence        {d.confidence:.2f}",
                f"  candidate_repair  {d.candidate_repair}",
                f"  cited             {', '.join(d.evidence_ids) or '(none)'}",
                f"  reasoning         {d.reasoning[:180]}",
            ]
            for alt in d.rejected_alternatives:
                lines.append(f"  ruled out         {alt.fault_class}: {alt.reason[:90]}")
        if self.validation:
            lines.append("")
            lines.append(self.validation.render())
        return "\n".join(lines)


def build_prompt(frame: EvidenceFrame, prompt_path: Path | None = None) -> str:
    template = (prompt_path or PROMPT_PATH).read_text(encoding="utf-8")
    if "{evidence}" not in template:
        raise RuntimeError("prompt template is missing the {evidence} slot")
    return template.replace("{evidence}", frame.render())


LlmCall = Callable[[str, str, dict[str, Any]], LlmResponse]


def diagnose(
    frame: EvidenceFrame,
    deterministic: rc.Detection,
    confidence_threshold: float,
    llm: OllamaClient | None = None,
    llm_call: LlmCall | None = None,
    declared_services: set[str] | None = None,
    prompt_path: Path | None = None,
) -> RcaResult:
    """Run RCA over a collected evidence frame.

    `llm_call` is injectable so tests exercise the schema and validation paths
    with recorded responses and never touch a model (AGENTS.md: no model calls
    in CI).
    """
    result = RcaResult(evidence=frame, deterministic=deterministic)

    if llm_call is None:
        if llm is None:
            result.error = "no LLM client or call provided"
            result.validation = policy.validate(
                None, frame, deterministic, confidence_threshold,
                declared_services, parse_error=result.error,
            )
            return result
        llm_call = llm.structured

    prompt = build_prompt(frame, prompt_path)
    schema = ollama_schema()

    # --- the model call. Any failure becomes a rejection, never an exception.
    try:
        response = llm_call(SYSTEM, prompt, schema)
    except LlmError as exc:
        result.error = f"LLM call failed: {exc}"
        result.validation = policy.validate(
            None, frame, deterministic, confidence_threshold,
            declared_services, parse_error=result.error,
        )
        return result

    result.model = response.model
    result.latency_s = response.latency_s
    result.prompt_tokens = response.prompt_tokens
    result.completion_tokens = response.completion_tokens
    result.raw_response = response.raw

    # --- schema validation. Malformed output fails closed here.
    try:
        payload = response.parsed()
    except LlmError as exc:
        result.error = str(exc)
        result.validation = policy.validate(
            None, frame, deterministic, confidence_threshold,
            declared_services, parse_error=result.error,
        )
        return result

    try:
        result.diagnosis = Diagnosis.model_validate(payload)
    except ValidationError as exc:
        # Includes an invented field, a fault class outside the catalogue, a
        # confidence outside 0..1, duplicate citations - all rejected.
        result.error = f"diagnosis failed schema validation: {exc.error_count()} error(s)"
        result.validation = policy.validate(
            None, frame, deterministic, confidence_threshold,
            declared_services, parse_error=f"{result.error}: {exc.errors()[:3]}",
        )
        return result

    # --- deterministic policy decides
    result.validation = policy.validate(
        result.diagnosis, frame, deterministic, confidence_threshold,
        declared_services,
    )
    return result
