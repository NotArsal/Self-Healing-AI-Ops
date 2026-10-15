from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field, field_validator

from kavach.scenarios.schema import Scenario


class RCAResponse(BaseModel):
    fault_class: str = Field(
        description="The fault class identifier alone, e.g. 'F01'. "
        "Use 'INSUFFICIENT_EVIDENCE' if the evidence does not distinguish one."
    )
    confidence: float = Field(description="Confidence score between 0.0 and 1.0.")

    @field_validator("confidence")
    @classmethod
    def _confidence_is_a_probability(cls, v: float) -> float:
        """Coerce a percentage, reject anything else out of range.

        The RCA bench observed this field returned as both 1.0 and 100.0 by the
        same model on the same prompt. The gate compares it against 0.8, so an
        unbounded value passes trivially while a 0..100 reading of 50 would
        escalate by accident. A value in (1, 100] is treated as a percentage;
        beyond that the model's output is not interpretable and is refused.
        """
        if 1.0 < v <= 100.0:
            return v / 100.0
        if 0.0 <= v <= 1.0:
            return v
        raise ValueError(f"confidence {v} is neither a probability nor a percentage")

    evidence_ids: list[str] = Field(
        description="IDs of the evidence items supporting this diagnosis."
    )
    rejected_alternatives: list[str] = Field(
        description="Other fault classes considered but rejected."
    )


def analyze_root_cause(
    scenario: Scenario,
    model_name: str = "qwen2.5:7b-instruct",
    app_roles: set[str] | None = None,
) -> RCAResponse:
    from kavach.catalogue.loader import load_catalogue
    from kavach.topology.graph import build_topology_graph

    llm = ChatOllama(
        model=model_name, temperature=0.0, base_url="http://127.0.0.1:11434"
    )
    structured_llm = llm.with_structured_output(RCAResponse)

    topology = build_topology_graph(scenario.services)
    topo_text = topology.describe_topology()

    catalogue = load_catalogue(app_roles=app_roles)
    applicable_faults = list(catalogue.faults.keys())

    # Candidates are named, not described by their detection signal. The previous
    # version of this prompt carried a rule per fault ("if you see
    # gen_ai_error_ratio -> output F01"), and every scenario's evidence contained
    # exactly the string its rule named, so the model performed a lookup this
    # prompt spelled out. It also injected a fabricated past incident stating the
    # answer outright. Measured accuracy was 100% and meant nothing; see
    # docs/MEASUREMENTS.md.
    candidates = "\n".join(
        f"    - {fc} ({catalogue.faults[fc].name or 'unnamed'})"
        for fc in applicable_faults
    )

    prompt = f"""
    You are an expert AI operations engineer performing Root Cause Analysis (RCA).

    Reason from the evidence to the most likely root cause.

    SYSTEM TOPOLOGY:
    {topo_text}

    CANDIDATE FAULT CLASSES (diagnose exactly one, or INSUFFICIENT_EVIDENCE):
{candidates}

    How to answer:
    - fault_class must be the bare identifier and nothing else, for example
      F05, not "F05 (connection pool exhaustion)".
    - Cite in evidence_ids the evidence IDs supporting your conclusion. Cite only
      IDs that appear below.
    - List in rejected_alternatives the candidates you considered and ruled out.
    - confidence is a probability between 0.0 and 1.0.
    - If several services report errors, use the SYSTEM TOPOLOGY to find the root
      cause: the service lowest in the dependency chain.
    - If the evidence is absent, ambiguous between candidates, or matches no
      candidate, answer INSUFFICIENT_EVIDENCE with low confidence. That is a
      correct answer, not a failure.

    Scenario ID: {scenario.id}
    Evidence:
    """
    if scenario.evidence:
        for ev in scenario.evidence:
            prompt += f"- ID: {ev.id} | Kind: {ev.kind} | Source: {ev.source} | Value: {ev.value} | Payload: {ev.payload}\n"
    else:
        prompt += "- None\n"

    # Past incidents arrive as ev-memory-* evidence items from the knowledge base
    # (see diagnose_node in graph/nodes.py), so they are already in the block
    # above. Nothing is synthesised here.

    from kavach.knowledge.context7 import query_docs_for_incident

    docs = query_docs_for_incident(scenario.fault_class, list(scenario.services.keys()))
    if docs:
        prompt += f"\n--- CONTEXT7 DOCUMENTATION EVIDENCE ---\n{docs}\n---------------------------------------\n"

    prompt += "\nOutput the structured RCA response."

    import logging

    logger = logging.getLogger(__name__)

    try:
        # In case Ollama's structured output struggles, we wrap with a try-except.
        response = structured_llm.invoke(prompt)
        if isinstance(response, RCAResponse):
            return response
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"Primary LLM ({model_name}) failed: {e}. Degrading to fallback model."
        )
        try:
            fallback_model = "qwen2.5:0.5b-instruct"
            llm_fallback = ChatOllama(
                model=fallback_model, temperature=0.0, base_url="http://127.0.0.1:11434"
            )
            structured_fallback = llm_fallback.with_structured_output(RCAResponse)
            fallback_response = structured_fallback.invoke(prompt)
            if isinstance(fallback_response, RCAResponse):
                return fallback_response
        except Exception as e2:  # noqa: BLE001
            logger.error(f"Fallback LLM also failed: {e2}")

    # Fallback if structure parsing fails silently or both LLMs fail
    return RCAResponse(
        fault_class="INSUFFICIENT_EVIDENCE",
        confidence=0.0,
        evidence_ids=[],
        rejected_alternatives=[],
    )
