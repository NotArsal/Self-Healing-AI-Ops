"""F06 retrieval collapse.

Raises the target's rerank threshold so that every retrieved chunk is filtered
out. Retrieval still runs, embeddings still work, similarity stays healthy, and
the application returns HTTP 200 with "I don't know based on the provided
documents." That silent-200 behaviour is the fault, and it already exists in the
target - this injector does not simulate it, it triggers it.

THE BAD VALUE WAS MEASURED, NOT CHOSEN
A sweep applied each candidate through the target's config interface and ran the
real 3-case fast-verification set three times at each:

    threshold   fast-set passes per rep   verdict
    0.35        [3, 3, 3]                 healthy baseline
    0.97        [3, 3, 3]                 healthy
    0.98        [2, 2, 2]                 partial collapse
    0.99        [1, 1, 1]                 partial collapse
    0.995       [1, 1, 1]                 partial collapse
    0.999       [0, 0, 0]                 FULL COLLAPSE  <- chosen
    1.0         [0, 0, 0]                 full collapse

0.999 is the chosen value: the lowest tested threshold that fails all three
cases in every repetition. The reranker is deterministic - results were
identical across reps at every value - so the partial results are genuine
partial collapse, not flakiness.

1.0 was rejected despite also collapsing: the reranker emits sigmoid scores that
approach but never reach 1.0, so a 1.0 threshold would collapse retrieval on any
corpus regardless of content. That is a degenerate boundary rather than a
measured property of this system, and it would still "work" if the corpus were
replaced - which would make it useless as evidence.

NOT TOUCHED: the corpus, the embedding model, the prompts, and every setting
other than rerank_threshold. The injector asserts this.
"""

from __future__ import annotations

from typing import Any, Callable

from harness.faults.base import Fault, InjectionRecord
from kavach.target import TargetClient

# Measured: the lowest threshold that fails all three fast-verification cases
# in every repetition. See the module docstring for the sweep.
BAD_THRESHOLD = 0.999

# Documented for reference; not used as a fallback. revert() replays the
# captured pre-state, never a constant.
EXPECTED_HEALTHY_THRESHOLD = 0.35

SETTING = "rerank_threshold"


class F06RetrievalCollapse(Fault):
    fault_class = "F06"
    fault_name = "retrieval_collapse"
    service = "backend"

    def __init__(
        self,
        client: TargetClient,
        corpus_probe: Callable[[], dict[str, Any]] | None = None,
        bad_threshold: float = BAD_THRESHOLD,
    ) -> None:
        super().__init__()
        self.client = client
        self.bad_threshold = float(bad_threshold)
        # Injected so the injector can assert corpus immutability without
        # reaching into the database itself.
        self._corpus_probe = corpus_probe or (lambda: {})

    # --- state --------------------------------------------------------------

    def current_threshold(self) -> float:
        return float(self.client.settings()[SETTING])

    def is_active(self) -> bool:
        return self.current_threshold() == self.bad_threshold

    # --- inject / revert ----------------------------------------------------

    def inject(self) -> InjectionRecord:
        settings = self.client.settings()
        if SETTING not in settings:
            raise RuntimeError(f"target does not expose {SETTING!r}; cannot inject F06")

        # Capture everything first. revert() restores from this, not a constant.
        self.record.pre_state = {
            "settings": dict(settings),
            "config_hash": self.client.config_hash(),
        }
        self.record.corpus_before = self._corpus_probe()

        self.client.apply_settings({SETTING: self.bad_threshold})
        self.record.applied = {SETTING: self.bad_threshold}
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
        """Only rerank_threshold may differ from the pre-state."""
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
        return True, "only rerank_threshold differs from the pre-state"

    def assert_corpus_unchanged(self) -> tuple[bool, str]:
        after = self._corpus_probe()
        before = self.record.corpus_before
        if not before:
            return False, "no corpus fingerprint captured before injection"
        if before != after:
            return False, f"CORPUS MUTATED: {before} -> {after}"
        return True, f"corpus unchanged {after}"

    def restored_exactly(self) -> tuple[bool, str]:
        """The live threshold equals the captured pre-state value, exactly."""
        want = self.record.pre_state.get("settings", {}).get(SETTING)
        if want is None:
            return False, "no pre-state threshold captured"
        live = self.current_threshold()
        if live != want:
            return False, f"not restored: wanted {want}, live {live}"
        return True, f"restored to the captured value {want}"
