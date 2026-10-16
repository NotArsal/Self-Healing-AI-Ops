"""LLM RCA tests. Zero network calls — recorded responses only.

AGENTS.md forbids calling a model in CI, and these need to be deterministic
anyway: most of them assert that a *bad* model response is refused, which
requires producing bad responses on demand.

The weight is on rejection. An RCA layer that accepts a correct diagnosis is
easy; one that refuses a confident wrong one is the whole point, because
SREGym's finding is that mitigation succeeds 22-62% of the time even when the
diagnosis is wrong. Every rejection path gets a test.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kavach.detection import retrieval_collapse as rc
from kavach.llm.client import LlmError, LlmResponse, assert_not_proxied
from kavach.rca.engine import RcaResult, build_prompt, diagnose
from kavach.rca.evidence import EvidenceFrame, reading
from kavach.rca.schema import Diagnosis, ollama_schema
from kavach.rca.validate import Outcome, supported_fault_classes, validate

THRESHOLD = 0.75
SERVICES = {"backend", "db", "frontend", "toxiproxy", "prometheus"}


# --- fixtures ---------------------------------------------------------------


def collapsed_frame() -> EvidenceFrame:
    """Evidence as it looks under a real F06: similarity fine, grounding gone."""
    f = EvidenceFrame(collected_at="2026-10-03T00:00:00+00:00")
    f.add(eid="EV-M01", kind="metric", name="retrieval_top_similarity_p50",
          value=0.658, expected=">= 0.50")
    f.add(eid="EV-M02", kind="metric", name="retrieval_kept_chunks_mean",
          value=0.0, expected=">= 1.0")
    f.add(eid="EV-M03", kind="metric", name="retrieval_empty_context_ratio",
          value=1.0, expected="< 0.20")
    f.add(eid="EV-M04", kind="metric", name="corpus_chunks", value=30.0)
    f.add(eid="EV-C01", kind="config", name="rerank_threshold", value=0.999)
    f.add(eid="EV-B01", kind="baseline", name="baseline_rerank_threshold", value=0.35)
    f.add(eid="EV-V00", kind="verification", name="fast_set_overall", value="FAIL (0%)")
    return f


def healthy_detection() -> rc.Detection:
    return rc.evaluate(
        {"similarity_p50": 0.658, "kept_chunks_mean": 2.73,
         "empty_context_ratio": 0.0, "corpus_chunks": 30.0},
        fast_set_passed=True, fast_set_pass_rate=1.0,
    )


def collapsed_detection() -> rc.Detection:
    return rc.evaluate(
        {"similarity_p50": 0.658, "kept_chunks_mean": 0.0,
         "empty_context_ratio": 1.0, "corpus_chunks": 30.0},
        fast_set_passed=False, fast_set_pass_rate=0.0,
    )


GOOD_DIAGNOSIS: dict[str, Any] = {
    "fault_class": "F06",
    "fault_name": "retrieval_collapse",
    "service": "backend",
    "confidence": 0.92,
    "evidence_ids": ["EV-M01", "EV-M02", "EV-M03", "EV-C01"],
    "reasoning": (
        "EV-M01 shows raw similarity at 0.658, which is healthy, so retrieval "
        "itself works. EV-M02 shows zero chunks kept and EV-M03 an empty-context "
        "ratio of 1.0, so everything retrieved is being filtered out. EV-C01 "
        "shows rerank_threshold at 0.999 against a known-good 0.35."
    ),
    "candidate_repair": "rollback_config",
    "rejected_alternatives": [
        {"fault_class": "F08", "reason": "only rerank_threshold differs; no other config moved"},
        {"fault_class": "F01", "reason": "llm_error_ratio is 0, the endpoint is serving"},
    ],
}


def recorded(
    payload: dict[str, Any] | str, latency: float = 3.2
) -> Callable[[str, str, dict[str, Any]], LlmResponse]:
    """An llm_call that replays a fixed response."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)

    def call(_system: str, _user: str, _schema: dict[str, Any]) -> LlmResponse:
        return LlmResponse(raw=raw, model="llama3.2(recorded)", latency_s=latency,
                           prompt_tokens=900, completion_tokens=120)
    return call


def run(
    payload: dict[str, Any] | str,
    frame: EvidenceFrame | None = None,
    detection: rc.Detection | None = None,
    threshold: float = THRESHOLD,
) -> RcaResult:
    return diagnose(
        frame or collapsed_frame(),
        detection if detection is not None else collapsed_detection(),
        threshold,
        llm_call=recorded(payload),
        declared_services=SERVICES,
    )


# --- 1. the happy path ------------------------------------------------------


def test_valid_rca_is_approved_and_maps_to_rollback_config() -> None:
    r = run(GOOD_DIAGNOSIS)
    assert r.approved, r.render()
    assert r.approved_action == "rollback_config"
    assert r.diagnosis is not None
    assert r.diagnosis.fault_class == "F06"
    assert r.diagnosis.fault_name == "retrieval_collapse"
    assert r.diagnosis.service == "backend"
    assert r.diagnosis.confidence == 0.92


def test_diagnosis_carries_explicit_evidence_and_confidence() -> None:
    r = run(GOOD_DIAGNOSIS)
    d = r.diagnosis
    assert d is not None
    assert len(d.evidence_ids) >= 2
    assert r.evidence is not None
    assert all(e in r.evidence.ids for e in d.evidence_ids)
    assert 0.0 <= d.confidence <= 1.0
    assert d.rejected_alternatives, "FR-10 requires alternatives considered and rejected"


# --- 2. healthy system ------------------------------------------------------


def test_healthy_system_rca_is_not_approved() -> None:
    """Even a model insisting on F06 cannot act when nothing is wrong."""
    r = run(GOOD_DIAGNOSIS, detection=healthy_detection())
    assert not r.approved
    assert any("deterministic_agreement" in x for x in r.rejection_reasons)


# --- 3. malformed output fails closed ---------------------------------------


def test_non_json_response_is_rejected() -> None:
    r = run("I think the retrieval pipeline is broken. Probably F06?")
    assert not r.approved
    assert r.diagnosis is None
    assert "not JSON" in r.error


def test_json_but_wrong_shape_is_rejected() -> None:
    r = run({"verdict": "broken", "why": "dunno"})
    assert not r.approved
    assert r.diagnosis is None
    assert "schema validation" in r.error


def test_invented_field_is_rejected() -> None:
    """extra="forbid": a model that adds a field is not partially understood."""
    r = run({**GOOD_DIAGNOSIS, "execute_now": True})
    assert not r.approved
    assert r.diagnosis is None


def test_confidence_out_of_range_is_rejected() -> None:
    r = run({**GOOD_DIAGNOSIS, "confidence": 1.7})
    assert not r.approved
    assert r.diagnosis is None


def test_fault_class_outside_the_catalogue_is_rejected() -> None:
    r = run({**GOOD_DIAGNOSIS, "fault_class": "F04"})
    assert not r.approved, "F04 is retired and must not be accepted"
    assert r.diagnosis is None


def test_llm_transport_failure_is_rejected_not_raised() -> None:
    def boom(_s: str, _u: str, _sc: dict[str, Any]) -> LlmResponse:
        raise LlmError("connection refused")
    r = diagnose(collapsed_frame(), collapsed_detection(), THRESHOLD, llm_call=boom)
    assert not r.approved
    assert "connection refused" in r.error


def test_missing_llm_entirely_is_rejected() -> None:
    r = diagnose(collapsed_frame(), collapsed_detection(), THRESHOLD)
    assert not r.approved
    assert r.validation is not None and not r.validation.accepted


# --- 4. wrong fault class ---------------------------------------------------


def test_wrong_fault_class_is_rejected_by_deterministic_validation() -> None:
    """A confident F01 against F06 evidence must not execute anything."""
    r = run({**GOOD_DIAGNOSIS, "fault_class": "F01",
             "fault_name": "primary_llm_endpoint_outage",
             "candidate_repair": "none"})
    assert not r.approved
    joined = " ".join(r.rejection_reasons)
    assert "fault_class_supported" in joined or "deterministic_agreement" in joined


def test_unsupported_but_real_fault_class_is_rejected() -> None:
    """F09 is a legitimate thing to say and an illegitimate thing to act on."""
    r = run({**GOOD_DIAGNOSIS, "fault_class": "F09",
             "fault_name": "token_blowout", "candidate_repair": "none"})
    assert not r.approved
    assert any("has no implementation" in x for x in r.rejection_reasons)


def test_wrong_service_is_rejected() -> None:
    r = run({**GOOD_DIAGNOSIS, "service": "db"})
    assert not r.approved
    assert any("deterministic_agreement" in x for x in r.rejection_reasons)


def test_undeclared_service_is_rejected() -> None:
    r = run({**GOOD_DIAGNOSIS, "service": "nginx"})
    assert not r.approved
    assert any("service_declared" in x for x in r.rejection_reasons)


# --- 5. low confidence ------------------------------------------------------


def test_low_confidence_is_rejected() -> None:
    r = run({**GOOD_DIAGNOSIS, "confidence": 0.40})
    assert not r.approved
    assert any("confidence_threshold" in x for x in r.rejection_reasons)


def test_confidence_exactly_at_threshold_is_accepted() -> None:
    r = run({**GOOD_DIAGNOSIS, "confidence": THRESHOLD})
    assert r.approved, r.render()


def test_threshold_comes_from_configuration_not_a_constant() -> None:
    """A stricter operator threshold must actually bind."""
    r = run({**GOOD_DIAGNOSIS, "confidence": 0.80}, threshold=0.95)
    assert not r.approved


# --- 6. honest non-answers --------------------------------------------------


def test_insufficient_evidence_is_respected_and_executes_nothing() -> None:
    r = run({**GOOD_DIAGNOSIS, "fault_class": "INSUFFICIENT_EVIDENCE",
             "fault_name": "insufficient_evidence", "candidate_repair": "none",
             "confidence": 0.9})
    assert not r.approved
    assert any("honest non-answer" in x for x in r.rejection_reasons)


def test_unknown_never_executes() -> None:
    """FR-29: UNKNOWN can never reach execution, at any confidence."""
    r = run({**GOOD_DIAGNOSIS, "fault_class": "UNKNOWN",
             "fault_name": "unknown", "candidate_repair": "none",
             "confidence": 1.0})
    assert not r.approved


# --- 7. fabricated citations ------------------------------------------------


def test_citation_to_nonexistent_evidence_is_rejected() -> None:
    """A citation resolving to nothing is a fabricated justification."""
    r = run({**GOOD_DIAGNOSIS, "evidence_ids": ["EV-M01", "EV-FAKE99"]})
    assert not r.approved
    assert any("does not exist" in x for x in r.rejection_reasons)


def test_too_few_citations_is_rejected() -> None:
    """Rejected at the SCHEMA layer now that minItems=2 is in the grammar.

    The validator still carries the same MIN_CITED_EVIDENCE rule as a second
    barrier, for a diagnosis that reaches it by some other route.
    """
    r = run({**GOOD_DIAGNOSIS, "evidence_ids": ["EV-M01"]})
    assert not r.approved
    assert r.diagnosis is None
    assert "schema validation" in r.error


def test_duplicate_citations_do_not_count_as_two() -> None:
    r = run({**GOOD_DIAGNOSIS, "evidence_ids": ["EV-M01", "EV-M01"]})
    assert not r.approved
    assert r.diagnosis is None, "duplicates are a schema violation"


# --- 8. repair vocabulary ---------------------------------------------------


def test_repair_outside_the_permitted_set_is_rejected() -> None:
    r = run({**GOOD_DIAGNOSIS, "candidate_repair": "restart_container"})
    assert not r.approved
    assert r.diagnosis is None, "an unimplemented action is not in the schema"


def test_repair_none_for_f06_is_rejected() -> None:
    r = run({**GOOD_DIAGNOSIS, "candidate_repair": "none"})
    assert not r.approved
    assert any("repair_permitted" in x for x in r.rejection_reasons)


# --- 9. preconditions the repair depends on ---------------------------------


def test_missing_baseline_blocks_the_repair() -> None:
    f = collapsed_frame()
    item = f.by_id("EV-B01")
    assert item is not None
    item.value = None
    r = run(GOOD_DIAGNOSIS, frame=f)
    assert not r.approved
    assert any("baseline_available" in x for x in r.rejection_reasons)


def test_empty_corpus_blocks_the_repair() -> None:
    f = collapsed_frame()
    item = f.by_id("EV-M04")
    assert item is not None
    item.value = 0.0
    r = run(GOOD_DIAGNOSIS, frame=f)
    assert not r.approved
    assert any("corpus_intact" in x for x in r.rejection_reasons)


# --- 10. the plumbing -------------------------------------------------------


def test_prompt_includes_every_evidence_id() -> None:
    frame = collapsed_frame()
    prompt = build_prompt(frame)
    for eid in frame.ids:
        assert eid in prompt, f"{eid} missing from the prompt"


def test_prompt_explains_the_similarity_discriminator() -> None:
    """The one piece of reasoning the model cannot get right unaided."""
    prompt = build_prompt(collapsed_frame())
    assert "BEFORE" in prompt and "rerank" in prompt.lower()


def test_schema_offers_the_whole_catalogue_not_just_f06() -> None:
    """A model given one option always picks it, which proves nothing."""
    classes = Diagnosis.model_json_schema()["properties"]["fault_class"]["enum"]
    assert "F06" in classes and "F01" in classes and "F09" in classes
    assert "INSUFFICIENT_EVIDENCE" in classes and "UNKNOWN" in classes
    assert "F04" not in classes, "F04 is retired"
    # Asserted as an invariant rather than a literal set, because the
    # actionable set grows every phase and a literal would have to be edited
    # by whoever adds a fault - which is the edit P6 says a new fault must not
    # require. What must stay true is that SAYING a class is always allowed
    # while ACTING on one is not, so the actionable set is a strict subset.
    actionable = supported_fault_classes()
    assert actionable, "at least one class must be actionable"
    assert actionable < set(classes), (
        "every actionable class must be sayable, and the model must be able to "
        "name classes Kavach cannot act on - otherwise a one-option model "
        "always picks the option it has"
    )
    assert all(c in classes for c in actionable)


def test_ollama_schema_is_generated_from_the_model() -> None:
    s = ollama_schema()
    assert s["additionalProperties"] is False
    assert set(s["required"]) >= {"fault_class", "service", "confidence",
                                  "candidate_repair", "reasoning",
                                  "evidence_ids"}


def test_client_refuses_the_fault_injection_path() -> None:
    """PRD §6.3: breaking the target must not blind the diagnostician."""
    for bad in ("http://toxiproxy:21434", "http://localhost:21435"):
        with pytest.raises(LlmError, match="blind RCA"):
            assert_not_proxied(bad)
    assert_not_proxied("http://localhost:11434")


def test_validation_is_deterministic() -> None:
    a = validate(Diagnosis.model_validate(GOOD_DIAGNOSIS), collapsed_frame(),
                 collapsed_detection(), THRESHOLD, SERVICES).to_dict()
    b = validate(Diagnosis.model_validate(GOOD_DIAGNOSIS), collapsed_frame(),
                 collapsed_detection(), THRESHOLD, SERVICES).to_dict()
    assert a == b
    assert a["outcome"] == str(Outcome.ACCEPTED)


def test_evidence_ids_is_required_not_optional() -> None:
    """The regression this exists for.

    evidence_ids was optional at first, and a real llama3.2 run cited
    EV-M01/EV-M02/EV-M06 inside `reasoning` while leaving the array empty -
    every other field correct. A constrained decoder may skip an optional
    field, and prompting did not fix it across repeated runs. Requiring it with
    minItems=2 moves the requirement into the grammar.
    """
    schema = ollama_schema()
    assert "evidence_ids" in schema["required"]
    assert schema["properties"]["evidence_ids"]["minItems"] == 2


def test_omitted_evidence_ids_is_a_schema_violation() -> None:
    payload = {k: v for k, v in GOOD_DIAGNOSIS.items() if k != "evidence_ids"}
    r = run(payload)
    assert not r.approved
    assert r.diagnosis is None, "a missing citation list must fail schema validation"


def test_single_citation_is_a_schema_violation() -> None:
    """Rejected at decode AND at validation - the same rule, enforced twice."""
    r = run({**GOOD_DIAGNOSIS, "evidence_ids": ["EV-M01"]})
    assert not r.approved
    assert r.diagnosis is None


def test_service_identity_is_present_in_a_collected_frame() -> None:
    """The other real-run bug: nothing named the services, so the model
    invented service="RAG". Validation caught it, but the gap was in the
    evidence frame."""
    import kavach.rca.evidence as evmod

    src = Path(evmod.__file__).read_text(encoding="utf-8")
    assert 'eid="EV-S01"' in src and 'eid="EV-S02"' in src
    assert '"backend"' in src


# --- NaN is missing data, not a number -------------------------------------


def test_a_nan_metric_is_presented_as_missing_not_as_a_number() -> None:
    """The misdiagnosis this prevents actually happened, on the first live F01.

    Shown `retrieval_top_similarity_p50 = nan`, llama3.2 reported "EV-M01
    shows similarity at 0.658 which is healthy" - reciting this project's
    documented baseline rather than reading the evidence - ruled out F01 with
    "EV-M06 shows llm_error_ratio 0.0" when EV-M06 was 1.0, and diagnosed F06
    at 0.9 confidence against a real endpoint outage. The deterministic
    cross-check refused it, which is the system working; the NaN is the part
    that should never have been shown.
    """
    value, note = reading(float("nan"))
    assert value is None, "a NaN must not reach the model as a number"
    assert "NO DATA" in note
    assert "not zero and not healthy" in note


def test_a_missing_series_and_a_nan_are_presented_identically() -> None:
    """Both mean 'there is nothing to read here', so they must not be
    distinguishable to the model - one of them inviting a guess is enough."""
    assert reading(None) == reading(float("nan"))


def test_a_real_reading_is_rounded_and_carries_no_note() -> None:
    value, note = reading(0.6578431)
    assert value == 0.6578
    assert note == ""


def test_zero_is_a_real_reading_and_must_not_be_treated_as_missing() -> None:
    """The opposite error. A kept-chunks mean of 0.0 IS the F06 symptom, and
    collapsing it into 'no data' would hide the fault."""
    value, note = reading(0.0)
    assert value == 0.0
    assert note == ""
