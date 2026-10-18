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

## Measured 2026-10-18, and CORRECTED 2026-10-19

### What the first measurement said, and why it was wrong

On 2026-10-18 this section reported 0 of 15 - no model, local or
otherwise, writing a patch that applies - and attributed it to model
capability. **That attribution was wrong, and the largest single cause was
a defect in Kavach.**

`git apply` treats a patch whose final line has no newline as truncated
and reports `corrupt patch at line N`, which describes its parser rather
than the patch. A model returns its diff as a JSON string, and a JSON
string ends where the content ends, so the last hunk line arrived
unterminated nearly every time. Diffs whose headers, markers and context
lines were all correct were being rejected for a missing `
`.

A second, smaller cause was also ours: this prompt said *"do not worry
about the numbers in the `@@` header being exact"* and a model read that
as permission to omit them, emitting a bare `@@`. The prompt now says the
numbers must be PRESENT though not exact.

The lesson is the one the project keeps relearning: **before a measurement
becomes a finding about the world, check that it is not a finding about
the instrument.** A hand-written diff through the same path would have
exposed this on day one, and is now a test.

### The corrected numbers

Applicability - does `git apply --check` accept the patch against the
degraded file? Ten samples each, all after the fix except where noted.
A call that never reached the model is excluded from the denominator
rather than counted as a failure.

| model | via | applies |
|---|---|---|
| gpt-oss-120b | Groq | **10 / 10** |
| gemini-3.8-flash | Gemini | 7 / 10 *(measured BEFORE the fix; floor, not ceiling)* |
| llama3.1 | Ollama, local | 0 / 10 |
| llama3.2 | Ollama, local | 0 / 10 |
| qwen2.5:7b-instruct | Ollama, local | 0 / 10 |

Reproduce with `harness/patch_live.py --probe N --provider P --model M`.

### The local result survives, for a different reason

0 of 30 across three local models still holds after the fix, and the
error changed in a way that matters: from `corrupt patch` - a structural
complaint - to `patch failed: answer.txt:N`, a CONTENT mismatch. The local
models cannot reproduce this file's context lines exactly. Its lines begin
with `- `, so a line being deleted must begin with two minus signs, and
they write one. That is a real capability limit and it is now the only
thing being claimed.

### End to end, against the live sandbox

`harness/patch_live.py` injects F07 for real, asks for a patch, applies it
to the clone and runs the clone's fast set there.

- **gemini-3.8-flash: PASS.** Production degraded at 0%, the generated
  patch applied to the sandbox, the sandbox fast set returned 100%, and
  production was untouched and restored byte-exact. The first generated
  repair this project has produced and verified.
- **gpt-oss-120b, 3 runs: 1 inapplicable, 2 REFUSED BY THE SANDBOX.** Both
  refusals are the most useful result here. The patch passed all six
  deterministic checks and applied cleanly; the sandbox fast set then came
  back 67% and the action was refused before it could be offered to
  anyone. A patch that is well-formed, permitted, applicable and does not
  actually repair the behaviour is exactly what constraint 4 exists for,
  and it is not detectable by any amount of static checking.

Production was restored byte-exact after every run, including the
failures.

## What would reverse this

If `apply_patch` cannot be shown working end to end in time, it is cut again
by un-registering it — one line in `executor/catalogue.py` — and the sandbox
stays, because the sandbox earns its place as a verification surface
independently of whether anything generated is ever applied to it.
