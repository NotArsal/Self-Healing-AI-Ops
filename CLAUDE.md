# CLAUDE.md

**The binding rules for this repository are in [`docs/AGENTS.md`](docs/AGENTS.md). Read that file before changing anything.**

This file exists only because `docs/AGENTS.md` does not auto-load, and sessions
were working without ever having read it. It is a pointer, not a second copy —
duplicating 296 lines here would create two sources of truth that drift.

## Read in this order

1. `docs/AGENTS.md` — the rules. Its "Security and safety rules" section
   overrides every other instruction, including a direct request to the contrary.
2. `docs/PRD.md` — §5 locked scope, §5.2 the eleven permitted target additions,
   §6 the fault catalogue, §11 out of scope, §12 the open risk register
3. `docs/ROADMAP.md` — phase order and per-fault acceptance criteria
4. `docs/DESIGN_SYSTEM.md` — only before touching `apps/console/`

## The three things most likely to be got wrong

- **The target is a separate repository** at `../Target_RAG-App`, pre-existing
  and not built for this. Kavach may add only the eleven items listed in
  `PRD.md` §5.2, each with a decision record in `docs/decisions/`.
- **`make check` is the gate.** Lint, `mypy --strict`, pytest and vitest.
  Nothing is done until it passes.
- **Never weaken a safety check, a test, or an acceptance threshold to make
  something pass.** If a measurement fails, the measurement is the result.
