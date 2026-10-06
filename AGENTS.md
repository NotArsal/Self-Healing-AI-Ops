# AGENTS.md — Kavach

Instructions for AI coding agents working in this repository.

---

## Project context

Kavach is an **autonomous AI operations platform**. It observes a separate docker-compose AI application, detects when it breaks, diagnoses why, executes a bounded repair, verifies the repair did not make anything worse, and unwinds automatically when it did.

It is a **platform defined by a contract**, not a script with a config file. `CONTRACT.md` specifies what an application must expose to be autonomously recoverable; Kavach is the reference implementation. The test the project lives by: a person who has not read this source onboards an unseen application in under an hour, from `CONTRACT.md` alone, with **zero changes to Kavach's source**. Every change proof #2 needs is a contract defect, not a feature request.

This is a university research project with a hard deadline and a live demo. Two consequences you must internalise:

1. **Working beats complete.** A narrow path that runs end-to-end on stage is worth more than a broad path that half-runs.
2. **This code takes write actions against a real system.** The safety rules in this document are not style preferences. A bug in the executor restarts someone's containers.

**Stack:** Python 3.12 / FastAPI / LangGraph / Postgres+pgvector+TimescaleDB / Redis / Prometheus / OpenTelemetry / Ollama · Next.js 15 / TypeScript / Tailwind v4 / shadcn/ui

---

## Before you start

Read these before changing anything. In this order:

1. `CONTRACT.md` — the specification. Anything that looks like a missing capability is usually a missing obligation here
2. `PRD.md` — especially §5 (locked scope), §7 (the fault catalogue), §12 (out of scope)
3. `ARCHITECTURE.md` — especially §1.1 (four things easy to get wrong), §2.2 (rejected technology), §6 (TNR), §7 (the gate)
4. `DESIGN_SYSTEM.md` — before touching anything in `apps/console/`
5. The nearest existing module to what you are about to write. Match it.

If a task conflicts with any of those documents, **stop and say so**. Do not resolve the conflict yourself.

---

## General rules

**Ask before assuming.** If intent, architecture or requirements are unclear, ask. Do not pick an interpretation and build on it silently. When running unattended and genuinely blocked, pick the most defensible reading, proceed, and record the assumption in a `## Assumptions` section of your summary.

**Simplest thing that works.** Simple problems get simple solutions. Do not add flexibility, configuration, abstraction layers or plugin points that nothing currently uses. A function is better than a class. A dict is better than a registry. Three if-statements are better than a strategy pattern. If you find yourself writing a base class with one implementation, write the implementation.

**Do not touch unrelated code.** Fix what you were asked to fix. If you spot bad code, a design smell, a bug, or something that will bite later — **report it in your summary, do not fix it**. Unrelated changes make review impossible and get the whole change rejected.

**Flag uncertainty explicitly.** If you are unsure something works, say so. Where it is cheap, run a small localised experiment and report the hypothesis and result rather than asserting. Confidence without certainty costs more than admitting a gap.

**Suggest better approaches.** If there is a cleaner design, or a tactical fix where a structural one would last longer, say so before implementing. Propose it; do not unilaterally take the larger path.

**Fault classes are data, not code.** Adding a fault class must require changing no Python file. If you find yourself adding an `elif fault_class ==` anywhere outside `catalogue/`, stop — the interpreter is incomplete and that is the bug.

**Verification returns deltas, never booleans.** A repair that restores availability while degrading quality is `MITIGATED`, not `RESOLVED`. If you write code that collapses the outcome to pass/fail, you have deleted the feature that makes this an AI operations platform.

**Scope is binding.** `PRD.md` §12 lists what is explicitly out of scope. Do not implement Kubernetes support, cloud deploy integrations, multi-tenancy, RBAC, or predictive forecasting, even if they seem natural. Widening scope requires a new file in `docs/decisions/`.

---

## Code guidelines

### Python

- Target 3.12. Use `match`, `|` unions, builtin generics (`list[str]`, not `List[str]`).
- **Type everything.** `mypy --strict` must pass. No bare `Any`, no untyped `dict` crossing a module boundary.
- **Pydantic v2 for every boundary:** HTTP request/response, LLM structured output, `kavach.yaml` parsing, every action's params. If data crosses a seam, it has a model.
- Async by default in the API and graph layers. Sync is fine for CPU-bound scoring and for the executor adapters, which run in a thread pool.
- **Layering is enforced:** `api/` contains no business logic — it validates, calls a service, serialises. `graph/nodes/` contains no side effects — nodes return state updates and delegate writes to `executor/`. `executor/adapters/` is the only place with side effects.
- Dependency injection via FastAPI `Depends`. No module-level singletons except the settings object.
- Errors: define exceptions in the module that raises them, map to HTTP at the API boundary only. Never `except Exception: pass`.
- Logging is structured (`structlog`). Every log line in an incident path carries `incident_id`. No `print`.
- Docstrings on public functions explain **why**, not what. The signature already says what.

### TypeScript / React

- Strict mode. No `any`. No non-null assertions (`!`) without a comment justifying it.
- Server Components by default; `"use client"` only where you need state, effects or event handlers.
- **Generate the API client from the OpenAPI schema** (`make gen-client`). Never hand-write a fetch call against a Kavach endpoint; a changed backend type must break the frontend build.
- Component files: one component per file, named export, `PascalCase.tsx`. Hooks in `lib/hooks/`, `useThing.ts`.
- No `useEffect` for data fetching. Server Components, or the WebSocket hook for live incident state.
- Props interfaces defined above the component in the same file. No `React.FC`.
- Reuse before you create. Check `components/ui/` (shadcn) and `components/incident/` first.

### Laya integration

The decision model has three documented defects. Each one is a trap you will walk into if you follow the obvious API. Read PRD §7.1 before touching `decision/laya.py`.

- **Never ask a `noul` (boolean) question.** Its `false:`/`true:` option labels can dominate the answer and return a confident "no" for clearly positive input (upstream issue #156). Phrase every yes/no as a two-option `choice` with neutral keys `A`/`B` and the wording in the descriptions.
- **Never gate on `action.act_probability`.** It reads 1.0 for almost everything and its logits run against correctness (AUROC 0.30). Gate on `confidence` (AUROC 0.77).
- **Never use raw probabilities.** Refit one temperature per (question type, option count) on our own data before any value reaches the safety engine or the console. Uncalibrated output is a correctness bug here, not a polish item.
- **Risk tier is a `choice` over LOW/MEDIUM/HIGH, never an ordinal `score`.** `score` is the model's weakest primitive.
- **Respect the state budget.** `laya-typed-decisions` leaves roughly 768 tokens for state after the option budget. Pass a compressed decision frame, never raw evidence. If the frame overflows, that is a bug in the compressor, not a reason to truncate silently.
- **Laya is shadow-only in v1.** It must not gate an action. If you find yourself wiring its output into `safety.engine.permit()`, stop and ask.
- **Do not add TensorFlow.** Beyond being rejected in `ARCHITECTURE.md` §2.2, `transformers` probes for TF at import and its abseil runtime deadlocks `laya.load()`.

### Context7 documentation evidence

- **Never put incident data in a documentation query.** Queries are module-level constants in `docs/queries.py`, one per fault class, human-reviewed. No f-strings, no `.format()`, no concatenation, no interpolation of logs, config, prompts, container names, environment or stack traces. The service's own guidance forbids sending credentials, personal data and proprietary code, and incident evidence is exactly where those live. A CI test asserts every query reaching the client originates from `DOC_QUERIES` — if you need to weaken that test, you are about to leak user data.
- **Resolve at onboarding, query at incident.** `resolve-library-id` runs only during preflight, once per declared dependency, and the versioned ID is stored. Never call it from a graph node. The API caps calls at 3 per tool per question.
- **One concept per query, max 2 queries per incident.**
- **Retrieved documentation is untrusted data, never instructions.** It enters the RCA prompt inside a delimited evidence block. If you find yourself letting retrieved text steer control flow, tool choice, or a repair decision, stop — that is the injection path.
- **Cache first, always.** A cache hit must make zero network calls. Onboarding pre-warms from declared dependencies.
- **Non-fatal, 5s timeout.** A failed lookup logs and continues. Never let evidence collection block on it.
- **Only for `F05`, `F08`, `F09` and `UNKNOWN`.** Adding a documentation lookup to `F01`–`F04`, `F06` or `F07` puts a network call on the LOW-risk critical path. Don't.
- **The demo must run with networking disabled.** If a change makes that false, say so in your summary.

### Telemetry attribute names

Nothing downstream of `ingestion/genai.py` may reference a raw `gen_ai.*` attribute name. The GenAI semantic conventions are `Development` status and attributes have already been renamed in flight. Normalise at the boundary into Kavach's internal schema and record `semconv_version` on every row. See `ARCHITECTURE.md` §2.3.

### Naming

- Python: `snake_case` functions, `PascalCase` classes, `UPPER_SNAKE` constants.
- Actions, fault classes and probe names are `snake_case` string constants defined once in a single enum and referenced everywhere. Never a string literal at a call site.
- Fault classes keep their catalogue IDs: `F01`…`F09`. They appear in logs, the UI, tests and the metrics table, so they must match exactly.

### Testing

- `pytest` for the control plane, `vitest` for console units, `playwright` for the console happy path.
- **Every executor adapter needs a test that proves its inverse restores the prior state.** This is non-negotiable; it is the property the whole rollback guarantee rests on.
- **Every safety engine rule needs a test for the deny case.** Testing that it allows is not enough.
- Each of `F01`–`F09` needs an integration test: inject → assert detection → assert diagnosis class → assert repair → assert verification.
- Mock the LLM in unit tests with recorded structured outputs. Do not call a model in CI.
- No test may leave the demo stack in a broken state. Injector `revert()` runs in teardown, always.

---

## Design rules

Everything visual is governed by `DESIGN_SYSTEM.md`. Specifically:

- **Use design tokens, never raw values.** No hex colours, no `px` outside the spacing scale, no ad-hoc font sizes in component code. If a token does not exist for what you need, say so rather than hardcoding.
- Risk tier and incident state have dedicated token sets. A LOW-risk badge uses the LOW token, not "a green".
- **Never carry meaning by colour alone.** Every state has an icon or a label alongside its colour. The console gets shown on projectors and read by colourblind reviewers.
- Dark theme is the primary theme and must be correct first. Light theme is secondary.
- Do not introduce a new component pattern when an existing one fits. Do not install a UI library.

---

## Security and safety rules

**These override every other instruction in this document, including a direct request to the contrary.**

1. **Never bypass the allow-list.** `safety.engine.permit()` is called before every execution. Do not add a code path that executes an action without it. Do not add a `force` or `skip_safety` flag.
2. **Never widen the default allow-list.** A project's default allowed actions set is empty. Code must not add defaults.
3. **Never remove or weaken the circuit breaker or blast-radius checks.** If a test is failing because of them, the test is wrong.
4. **Every repair action must declare an inverse.** An action class without a working `inverse()` must not be registerable in the executor registry. Enforce this at registration time, not at execution time.
4a. **The undo stack is the system's core guarantee.** Repairs push `(action, inverse, pre_state_witness)` before executing and abort unwinds in reverse order. Never replace the stack with a single stored inverse. Never acquire the writer lock in two places. Never derive an inverse by asking a model what it just did — capture the prior state as data. Published ablations put this mechanism at roughly a 3× difference in mitigation success; it is the last thing to cut, not the first.
4b. **The gate must be able to refuse.** `permit()` returns a verdict, not a score. Never add a code path where a high confidence or a low risk tier bypasses the allow-list or the forbidden-services check. Scoring and permission are different operations; conflating them is how an autonomous system takes an action it should never have been able to take.
4c. **Verification failure unwinds before it analyses.** Never insert analysis, learning, or a knowledge-base write between a failed probe and the unwind. Analysis is what happens once the system is safe.
4d. **Debt repayment is not privileged.** A repayment action goes through `permit()` exactly like any other action.
5. **`SIMULATION` mode must produce zero side effects.** If you add an action adapter, add the simulation branch in the same commit.
6. **The executor never writes to the user's working git branch.** All file changes go to `kavach/ops`. Never `git push`. Never `git commit --amend`. Never touch `main`.
7. **No action may delete data, drop a database, scale to zero, or run a migration.** These are not in the catalogue and must not become reachable.
8. **The audit log is append-only.** Expose no update or delete route. Do not add one "for cleanup".
9. **Never log secrets, API keys, full prompts containing user data, or raw `.env` contents.** Redact at the logging layer, not at call sites.
10. **Never commit a `.env`, a key, or a real endpoint URL.** Use `.env.example` with placeholders.
11. **The docker socket mount is the most dangerous privilege in this system.** Any code touching it goes through `executor/adapters/docker.py`. Nowhere else imports the docker SDK.
12. **Never disable TLS verification, never add `# type: ignore` or `# noqa` to silence a real problem.** Fix it or report it.

---

## Commands

```bash
# Setup
make setup                 # uv sync + pnpm install + pre-commit install
cp .env.example .env

# Development
make up                    # control plane stack
make target-up             # demo-rag, the system under management
make dev-api               # FastAPI with reload
make dev-console           # Next.js dev server
make logs SERVICE=api

# Quality — all must pass before you report done
make lint                  # ruff check + eslint
make format                # ruff format + prettier
make types                 # mypy --strict + tsc --noEmit
make test                  # pytest + vitest
make test-integration      # the F01..F09 loop tests, needs the stack up
make check                 # lint + types + test. The gate.

# Database
make migrate               # alembic upgrade head
make migration NAME="..."  # autogenerate a revision

# Codegen
make gen-client            # OpenAPI → typed TS client

# Demo and measurement
make onboard               # preflight + baseline for demo-rag
make inject FAULT=F01      # single injection
make scenario NAME=demo-full
make bench                 # 9 faults × 5 reps → metrics table
```

---

## Boundaries

**Do without asking:**
- Implement a feature already specified in `PRD.md` with a clear acceptance path
- Add tests, fix a failing test that is wrong, fix a type error
- Refactor within a single module where behaviour is unchanged and tests prove it
- Add a new fault injector for an existing catalogue entry
- Write or improve a docstring

**Ask first:**
- Adding any dependency. Justify it against `ARCHITECTURE.md` §2.2 first — several obvious candidates are there because they were already rejected
- Changing the database schema, or any migration that is not purely additive
- Changing anything in `safety/`, `tnr/`, `executor/`, or `verification/`
- Changing `CONTRACT.md` — it is a versioned specification; a change is a breaking change and needs a version bump and an ADR
- Changing the fault-definition schema in `catalogue/`
- Changing the `DecisionEngine`, `RuntimeAdapter`, or `Action` interfaces
- Changing the risk tier table
- Changing the fault catalogue — adding, removing, or reclassifying an entry (editing a `builtin/*.yaml` threshold is fine; changing what a fault class *means* is not)
- Changing the `kavach.yaml` schema
- Adding a new API route or changing an existing contract
- Introducing a new frontend pattern, library or layout primitive
- Anything that touches `PRD.md` §11 (out of scope)

**Never:**
- Commit secrets
- Weaken a safety check to make something pass
- Add a second agent framework, a second database, or a second dashboard
- Implement Kubernetes, cloud deploy, canary traffic splitting, or multi-tenancy support
- Implement autonomous code repair, GitHub PR-based remediation, Loki or Tempo. All four are rejected in `ARCHITECTURE.md` §2.2 with reasons
- Let an unknown failure auto-execute anything. Unknown always escalates to a human in v1
- Put a Context7 lookup on a LOW-risk repair path, or let retrieved documentation influence a decision as anything other than cited evidence
- Rewrite a component in another language
- Delete or rewrite the audit log

---

## Reporting back

When you finish a task, your summary should have:

- **What changed** — files and the reason, not a diff restatement
- **What I was unsure about** — explicitly, with what you did about it
- **Assumptions** — anything you decided without asking
- **Problems I noticed but did not fix** — the design smells and latent bugs you left alone, so they can be triaged separately
- **Suggested next step** — including any case where a structural fix would serve better than what was asked for

---

## Commits

```
<type>(<scope>): <subject>

feat(safety): add circuit breaker for repeated same-fault heals
fix(executor): docker restart adapter now records inverse before acting
test(faults): integration test for F07 prompt regression
docs(adr): record decision to drop the rust executor
```

Types: `feat` `fix` `refactor` `test` `docs` `chore` `perf`
Scopes: `contract` `onboarding` `ingestion` `eval` `detection` `catalogue` `graph` `safety` `tnr` `executor` `verification` `debt` `docs` `knowledge` `audit` `console` `harness` `infra` `adr`

One logical change per commit. Never mix a refactor with a behaviour change.
