# Spec: Phase 9 - Laya Integration & Autonomous TNR Gate

## Objective
Transition Kavach into a dynamic autonomous remediation platform by deeply integrating the **Laya** decision engine. Laya will act as the "System 1" nervous system of Kavach, providing ultra-fast, local, non-autoregressive routing and safety decisions to complement Qwen's heavy "System 2" reasoning.

## Laya Capability Map (The 4 Pillars)
1. **Incident Triage & Routing**: Laya instantly classifies incoming alerts (e.g., Database vs Network) to route to the correct Qwen RCA sub-graph, saving time and context.
2. **Log Noise Reduction**: Laya reads raw logs and scores them for incident relevance, passing only the most critical signals to Qwen.
3. **The TNR Safety Gate**: Laya evaluates Qwen's proposed remediation commands for destructive potential and downtime risk. High-risk commands halt for human approval; low-risk commands auto-execute.
4. **Post-Execution Verification**: Laya reads the executor's terminal output and telemetry to verify if the remediation succeeded.

## Tech Stack
- **Kavach Core**: FastAPI, Python 3.10+, Qwen.
- **Laya**: `laya` package (local execution). *Note: Laya can be fine-tuned on custom Kavach operational data if zero-shot accuracy is insufficient.*
- **Environment**: Local CLI execution within the control-plane environment for testing.

## Commands
```bash
# Install Laya dependency
uv add laya

# Run backend
cd apps/control-plane
uv run uvicorn kavach.main:app --host 0.0.0.0 --port 8000
```

## Project Structure
```text
apps/control-plane/kavach/
├── remediation/
│   ├── executor.py       -> Executes CLI commands locally
│   └── tnr_gate.py       -> Laya evaluates command safety
├── triage/
│   └── router.py         -> Laya classifies incoming alerts
└── evaluation/
    └── log_filter.py     -> Laya scores log relevance
```

## Boundaries
- **Always do**: Use Laya exclusively for fast, binary/categorical decisions (routing, safety checking, verification). Use Qwen exclusively for generative RCA and planning.
- **Ask first**: If Laya flags an action as destructive or high risk in the TNR gate, pause the incident and require human approval.
- **Never do**: Never let the executor run un-gated commands that bypass Laya's safety check.

## Success Criteria
1. Laya successfully categorizes an incoming alert (Triage).
2. Laya filters a noisy log file down to the relevant lines (Log Reduction).
3. Laya blocks a simulated destructive command (e.g., `rm -rf`) while allowing a safe command (e.g., `systemctl status`) (TNR Gate).
4. Laya correctly reads terminal output and classifies it as success/failure (Verification).
