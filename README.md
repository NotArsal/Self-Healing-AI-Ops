# Kavach

**Autonomous Self-Healing AI Operations Platform**
VIT · CSE-AI (E) · Group 14 · Engineering Research & Innovation · AY 2026-27

Kavach watches an AI application, works out why it broke, fixes it, and proves the fix worked — without waking anyone up.

**Status: Phase 0 — scaffold.** No ingestion, detection, RCA, safety engine, executor or fault injection yet. See `docs/ROADMAP.md`.

---

## The two systems

Kavach is a **control plane**. It does not contain the application it heals.

| | Kavach (this repo) | System under management |
|---|---|---|
| What | The control plane | `Simple_RAG-Pipeline`, a real RAG application |
| Where | `D:\Vit\Academics Sem-5\EDI\Self-Healing AI Ops` | `D:\Vit\Academics Sem-5\EDI\Target_RAG-App` |
| Repo | this one | `NotArsal/Simple_RAG-Pipeline` (separate) |
| Branch | `main` | Kavach works on `kavach/ops`, off `modernize-stack` |

The target is a pre-existing application that was **not** designed to be healed — which is the point. Kavach never vendors it, never imports it, and may only make the ten changes listed in `PRD.md` §5.2. See `docs/decisions/0002`.

## Documentation

**Specification** — read in this order:

1. `docs/PRD.md` — what it does, the locked scope, the fault catalogue
2. `docs/ARCHITECTURE.md` — how it is built
3. `docs/AGENTS.md` — rules for anyone (human or agent) writing code here
4. `docs/DESIGN_SYSTEM.md` — visual rules for `apps/console/` **only**
5. `docs/ROADMAP.md` — build order and acceptance criteria

**Decisions:** `docs/decisions/` — one record per scope change.

**Reference only, no authority:** `docs/synopsis-original.md` (the original academic synopsis, superseded) and `docs/DESIGN-cursor.md` (visual reference).

## Quick start

Requires Docker Desktop, [uv](https://docs.astral.sh/uv/), Node 20+, pnpm, and a local Ollama.

```bash
cp .env.example .env

make setup        # uv sync + pnpm install
make up           # control plane: postgres+pgvector, redis, prometheus, otel-collector, api
make check        # lint + mypy --strict + pytest + tsc. The gate.
make socket-test  # prove Docker socket access (see below)

curl localhost:8000/healthz
```

**On Windows**, GNU `make` is not installed by default. Use `.\make.ps1 <target>` instead — same target names. To remove the shim: `winget install ezwinports.make`, then delete `make.ps1`.

### Ports

Control-plane host ports are offset so Kavach and the target can run side by side — the target already publishes 5432, 9090, 8000 and 3000.

| Service | Host port |
|---|---|
| Kavach API | 8000 |
| Postgres + pgvector | **5433** |
| Redis | **6380** |
| Prometheus | **9091** |
| OTLP (HTTP / gRPC) | 4318 / 4317 |

### One Ollama, one Prometheus

Not a simplification — a constraint. The demo machine has 16GB RAM and 8GB VRAM, and the target already runs `llama3.2`, `nomic-embed-text` and a CrossEncoder reranker. The control-plane compose therefore ships **no Ollama**, reaching the existing one at `host.docker.internal:11434`, and is the **only** Prometheus. See `docs/ARCHITECTURE.md` §2.4.

Kavach's own RCA calls go **directly** to Ollama, never through the Toxiproxy path that `F01`/`F02` fault — breaking the system under diagnosis must not blind the diagnostician.

## The Docker socket

`infra/docker-compose.yml` mounts `/var/run/docker.sock` into the `api` service. This is the executor's only route to the target and the most dangerous privilege in the system.

Phase 0 mutates nothing. `make socket-test` proves access against a throwaway container it creates and removes itself, and refuses to act on any container lacking a `kavach.selftest=true` label. Real project-ownership enforcement (`ARCHITECTURE.md` §6.3) is P3.

## Safety properties

These are requirements, not aspirations. `docs/AGENTS.md` § Security and safety rules is binding.

- Default mode is **`SIMULATION`** — zero writes. Moving a project out of it is explicit (ADR 0006)
- The action allow-list defaults to **empty**
- A deny-list runs *before* the allow-list. `EMBED_MODEL` is on it permanently — changing it makes the target drop its own corpus
- Every repair records an inverse and a pre-state witness **before** executing; verification failure unwinds the stack
- Kavach **never** pushes to any remote, never modifies `main`, and is the only self-healing writer (ADR 0003)
- No arbitrary shell execution, ever

## Licence

University coursework. Not currently licensed for redistribution.
