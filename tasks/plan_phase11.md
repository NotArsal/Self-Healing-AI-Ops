# Implementation Plan: Phase 11 - Alert Triage Integration

## Overview
Connect the `classify_alert` Laya module to a new FastAPI webhook route, enabling end-to-end autonomous healing triggered by raw alerts.

## Task List

### Phase 1: Webhook Endpoint
- [ ] Task 1: Create `apps/control-plane/kavach/api/routes/alerts.py`.
- [ ] Task 2: Implement `POST /api/v1/alerts/webhook` accepting a JSON payload.
- [ ] Task 3: Call `triage.router.classify_alert` on the incoming alert text.
- [ ] Task 4: If classified as actionable (e.g. `application`), programmatically trigger the `F10` scenario workflow.

### Phase 2: Wiring
- [ ] Task 5: Register the `alerts` router in `apps/control-plane/kavach/main.py`.

### Phase 3: Verification
- [ ] Task 6: Write a script `simulate_alert.py` to POST a mock Prometheus alert to the webhook.
- [ ] Task 7: Verify that the incident starts, executes safely, and mitigates automatically.
