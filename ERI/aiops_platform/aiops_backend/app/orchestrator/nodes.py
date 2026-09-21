"""
LangGraph workflow nodes — each is a pure function that receives the
OrchestratorState, performs its task (calling Gemini, querying metrics,
querying memory, etc.) and returns a partial state update dict.
"""

import os
import logging
import json
from typing import Dict, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from app.orchestrator.state import OrchestratorState
from app.managers.monitoring import monitoring_manager
from app.memory.store import retrieve_similar_incidents

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Shared LLM instance (Gemini Flash for speed)
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0.1
)


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: Investigation
# ─────────────────────────────────────────────────────────────────────────────

def investigation_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Gather evidence: metrics, recent logs, and Kubernetes events
    for the affected service. Returns a brief summary of each.
    """
    logger.info(f"[Investigation] Starting for {state['affected_service']}")
    service = state["affected_service"]

    # Query Prometheus for CPU and memory
    cpu_data = monitoring_manager.query_metrics(
        f'avg(rate(container_cpu_usage_seconds_total{{pod=~"{service}.*"}}[5m])) * 100'
    )
    mem_data = monitoring_manager.query_metrics(
        f'avg(container_memory_working_set_bytes{{pod=~"{service}.*"}}) / 1024 / 1024'
    )

    cpu_str = f"{round(float(cpu_data[0]['value'][1]), 2)}%" if cpu_data else "unavailable"
    mem_str = f"{round(float(mem_data[0]['value'][1]), 1)} MiB" if mem_data else "unavailable"

    metrics_summary = (
        f"Service: {service} | CPU: {cpu_str} | Memory: {mem_str} | "
        f"Failure type: {state['failure_type']}"
    )

    # Placeholder for log summary (will expand with Loki in a later iteration)
    logs_summary = f"Recent logs for {service} show repeated {state['failure_type']} events."

    # Placeholder Kubernetes events
    k8s_events = f"Pod {service} had unexpected restarts. Event stream captured."

    logger.info(f"[Investigation] metrics={metrics_summary}")
    return {
        "metrics_summary": metrics_summary,
        "logs_summary": logs_summary,
        "k8s_events": k8s_events,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: RCA / Hypothesis Generation
# ─────────────────────────────────────────────────────────────────────────────

def rca_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Ask Gemini to generate ranked hypotheses with confidence scores
    based on the evidence gathered during investigation.
    """
    logger.info("[RCA] Generating hypotheses with Gemini")
    prompt = f"""
You are an expert Site Reliability Engineer performing Root Cause Analysis.

Incident Details:
- Service: {state['affected_service']}
- Failure type: {state['failure_type']}
- Severity: {state['severity']}
- Metrics: {state['metrics_summary']}
- Logs: {state['logs_summary']}
- K8s Events: {state['k8s_events']}

Generate 3 ranked hypotheses for the root cause. 
Respond ONLY in this JSON format (no markdown):
[
  {{"hypothesis": "...", "confidence": 0.0, "evidence": "..."}},
  {{"hypothesis": "...", "confidence": 0.0, "evidence": "..."}},
  {{"hypothesis": "...", "confidence": 0.0, "evidence": "..."}}
]
"""
    try:
        response = llm.invoke(prompt)
        hypotheses = json.loads(response.content.strip())
        top = max(hypotheses, key=lambda h: h["confidence"])
        logger.info(f"[RCA] Top hypothesis: {top['hypothesis']} ({top['confidence']})")
        return {"hypotheses": hypotheses, "top_hypothesis": top["hypothesis"]}
    except Exception as e:
        logger.error(f"[RCA] Failed: {e}")
        fallback = [{"hypothesis": "Unknown root cause", "confidence": 0.1, "evidence": str(e)}]
        return {"hypotheses": fallback, "top_hypothesis": "Unknown root cause"}


# ─────────────────────────────────────────────────────────────────────────────
# Node 3: Memory Retrieval
# ─────────────────────────────────────────────────────────────────────────────

def memory_retrieval_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Query pgvector for similar past incidents to inform repair planning.
    Uses a simple embedding of the top hypothesis text.
    Uses a placeholder embedding (768-dim zero vector) until the embedding
    model is integrated in a later iteration.
    """
    logger.info("[Memory] Retrieving similar past incidents")
    # Placeholder: real embedding would use Gemini text-embedding-004 model
    dummy_embedding = [0.0] * 768
    similar = retrieve_similar_incidents(dummy_embedding, limit=3)
    if similar:
        logger.info(f"[Memory] Found {len(similar)} similar incidents")
    else:
        logger.info("[Memory] No similar incidents found yet.")
    return {"similar_incidents": similar}


# ─────────────────────────────────────────────────────────────────────────────
# Node 4: Repair Planning
# ─────────────────────────────────────────────────────────────────────────────

def repair_planning_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Ask Gemini to propose concrete, ranked repair actions with risk
    metadata, taking past incidents into account.
    """
    logger.info("[RepairPlanning] Generating repair candidates")
    memory_context = ""
    if state.get("similar_incidents"):
        memory_context = "Past similar incidents context:\n" + "\n".join(
            f"- INC {inc['id']}: {inc['failure_type']} → successful action: {inc.get('successful_action', 'unknown')}"
            for inc in state["similar_incidents"]
        )

    prompt = f"""
You are an SRE designing a safe recovery plan for a Kubernetes incident.

Root cause hypothesis: {state['top_hypothesis']}
Service: {state['affected_service']}
{memory_context}

Propose up to 3 ranked repair actions, ordered safest first.
Respond ONLY in this JSON format (no markdown):
[
  {{
    "action": "...",
    "risk": "LOW|MEDIUM|HIGH",
    "expected_effect": "...",
    "rollback": "..."
  }}
]
"""
    try:
        response = llm.invoke(prompt)
        candidates = json.loads(response.content.strip())
        selected = candidates[0]  # Default: safest first
        logger.info(f"[RepairPlanning] Selected action: {selected['action']} (risk={selected['risk']})")
        return {"repair_candidates": candidates, "selected_action": selected}
    except Exception as e:
        logger.error(f"[RepairPlanning] Failed: {e}")
        fallback = [{"action": "Restart affected service", "risk": "LOW", "expected_effect": "Clear transient failure", "rollback": "Re-deploy previous version"}]
        return {"repair_candidates": fallback, "selected_action": fallback[0]}
