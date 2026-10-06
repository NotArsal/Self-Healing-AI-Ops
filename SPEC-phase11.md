# Spec: Phase 11 - Real-Time Telemetry & Alert Triage

## Objective
Wire the Laya-powered Triage Router (built in Phase 9) into a live webhook endpoint that can ingest incoming alerts, filter out noise, categorize them, and autonomously trigger the Kavach incident workflow.

## Current State
- `apps/control-plane/kavach/triage/router.py` correctly classifies strings into `database`, `network`, `application`, etc. using Laya.
- However, there is no HTTP ingestion endpoint for external monitoring systems (like Prometheus or Datadog) to post alerts to.

## Target State
1. **Alert Webhook**: A new FastAPI endpoint `/api/v1/alerts/webhook` that accepts standard JSON alert payloads.
2. **Laya Triage**: The endpoint passes the alert text to `triage.router.classify_alert()`.
3. **Trigger Workflow**: If the alert is actionable (e.g., categorized as `application` or `database` rather than `noise` or `unknown`), the backend maps it to a known incident scenario and dynamically calls `/incidents/run` (or directly triggers `execute_graph_background`).
4. **Dashboard visibility**: The `apps/console` frontend should reflect the new incident automatically via SSE (which was built in Phase 4).

## Architecture Details
- Endpoint: `POST /api/v1/alerts/webhook`
- Payload Example:
  ```json
  {
    "status": "firing",
    "alerts": [
      {
        "labels": {"alertname": "HighLatency", "service": "api"},
        "annotations": {"description": "API latency is > 5s"}
      }
    ]
  }
  ```
- Triage Logic: If Laya classifies it as `application`, trigger scenario `F10` (Safe command test) to prove the end-to-end flow from Alert -> Laya Triage -> Qwen RCA -> Laya TNR Gate -> Executor.

## Success Criteria
- Sending a `curl` POST request to the webhook with a raw text description of an alert successfully starts the `F10` scenario if it's actionable.
- Sending a noisy/irrelevant alert does not trigger an incident.
