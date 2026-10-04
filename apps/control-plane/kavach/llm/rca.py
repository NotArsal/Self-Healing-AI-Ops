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
    Review the following incident scenario evidence and classify the fault STRICTLY based on the rules below.
    
    CRITICAL RULES - Match the evidence to the EXACT class below:
    - If you see 'error ratio' or 'gen_ai_error_ratio' -> output F01
    - If you see 'provider_latency_ms' or '504' or 'timeout' (unless db/search) -> output F02
    - If you see 'pod_restart_count' or 'panic' -> output F03
    - If you see 'cache' or 'stale malformed prompt' -> output F04
    - If you see 'connection from pool' or 'db_connection_timeouts' -> output F05
    - If you see 'search timeout' or 'missing_contexts' -> output F06
    - If you see 'hallucination_rate' or 'quality_score' (without cache issues) -> output F07
    - If you see 'feature toggle flag' or 'config_errors' -> output F08
    - If you see '429' or 'token_usage' -> output F09
    
    If none match, output INSUFFICIENT_EVIDENCE.
    
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
