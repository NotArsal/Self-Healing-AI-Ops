from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from kavach.scenarios.schema import Scenario


class RCAResponse(BaseModel):
    fault_class: str = Field(
        description="The classified fault, e.g. F01. Use 'INSUFFICIENT_EVIDENCE' if uncertain."
    )
    confidence: float = Field(description="Confidence score between 0.0 and 1.0.")
    evidence_ids: list[str] = Field(
        description="IDs of the evidence items supporting this diagnosis."
    )
    rejected_alternatives: list[str] = Field(
        description="Other fault classes considered but rejected."
    )


def analyze_root_cause(
    scenario: Scenario, model_name: str = "llama3.2:latest"
) -> RCAResponse:
    llm = ChatOllama(model=model_name, temperature=0.0, base_url="http://127.0.0.1:11434")
    structured_llm = llm.with_structured_output(RCAResponse)

    prompt = f"""
    You are an expert AI operations engineer performing Root Cause Analysis (RCA).
    Review the following incident scenario evidence and classify the fault.
    
    Fault Classes Catalogue:
    - F01: Provider Outage (Indicators: high error ratio, 503 errors, gen_ai_error_ratio)
    - F02: Provider Latency (Indicators: high provider_latency_ms, upstream request timeout, 504 errors)
    - F03: Crash-Loop (Indicators: high pod_restart_count, crash-loop status, panic nil pointer)
    - F04: Cache Poisoning (Indicators: serving stale malformed prompt from cache, high cache_hit_ratio but bad quality)
    - F05: Pool Exhaustion (Indicators: Timeout waiting for connection from pool, db_connection_timeouts)
    - F06: Retrieval Collapse (Indicators: search timeout, missing_contexts)
    - F07: Prompt Regression (Indicators: quality_score drops, hallucination_rate increases, prompt_health regressed)
    - F08: Config Regression (Indicators: KeyError: missing feature toggle flag, config_errors)
    - F09: Token Blowout (Indicators: 429 Too Many Requests, token_usage spikes)
    - INSUFFICIENT_EVIDENCE: Cannot confidently classify.
    
    Scenario ID: {scenario.id}
    Evidence:
    """
    if scenario.evidence:
        for ev in scenario.evidence:
            prompt += f"- ID: {ev.id} | Kind: {ev.kind} | Source: {ev.source} | Value: {ev.value} | Payload: {ev.payload}\n"
    else:
        prompt += "- None\n"

    prompt += "\nOutput the structured RCA response."

    # In case Ollama's structured output struggles, we could wrap with a retry or fallback.
    # But for MVP, we rely on `langchain_ollama` structured output.
    response = structured_llm.invoke(prompt)

    # Type hinting check for invoke which returns BaseModel depending on config
    if isinstance(response, RCAResponse):
        return response

    # Fallback if structure parsing fails silently
    return RCAResponse(
        fault_class="INSUFFICIENT_EVIDENCE",
        confidence=0.0,
        evidence_ids=[],
        rejected_alternatives=[],
    )
