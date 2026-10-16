"""F08 config / environment regression.

Clamps the target's `max_tokens` so generated answers are truncated before the
figure the fast-verification set is looking for can appear. Retrieval still
works, the chunks are still retrieved, the endpoint still answers, and the
response still carries its `**Sources:**` block - only the content is cut off.

THE SIGNATURE IS WHY THIS SETTING AND NOT ANOTHER
`F08` has to be distinguishable from every other config-driven class, and the
`settable` list is short. Measured on the live target:

    keyword_present  False   the figure never appears - the answer is cut
    non_refusal      True    it is NOT a refusal; the model answered
    sources_block    True    chunks WERE retrieved and cited
    llm_error_ratio  0.0     the endpoint answered every call
    kept_chunks      healthy grounding is entirely intact

Nothing else in the catalogue produces that. `F06` requires grounding LOST
(`kept_chunks` at zero, `empty_context` at one); here grounding is perfect.
`F01` requires a high error ratio; here it is zero. So the three config-driven
classes separate on evidence rather than on registration order.

THE CLAMP WAS SWEPT, NOT CHOSEN, AND THE SWEEP NEEDED REPETITIONS
Three fast-set cases at each value, three repetitions each, against the live
clean system on 2026-10-16:

    max_tokens   fv-01  fv-02  fv-03        verdict
    0 (default)  pass   pass   pass         healthy baseline
    8            fail   fail   pass         partial collapse
    4            fail   fail   1 fail/2 pass  PARTIAL, NON-DETERMINISTIC
    3            fail   fail   pass pass pass  partial collapse
    2            fail   fail   fail fail fail  FULL COLLAPSE  <- chosen
    1            fail   fail   fail fail fail  full collapse

2 is the chosen value: the HIGHEST tested clamp that fails all three cases in
every repetition, which is the least aggressive misconfiguration that still
collapses quality completely - the closest thing to a realistic operator error.

1 was rejected despite also collapsing. At one token the model emits a bare
"The" and produces no content at all; that is a degenerate boundary rather
than a measured property of this system, and it would collapse any corpus with
any prompt. Same reasoning that rejected a 1.0 rerank threshold for `F06`.

4 IS THE FINDING WORTH KEEPING. It fails all three on one run and passes
`fv-03` on the next, because "91.2%" sometimes fits in four tokens and
sometimes does not. `f06_retrieval_collapse.py` records that "the reranker is
deterministic - results were identical across reps at every value". GENERATION
IS NOT, and a single-repetition sweep here would have picked 4 and produced an
injector that silently fails to inject about two runs in three. The repetitions
are the reason this constant is trustworthy.

NOT TOUCHED: the corpus, the embedding model, the prompts, the rerank
threshold, the LLM endpoint, and every setting other than `max_tokens`. The
injector asserts the first and the last of those.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from harness.faults.base import Fault, InjectionRecord
from kavach.target import TargetClient

# Measured: the highest clamp that fails all three fast-verification cases in
# every repetition. See the module docstring for the sweep.
BAD_MAX_TOKENS = 2

# Documented for reference; not used as a fallback. revert() replays the
# captured pre-state, never a constant.
EXPECTED_HEALTHY_MAX_TOKENS = 0

SETTING = "max_tokens"


class F08ConfigRegression(Fault):
    fault_class = "F08"
    fault_name = "config_regression"
    service = "backend"

    def __init__(
        self,
        client: TargetClient,
        corpus_probe: Callable[[], dict[str, Any]] | None = None,
        bad_max_tokens: int = BAD_MAX_TOKENS,
    ) -> None:
        super().__init__()
        self.client = client
        self.bad_max_tokens = int(bad_max_tokens)
        # Injected so the injector can assert corpus immutability without
        # reaching into the database itself.
        self._corpus_probe = corpus_probe or (lambda: {})

    # --- state --------------------------------------------------------------

    def current_max_tokens(self) -> int:
        return int(self.client.settings()[SETTING])

    def is_active(self) -> bool:
        return self.current_max_tokens() == self.bad_max_tokens

    # --- inject / revert ----------------------------------------------------

    def inject(self) -> InjectionRecord:
        settings = self.client.settings()
        if SETTING not in settings:
            raise RuntimeError(
                f"target does not expose {SETTING!r}; cannot inject F08"
            )

        # Capture everything first. revert() restores from this, not a constant.
        self.record.pre_state = {
            "settings": dict(settings),
            "config_hash": self.client.config_hash(),
        }
        self.record.corpus_before = self._corpus_probe()

        self.client.apply_settings({SETTING: self.bad_max_tokens})
        self.record.applied = {SETTING: self.bad_max_tokens}
        self._stamp_injected()
        return self.record

    def revert(self) -> InjectionRecord:
        prior = self.record.pre_state.get("settings")
        if not prior:
            # Nothing captured means nothing was injected. Reverting to a
            # guessed value would be worse than doing nothing.
            return self.record
        self.client.apply_settings({SETTING: prior[SETTING]})
        self.record.corpus_after = self._corpus_probe()
        self._stamp_reverted()
        return self.record

    # --- assertions the injector owns ---------------------------------------

    def assert_scope_respected(self) -> tuple[bool, str]:
        """Only max_tokens may differ from the pre-state.

        This matters more for F08 than for the other injectors: the whole
        detection signal is "which settings drifted from the baseline", so an
        injector that moved a second setting would manufacture the very
        evidence the detector is being tested on.
        """
        before = self.record.pre_state.get("settings", {})
        if not before:
            return False, "no pre-state captured"
        live = self.client.settings()
        drift = {
            k: {"before": before.get(k), "live": live.get(k)}
            for k in before
            if k != SETTING and live.get(k) != before.get(k)
        }
        if drift:
            return False, f"unrelated settings changed: {drift}"
        return True, f"only {SETTING} differs from the pre-state"

    def assert_corpus_unchanged(self) -> tuple[bool, str]:
        after = self._corpus_probe()
        before = self.record.corpus_before
        if not before:
            return False, "no corpus fingerprint captured before injection"
        if before != after:
            return False, f"CORPUS MUTATED: {before} -> {after}"
        return True, f"corpus unchanged {after}"

    def restored_exactly(self) -> tuple[bool, str]:
        """The live value equals the captured pre-state value, exactly."""
        want = self.record.pre_state.get("settings", {}).get(SETTING)
        if want is None:
            return False, f"no pre-state {SETTING} captured"
        live = self.current_max_tokens()
        if live != want:
            return False, f"not restored: wanted {want}, live {live}"
        return True, f"restored to the captured value {want}"
