"""F07 prompt version regression.

Rewrites the target's `answer.txt` to a plausibly-bad edit, so the model keeps
answering from retrieved context but stops producing the specific figures the
fast-verification set looks for.

NOTHING IS RESTARTED, AND THAT IS A PROPERTY OF THE TARGET, NOT A SHORTCUT
`prompts_loader` reads each prompt per request with no cache, deliberately, so
that a revert "takes effect without a rebuild or restart". The file is written
on the host and the target reads it through a read-only bind mount, so the
next request uses the new text. An injector that needed `docker restart` would
be injecting a restart as well as a prompt change.

WHY THIS EDIT AND NOT A REFUSAL
The obvious injection - instruct the model to refuse - is wrong here, and the
reason is in the target's own code. `rag.py` appends the `**Sources:**` block
only when the answer is NOT a fallback:

    is_fallback = "don't know" in lowered_answer or ...
    if citations and not is_fallback and return_sources:

So a prompt that induces a refusal ALSO suppresses the sources block, and the
fast set then reads `non_refusal=False, sources_block=False` - which is
exactly F06's signature. Detection would still separate them, because F06
claims on retrieval metrics and a prompt cannot move those, but the evidence
frame would show the RCA model a refusal with no sources and invite the F06
answer it already defaults to. Manufacturing that is the injector's fault, not
the model's.

The edit used instead keeps the model answering and grounded, and removes only
the specifics:

    keyword_present  False   the figure never appears - it was suppressed
    non_refusal      True    the model answered
    sources_block    True    chunks WERE retrieved and cited
    llm_error_ratio  0.0     the endpoint answered every call
    kept_chunks      healthy grounding is entirely intact

That is the same fast-set shape as F08, and deliberately so. F07 and F08 are
behaviourally indistinguishable at the symptom level and separate ONLY on
which artifact drifted from its captured known-good - a prompt digest for one,
a settings key for the other. A catalogue where every class has a distinct
symptom would not test discrimination at all.

THE EDIT IS A WRONG PROMPT, NOT A WEAKENED ONE, AND THE SWEEP SAYS WHY

Measured live on 2026-10-17, five candidates, three repetitions of the full
three-case fast set each (nine queries per candidate):

    candidate                        lost keyword   verdict
    B  "ignore the context,
        answer from your own
        knowledge"                   0 of 3 x3      NO INJECTION AT ALL
    C  "answer in at most
        five words"                  0 of 3 x3      NO INJECTION AT ALL
    D  "do not answer; list
        the topics"                  3 of 3 x3      full collapse
    F  "you are a summarisation
        assistant"                   3 of 3 x3      FULL COLLAPSE  <- chosen
    G  "answer a different
        question"                    1-2 of 3       PARTIAL, NON-DETERMINISTIC

THE FINDING THAT EXPLAINS THE WHOLE TABLE: this model obeys instructions
about the FORM or the TASK of its answer, and ignores instructions to
WITHHOLD information that is sitting in its context. A marker probe pinned
this down separately - told to "begin every answer with the exact word
BANANA" it complied immediately, while told to disregard the context it
answered "The LSTM model achieved a ROC-AUC of 0.91" from that very context.
B and E (an earlier "do not quote specific figures" wording, also 0 of 3) are
both suppression directives and both failed. D and F are task directives and
both worked.

C IS THE FINDING WORTH KEEPING, and it is the mirror image of F08's. F08
injects by truncating the answer, so one might expect a brevity instruction
to do the same thing through the prompt. It does not: told to answer in five
words the model replied "0.91", which IS the keyword. Truncation removes a
figure only when the figure comes late in a sentence; an instruction to be
brief makes the model lead with it. The two faults are not reachable by the
same mechanism from different directions.

F IS CHOSEN OVER D, which also collapsed 3 of 3. D contains "Do NOT include
figures, percentages or measurements", which engineers the injection around
the thing the fast set happens to check - the keyword is lost because the
injector asked for it to be. F says nothing about figures at all. It replaces
the answering task with a summarising one, the keyword disappears as a
CONSEQUENCE of the degradation rather than as its mechanism, and the slip it
models - a prompt file pasted over with the contents of another one - is a
regression that actually happens. G was rejected for the reason F08 rejected
a four-token clamp: partial and non-deterministic is an injector that
silently fails to inject.

STILL NOT MEASURED: the 20-cycle manifestation rate. Three repetitions
established which candidate to choose; they do not establish how often the
chosen one manifests. F08 manifests 46 times in 50, and the equivalent number
for F07 is what `stability_f07.py` exists to produce. `assert_symptom_shape()`
runs on every injection so a run cannot quietly pass while injecting the
wrong fault - it is what caught the first attempt, which changed the file
correctly and degraded nothing.

NOT TOUCHED: the corpus, the embedding model, every runtime setting, the LLM
endpoint, and `query_expansion.txt`. The injector asserts the first, the
second-to-last and the last of those.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from harness.faults.base import Fault, InjectionRecord
from kavach.target import TargetClient

# The one file this injector touches. `query_expansion.txt` is left alone so
# `unchanged_elsewhere` on the repair has something real to verify.
PROMPT_FILE = "answer.txt"

# SWEPT, not chosen: 3 of 3 cases lost in every one of three repetitions.
# See the module docstring for the five candidates and why this one.
#
# Both placeholders are mandatory even though this prompt no longer uses
# the question: `prompts_loader.render()` raises on a missing one rather
# than returning a partially-filled prompt, and a raising prompt would be
# an endpoint error rather than a quality regression. Leaving {question}
# in and ignoring it is also what the real slip looks like.
DEGRADED_PROMPT = """You are a document summarisation assistant.
- Write one sentence describing what subject area the context below covers.
- This is a summary task. There is no question to answer.

CONTEXT:
{context}

QUESTION:
{question}

ANSWER:
"""


def digest(text: str) -> str:
    """The digest the target reports for a prompt file, so the two compare."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class F07PromptRegression(Fault):
    fault_class = "F07"
    fault_name = "prompt_regression"
    service = "backend"

    def __init__(
        self,
        client: TargetClient,
        prompts_dir: str | Path,
        corpus_probe: Callable[[], dict[str, Any]] | None = None,
        degraded_prompt: str = DEGRADED_PROMPT,
    ) -> None:
        super().__init__()
        self.client = client
        self.prompts_dir = Path(prompts_dir)
        self.degraded_prompt = degraded_prompt
        self._corpus_probe = corpus_probe or (lambda: {})

    # --- state --------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self.prompts_dir / PROMPT_FILE

    def reported_digests(self) -> dict[str, str]:
        """What the RUNNING target hashes its prompts to."""
        cfg = self.client.config()
        return dict((cfg.get("prompt_version") or {}).get("files") or {})

    def is_active(self) -> bool:
        """True when the TARGET reports the degraded digest.

        Deliberately not `self.path.read_text() == self.degraded_prompt`. That
        would confirm the file was written, which is never in doubt; what is
        in doubt is whether the container reads this directory at all, and
        only the target can answer that.
        """
        return self.reported_digests().get(PROMPT_FILE) == digest(self.degraded_prompt)

    # --- inject / revert ----------------------------------------------------

    def inject(self) -> InjectionRecord:
        if not self.path.is_file():
            raise RuntimeError(f"no prompt file at {self.path}; cannot inject F07")

        before = self.path.read_text(encoding="utf-8")
        reported = self.reported_digests()
        if reported.get(PROMPT_FILE) != digest(before):
            # The host file and the file the container reads are not the same
            # file. Injecting here would change nothing the target can see,
            # and the run would record a fault that never happened.
            raise RuntimeError(
                f"{self.path} hashes to {digest(before)} but the target "
                f"reports {reported.get(PROMPT_FILE)} for {PROMPT_FILE}; the "
                f"control plane is not looking at the directory the target "
                f"reads, so this injection would not reach it"
            )

        self.record.pre_state = {
            "prompt_text": {PROMPT_FILE: before},
            "prompt_version": reported,
            "settings": dict(self.client.settings()),
            "config_hash": self.client.config_hash(),
        }
        self.record.corpus_before = self._corpus_probe()

        self.path.write_text(self.degraded_prompt, encoding="utf-8", newline="")
        self.record.applied = {PROMPT_FILE: digest(self.degraded_prompt)}
        self._stamp_injected()
        return self.record

    def revert(self) -> InjectionRecord:
        prior = self.record.pre_state.get("prompt_text")
        if not prior:
            # Nothing captured means nothing was injected. Writing a guessed
            # prompt back would be worse than doing nothing.
            return self.record
        self.path.write_text(prior[PROMPT_FILE], encoding="utf-8", newline="")
        self.record.corpus_after = self._corpus_probe()
        self._stamp_reverted()
        return self.record

    # --- assertions the injector owns ---------------------------------------

    def assert_scope_respected(self) -> tuple[bool, str]:
        """Only `answer.txt` may differ, and no runtime setting may have moved.

        Both halves matter. A second prompt file would make the repair's
        `unchanged_elsewhere` check vacuous, and a moved setting would
        manufacture F08's evidence during an F07 run - which would make the
        one discrimination this fault class exists to test meaningless.
        """
        before_pv = self.record.pre_state.get("prompt_version", {})
        if not before_pv:
            return False, "no pre-state captured"
        live_pv = self.reported_digests()
        drift = {
            n: {"before": before_pv.get(n), "live": live_pv.get(n)}
            for n in set(before_pv) | set(live_pv)
            if n != PROMPT_FILE and live_pv.get(n) != before_pv.get(n)
        }
        if drift:
            return False, f"unrelated prompt files changed: {drift}"

        before_s = self.record.pre_state.get("settings", {})
        live_s = self.client.settings()
        moved = {k: {"before": before_s.get(k), "live": live_s.get(k)}
                 for k in before_s if live_s.get(k) != before_s.get(k)}
        if moved:
            return False, f"runtime settings changed during an F07 injection: {moved}"
        return True, f"only {PROMPT_FILE} differs, and no setting moved"

    def assert_symptom_shape(self, cases: list[Any]) -> tuple[bool, str]:
        """The fast set must fail the way F07 fails, not the way F06 fails.

        Given the fast set's `CaseMeasurement`s taken under injection. A
        refusal with no sources block is F06's shape; seeing it here means the
        degraded prompt induced the wrong fault and every number from the run
        describes something other than F07.
        """
        if not cases:
            return False, "no fast-set cases supplied"
        refusals = [c.case_id for c in cases if not c.non_refusal]
        ungrounded = [c.case_id for c in cases if not c.sources_block]
        if refusals or ungrounded:
            return False, (
                f"the degraded prompt produced an F06-SHAPED symptom: "
                f"refusals={refusals} missing_sources={ungrounded}. F07 must "
                f"leave the model answering and grounded; only the specifics "
                f"should be lost. The injected text needs re-wording"
            )
        broke = [c.case_id for c in cases if not c.keyword_present]
        if not broke:
            return False, (
                "every fast-set case still found its keyword, so the prompt "
                "regression did not manifest on this injection"
            )
        return True, (
            f"F07 shape: {len(broke)}/{len(cases)} lost the keyword, all "
            f"answered, all grounded"
        )

    def assert_corpus_unchanged(self) -> tuple[bool, str]:
        after = self._corpus_probe()
        before = self.record.corpus_before
        if not before:
            return False, "no corpus fingerprint captured before injection"
        if before != after:
            return False, f"CORPUS MUTATED: {before} -> {after}"
        return True, f"corpus unchanged {after}"

    def restored_exactly(self) -> tuple[bool, str]:
        """The TARGET reports the captured pre-state digest, exactly."""
        want = self.record.pre_state.get("prompt_version", {}).get(PROMPT_FILE)
        if want is None:
            return False, f"no pre-state digest captured for {PROMPT_FILE}"
        live = self.reported_digests().get(PROMPT_FILE)
        if live != want:
            return False, f"not restored: wanted {want}, target reports {live}"
        return True, f"restored to the captured digest {want}"
