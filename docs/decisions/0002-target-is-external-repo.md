# ADR 0002 — The system under management is an external repository

**Date:** 2026-10-02
**Status:** Accepted
**Supersedes:** the `targets/demo-rag/` plan in earlier drafts of `ARCHITECTURE.md`

## Context

Earlier drafts had Kavach ship its own reference target, `demo-rag` — a purpose-built five-service RAG stack (`api`, `pgvector`, `redis`, `ollama`, `llm-proxy`) living at `targets/demo-rag/`, with a dedicated two-week roadmap phase to build it.

A real RAG application already exists: `NotArsal/Simple_RAG-Pipeline`, at `D:\Vit\Academics Sem-5\EDI\Target_RAG-App`. It has a FastAPI backend, a pgvector store, a reranker, query expansion, a Next.js frontend, a RAGAS evaluation suite and a 40-case dataset.

## Decision

**Kavach does not build a target. It onboards the existing one.**

- The target stays in its own git repository, with its own remotes and its own development cycle.
- Kavach points at it by path (`targets/simple-rag.yaml`). It is never vendored, copied or submoduled into this repo.
- `ROADMAP.md` P1 becomes "onboard and instrument", replacing "build `demo-rag`".
- `llm-proxy` is deleted from the design; Toxiproxy in front of the target's existing Ollama covers `F01`/`F02`.
- The permitted changes to the target are a closed list of ten items (`PRD.md` §5.2). An eleventh requires a decision record.

## Consequences

- **Positive, and the main reason:** the target was not designed to be healed. Its failure modes are not staged for Kavach's convenience, which makes every result stronger than the same result against a purpose-built victim.
- **Positive:** two weeks of roadmap freed, and one fewer codebase to maintain.
- **Positive:** `F06` retrieval collapse is injectable against the target as it stands, via a live config value, and it produces a genuine silent HTTP-200 failure.
- **Negative:** the target has **no** OpenTelemetry, no token accounting, no externalised prompts, no cache and no vector index. Four of those gaps have to be closed before the catalogue is detectable, and `F04` cannot be closed at all (ADR 0004).
- **Negative:** a boundary now has to be actively defended. `AGENTS.md` § Target boundary exists for this, and every target commit uses the `target` scope so the boundary is auditable from `git log`.
- **Negative:** two compose projects must coexist on one laptop. Control-plane host ports are offset (5433/6380/9091) to avoid colliding with the target's 5432/9090.
