"""F07 prompt regression: detection, discrimination, and the file write.

Two things make F07 different from every fault before it and most of this
file is about them.

It is the first fault whose repair writes a FILE. `rollback_prompt` is the
only code path in Kavach that turns a name into a filesystem path, so the
tests that matter most here are the ones that try to make it write somewhere
it should not.

It is also the first fault that is behaviourally indistinguishable from
another one. F07 and F08 produce the same fast-set shape - the model answers,
the answer is grounded, the keyword is missing - and separate only on which
artifact moved. So the discrimination tests check that each detector stays
silent during the OTHER one's fault, which is a property neither module can
establish about itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kavach.detection import base as det
from kavach.detection import catalogue  # noqa: F401 - registers the detectors
from kavach.detection.prompt_regression import collect, evaluate
from kavach.executor import catalogue as action_catalogue  # noqa: F401
from kavach.executor.base import registry as actions
from kavach.executor.config_rollback import ActionError
from kavach.executor.prompt_rollback import (
    PromptRollback,
    build_rollback_for_prompt_regression,
    digest,
    resolve,
)
from kavach.loop import IncidentStatus
from kavach.target import TargetClient, TargetEndpoints

GOOD_ANSWER = "You are a helpful assistant. Answer from the context.\n{context}\n{question}\n"
GOOD_EXPAND = "Rewrite the question.\n{question}\n"
BAD_ANSWER = "Answer in general terms. Do not quote figures.\n{context}\n{question}\n"

BASELINE: dict[str, Any] = {
    "prompt_version": {"files": {"answer.txt": digest(GOOD_ANSWER),
                                 "query_expansion.txt": digest(GOOD_EXPAND)}},
    "prompt_contents": {"answer.txt": GOOD_ANSWER,
                        "query_expansion.txt": GOOD_EXPAND},
    # F08 reads these. Present so the cross-detector tests drive both
    # detectors off one realistic baseline rather than two tailored ones.
    "settings": {"rerank_threshold": 0.35, "max_tokens": 0},
    "config_hash": "de4cfaed14a8bb98",
}


class FakeTarget:
    """A target whose prompt digests follow whatever is on disk.

    Reads the files rather than being told their hashes, because the property
    under test throughout `prompt_rollback.py` is that the control plane and
    the target agree about what is in the directory. A fake that reported a
    digest independently of the bytes would make every one of those checks
    pass vacuously.
    """

    def __init__(self, prompts_dir: Path, settings: dict[str, Any] | None = None,
                 config_hash: str = "de4cfaed14a8bb98") -> None:
        self.dir = prompts_dir
        self._settings = settings or {"rerank_threshold": 0.35, "max_tokens": 0}
        self._hash = config_hash
        self.lies_about: dict[str, str] = {}

    def config(self) -> dict[str, Any]:
        files = {p.name: digest(p.read_text(encoding="utf-8"))
                 for p in sorted(self.dir.glob("*.txt"))}
        files.update(self.lies_about)
        return {"settings": dict(self._settings), "config_hash": self._hash,
                "prompt_version": {"dir": "/app/prompts", "files": files}}

    def settings(self) -> dict[str, Any]:
        return dict(self._settings)

    def config_hash(self) -> str:
        return self._hash


@pytest.fixture
def prompts(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "answer.txt").write_text(GOOD_ANSWER, encoding="utf-8", newline="")
    (d / "query_expansion.txt").write_text(GOOD_EXPAND, encoding="utf-8", newline="")
    return d


def readings(prompts_dir: Path, baseline: dict[str, Any] | None = None) -> Any:
    return collect(det.Signals(
        prometheus_url="http://unused",
        promql=lambda _u, _q: None,
        client=FakeTarget(prompts_dir),
        baseline=BASELINE if baseline is None else baseline,
    ))


# --- 1. the two verdicts that matter ----------------------------------------


def test_a_changed_prompt_with_a_failing_fast_set_is_f07(prompts: Path) -> None:
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    d = evaluate(readings(prompts), fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.detected
    assert d.fault_class == "F07"
    assert d.service == "backend"
    assert any("answer.txt" in str(r) for r in d.reasons)


def test_a_changed_prompt_with_a_passing_fast_set_is_not_a_fault(prompts: Path) -> None:
    """Editing a prompt is how this application is improved. Rolling an
    author's work back because it is merely different would be the control
    plane overruling its own owner."""
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    d = evaluate(readings(prompts), fast_set_passed=True, fast_set_pass_rate=1.0)
    assert d.verdict is det.Verdict.NO_FAULT
    assert not d.detected
    # The drift is still reported, so a human can see it without a write.
    assert any("answer.txt" in str(e.value) for e in d.evidence)


# --- 2. refusing to claim what it cannot repair -----------------------------


def test_a_baseline_with_digests_but_no_text_cannot_claim(prompts: Path) -> None:
    """THE failure this check exists for. A digest identifies a file; it
    cannot restore one. Claiming F07 against a baseline captured before
    `prompt_contents` existed would produce a diagnosis whose repair fails at
    prepare() every single time, which is worse for an operator than being
    told the baseline is incomplete."""
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    digests_only = {k: v for k, v in BASELINE.items() if k != "prompt_contents"}
    d = evaluate(readings(prompts, digests_only),
                 fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE
    assert not d.detected
    assert any("make onboard" in r for r in d.reasons)


def test_a_vanished_prompt_is_not_a_regression(prompts: Path) -> None:
    """Captured, then gone. Writing text back is not obviously the fix."""
    (prompts / "query_expansion.txt").unlink()
    d = evaluate(readings(prompts), fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE
    assert any("query_expansion.txt" in str(r) for r in d.reasons)


def test_an_unreadable_control_interface_is_missing_evidence(prompts: Path) -> None:
    class Broken:
        def config(self) -> dict[str, Any]:
            raise RuntimeError("connection refused")

    r = collect(det.Signals(prometheus_url="http://unused",
                            promql=lambda _u, _q: None,
                            client=Broken(), baseline=BASELINE))
    d = evaluate(r, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert d.verdict is det.Verdict.INSUFFICIENT_EVIDENCE
    assert not d.detected


# --- 3. discrimination, checked from both sides -----------------------------


def test_f08_stays_silent_during_an_f07(prompts: Path) -> None:
    """A prompt edit moves no setting, so the residual config class must not
    claim it. Neither module can establish this about itself."""
    from kavach.detection.config_regression import collect as f08_collect
    from kavach.detection.config_regression import evaluate as f08_evaluate

    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    r = f08_collect(det.Signals(prometheus_url="http://unused",
                                promql=lambda _u, _q: None,
                                client=FakeTarget(prompts), baseline=BASELINE))
    d = f08_evaluate(r, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert not d.detected, "F08 claimed a prompt regression"


def test_f07_stays_silent_during_an_f08(prompts: Path) -> None:
    """The mirror. A drifted setting leaves every prompt digest untouched."""
    target = FakeTarget(prompts, settings={"rerank_threshold": 0.35, "max_tokens": 2})
    r = collect(det.Signals(prometheus_url="http://unused",
                            promql=lambda _u, _q: None,
                            client=target, baseline=BASELINE))
    d = evaluate(r, fast_set_passed=False, fast_set_pass_rate=0.0)
    assert not d.detected, "F07 claimed a config regression"


def test_only_one_detector_claims_a_live_prompt_regression(prompts: Path) -> None:
    """The registry-level statement of the two tests above. `run_all()`
    refuses to choose when two detectors claim, so a collision here would not
    be a wrong diagnosis - it would be no diagnosis at all."""
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    d = det.run_all(
        det.registry.specs(),
        det.Signals(prometheus_url="http://unused", promql=lambda _u, _q: None,
                    client=FakeTarget(prompts), baseline=BASELINE),
        fast_set_passed=False, fast_set_pass_rate=0.0,
    )
    assert d.fault_class == "F07", f"expected F07 alone, got {d.verdict} {d.reasons}"


# --- 4. the file write, which is the new privilege --------------------------


@pytest.mark.parametrize("name", [
    "../kavach.yaml",            # out of the directory
    "../../etc/passwd",
    "sub/answer.txt",            # into a subdirectory
    "/etc/passwd",               # absolute
    "answer.txt.bak",            # not a .txt
    "docker-compose.yml",
    "",
    ".",
    "..",
])
def test_resolve_refuses_anything_that_is_not_a_bare_txt_name(
    prompts: Path, name: str,
) -> None:
    """The only place in Kavach where a name becomes a path. Every one of
    these is currently unreachable - the names come from the target's own
    report - but 'unreachable today' is not a safety property."""
    with pytest.raises(ActionError):
        resolve(prompts, name)


def test_resolve_accepts_a_real_prompt_name(prompts: Path) -> None:
    assert resolve(prompts, "answer.txt") == (prompts / "answer.txt").resolve()


def test_the_repair_restores_the_captured_text(prompts: Path) -> None:
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    client = FakeTarget(prompts)
    action = build_rollback_for_prompt_regression(
        "inc-1", client,  # type: ignore[arg-type]
        {"dir": str(prompts), "files": BASELINE["prompt_contents"]},
    )
    ok, why = action.verify_applied(client)  # type: ignore[arg-type]
    assert not ok, f"nothing has been written yet, but verify_applied says {why}"

    action.execute(client)  # type: ignore[arg-type]
    assert (prompts / "answer.txt").read_text(encoding="utf-8") == GOOD_ANSWER
    ok, why = action.verify_applied(client)  # type: ignore[arg-type]
    assert ok, why
    ok, why = action.unchanged_elsewhere(client)  # type: ignore[arg-type]
    assert ok, why


def test_the_inverse_restores_the_degraded_prompt_not_the_baseline(
    prompts: Path,
) -> None:
    """An inverse that restored the BASELINE would be a second repair
    pretending to be an undo, and a failed verification would be
    unobservable: the target would look healed either way."""
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    client = FakeTarget(prompts)
    action = build_rollback_for_prompt_regression(
        "inc-1", client,  # type: ignore[arg-type]
        {"dir": str(prompts), "files": BASELINE["prompt_contents"]},
    )
    action.execute(client)  # type: ignore[arg-type]
    action.invert(client)  # type: ignore[arg-type]
    assert (prompts / "answer.txt").read_text(encoding="utf-8") == BAD_ANSWER
    ok, why = action.verify_restored(client)  # type: ignore[arg-type]
    assert ok, why


def test_only_the_drifted_file_is_written(prompts: Path) -> None:
    """The builder is handed BOTH baseline prompts. Writing the one that is
    already correct would be a no-op that still moved an mtime and still
    widened what `unchanged_elsewhere` has to vouch for."""
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    before = (prompts / "query_expansion.txt").stat().st_mtime_ns
    client = FakeTarget(prompts)
    action = build_rollback_for_prompt_regression(
        "inc-1", client,  # type: ignore[arg-type]
        {"dir": str(prompts), "files": BASELINE["prompt_contents"]},
    )
    assert sorted(action.target_prompts) == ["answer.txt"]
    action.execute(client)  # type: ignore[arg-type]
    assert (prompts / "query_expansion.txt").stat().st_mtime_ns == before


def test_a_repair_that_would_write_nothing_refuses_to_be_built(
    prompts: Path,
) -> None:
    """A no-op reported as a successful repair is a false recovery, which
    this project ranks above every other failure mode."""
    client = FakeTarget(prompts)
    with pytest.raises(ActionError, match="already matches"):
        build_rollback_for_prompt_regression(
            "inc-1", client,  # type: ignore[arg-type]
            {"dir": str(prompts), "files": BASELINE["prompt_contents"]},
        )


def test_a_baseline_without_text_cannot_build_the_repair(prompts: Path) -> None:
    client = FakeTarget(prompts)
    with pytest.raises(ActionError, match="holds no prompt text"):
        build_rollback_for_prompt_regression(
            "inc-1", client, {"dir": str(prompts), "files": {}},  # type: ignore[arg-type]
        )

    # And the other shape of the same hole: no baseline at all.
    with pytest.raises(ActionError, match="a digest restores nothing"):
        build_rollback_for_prompt_regression("inc-1", client, None)  # type: ignore[arg-type]


def test_no_declared_directory_is_a_refusal_not_a_guess(prompts: Path) -> None:
    client = FakeTarget(prompts)
    with pytest.raises(ActionError, match="write into the dark"):
        build_rollback_for_prompt_regression(
            "inc-1", client,  # type: ignore[arg-type]
            {"dir": "", "files": BASELINE["prompt_contents"]},
        )


def test_the_repair_refuses_when_the_target_reads_a_different_directory(
    prompts: Path,
) -> None:
    """THE failure mode this whole class of repair has. The control plane
    writes a host path; the target reads a bind mount. If those are not the
    same directory the write lands nowhere the target can see, and a repair
    that confidently changed nothing is worse than one that refused."""
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    client = FakeTarget(prompts)
    client.lies_about = {"answer.txt": "000000000000"}
    with pytest.raises(ActionError, match="different files"):
        build_rollback_for_prompt_regression(
            "inc-1", client,  # type: ignore[arg-type]
            {"dir": str(prompts), "files": BASELINE["prompt_contents"]},
        )


def test_execute_refuses_without_prepare(prompts: Path) -> None:
    action = PromptRollback(incident_id="inc-1", prompts_dir=prompts,
                            target_prompts={"answer.txt": GOOD_ANSWER})
    with pytest.raises(ActionError, match="prepare"):
        action.execute(FakeTarget(prompts))  # type: ignore[arg-type]


def test_the_audit_record_carries_digests_and_never_prompt_text(
    prompts: Path,
) -> None:
    """The audit log is append-only forever. A full prompt in every record
    would make it unreadable, and the digest is what a reader can check."""
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    client = FakeTarget(prompts)
    action = build_rollback_for_prompt_regression(
        "inc-1", client,  # type: ignore[arg-type]
        {"dir": str(prompts), "files": BASELINE["prompt_contents"]},
    )
    action.execute(client)  # type: ignore[arg-type]
    blob = str(action.to_dict())
    assert GOOD_ANSWER not in blob and BAD_ANSWER not in blob
    assert action.to_dict()["requested_settings"] == {"answer.txt": digest(GOOD_ANSWER)}
    assert action.to_dict()["bytes_written"] == {"answer.txt": len(GOOD_ANSWER.encode())}


def test_the_gate_can_see_parameters_and_an_inverse(prompts: Path) -> None:
    """`loop.py` builds its `ActionRequest` by reading `target_settings` and
    `inverse_settings` off the action by duck typing. An action missing them
    reaches the gate looking like a write with no parameters and no undo, and
    a sound repair gets denied for failing a check it actually passes."""
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    client = FakeTarget(prompts)
    action = build_rollback_for_prompt_regression(
        "inc-1", client,  # type: ignore[arg-type]
        {"dir": str(prompts), "files": BASELINE["prompt_contents"]},
    )
    assert dict(getattr(action, "target_settings", {}))
    assert bool(getattr(action, "inverse_settings", None))


# --- 5. the wiring ----------------------------------------------------------


def test_f07_names_a_repair_the_executor_can_build() -> None:
    assert det.registry.repair_for("F07") == "rollback_prompt"
    assert actions.knows("rollback_prompt")
    assert actions.tier("rollback_prompt") == "MEDIUM"


@pytest.mark.target_repo
def test_the_target_manifest_permits_the_repair() -> None:
    """An action the executor can build but the manifest does not list is
    denied by `permit()`, so the two have to be changed together."""
    from kavach.config import get_settings
    from kavach.onboarding.manifest import load

    manifest = load(Path(get_settings().target_path) / "kavach.yaml")
    assert "rollback_prompt" in manifest.allowed_actions
    assert "prompts" in manifest.versioned_paths


def test_the_model_may_propose_this_repair() -> None:
    """`CandidateRepair` is the model's entire output vocabulary. A repair
    missing from it cannot be proposed however correct the diagnosis, which
    is the bug that made F08 return `none` for ten runs."""
    from typing import get_args

    from kavach.rca.schema import CandidateRepair

    assert "rollback_prompt" in get_args(CandidateRepair)


# --- 6. the whole loop, including the forced-verification failure -----------
#
# The tests above drive the detector and the action directly. These drive
# `run_once`, which is where a fault class either is an adapter or is not: if
# F07 needed the loop to know anything about prompts, it would show up here.

SOURCES = "\n\n**Sources:**\n- Page 1 of `1662.pdf`"
REFUSAL = "I do not know based on the provided documents."

FULL = {
    "What ROC-AUC did the LSTM model achieve?":
        "The LSTM model achieved a ROC-AUC of 0.91." + SOURCES,
    "How many clips were used in the PhysioCheck feasibility evaluation?":
        "339 clips were used." + SOURCES,
    "What was the reported Stage-2 accuracy for Arm Raise?":
        "The reported Stage-2 accuracy for Arm Raise is 91.2%." + SOURCES,
}
# What the summarisation prompt actually returns, measured live 2026-10-17:
# a real answer to the WRONG question. Not a refusal, and still grounded -
# which is exactly what separates F07's symptom from F06's.
SUMMARISED = {
    "What ROC-AUC did the LSTM model achieve?":
        "The context covers machine learning for clinical deterioration." + SOURCES,
    "How many clips were used in the PhysioCheck feasibility evaluation?":
        "The context covers remote physiotherapy assessment." + SOURCES,
    "What was the reported Stage-2 accuracy for Arm Raise?":
        "The context covers movement quality scoring." + SOURCES,
}

LOOP_SETTINGS: dict[str, Any] = {"rerank_threshold": 0.35, "max_tokens": 0}
LOOP_HASH = "de4cfaed14a8bb98"


class FakePromptTarget(TargetClient):
    """A target whose answers summarise when `answer.txt` is not the good one.

    Reads the prompt from disk to decide, for the same reason `FakeTarget`
    hashes it rather than being told: the property under test is that the
    control plane's write and the target's behaviour are connected.
    """

    def __init__(self, prompts_dir: Path) -> None:
        super().__init__(TargetEndpoints())
        self.dir = prompts_dir
        self._settings = dict(LOOP_SETTINGS)
        self.corpus = {"chunks": 30.0, "files": 2.0}
        self.stuck = False

    @property
    def degraded(self) -> bool:
        if self.stuck:
            return True
        return (self.dir / "answer.txt").read_text(encoding="utf-8") != GOOD_ANSWER

    def health(self, timeout: float = 10.0) -> dict[str, Any]:
        return {"status": "ok", "dependencies": {
            "database": {"ok": True, "detail": "ok"},
            "ollama": {"ok": True, "detail": "ok"}}}

    def config(self, timeout: float = 15.0) -> dict[str, Any]:
        files = {p.name: digest(p.read_text(encoding="utf-8"))
                 for p in sorted(self.dir.glob("*.txt"))}
        return {"settings": dict(self._settings),
                "config_hash": LOOP_HASH,
                "prompt_version": {"files": files}}

    def settings(self) -> dict[str, Any]:
        return dict(self._settings)

    def config_hash(self) -> str:
        return LOOP_HASH

    def ask(self, question: str, timeout: float = 240.0) -> str:
        table = SUMMARISED if self.degraded else FULL
        return table.get(question, REFUSAL)


def promql_for(target: FakePromptTarget) -> Any:
    """Healthy metrics throughout: that is the point of this fault.

    Identical in shape to F08's, and deliberately so. F07 and F08 are
    indistinguishable in every metric; if this function had to differ from
    F08's to make F07 detectable, the two classes would be separating on
    something other than which artifact drifted.
    """
    def q(_url: str, expr: str) -> float | None:
        if "corpus_chunks" in expr:
            return target.corpus["chunks"]
        if "corpus_files" in expr:
            return target.corpus["files"]
        if "outcome" in expr and "clamp_min" in expr:
            return 0.0                    # the endpoint is fine
        if "increase(ragapp_llm_requests_total" in expr:
            return 12.0
        if 'outcome="ok"' in expr:
            return 0.7
        if "top_similarity" in expr:
            return 0.658
        if "kept_chunks_sum" in expr:
            return 2.73                   # grounding intact
        if "empty_context" in expr:
            return 0.0
        return None
    return q


@pytest.fixture
def fast_set() -> Path:
    return (Path(__file__).resolve().parents[1]
            / "kavach" / "verification" / "fast_set.yaml")


def _loop_baseline() -> dict[str, Any]:
    return {**BASELINE, "settings": dict(LOOP_SETTINGS),
            "config_hash": LOOP_HASH}


def _run(target: FakePromptTarget, fast_set: Path, prompts_dir: Path) -> Any:
    from kavach.loop import run_once

    return run_once(
        target, "http://prom", fast_set, promql_for(target),
        baseline_value=0.35, baseline=_loop_baseline(),
        repair_values={"rollback_prompt": {
            "dir": str(prompts_dir), "files": BASELINE["prompt_contents"]}},
    )


def test_f07_is_detected_and_healed_by_restoring_the_prompt(
    prompts: Path, fast_set: Path,
) -> None:
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    t = FakePromptTarget(prompts)
    inc = _run(t, fast_set, prompts)

    assert inc.status is IncidentStatus.RESOLVED, inc.escalation_reason
    assert inc.fault_class == "F07"
    assert inc.planned_action == "rollback_prompt"
    assert (prompts / "answer.txt").read_text(encoding="utf-8") == GOOD_ANSWER
    assert inc.action is not None
    assert inc.action["restored_files"] == ["answer.txt"]
    assert inc.action["risk_tier"] == "MEDIUM"


def test_clean_prompts_produce_no_incident(prompts: Path, fast_set: Path) -> None:
    t = FakePromptTarget(prompts)
    inc = _run(t, fast_set, prompts)
    assert inc.status is IncidentStatus.NO_FAULT


def test_without_captured_text_the_loop_escalates_and_writes_nothing(
    prompts: Path, fast_set: Path,
) -> None:
    """A baseline with digests but no text: the detector refuses rather than
    proposing a repair that cannot be built, and the file is left alone."""
    from kavach.loop import run_once

    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    t = FakePromptTarget(prompts)
    baseline = {k: v for k, v in _loop_baseline().items()
                if k != "prompt_contents"}
    inc = run_once(t, "http://prom", fast_set, promql_for(t),
                   baseline_value=0.35, baseline=baseline)

    assert inc.status is IncidentStatus.ESCALATED
    assert (prompts / "answer.txt").read_text(encoding="utf-8") == BAD_ANSWER, (
        "nothing may be written from an undiagnosed fault"
    )


def test_a_restore_that_does_not_fix_quality_unwinds(
    prompts: Path, fast_set: Path,
) -> None:
    """The forced-verification-failure case for F07.

    The prompt file is restored correctly and the answers stay wrong anyway,
    because something else is degrading them. The loop must not report a
    recovery it cannot demonstrate, and must leave the prompt as it found it.
    """
    (prompts / "answer.txt").write_text(BAD_ANSWER, encoding="utf-8", newline="")
    t = FakePromptTarget(prompts)
    t.stuck = True          # answers summarise whatever the prompt says
    inc = _run(t, fast_set, prompts)

    assert inc.status is IncidentStatus.ESCALATED
    assert not inc.resolved
    assert "fast verification did not pass" in inc.escalation_reason
    assert (prompts / "answer.txt").read_text(encoding="utf-8") == BAD_ANSWER, (
        "the inverse must restore the bytes that were there, not the baseline"
    )
