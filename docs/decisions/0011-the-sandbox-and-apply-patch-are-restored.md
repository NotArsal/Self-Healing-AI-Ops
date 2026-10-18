# ADR 0011 — The sandbox and `apply_patch` are restored; Laya and the knowledge base stay cut

**Date:** 2026-10-18
**Status:** Accepted
**Partially supersedes:** `0009-p7-is-cut.md`
**Required by:** `PRD.md` §5, which makes scope binding and requires a decision record for a change to it.

## Context

ADR 0009 cut all of P7 as one decision, on the reasoning that the sandbox
(`F-SBX`), generated repairs (`F-CODE`), Laya (`F-DEC`) and the knowledge base
were a single block of unstarted work competing with P8 for the remaining
time, and that P8 — measurement — is what a reviewer notices.

That reasoning was right about the ordering and wrong about the coupling. It
treated four items as one because they shared a phase number, not because they
shared a dependency. In fact only two of them are coupled: `apply_patch`
cannot exist without the sandbox, because `ARCHITECTURE.md` §6.2.1 constraint
4 makes a sandbox result a precondition of the proposal. Laya and the
knowledge base depend on neither and are depended on by neither.

Since 0009 was written, the measurement work it was protecting has largely
landed: the undo ablation, `make bench`, `make scenario`, the Kavach MTTR
numbers and the scripted runbook baseline all exist and have been run. The
scarcity 0009 was rationing no longer binds in the same way.

The sandbox was then built and proven live (`destroy()` → `ensure()` rebuilds
in 14.4s, corpus 30 rows, fast set 3/3, production untouched), which removes
the specific objection 0009 raised against `apply_patch`: that registering it
would let `permit()` authorise something whose safety precondition was
unbuilt.

## Decision

**Restore the sandbox and `apply_patch`.** `apply_patch` registers with
`tier_is_fixed=True` at HIGH, and its `prepare()` applies the patch to the
sandbox and runs the fast set there before the action is ever offered to
`permit()`.

**Laya (`F-DEC`) and the pgvector knowledge base stay cut.** Nothing in this
ADR revives them. They remain out of v1 for the reasons 0009 gives, which this
ADR does not dispute: they are genuinely unstarted, genuinely large, and
genuinely not load-bearing for anything else.

**The full git-isolation model stays cut.** `apply_patch` writes files; it
does not branch, commit or push, and `executor/adapters/git.py` contains no
code path that could (`AGENTS.md` rule 10, honoured by absence).

## Consequences

- `PRD.md` §6's phase column for `F-SBX` and `F-CODE` is live again; `F-DEC`
  stays cut.
- A fifth repair action exists, and it is the only one whose payload a model
  authored. It is the only HIGH-tier action in the catalogue.
- `permit()` needs no change: it already returns `REQUIRE_SANDBOX` for an
  approved HIGH action.
- The claim "Kavach never applies generated code" is no longer true and must
  be struck wherever the report makes it. What is true, and is the more
  interesting claim, is that generated code is applied only to a clone, only
  after six deterministic checks, only with a byte-exact inverse recorded, and
  only to one directory.

## What would reverse this

If `apply_patch` cannot be shown working end to end in time, it is cut again
by un-registering it — one line in `executor/catalogue.py` — and the sandbox
stays, because the sandbox earns its place as a verification surface
independently of whether anything generated is ever applied to it.
