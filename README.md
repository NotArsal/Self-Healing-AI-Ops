# Kavach: Autonomous Self-Healing Control Plane

Kavach is an autonomous self-healing control plane designed to detect, diagnose, and mitigate infrastructure and application faults in real-time. It leverages advanced LLM-driven Root Cause Analysis (RCA) via Ollama, zero-shot Task Negative Representation (TNR) safety gating via Laya, and an interactive Next.js console for operators to observe the autonomous pipelines.

## Key Capabilities
- **LLM-Driven RCA**: Uses Qwen/Llama running locally via Ollama to diagnose complex cascading failures (F01-F12 taxonomy).
- **Topology-Aware**: Incorporates a lightweight dependency graph to trace faults to their true root cause (e.g., distinguishing between a degraded API and a dead database).
- **TNR Safety Gate**: Evaluates the destructive probability of auto-generated remediation commands (e.g., `rm -rf`) using Laya. Includes a custom fine-tuning pipeline to calibrate Laya's thresholds to organizational policies.
- **Agentic State Graph**: Implemented with LangGraph, orchestrating the full lifecycle: Detect -> Diagnose -> Plan -> Gate -> Execute -> Verify -> Unwind.
- **Frontend Console**: A Next.js dashboard providing real-time visibility into incidents, remediation plans, and gate verdicts.

## Architecture
- **Control Plane**: FastAPI (Backend API), LangGraph (Workflow), Laya (Safety Gate), Ollama (RCA).
- **Console**: Next.js 15, React 19, Tailwind CSS.

## Getting Started
1. Start Ollama: `ollama serve`
2. Start the Control Plane: `cd apps/control-plane && uv run uvicorn kavach.main:app --port 8000`
3. Start the Console: `cd apps/console && pnpm dev`
4. Simulate Alerts: `cd apps/control-plane && uv run python simulate_alert.py`

## Project Status: Completed
All 13 core phases of the Kavach Self-Healing Platform have been successfully implemented and verified:
1. Scenario Framework & Schema Definition
2. State Graph Skeleton (LangGraph)
3. LLM RCA Integration
4. Simulated Execution & Rollback
5. TNR Safety Gate
6. Declarative Action Catalogue
7. Full F01-F09 Validation
8. External Evaluation
9. Laya Environment Sandbox
10. End-to-End Incident Pipeline
11. Real-Time Telemetry Webhooks
12. Knowledge Graph Context
13. Laya Fine-Tuning Pipeline
