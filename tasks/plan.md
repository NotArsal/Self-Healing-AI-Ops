# Implementation Plan: Phase 9 - Laya Integration

## Overview
Integrate the local, non-autoregressive `laya` decision engine into Kavach as the "System 1" nervous system. This will add a TNR (Trust, Negotiate, Resolve) safety gate, fast alert triage, log noise reduction, and post-execution verification to complement Qwen's heavy RCA reasoning.

## Architecture Decisions
- **Execution Model**: Laya runs locally in-process via the `laya` Python package, requiring no external API calls, executing inference locally in ~33ms.
- **TNR First**: We will implement the TNR Safety Gate first (Phase 1), as it is the most critical block for autonomous execution, followed by Triage, Filtering, and Verification.

## Task List

### Phase 1: Foundation (The TNR Safety Gate)
- [ ] Task 1: Install `laya` and build `tnr_gate.py`
- [ ] Task 2: Build `executor.py` connected to TNR

### Checkpoint: Foundation
- [ ] Safe commands (e.g. `systemctl status`) auto-execute
- [ ] Destructive commands (e.g. `rm -rf`) correctly blocked
- [ ] Review with human

### Phase 2: Alert Triage & Routing
- [ ] Task 3: Build `triage/router.py`

### Checkpoint: Alert Triage
- [ ] Incoming generic alerts correctly classified as `database`, `network`, etc.

### Phase 3: Log Filtering & Post-Execution Verification
- [ ] Task 4: Build `evaluation/log_filter.py`
- [ ] Task 5: Integrate Post-Execution Verification

### Checkpoint: Complete
- [ ] All 4 Laya use cases integrated
- [ ] Ready for End-to-End Autonomous Remediation Test

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Laya zero-shot accuracy is low on custom operational logs | Med | We have explicitly scoped the option to fine-tune Laya using the `laya_finetune_typed_decisions_mps.py` notebook. |
| Executor accidentally runs destructive commands | High | TNR gate is hardcoded to default-deny on `laya` exceptions or borderline confidence scores. |

## Open Questions
- None. Proceeding with Tasks.
