# The human baseline — protocol

**Status:** ready to run · **Owner:** whole team · **Budget:** ~2 hours
**Required by:** `PRD.md` §10.3, `ROADMAP.md` week-12 checkpoint
**Runner:** `harness/human_baseline.py`

> `PRD.md` §10 lists MTTR < 3 min as "the core claim". A duration with nothing
> to compare it against is not a claim, it is a number. This is the
> comparison, and it is the single cheapest thing left that changes what the
> report can say.

---

## 1. What is being measured

For each injected fault, with a human operator in place of Kavach:

| Clock | Starts | Stops |
|---|---|---|
| **MTTD** (detect) | the injector writes | the operator says *"something is wrong"* |
| **MTTD→diagnosis** | as above | the operator names a cause **and** the change they intend |
| **MTTR** (resolve) | the injector writes | the fast set passes 3/3 **and** `/healthz` is 200 |

The resolve clock does **not** stop when the operator says they are done. It
stops when the same verification Kavach is held to passes. An operator who
declares victory on a system that is still broken has produced a false
recovery, which is the failure mode this project ranks above all others, and
it must be recorded as one rather than smoothed into a slightly longer time.

## 2. The rules that make the number honest

**The operator does not know which fault was injected.** The runner picks
from the implemented catalogue at random and prints nothing but a start
marker. Without this the exercise measures repair speed, not detection or
diagnosis, and those are two thirds of what Kavach is being compared on.

**The operator does not see Kavach's diagnosis.** They get the target, its
`/metrics`, Prometheus at `:9091`, the application logs and the repository —
everything a real on-call engineer would have. They do **not** get Kavach's
console, its incident list, or its proposed plan. Showing them Kavach's
verdict and then timing them against Kavach measures reading speed.

**Kavach runs in `SIMULATION` alongside, and this is the best part of the
design.** It observes the same incident, forms a diagnosis and a plan, and
writes nothing. So each run yields a *paired* observation on the identical
incident — human time against Kavach's plan and whether that plan was right
— rather than two unpaired samples taken minutes apart on a drifting system.
`docs/decisions/0006` is why SIMULATION is safe to leave running.

**The operator may use anything except Kavach.** Editing config by hand,
`docker logs`, reading the source, grep. Restricting their tooling to make
the comparison flattering would invalidate it.

**One operator may not run a fault class twice.** The second injection of a
class is trivially fast because they remember it, and that is a memory
measurement. With four classes and a team of four, rotate so no one repeats.

## 3. Known biases, and which way each one cuts

State these in the report. A reviewer will find them in one question, and
naming them first is worth more than the number.

| Bias | Direction | Why it is acceptable |
|---|---|---|
| The operators **built this system** and know the fault catalogue by heart | **Favours the human**, makes Kavach look worse | The safe direction. A result that survives a biased-against-Kavach baseline is a stronger result |
| The corpus is small and the fast set is 3 cases, so verification is fast | Favours the human | Same verification Kavach uses; it is not an advantage either side has |
| Only four fault classes, all previously documented | Favours the human | Stated with the denominator, as `PRD.md` §10.2 requires for localization |
| A laptop demo machine; no pager, no 3am, no other incidents competing | **Strongly favours the human** | The most important caveat to state. Real on-call MTTR is dominated by notice-and-context-switch time, which this protocol excludes entirely by starting the clock at injection |

That last row is the one to be most careful about in writing. This protocol
measures a human **already sitting at the machine and already paying
attention**. `PRD.md` §10 glosses the human MTTD baseline as *"when a user
complains"* — this measurement is dramatically kinder than that, and the
report must not quote it as if it were on-call performance.

## 4. Sample size

`PRD.md` §10.3 says "the same 35 injections", written when the catalogue was
eight classes. Four are implemented, so:

**4 classes × 3 repetitions × (rotating operators) = 12 runs.**

At an estimated 5–10 minutes each that is 60–120 minutes, which is the two
hours the roadmap budgets. Three repetitions per class is thin and should be
reported as thin — it is enough to show an order of magnitude, not enough for
a confidence interval, and the report should give the raw times per run
rather than only a mean.

## 5. Running it

```bash
# one run, random blind fault, times the operator, verifies, records
uv run --project apps/control-plane python -I harness/human_baseline.py \
    --operator <name>

# the whole session
uv run --project apps/control-plane python -I harness/human_baseline.py \
    --operator <name> --runs 3
```

The runner injects, waits for the operator to press enter at each milestone,
verifies with the real fast set, reverts whatever is still broken, and
appends to `harness/reports/human-baseline.json`. It refuses to record a run
as resolved when verification fails, and records it as a **false recovery**
instead.

**Before each session:** confirm the stack is healthy and the corpus
fingerprint matches (`30 chunks / 2 files`). A session run on a drifted
corpus measures the drift, and `PRD.md` §12 records that happening twice.

## 6. What to do with the output

Report per fault class, not pooled:

- human MTTD, MTTR (median and raw values, n=3)
- Kavach MTTD, MTTR on the same class
- **P(Kavach's SIMULATION plan was correct | same incident)** — the paired
  number, and the one worth the most
- false recoveries, on both sides, counted not averaged

A pooled mean across four classes hides that `F01` is trivial for a human
(the logs say `ConnectionError`) while `F07` and `F08` are not — the two
classes that are behaviourally identical and separable only by which artifact
drifted. **That contrast is the result.** If humans are fast on `F01` and slow
on the `F07`/`F08` pair while Kavach is uniform, that says something specific
and defensible about where an automated differ beats a person, and it is a
much better finding than a single ratio.
