"""Baseline logic tests.

The parts that decide whether an artifact is usable. A baseline wrongly marked
healthy is the worst outcome in this module: every later comparison would
inherit the fault as normal, so the guards get the tests.
"""

from kavach.onboarding.baseline import Baseline, CaseMeasurement, compare


def _case(cid: str = "fv-01", *, kw: bool = True, nonref: bool = True,
          src: bool = True, lat: float = 6.0) -> CaseMeasurement:
    return CaseMeasurement(
        case_id=cid, question="q", expected_keyword="0.91",
        keyword_present=kw, non_refusal=nonref, sources_block=src, latency_s=lat,
    )


def test_case_passes_only_when_all_three_checks_hold() -> None:
    assert _case().passed
    assert not _case(kw=False).passed
    assert not _case(nonref=False).passed
    # The grounding check is the one that makes the probe detect retrieval
    # failure; a case passing without it would report healthy with retrieval
    # destroyed.
    assert not _case(src=False).passed


def test_ungrounded_case_is_not_a_pass() -> None:
    """A keyword-matching, non-refusing answer with no Sources block came from
    model parameters, not the corpus. It must not count."""
    c = _case(kw=True, nonref=True, src=False)
    assert c.keyword_present and c.non_refusal
    assert not c.passed


def test_compare_detects_config_drift() -> None:
    old = Baseline(captured_at="t0", project="p", healthy=True, config_hash="aaa")
    new = Baseline(captured_at="t1", project="p", healthy=True, config_hash="bbb")
    assert any("config_hash" in d for d in compare(old, new))


def test_compare_detects_prompt_change() -> None:
    old = Baseline(captured_at="t0", project="p", healthy=True,
                   prompt_version={"files": {"answer.txt": "aaa"}})
    new = Baseline(captured_at="t1", project="p", healthy=True,
                   prompt_version={"files": {"answer.txt": "zzz"}})
    assert any("prompt" in d for d in compare(old, new))


def test_compare_detects_corpus_change() -> None:
    old = Baseline(captured_at="t0", project="p", healthy=True,
                   corpus_fingerprint={"chunks": 30.0, "files": 2.0})
    new = Baseline(captured_at="t1", project="p", healthy=True,
                   corpus_fingerprint={"chunks": 12.0, "files": 1.0})
    assert any("corpus" in d for d in compare(old, new))


def test_compare_detects_threshold_change() -> None:
    old = Baseline(captured_at="t0", project="p", healthy=True, rerank_threshold=0.35)
    new = Baseline(captured_at="t1", project="p", healthy=True, rerank_threshold=0.9)
    assert any("rerank_threshold" in d for d in compare(old, new))


def test_compare_flags_large_latency_shift_only() -> None:
    old = Baseline(captured_at="t0", project="p", healthy=True, cases=[_case(lat=6.0)])
    same = Baseline(captured_at="t1", project="p", healthy=True, cases=[_case(lat=6.5)])
    slow = Baseline(captured_at="t1", project="p", healthy=True, cases=[_case(lat=20.0)])
    assert not any("latency" in d for d in compare(old, same))
    assert any("latency" in d for d in compare(old, slow))


def test_identical_captures_show_no_drift() -> None:
    a = Baseline(captured_at="t0", project="p", healthy=True, config_hash="h",
                 rerank_threshold=0.35, cases=[_case()],
                 corpus_fingerprint={"chunks": 30.0},
                 prompt_version={"files": {"answer.txt": "d"}})
    b = Baseline(captured_at="t1", project="p", healthy=True, config_hash="h",
                 rerank_threshold=0.35, cases=[_case()],
                 corpus_fingerprint={"chunks": 30.0},
                 prompt_version={"files": {"answer.txt": "d"}})
    assert compare(a, b) == []


def test_render_marks_an_unhealthy_baseline_unusable() -> None:
    bl = Baseline(captured_at="t", project="p", healthy=False,
                  cases=[_case(kw=False)], problems=["something broke"])
    text = bl.render()
    assert "NOT USABLE AS A BASELINE" in text
    assert "something broke" in text


def test_round_trips_to_dict() -> None:
    bl = Baseline(captured_at="t", project="p", healthy=True, cases=[_case()])
    d = bl.to_dict()
    assert d["project"] == "p"
    assert d["cases"][0]["case_id"] == "fv-01"
