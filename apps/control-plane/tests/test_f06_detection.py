"""F06 detector tests. Pure functions, no network, fully deterministic.

The detector's job is not only to fire on a real collapse but to REFUSE to
claim retrieval_collapse when the evidence points elsewhere. A detector that
says retrieval_collapse whenever the fast set fails would send a config
rollback at a broken corpus, which is the symptom-matching failure the project
is meant to avoid. Most of these tests are that refusal.
"""

from kavach.detection.retrieval_collapse import Thresholds, Verdict, evaluate

HEALTHY: dict[str, float | None] = {
    "similarity_p50": 0.658,     # measured healthy baseline
    "kept_chunks_mean": 2.73,
    "empty_context_ratio": 0.0,
    "corpus_chunks": 30.0,
}

COLLAPSED: dict[str, float | None] = {
    # What a too-high rerank threshold looks like: similarity UNCHANGED,
    # grounding gone.
    "similarity_p50": 0.658,
    "kept_chunks_mean": 0.0,
    "empty_context_ratio": 1.0,
    "corpus_chunks": 30.0,
}


def test_healthy_baseline_detects_nothing() -> None:
    d = evaluate(HEALTHY, fast_set_passed=True, fast_set_pass_rate=1.0)
    assert d.verdict is Verdict.NO_FAULT
    assert not d.detected


def test_collapse_is_detected_as_retrieval_collapse() -> None:
    d = evaluate(COLLAPSED, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is Verdict.RETRIEVAL_COLLAPSE
    assert d.detected
    assert d.fault_class == "F06"
    assert d.fault_name == "retrieval_collapse"
    assert d.service == "backend"


def test_detection_cites_supporting_evidence() -> None:
    d = evaluate(COLLAPSED, fast_set_passed=False, fast_set_pass_rate=0.0)
    citations = d.citations()
    assert citations, "a diagnosis with no cited evidence is not inspectable"
    joined = " ".join(citations)
    assert "kept_chunks" in joined
    assert "empty_context_ratio" in joined
    assert "similarity_p50" in joined


def test_low_similarity_is_not_retrieval_collapse() -> None:
    """The discriminator. Grounding is lost AND similarity collapsed, so the
    fault is upstream of the rerank filter - embeddings or corpus. A config
    rollback would be the wrong repair, so the detector must refuse."""
    broken_embeddings = dict(COLLAPSED, similarity_p50=0.05)
    d = evaluate(broken_embeddings, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert not d.detected
    assert any("upstream of the rerank filter" in r for r in d.reasons)


def test_empty_corpus_is_not_retrieval_collapse() -> None:
    d = evaluate(dict(COLLAPSED, corpus_chunks=0.0),
                 fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert any("corpus is empty" in r for r in d.reasons)


def test_fast_set_failure_with_healthy_grounding_is_not_collapse() -> None:
    """Something else broke. Not our fault class."""
    d = evaluate(HEALTHY, fast_set_passed=False, fast_set_pass_rate=0.33)
    assert d.verdict is Verdict.INSUFFICIENT_EVIDENCE


def test_missing_similarity_series_refuses_to_guess() -> None:
    """No data is not zero, and it is not healthy either."""
    d = evaluate(dict(COLLAPSED, similarity_p50=None),
                 fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert any("cannot be distinguished" in r for r in d.reasons)


def test_missing_grounding_series_does_not_fabricate_a_fault() -> None:
    missing: dict[str, float | None] = {
        "similarity_p50": 0.658, "kept_chunks_mean": None,
        "empty_context_ratio": None, "corpus_chunks": 30.0,
    }
    d = evaluate(
        missing,
        fast_set_passed=True, fast_set_pass_rate=1.0,
    )
    assert d.verdict is Verdict.NO_FAULT


def test_empty_context_alone_above_ceiling_detects() -> None:
    """Either grounding signal is sufficient; they are OR-ed."""
    d = evaluate(dict(HEALTHY, empty_context_ratio=0.9),
                 fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is Verdict.RETRIEVAL_COLLAPSE


def test_thresholds_match_the_rebased_slos() -> None:
    t = Thresholds()
    assert t.similarity_floor == 0.50, "must track kavach.yaml retrieval_similarity_p50"
    assert t.empty_context_ceiling == 0.20, "must track kavach.yaml empty_context_ratio"


def test_evaluate_is_deterministic() -> None:
    a = evaluate(COLLAPSED, False, 0.0).to_dict()
    b = evaluate(COLLAPSED, False, 0.0).to_dict()
    assert a == b


def test_borderline_values_do_not_trip_detection() -> None:
    """Exactly at the floor/ceiling is still healthy; only crossing counts."""
    borderline: dict[str, float | None] = {
        "similarity_p50": 0.50,       # == floor
        "kept_chunks_mean": 1.0,      # == floor
        "empty_context_ratio": 0.20,  # == ceiling
        "corpus_chunks": 30.0,
    }
    d = evaluate(borderline, fast_set_passed=True, fast_set_pass_rate=1.0)
    assert d.verdict is Verdict.NO_FAULT


def test_stale_window_does_not_trigger_a_repair() -> None:
    """The regression this exists for.

    Grounding metrics are rates over 10 minutes and therefore lag. After a
    fault is reverted the window still remembers it. If that outvoted the fast
    set, Kavach would "heal" a system that is already working - a self-inflicted
    write recorded as a successful heal of nothing. This was a real false
    positive observed against the live stack.
    """
    d = evaluate(COLLAPSED, fast_set_passed=True, fast_set_pass_rate=1.0)
    assert d.verdict is Verdict.NO_FAULT
    assert not d.detected
    assert any("not currently present" in r for r in d.reasons)


def test_current_evidence_is_required_for_a_fault_claim() -> None:
    """Same metrics, differing only in whether the symptom is live."""
    stale = evaluate(COLLAPSED, fast_set_passed=True, fast_set_pass_rate=1.0)
    live = evaluate(COLLAPSED, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert stale.verdict is Verdict.NO_FAULT
    assert live.verdict is Verdict.RETRIEVAL_COLLAPSE
