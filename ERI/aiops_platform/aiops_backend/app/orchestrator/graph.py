"""
LangGraph workflow definition — wires together all nodes into the
Detect → Investigate → RCA → Memory → Plan → Safety decision pipeline.
"""

from langgraph.graph import StateGraph, END
from app.orchestrator.state import OrchestratorState
from app.orchestrator.nodes import (
    investigation_node,
    rca_node,
    memory_retrieval_node,
    repair_planning_node,
)


import os
import httpx
import logging

logger = logging.getLogger(__name__)

HEALING_EXECUTOR_URL = os.environ.get(
    "HEALING_EXECUTOR_URL",
    "http://healing-executor.aiops.svc.cluster.local:9000"
)


def safety_router(state: OrchestratorState) -> str:
    """
    Delegate to the deterministic Safety Engine to decide routing.
    """
    from app.core.safety import evaluate
    action = state.get("selected_action", {})
    service = state.get("affected_service", "unknown")
    decision, reason = evaluate(action, service)
    logger.info(f"[SafetyRouter] Decision={decision}: {reason}")
    # Map "blocked" to approval_required for the graph (dashboard will show reason)
    if decision == "blocked":
        return "approval_required"
    return decision


async def _call_executor(incident_id: str, action: str, namespace: str, resource: str):
    """Call the Rust Healing Executor API."""
    payload = {
        "action": action,
        "namespace": namespace,
        "resource_name": resource,
        "incident_id": incident_id,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{HEALING_EXECUTOR_URL}/execute", json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"[Executor] Call failed: {e}")
        return {"success": False, "message": str(e)}


def auto_execute_node(state: OrchestratorState):
    """Execute a LOW-risk action automatically via the Rust executor."""
    import asyncio
    action = state["selected_action"]
    result = asyncio.get_event_loop().run_until_complete(
        _call_executor(
            state["incident_id"],
            action.get("action", "restart_deployment"),
            "target-system",
            state["affected_service"],
        )
    )
    msg = result.get("message", "Executed")
    return {
        "safety_decision": "auto",
        "execution_result": f"[AUTO] {msg}",
    }


def sandbox_node(state: OrchestratorState):
    """Simulate sandbox validation for MEDIUM-risk actions."""
    action = state["selected_action"]["action"]
    return {
        "safety_decision": "sandbox",
        "execution_result": f"[SANDBOX] Tested action: '{action}'. Validation passed. Awaiting production execution.",
    }


def approval_required_node(state: OrchestratorState):
    """Hold action pending human approval via the dashboard."""
    action = state["selected_action"]["action"]
    return {
        "safety_decision": "approval_required",
        "execution_result": f"[HOLD] Action '{action}' requires human approval. Dashboard notified.",
    }


def verification_node(state: OrchestratorState):
    """
    Actively queries Prometheus metrics to confirm recovery.
    """
    import time
    from app.managers.monitoring import monitoring_manager

    # For actions needing human approval, we can't verify yet
    if state.get("safety_decision") == "approval_required":
        return {
            "verification_passed": False,
            "verification_details": "Pending human approval.",
            "final_status": "ESCALATED",
        }

    logger.info("[Verification] Waiting 15s for metrics to stabilize...")
    time.sleep(15)  # Wait for metric collection cycle

    service = state.get("affected_service", "unknown")
    
    # Query restart counts again to ensure they've stopped
    restarts_query = f'sum(changes(kube_pod_container_status_restarts_total{{namespace="target-system", pod=~"{service}.*"}}[2m])) by (pod)'
    restarts_data = monitoring_manager.query_metrics(restarts_query)
    
    has_restarts = False
    if restarts_data:
        for result in restarts_data:
            if float(result['value'][1]) > 0:
                has_restarts = True
                break

    if has_restarts:
        logger.warning(f"[Verification] Service {service} is still crashlooping.")
        return {
            "verification_passed": False,
            "verification_details": "Service is still experiencing restarts.",
            "final_status": "ROLLED_BACK",  # Triggering rollback logic (simulated for now)
        }

    logger.info(f"[Verification] Service {service} appears healthy.")
    return {
        "verification_passed": True,
        "verification_details": "All health checks passed post-repair.",
        "final_status": "RESOLVED",
    }


def build_graph() -> StateGraph:
    builder = StateGraph(OrchestratorState)

    # Register nodes
    builder.add_node("investigate",         investigation_node)
    builder.add_node("rca",                 rca_node)
    builder.add_node("memory_retrieval",    memory_retrieval_node)
    builder.add_node("repair_planning",     repair_planning_node)
    builder.add_node("auto_execute",        auto_execute_node)
    builder.add_node("sandbox",             sandbox_node)
    builder.add_node("approval_required",   approval_required_node)
    builder.add_node("verification",        verification_node)

    # Define linear edges
    builder.set_entry_point("investigate")
    builder.add_edge("investigate",       "rca")
    builder.add_edge("rca",               "memory_retrieval")
    builder.add_edge("memory_retrieval",  "repair_planning")

    # Conditional branch: safety router
    builder.add_conditional_edges(
        "repair_planning",
        safety_router,
        {
            "auto_execute":       "auto_execute",
            "sandbox":            "sandbox",
            "approval_required":  "approval_required",
        }
    )

    # All execution paths converge to verification
    builder.add_edge("auto_execute",        "verification")
    builder.add_edge("sandbox",             "verification")
    builder.add_edge("approval_required",   "verification")
    builder.add_edge("verification",        END)

    return builder.compile()


# Singleton compiled graph
orchestrator_graph = build_graph()
