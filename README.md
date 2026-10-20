# Kavach

**Autonomous Self-Healing AI Operations Platform**
VIT · CSE-AI (E) · Group 14 · Engineering Research & Innovation · AY 2026-27

Kavach watches an AI application, works out why it broke, fixes it, and proves the fix worked — without waking anyone up.

**Status: P0–P8 complete.** Detection, LLM root-cause analysis, a ten-check safety gate, a reversible executor, a console and a measured benchmark all run. `make check` is the gate: **506 Python tests, 82 TypeScript tests.**

> **Work happens on `kavach/ops`, not on `main`.** This repository also contains an unrelated earlier implementation of the same project under `archive/first-implementation`. It shares no commit with this branch, its claims are not this project's claims, and nothing in the report is derived from it.

---

## What was actually built, and what was not

The honest version, because the report's argument depends on it.

| | result |
|---|---|
| Fault classes implemented | **4** — `F01` endpoint outage, `F06` retrieval collapse, `F07` prompt regression, `F08` config regression |
| Fault classes in the catalogue | 8 (`F04` retired, its number not reused) |
| Injections benchmarked | **40** across two full runs, 4 classes × 5 reps each |
| **False heals** | **0 / 40.** Target verified clean after every single run |
| Detection rate | 100% (20/20, both runs) |
| RCA accuracy, the model's own answer | 85% (17/20, both runs) |
| Auto-resolution | 75% run A, 70% run B |
| MTTR median | 124.4s / 114.9s, against a < 180s target |

**The four classes not implemented are reported with the reason, not omitted.** `F02` and `F05` were dropped at the week-10 checkpoint. `F03`'s injector is deferred because the target sets `restart: always` — making it injectable would mean deliberately weakening the target's own resilience to manufacture a fault, which is forbidden. `F09` was **closed on measurement**: three mechanisms were tried and published (1.20×, 0.87–1.17×, and `max_tokens` is a ceiling), none of which moves tokens-per-request enough to inject honestly.

**MTTD is reported per class, never as one number.** The twenty samples are bimodal with nothing between 20.5s and 36.5s: the two classes whose detectors read no PromQL land at 18.5s and 20.1s, the two that wait on a `rate()` window at 60.8s and 71.2s. The aggregate median clears the `< 30s` target and saying only that would be misleading, so the target was left exactly as written and the two classes that miss it are reported as missing it. See [`docs/decisions/0019`](docs/decisions/0019-mttd-is-measured-and-the-target-stays-but-per-class.md).

Every figure above traces to a file in [`harness/reports/`](harness/reports/), which is committed. [`docs/REPORT_DRAFT.md`](docs/REPORT_DRAFT.md) is the full write-up, with its limits stated in §6.

## The two systems

Kavach is a **control plane**. It does not contain the application it heals.

| | Kavach (this repo) | System under management |
|---|---|---|
| What | The control plane | `Simple_RAG-Pipeline`, a real RAG application |
| Repo | this one, branch `kavach/ops` | `NotArsal/Simple_RAG-Pipeline` (separate) |
| Local path | `.../EDI/Self-Healing AI Ops` | `.../EDI/Target_RAG-App` |

The target is a pre-existing application that was **not** designed to be healed — which is the point. Kavach never vendors it, never imports it, and may only make the **eleven** changes listed in `PRD.md` §5.2, each with its own decision record. See [`docs/decisions/0002`](docs/decisions/0002-target-is-external-repo.md).

## Documentation

**Specification** — read in this order:

1. [`docs/PRD.md`](docs/PRD.md) — what it does, the locked scope, the fault catalogue
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how it is built
3. [`docs/AGENTS.md`](docs/AGENTS.md) — binding rules for anyone (human or agent) writing code here
4. [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md) — visual rules for `apps/console/` **only**
5. [`docs/ROADMAP.md`](docs/ROADMAP.md) — build order and per-phase acceptance criteria

**Results:** [`docs/REPORT_DRAFT.md`](docs/REPORT_DRAFT.md) · **Open findings:** [`docs/RESEARCH_NOTES.md`](docs/RESEARCH_NOTES.md) · **Decisions:** [`docs/decisions/`](docs/decisions/) — 20 records, one per scope change or reversal.

## Quick start

Requires Docker Desktop, [uv](https://docs.astral.sh/uv/), Node 20+, pnpm, and a local Ollama.

```bash
cp .env.example .env

make setup        # uv sync + pnpm install
make up           # 7 containers: postgres, prometheus, otel-collector, jaeger, grafana, api, console
make check        # ruff + mypy --strict + pytest + vitest. THE GATE.

curl localhost:8080/healthz      # API
open http://localhost:3001       # console
```

Then, in rough order of what is worth seeing:

```bash
make scenario     # the four-act demo: autonomous heal, approval heal, rollback, unknown fault
make inject       # inject one fault by hand
make bench        # the full metrics table (paced under the limiter: ~8 hours)
make figures      # the report figures, drawn from harness/reports/
make postmortem ARGS=INC-xxxxxx   # render any incident, audit chain verified
make offline      # prove it runs with the network down and every cloud key empty
```

**On Windows**, run `make` from **Git Bash**, not PowerShell — under PowerShell `bash` resolves to WSL and the harness scripts fail on path translation. If GNU `make` is absent: `winget install ezwinports.make`.

### Ports

Every control-plane host port is offset so Kavach and the target can run side by side. The target's ports are **not** ours to move — its frontend has `http://localhost:8000` hardcoded.

| Service | Kavach host port | Target uses |
|---|---|---|
| API | **8080** | 8000 |
| Console | **3001** | 3000 |
| Grafana | **3002** | — |
| Jaeger UI | **16686** | — |
| Postgres | **5433** | 5432 |
| Prometheus | **9091** | 9090 |
| OTLP (HTTP / gRPC) | 4318 / 4317 | — |
| Ollama | — (shared) | 11434 |

Inside the containers nothing moved: the Kavach API still listens on 8000, so only the published port differs.

**There is no Redis.** Earlier plans plumbed it in for P3; nothing ever needed it, so it was never added. `alembic` and `langgraph` are absent for the same reason — see the dependency rationale in `apps/control-plane/pyproject.toml`.

### One Ollama, one Prometheus

Not a simplification — a constraint. The demo machine has 16GB RAM and 8GB VRAM, and the target already runs `llama3.2`, `nomic-embed-text` and a CrossEncoder reranker. The control-plane compose therefore ships **no Ollama**, reaching the existing one at `host.docker.internal:11434`, and is the **only** Prometheus. See `docs/ARCHITECTURE.md` §2.4.

Kavach's own RCA calls go **directly** to Ollama, never through the Toxiproxy path that `F01` faults — breaking the system under diagnosis must not blind the diagnostician.

## The Docker socket

`infra/docker-compose.yml` mounts `/var/run/docker.sock` into the `api` service. This is the executor's only route to the target and the most dangerous privilege in the system.

It is reached through exactly one module, `executor/adapters/docker.py`, and project ownership is verified before **every** mutation — a container without the expected project label is refused, not skipped. `make socket-test` proves access against a throwaway container it creates and removes itself.

## Safety properties

These are requirements, not aspirations. `docs/AGENTS.md` § Security and safety rules is binding and overrides every other instruction in the repository.

- Default mode is **`SIMULATION`** — zero writes. Moving a project out of it is explicit (ADR 0006)
- The action allow-list defaults to **empty**, and a **deny-list runs before it**. `EMBED_MODEL` is denied permanently — changing it makes the target drop its own corpus
- `permit()` runs **ten checks and then routes on mode** — mode is last because it routes rather than decides — returning one of `ALLOW_AUTO`, `REQUIRE_SANDBOX`, `REQUIRE_APPROVAL`, `DENY`
- **Blast radius: 5 incident starts per sliding hour**, where an approved heal costs 2. The system halts rather than widening — this is why `make bench` takes eight hours
- Every repair declares an **inverse** and captures a pre-state witness **before** executing. An action with no inverse cannot be registered: `register()` raises at import time
- Verification failure **unwinds the stack**, and the unwind is checked against the witness
- An **UNKNOWN diagnosis never executes.** A model answer the deterministic validator cannot corroborate is refused — measured at 0 false heals in 40 injections
- The audit log is **hash-chained and append-only**; `make postmortem` verifies the chain while rendering
- Kavach **never** pushes to the target's remote, never writes to its `main` or working branch, and is the only self-healing writer (ADR 0003)
- **No arbitrary shell execution, ever** (FR-27)

## Licence

University coursework. Not currently licensed for redistribution.
