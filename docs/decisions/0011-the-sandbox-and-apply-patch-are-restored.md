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

## Measured on the day it was built, 2026-10-18

The machinery works. No local model has yet fed it a usable patch.

| model | patches that APPLY to the file |
|---|---|
| llama3.1 | 0 of 5 |
| llama3.2 | 0 of 5 |
| qwen2.5:7b-instruct | 0 of 5 |

Reproduce with `harness/patch_live.py --probe N --model M`. A patch counts
only if `git apply --check` accepts it; all three models pass the six
deterministic checks, which is why passing them is not the thing counted.

Two distinct failures, both about diff syntax rather than about the repair:

1. qwen2.5:7b-instruct omits the `--- a/<path>` header in most runs.
2. All three mis-handle a file whose own lines begin with `- `. Every hunk
   line needs its own marker in column 1, so a line of this file that is
   being deleted begins with two minus signs. The models write one, which
   git reads as an unchanged line, producing a hunk that changes nothing.

Neither is a prompt problem in the sense of being fixable by a better
prompt. Both were stated explicitly in `llm/prompts/patch.txt` and
re-measured; the rate did not move. A field `description` in the JSON
schema does nothing either, because Ollama compiles the schema to a
grammar and a grammar has no room for prose - that attempt took qwen from
1 in 3 to 0 in 5.

The honest reading is that writing a unified diff is a different and
harder skill than diagnosing, and a 3B-7B local model does not have it.
Diagnosis on the same hardware reached 10 of 10. This is a finding about
model capability, not a defect in the action, and the containment held on
every one of the 25 runs: nothing was applied, and the target was restored
byte-exact each time.

The next variable to try is a larger model through the cloud provider
path, which is already planned. The thresholds do not move to meet the
models.

## What would reverse this

If `apply_patch` cannot be shown working end to end in time, it is cut again
by un-registering it — one line in `executor/catalogue.py` — and the sandbox
stays, because the sandbox earns its place as a verification surface
independently of whether anything generated is ever applied to it.
