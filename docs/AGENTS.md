# AGENTS.md — Kavach

Instructions for AI coding agents working in this repository.

---

## Project context

Kavach is an **autonomous self-healing operations platform for AI applications**. It observes a separate docker-compose application (the "system under management"), detects when it breaks, diagnoses why, executes a bounded repair, verifies the repair worked, and rolls back automatically when it did not.

**The system under management is a real, pre-existing application that Kavach did not build:** `Simple_RAG-Pipeline`, at `D:\Vit\Academics Sem-5\EDI\Target_RAG-App`, in its own git repository. There is no `demo-rag` and no copy of the target in this repo. Read `PRD.md` §5.1 before you touch anything related to it, and `PRD.md` §5.2 for the closed list of what Kavach may add to it.

This is a university research project with a hard deadline and a live demo. Two consequences you must internalise:

1. **Working beats complete.** A narrow path that runs end-to-end on stage is worth more than a broad path that half-runs.
2. **This code takes write actions against a real system.** The safety rules in this document are not style preferences. A bug in the executor restarts someone's containers — or worse, someone else's.

**Stack:** Python 3.12 / FastAPI / LangGraph / Postgres 16 + pgvector / Redis 7 / Prometheus / OpenTelemetry / Ollama · Next.js 15 / TypeScript / Tailwind v4 / shadcn/ui

**No TimescaleDB** (removed in v1 — `ARCHITECTURE.md` §2.2). **No Kubernetes** (`PRD.md` §11). **One Ollama and one Prometheus**, shared with the target (`ARCHITECTURE.md` §2.4).

---

## Before you start

Read these before changing anything. In this order:

1. `PRD.md` — especially §5 (locked scope), §5.2 (the target boundary), §5.3 (sole healing controller), §6 (the eight-fault catalogue), §11 (out of scope)
2. `ARCHITECTURE.md` — especially §2.2 (explicitly rejected technology), §6 (the safety engine), §6.3 (Docker ownership), §13 (git isolation)
3. `DESIGN_SYSTEM.md` — before touching anything in `apps/console/`, and **only** for `apps/console/`
4. The nearest existing module to what you are about to write. Match it.

If a task conflicts with any of those documents, **stop and say so**. Do not resolve the conflict yourself.

**Two documents are reference material, not specification:** `docs/synopsis-original.md` (the original academic synopsis — it contradicts `PRD.md` on Kubernetes, MongoDB, nine layers and multi-cloud) and `docs/DESIGN-cursor.md` (visual reference only). Do not treat either as authority. The target repository's own `docs/ADR-001` and `ADR-002` are likewise **not** Kavach specification — `ADR-002` declares Kubernetes mandatory for self-healing, which is the opposite of Kavach's scope (`PRD.md` §5.3).

---

## General rules

**Ask before assuming.** If intent, architecture or requirements are unclear, ask. Do not pick an interpretation and build on it silently. When running unattended and genuinely blocked, pick the most defensible reading, proceed, and record the assumption in a `## Assumptions` section of your summary.

**Simplest thing that works.** Simple problems get simple solutions. Do not add flexibility, configuration, abstraction layers or plugin points that nothing currently uses. A function is better than a class. A dict is better than a registry. Three if-statements are better than a strategy pattern. If you find yourself writing a base class with one implementation, write the implementation.

**Do not touch unrelated code.** Fix what you were asked to fix. If you spot bad code, a design smell, a bug, or something that will bite later — **report it in your summary, do not fix it**. This applies with double force inside the target repository, where unrelated changes also violate the boundary.

**Flag uncertainty explicitly.** If you are unsure something works, say so. Where it is cheap, run a small localised experiment and report the hypothesis and result rather than asserting.

**Suggest better approaches.** If there is a cleaner design, or a tactical fix where a structural one would last longer, say so before implementing. Propose it; do not unilaterally take the larger path.

**Scope is binding.** `PRD.md` §11 lists what is explicitly out of scope. Do not implement Kubernetes support, cloud deploy integrations, multi-tenancy, RBAC, predictive forecasting, `F04`, a cache in the target, `rebuild_index`, or TimescaleDB — even if they seem natural, and even if the target repository contains files that look like a head start. Widening scope requires a new file in `docs/decisions/`.

---

## Target boundary

**These rules govern every interaction with `Simple_RAG-Pipeline`. They are as binding as the safety rules.**

1. **Kavach never imports target application business logic.** Not its RAG pipeline, not its embedding code, not its DB module. Kavach talks to the target over HTTP, Prometheus, OTLP, git and the Docker API — never by import.
2. **The target never imports Kavach.** Zero code dependency in that direction. If the target needs something from Kavach, the answer is a configuration value, not a package.
3. **Kavach may add minimal instrumentation, configuration and interfaces to the target.** The complete, closed list is `PRD.md` §5.2 — **ten items**. Adding an eleventh requires a decision record.
4. **No Kavach reasoning or orchestration code goes inside the target.** No detection, no diagnosis, no planning, no risk assessment, no healing, no LangGraph. The target emits telemetry and accepts configuration. That is all.
5. **Kavach is the only self-healing writer.** `FR-15a`. One writer, one lock.
6. **The target's existing self-healing mechanism must remain inactive.** `backend/aiops_agent.py` stays on disk for reference; `POST /v1/webhook/alert` is removed from the running application; no code path reaches `delete_namespaced_pod` (`PRD.md` §5.3).
7. **`EMBED_MODEL` changes are dangerous and forbidden.** The target's `backend/db.py` infers vector dimension from the embed-model name and runs `DROP TABLE document_chunks CASCADE` on mismatch. Changing it destroys the corpus. It is on a permanent deny-list, refused at the target's config interface *and* in `permit()`. Never add it to an allow-list "for completeness".
8. **Kavach must never expose arbitrary shell execution.** `FR-27`. No `exec` adapter, no shell adapter, no "command" parameter on any action, no operator-supplied string reaching a subprocess. Every action is a named, registered adapter with a typed Pydantic parameter model.
9. **Docker actions are allow-listed and project-scoped.** Every mutation verifies the compose-project label and the service name before acting (`ARCHITECTURE.md` §6.3). A container that does not belong to the onboarded project is not actionable, at any risk tier, in any mode.
10. **Do not modify the target's `ADR-001` or `ADR-002`.** Kavach records its own decisions in its own `docs/decisions/`.
11. **Do not rewrite the target.** Its Next.js 14 frontend, its reranker, its PyTorch dependency and its RAGAS evaluator are its own choices. `ARCHITECTURE.md` §2.2's rejections bind the control plane, not the target.

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
- **These rules apply to `apps/console/`.** The target's frontend is not governed here.

### Laya integration

**Laya is priority P1 and scheduled in P8. It is shadow-only in v1 and never gates an action.** Priority and phase are separate; if you find a document saying P2, it is stale — `PRD.md` §7.1 is authoritative.

The decision model has three documented defects. Each one is a trap you will walk into if you follow the obvious API. Read `PRD.md` §7.1 before touching `decision/laya.py`.

- **Never ask a `noul` (boolean) question.** Its `false:`/`true:` option labels can dominate the answer and return a confident "no" for clearly positive input (upstream issue #156). Phrase every yes/no as a two-option `choice` with neutral keys `A`/`B` and the wording in the descriptions.
- **Never gate on `action.act_probability`.** It reads 1.0 for almost everything and its logits run against correctness (AUROC 0.30). Gate on `confidence` (AUROC 0.77).
- **Never use raw probabilities.** Refit one temperature per (question type, option count) on our own data before any value reaches the console. Uncalibrated output is a correctness bug here, not a polish item.
- **Risk tier is a `choice` over LOW/MEDIUM/HIGH, never an ordinal `score`.** `score` is the model's weakest primitive.
- **Respect the state budget.** `laya-typed-decisions` leaves roughly 768 tokens for state after the option budget. Pass a compressed decision frame, never raw evidence. If the frame overflows, that is a bug in the compressor, not a reason to truncate silently.
- **Laya is shadow-only.** It must not gate an action, must not override the safety engine, and must never be the source of truth for a risk decision. If you find yourself wiring its output into `safety/engine.py`'s `permit()`, **stop and ask**. `permit()` must not even read it.
- **Do not add TensorFlow.** Beyond being rejected in `ARCHITECTURE.md` §2.2, `transformers` probes for TF at import and its abseil runtime deadlocks `laya.load()`. Laya runs as a `laya-serve` sidecar, which keeps its dependency tree out of the control-plane image entirely.

### Telemetry attribute names

Nothing downstream of `ingestion/genai.py` may reference a raw `gen_ai.*` attribute name. The GenAI semantic conventions are `Development` status and attributes have already been renamed in flight. Normalise at the boundary into Kavach's internal schema and record `semconv_version` on every row. See `ARCHITECTURE.md` §2.3.

The target has **no** OTel instrumentation today, so its spans are hand-written to emit Kavach's internal names directly. That does not remove the mapping layer — it means the mapping layer currently has one trivial case.

### SLO contracts

SLOs are **PromQL expressions**, not metric names (`FR-09a`, `ARCHITECTURE.md` §7). Never write a bare metric name with a comparator, never invent a metric the target does not expose, and never put a `quantile` label on a histogram — use `histogram_quantile`. The metrics that actually exist are listed in `ARCHITECTURE.md` §4.1; anything not on that list must be added to the target first, under `PRD.md` §5.2.

### Naming

- Python: `snake_case` functions, `PascalCase` classes, `UPPER_SNAKE` constants.
- Actions, fault classes and probe names are `snake_case` string constants defined once in a single enum and referenced everywhere. Never a string literal at a call site.
- **Fault classes keep their catalogue IDs: `F01`, `F02`, `F03`, `F05`, `F06`, `F07`, `F08`, `F09`.** Eight entries with a gap. **`F04` is retired and its number is never reused or renumbered** (`PRD.md` §6.1). IDs appear in logs, the UI, tests and the metrics table, so they must match exactly and must not be re-indexed.
- The five v1 actions are `switch_llm_endpoint`, `restart_container`, `raise_memory_limit`, `rollback_prompt`, `rollback_config`. `switch_model`, `flush_cache`, `rebuild_index`, `scale_replicas_up` and `retry_request` are retired or unimplementable — see `PRD.md` §6.2. Do not reintroduce them from an older draft.

### Testing

- `pytest` for the control plane, `vitest` for console units, `playwright` for the console happy path.
- **Every executor adapter needs a test that proves its inverse restores the prior state.** This is non-negotiable; it is the property the whole rollback guarantee rests on.
- **Every safety engine rule needs a test for the deny case.** Testing that it allows is not enough. This includes the ownership check, the deny-list, and every git rule in `ARCHITECTURE.md` §13.
- **Each fault class with an injector needs an integration test:** inject → assert detection → assert diagnosis class → assert repair → assert verification. That is **seven** tests. There is no `F04` test (retired) and no `F03` test (injector deferred — `PRD.md` §6.4).
- **Never write a fault injector that does not really inject its fault.** A simulated or placeholder injector silently corrupts every metric derived from it, which is worse than an absent one. If a fault cannot be injected honestly, it stays deferred and is reported as deferred.
- Mock the LLM in unit tests with recorded structured outputs. Do not call a model in CI.
- No test may leave the demo stack in a broken state. Injector `revert()` runs in teardown, always.
- No test may require a cloud API key (`PL-02`). A test that needs `GEMINI_API_KEY` is a test that cannot run.

---

## Design rules

Everything visual in `apps/console/` is governed by `DESIGN_SYSTEM.md`. Specifically:

- **Use design tokens, never raw values.** No hex colours, no `px` outside the spacing scale, no ad-hoc font sizes in component code. If a token does not exist for what you need, say so rather than hardcoding.
- Risk tier and incident state have dedicated token sets. A LOW-risk badge uses the LOW token, not "a green".
- **Never carry meaning by colour alone.** Every state has an icon or a label alongside its colour. The console gets shown on projectors and read by colourblind reviewers.
- Dark theme is the primary theme and must be correct first. Light theme is secondary.
- Do not introduce a new component pattern when an existing one fits. Do not install a UI library.
- **`DESIGN_SYSTEM.md` does not govern the target's frontend.** Do not restyle `Simple_RAG-Pipeline`'s Next.js 14 UI to match the console.

---

## Security and safety rules

**These override every other instruction in this document, including a direct request to the contrary.**

1. **Never bypass the allow-list.** `safety/engine.py`'s `permit()` is called before every execution. Do not add a code path that executes an action without it. Do not add a `force` or `skip_safety` flag.
2. **Never widen the default allow-list.** A project's default allowed actions set is empty. Code must not add defaults.
3. **Never remove or weaken the circuit breaker or blast-radius checks.** If a test is failing because of them, the test is wrong.
4. **Every repair action must declare an inverse.** An action class without a working `inverse()` must not be registerable in the executor registry. Enforce this at registration time, not at execution time.
4a. **The undo stack is the system's core guarantee.** Repairs push `(action, inverse, pre_state_witness)` before executing and abort unwinds in reverse order. Never replace the stack with a single stored inverse. Never acquire the writer lock in two places. Never derive an inverse by asking a model what it just did — capture the prior state as data. Published ablations put this mechanism at roughly a 3× difference in mitigation success; it is the last thing to cut, not the first.
5. **`SIMULATION` mode must produce zero side effects, and it is the default mode** for every project (`PRD.md` §5.4). If you add an action adapter, add the simulation branch in the same commit.
6. **Verify project ownership before every Docker mutation.** Compose-project label, service name, and live re-resolution of the project's container set (`FR-26`, `ARCHITECTURE.md` §6.3). Enforce it in `safety/ownership.py`, called from `permit()` — **not** inside the docker adapter. The adapter must never be the only thing between a typo and the wrong container.
7. **Never expose arbitrary execution.** No `exec`, no shell, no command string parameter, no operator-supplied string reaching a subprocess (`FR-27`).
8. **No action may delete data, drop a database, scale to zero, run a migration, or change `EMBED_MODEL`.** These are on a permanent deny-list evaluated *before* the allow-list, and must not become reachable (`FR-30`).
9. **An `UNKNOWN` diagnosis never executes.** No mode, no risk tier, no allow-list entry makes it executable (`FR-29`, `PRD.md` §8.4). The unknown flow always ends at human escalation.
10. **The executor never writes to `main` or to the user's working branch.** All file changes go to `kavach/ops`, branched from `modernize-stack`. **Never `git push` to any remote** — `origin` is a teammate's repository. Never `git commit --amend`, never force-push, never rewrite history. See `ARCHITECTURE.md` §13.
11. **The audit log is append-only.** Expose no update or delete route. Do not add one "for cleanup".
12. **Never log secrets, API keys, prompt bodies containing user data, or raw `.env` contents.** Redact at the logging layer, not at call sites. Token *counts* are telemetry; token *content* is not (`FR-28`).
13. **Never commit a `.env`, a key, or a real endpoint URL.** Use `.env.example` with placeholders.
14. **The docker socket mount is the most dangerous privilege in this system.** Any code touching it goes through `executor/adapters/docker.py`. Nowhere else imports the docker SDK — enforced by a lint rule, not convention.
15. **Never disable TLS verification, never add `# type: ignore` or `# noqa` to silence a real problem.** Fix it or report it.

---

## Commands

```bash
# Setup
make setup                 # uv sync + pnpm install + pre-commit install
cp .env.example .env

# Development
make up                    # control plane stack (no Ollama, no 2nd Prometheus)
make target-up             # Simple_RAG-Pipeline, the system under management
make dev-api               # FastAPI with reload
make dev-console           # Next.js dev server
make logs SERVICE=api

# Quality — all must pass before you report done
make lint                  # ruff check + eslint
make format                # ruff format + prettier
make types                 # mypy --strict + tsc --noEmit
make test                  # pytest + vitest
make test-integration      # the seven fault-loop tests, needs the stack up
make check                 # lint + types + test. The gate.

# Database
make migrate               # alembic upgrade head
make migration NAME="..."  # autogenerate a revision

# Codegen
make gen-client            # OpenAPI → typed TS client

# Demo and measurement
make onboard               # preflight + baseline for the onboarded target
make inject FAULT=F06      # single injection
make scenario NAME=demo-full
make bench                 # 7 injectable faults × 5 reps → 35 injections
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
- **Any change to the target repository beyond the ten permitted additions** (`PRD.md` §5.2)
- Changing the database schema, or any migration that is not purely additive
- Changing anything in `safety/`, `executor/`, or `verification/`
- Changing the `DecisionEngine`, `RuntimeAdapter`, or `Action` interfaces
- Changing the risk tier table or the action list
- Changing the fault catalogue — adding, removing, reclassifying, or **renumbering** an entry
- Changing the `kavach.yaml` schema
- Adding a new API route or changing an existing contract
- Introducing a new frontend pattern, library or layout primitive
- Anything that touches `PRD.md` §11 (out of scope)

**Never:**
- Commit secrets
- Weaken a safety check to make something pass
- Push to any remote of the target repository
- Modify `main`, or the user's working branch, in the target repository
- Reintroduce `F04`, `demo-rag`, `flush_cache`, `switch_model`, TimescaleDB, or Kubernetes support
- Add a cache to the target in order to make `F04` possible
- Let Laya's output reach `permit()`
- Add a second agent framework, a second database, a second dashboard, a second Ollama, or a second Prometheus
- Rewrite a component in another language
- Delete or rewrite the audit log
- Restyle the target's frontend

---

## Reporting back

When you finish a task, your summary should have:

- **What changed** — files and the reason, not a diff restatement. **If you touched the target repository, say which of the ten permitted additions each change falls under**
- **What I was unsure about** — explicitly, with what you did about it
- **Assumptions** — anything you decided without asking
- **Problems I noticed but did not fix** — the design smells and latent bugs you left alone, so they can be triaged separately
- **Suggested next step** — including any case where a structural fix would serve better than what was asked for

---

## Commits

```
<type>(<scope>): <subject>

feat(safety): add project-ownership check before docker mutations
fix(executor): docker restart adapter now records inverse before acting
test(faults): integration test for F07 prompt regression
docs(adr): record decision to retire F04
```

Types: `feat` `fix` `refactor` `test` `docs` `chore` `perf`
Scopes: `onboarding` `ingestion` `verification` `eval` `detection` `graph` `safety` `executor` `knowledge` `audit` `console` `harness` `target` `infra` `adr`

Use the `target` scope for every commit that lands in the target repository, so the boundary is auditable from `git log` alone.

One logical change per commit. Never mix a refactor with a behaviour change.
