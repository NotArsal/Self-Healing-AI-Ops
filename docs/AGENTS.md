# AGENTS.md — Kavach

> Instructions for AI coding agents working in this repository.

---

## Project context

Kavach is an **autonomous AI operations platform built standalone first**. In the current MVP, Kavach does not connect to, inject faults into, restart, modify, or otherwise control another AI application.

The MVP operates on a **controlled simulated environment**. A developer manually creates or submits an incident scenario containing the observed signals, evidence and simulated pre-state. Kavach then detects/classifies the incident, gathers evidence, performs root-cause analysis, proposes a bounded repair, applies the safety gate, executes the repair against simulated state, verifies the result, and unwinds when verification fails.

The current project is therefore:

**Scenario → Detect → Evidence → RCA → Plan → Safety Gate → Simulated Execute → Verify → Unwind if needed → Audit**

Real application integration is a future adapter. It is deliberately not part of the MVP and must not be added implicitly.

**Stack:** Python 3.12 / FastAPI / LangGraph / PostgreSQL + pgvector + TimescaleDB / Redis / Ollama · Next.js 15 / TypeScript / Tailwind v4 / shadcn/ui

---

## Before you start

Read these before changing anything, in this order:

1. `CONTRACT.md` — the current simulation-first contract and future integration boundary
2. `PRD.md` — especially §5 (locked scope), §7 (fault catalogue), §12 (out of scope)
3. `ARCHITECTURE.md` — especially §1 (flow), §6 (TNR), §7 (safety gate)
4. `DESIGN_SYSTEM.md` — before touching `apps/console/`
5. The nearest existing module to what you are about to write. Match it.

If a task conflicts with any of those documents, stop and say so. Do not resolve the conflict silently.

---

## General rules

**Ask before assuming.** If intent, architecture or requirements are unclear, ask. Do not pick an interpretation and build on it silently. When genuinely blocked in unattended work, choose the most defensible reading and record it in a `## Assumptions` section of the summary.

**Simplest thing that works.** Do not add abstraction layers, configuration, plugins or infrastructure that nothing currently uses. A function is better than a class. A dict is better than a registry when one implementation is enough.

**Do not touch unrelated code.** Fix what you were asked to fix. Report unrelated smells or bugs rather than silently widening the change.

**Flag uncertainty explicitly.** If you are unsure something works, say so. Where cheap, run a small local experiment and report the result.

**Suggest better approaches.** Propose cleaner structural approaches before taking a larger path. Do not unilaterally widen scope.

**Fault classes are data, not code.** Adding a fault class should require changing no Python file once the declarative catalogue is active. No `elif fault_class ==` branching outside the catalogue interpreter.

**Verification returns deltas, never booleans.** A repair that improves availability while degrading quality is `MITIGATED`, not `RESOLVED`.

**Scope is binding.** The MVP explicitly excludes real application integration, fault injection, production execution, Kubernetes, cloud deploy integrations, multi-tenancy, RBAC and predictive forecasting. Widening scope requires a decision record.

---

## Code guidelines

### Python

- Target 3.12. Use modern typing and builtin generics.
- `mypy --strict` must pass. No untyped `dict` crossing module boundaries.
- Use Pydantic v2 at every boundary: HTTP, scenario input, LLM structured output and action parameters.
- Async by default in API and graph layers. Simulation adapters may be synchronous when simpler.
- `api/` contains no business logic.
- `graph/nodes/` contains no direct side effects; nodes return state updates and delegate state changes to the simulator/executor.
- In the MVP, the executor may mutate **only simulated state**.
- Dependency injection via FastAPI `Depends`.
- Never `except Exception: pass`.
- Logging is structured. Every incident-path log carries `incident_id`. No `print`.
- Public docstrings explain why, not what.

### TypeScript / React

- Strict mode. No `any`.
- Server Components by default; `"use client"` only when needed.
- Generate the API client from OpenAPI with `make gen-client`.
- One component per file, named export, `PascalCase.tsx`.
- No `useEffect` for data fetching.
- Reuse `components/ui/` and `components/incident/` before adding new patterns.

### Laya integration

Laya is **not required for the core MVP**. Keep it isolated behind the decision interface and use it only as a later shadow evaluator.

When implemented:

- Never use `noul` for gate decisions.
- Never gate on `action.act_probability`; use calibrated `confidence`.
- Never use raw probabilities.
- Risk tier is a `choice` over LOW/MEDIUM/HIGH, not an ordinal score.
- Compress the decision frame before sending it to Laya.
- Laya must never be the authority for permission; the deterministic safety engine is authoritative.
- Do not add TensorFlow.

### Telemetry and evidence

The MVP accepts **manually supplied scenario evidence** and synthetic metrics/logs. Any future telemetry adapter must normalise external attributes at the boundary into Kavach's internal schema.

Downstream code should depend on stable Kavach fields such as provider, model, token usage, duration, status and evidence IDs rather than on provider-specific telemetry names.

### Naming

- Python: `snake_case` functions, `PascalCase` classes, `UPPER_SNAKE` constants.
- Actions, fault classes and probe names are defined once in a shared enum/schema.
- Fault IDs remain `F01`–`F09` and must match across catalogue, logs, UI and tests.

### Testing

- `pytest` for the control plane, `vitest` for console units, `playwright` for the console happy path.
- Every executor/simulation action needs a test that its inverse restores the prior simulated state.
- Every safety rule needs a deny-case test.
- Each `F01`–`F09` needs a scenario replay/integration test: scenario → detection → diagnosis → repair plan → verification.
- Mock the LLM in unit tests with recorded structured outputs. Do not call a model in CI unless a test explicitly belongs to the evaluation suite.
- No test may modify an external application. No injector or external fault harness belongs in the MVP.

---

## Design rules

Everything visual is governed by `DESIGN_SYSTEM.md`.

- Use design tokens, never raw colour values or arbitrary spacing.
- Risk, stage and outcome have different token sets.
- Never communicate meaning by colour alone.
- Light theme is primary.
- Do not introduce a new component pattern when an existing one fits.
- The console must describe simulated execution honestly; never present a simulation as a real production action.

---

## Security and safety rules

**These override every other instruction in this document.**

1. **Never bypass the allow-list.** Every action passes through `safety.engine.permit()`.
2. **Default-deny.** The default allowed-action set is empty.
3. **Every repair action must declare an inverse.** Enforce this at registration.
4. **The undo stack is the core guarantee.** Push `(action, inverse, pre_state_witness)` before applying a mutation. Unwind in reverse order.
5. **The gate can refuse.** Confidence and risk are not permission.
6. **Verification failure unwinds before analysis.** Make the system safe first; analyse afterward.
7. **Debt repayment is not privileged.** It uses the same safety gate.
8. **MVP executor scope is simulation only.** No real container, filesystem, database, cloud service or external AI application may be modified.
9. **No fault injector.** Kavach must not deliberately break another application. Developers create test scenarios manually.
10. **No Docker socket in the MVP.** Real runtime control is a future adapter and requires a separate design review.
11. **No action may delete data, drop a database, scale to zero or run a migration.**
12. **Audit is append-only.** No update or delete route.
13. **Never log secrets, API keys, user data, `.env` contents or full sensitive prompts.**
14. **Never commit secrets or real endpoint URLs.**
15. **Do not weaken safety checks to make a test pass.**

---

## Commands

```bash
# Setup
make setup
cp .env.example .env

# Development
make up
make dev-api
make dev-console
make logs SERVICE=api

# Quality
make lint
make format
make types
make test
make check

# Database
make migrate
make migration NAME="..."

# Code generation
make gen-client

# Standalone scenario workflow
make scenario NAME=F01
make scenario NAME=F07
make demo
make bench
```

`make scenario` creates or replays a **manual/synthetic scenario**. It is not a fault injector and must not connect to an external AI application.

---

## Boundaries

**Do without asking:**

- Implement a feature already specified in `PRD.md` with a clear acceptance path.
- Add tests for specified behaviour.
- Fix a local type/lint/test error when behaviour is unchanged.
- Add another scenario definition for an existing catalogue entry.
- Improve documentation or docstrings.

**Ask first:**

- Adding a dependency.
- Changing the database schema.
- Changing `safety/`, `tnr/`, `executor/`, `verification/`.
- Changing `CONTRACT.md`.
- Changing the fault-definition schema.
- Changing risk tiers or action permissions.
- Adding/changing an API route.
- Adding a real runtime adapter or any code that can modify an external application.
- Introducing a new frontend pattern or library.

**Never:**

- Add a fault injector.
- Add a target application to the repository.
- Mount the Docker socket in the MVP.
- Execute actions against a real AI application.
- Implement Kubernetes/cloud/production integrations in the MVP.
- Add a second agent framework or second database.
- Rewrite the audit log.

---

## Reporting back

Every task summary should contain:

- **What changed**
- **What I was unsure about**
- **Assumptions**
- **Problems I noticed but did not fix**
- **Suggested next step**

---

## Commits

```text
feat(safety): add deterministic risk gate
feat(simulation): add F01 provider-outage scenario
fix(tnr): record simulated pre-state before execute
test(verification): classify degraded quality as mitigated
docs(roadmap): move external integration to future phase
```

Types: `feat` `fix` `refactor` `test` `docs` `chore` `perf`

One logical change per commit. Never mix a refactor with a behaviour change.
