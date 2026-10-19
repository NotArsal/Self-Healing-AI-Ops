# ADR 0015 — Context7 is not a runtime component, and the reason is structural

**Date:** 2026-10-19
**Status:** Accepted
**Changes:** nothing in code. This records why a promised component was never
built, which until now was recorded nowhere at all.
**Supersedes the claim in:** `synopsis-original.md` — the tools line
(`Context7 , Laya AI system decsion model`) and the reference table entry
*"Current documentation source for code/config repair."*
**Related:** [ADR 0009](0009-p7-is-cut.md) — the same synopsis line's other
half, cut and documented; [ADR 0011](0011-the-sandbox-and-apply-patch-are-restored.md)

## Context

Context7 serves current library and API documentation. The synopsis named it
twice and gave it a job: *documentation source for code/config repair*.

It appears in **zero lines of code**, and in zero lines of `PRD.md`,
`ROADMAP.md`, `ARCHITECTURE.md`, `REPORT_DRAFT.md` or any other decision
record. It was dropped silently, at some point nobody wrote down.

That silence is the thing being fixed here. Laya was on the same synopsis
line, was also cut, and anybody asking why can read ADR 0009. Asking the same
question about Context7 had no answer anywhere, which is worse than either
building it or deciding against it.

## Why there is nowhere to put it

Kavach has exactly one path where a model's output becomes *content* rather
than a choice from a closed list: `apply_patch`, via `rca/patch_engine.py`.
Everything else picks an action name from `allowed_actions` and writes a value
recorded from the target's own prior state.

What that one path may write is fixed by the target's manifest:

```yaml
versioned_paths:
  prompts: ./prompts     # read at request time, revert needs no restart
  config: runtime        # via /v1/admin/config, not a file
```

**The only file content Kavach can ever generate is prompt text.** Not Python,
not a library call, not a framework configuration. There is no API for a model
to get wrong, so there is no documentation that would stop it being wrong.
Context7's stated job does not exist in this system.

Making it exist would mean adding source files to `versioned_paths` — widening
the HIGH-tier generated-write surface to the target's actual code. That is the
component `PRD.md` §12 calls "the highest risk thing in the system", and
widening it to satisfy a line in a document written before the architecture
existed is the wrong direction for the wrong reason.

## The constraint that settles it independently

**PL-02** (`PRD.md` §12, `FR-07b`, `AGENTS.md`): *no cloud API key is required
for any v1 path*. Context7 is a hosted service. Any runtime use would have to
be optional and degrade to nothing when absent — and the offline rehearsal
that P8 requires, and that passed on 2026-10-19 with the network physically
disconnected, is precisely a run where it would be absent. A feature that is
switched off during the one acceptance test that matters is not a feature.

## Decision

**Context7 is a development-time tool, not a component. It is not in the
architecture and it will not be added before submission.**

- It is reported in the report's tooling section, where it is true: library
  documentation for FastAPI, pydantic-settings, pgvector and Next.js 15 was
  read through it while Kavach was built.
- It is **not** in any architecture diagram, dependency list or data flow.
- The synopsis claim is listed as withdrawn, with this ADR as the reason,
  alongside the other synopsis-versus-implementation gaps.

## Where it would genuinely belong, if this project continued

Not in repair. In **onboarding**.

`onboarding/manifest.py` produces the manifest that `permit()` reads, and
today that manifest was written by hand for one target. The honest limitation
of this whole project is that it has been demonstrated against exactly one
application; generalising means reading an unfamiliar codebase and working out
what its services, config interface and versioned paths are. *That* is a task
where current documentation for an unfamiliar framework earns its place, and
it is a read-only, pre-flight activity with no path to a running system — so
PL-02 does not bite, because onboarding is not a v1 healing path.

Recorded as future work. Not built, because onboarding a second target is not
a four-day task and pretending otherwise would produce a worse result than
stating the limitation.

## The lesson, which is the same one as last time

ADR 0013 and ADR 0014 were both about measurements that described the
instrument. This is the documentation equivalent:

> **A plan is a claim about the future, and the parts of it that quietly did
> not happen are the parts nobody re-reads.**

The practical form: before submission, diff the synopsis against the
implementation line by line, and write down every gap — because a panel
comparing the two documents will find them, and the only thing that
distinguishes engineering judgement from an oversight is whether it was
written down before someone asked.
