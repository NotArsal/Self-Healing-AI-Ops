"""The generated repair: what it refuses, and in what order.

The sandbox and the fast set are faked here. What is under test is not
whether a container comes up - `test_sandbox.py` covers that, and a live run
covers it properly - but the ORDERING, which is the whole design:

    witness -> trial on a clone -> full six-check gate -> only then execute

Every test below is a way of asking "can anything reach production without
having gone through all four of those, in that order".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kavach.executor import apply_patch, sandbox
from kavach.executor.apply_patch import ApplyPatch
from kavach.executor.config_rollback import ActionError
from kavach.target import TargetClient, TargetEndpoints

VERSIONED = {"prompts": "./prompts"}
DENIED = ["embed_model_change", "data_delete", "database_drop"]
BEFORE = "old line\n"
AFTER = "Answer only from the context.\n"


def digest(text: str) -> str:
    return apply_patch.digest(text)


def a_diff(old: str = "old line", new: str = "Answer only from the context.") -> str:
    return (f"--- a/prompts/answer.txt\n+++ b/prompts/answer.txt\n"
            f"@@ -1,1 +1,1 @@\n-{old}\n+{new}\n")


class FakeTarget(TargetClient):
    """Reports whatever digest the files on disk currently hold.

    Subclasses rather than duck-types so `mypy --strict` checks these calls
    against the real signature, the way `test_f07_prompt.py` does it.
    """

    def __init__(self, prompts: Path, config_hash: str = "cfg-1") -> None:
        super().__init__(TargetEndpoints())
        self.prompts = prompts
        self.hash_ = config_hash
        self.calls = 0

    def config(self, timeout: float = 10.0) -> dict[str, Any]:
        self.calls += 1
        files = {p.name: digest(p.read_text(encoding="utf-8"))
                 for p in sorted(self.prompts.glob("*.txt"))}
        return {"prompt_version": {"files": files},
                "config_hash": self.hash_}


class FakeResult:
    def __init__(self, passed: bool, rate: float = 1.0) -> None:
        self.passed = passed
        self.pass_rate = rate


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Production prompts, a sandbox prompts dir, and a passing fast set."""
    prod = tmp_path / "production" / "prompts"
    prod.mkdir(parents=True)
    (prod / "answer.txt").write_text(BEFORE, encoding="utf-8", newline="")
    (prod / "other.txt").write_text("untouched\n", encoding="utf-8", newline="")

    box = tmp_path / "sandbox-prompts"
    box.mkdir()
    (box / "answer.txt").write_text(BEFORE, encoding="utf-8", newline="")

    state = type("S", (), {"usable": True, "problems": []})()
    monkeypatch.setattr(sandbox, "ensure", lambda *a, **k: state)
    monkeypatch.setattr(sandbox, "prompts_dir", lambda: box)
    monkeypatch.setattr(sandbox, "endpoints", lambda: TargetEndpoints())

    from kavach.verification import fast
    monkeypatch.setattr(fast, "run", lambda *a, **k: FakeResult(True))
    monkeypatch.setattr(apply_patch, "_fast_set_path", lambda: tmp_path / "x.yaml")

    return {"prod": prod, "box": box, "state": state, "tmp": tmp_path}


def an_action(world: dict[str, Any], diff: str | None = None) -> ApplyPatch:
    return ApplyPatch(
        incident_id="INC-1",
        proposal_diff=diff if diff is not None else a_diff(),
        target_file="prompts/answer.txt",
        prompts_dir=world["prod"],
        versioned_paths=VERSIONED,
        denied_mutations=DENIED,
        witness={"prompts/answer.txt": digest(BEFORE)},
    )


# --- the ordering ----------------------------------------------------------


def test_the_patch_is_tried_on_the_clone_before_anything_else(
    world: dict[str, Any],
) -> None:
    """Constraint 4: no sandbox result, no proposal. `prepare()` is where
    that result is obtained, which is why the trial lives there."""
    action = an_action(world)
    action.prepare(FakeTarget(world["prod"]))

    assert action.trial.ran and action.trial.applied
    assert action.trial.passed is True
    # And production has NOT been touched by preparing.
    assert (world["prod"] / "answer.txt").read_text(encoding="utf-8") == BEFORE


def test_preparing_leaves_the_clone_as_it_found_it(
    world: dict[str, Any],
) -> None:
    """One incident's experiment must not become the next one's starting
    state. The sandbox is the one place that contamination would be
    invisible, which is why it is restored in a `finally`."""
    an_action(world).prepare(FakeTarget(world["prod"]))
    assert (world["box"] / "answer.txt").read_text(encoding="utf-8") == BEFORE


def test_a_failing_sandbox_run_stops_the_action_existing(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kavach.verification import fast
    monkeypatch.setattr(fast, "run", lambda *a, **k: FakeResult(False, 0.33))

    with pytest.raises(ActionError, match="did not pass in the sandbox"):
        an_action(world).prepare(FakeTarget(world["prod"]))
    assert (world["prod"] / "answer.txt").read_text(encoding="utf-8") == BEFORE


def test_no_sandbox_means_no_action_rather_than_a_skipped_check(
    world: dict[str, Any],
) -> None:
    """THE failure mode worth naming: a sandbox that will not come up must
    not degrade into applying the patch anyway."""
    world["state"].usable = False
    world["state"].problems = ["docker is not running"]

    with pytest.raises(ActionError, match="did not pass in the sandbox"):
        an_action(world).prepare(FakeTarget(world["prod"]))
    assert (world["prod"] / "answer.txt").read_text(encoding="utf-8") == BEFORE


def test_the_clone_is_synced_from_production_before_the_trial(
    world: dict[str, Any],
) -> None:
    """Nothing in `seed()` copies prompts, so the two directories matching
    is luck rather than a guarantee. A drifted clone would have the trial
    answer a question about the wrong file, so the file under test is
    overwritten from production before the patch is applied."""
    (world["box"] / "answer.txt").write_text(
        "stale, left by an earlier incident\n", encoding="utf-8", newline="")

    action = an_action(world)
    action.prepare(FakeTarget(world["prod"]))
    assert action.trial.applied, action.trial.detail


def test_a_patch_that_does_not_apply_to_production_is_refused(
    world: dict[str, Any],
) -> None:
    """With the clone synced from production, "does not apply to the clone"
    can only mean "does not apply to production"."""
    (world["prod"] / "answer.txt").write_text(
        "someone else edited this\n", encoding="utf-8", newline="")

    with pytest.raises(ActionError, match="did not pass in the sandbox"):
        an_action(world).prepare(FakeTarget(world["prod"]))


def test_the_full_gate_runs_after_the_trial_not_before(
    world: dict[str, Any],
) -> None:
    """A patch that passes in the sandbox but breaks a static rule is still
    refused. The sandbox is a necessary condition, never a sufficient one."""
    bad = ("--- a/prompts/answer.txt\n+++ b/prompts/answer.txt\n"
           "@@ -1,1 +1,1 @@\n-old line\n+Then run DROP TABLE document_chunks;\n")
    with pytest.raises(ActionError, match="full gate refused"):
        an_action(world, diff=bad).prepare(FakeTarget(world["prod"]))
    assert (world["prod"] / "answer.txt").read_text(encoding="utf-8") == BEFORE


# --- execution cannot be reached by another road ---------------------------


def test_execute_without_prepare_is_refused(world: dict[str, Any]) -> None:
    action = an_action(world)
    with pytest.raises(ActionError, match="prepare\\(\\) must run"):
        action.execute(FakeTarget(world["prod"]))
    assert (world["prod"] / "answer.txt").read_text(encoding="utf-8") == BEFORE


def test_execute_is_refused_if_the_trial_result_is_cleared(
    world: dict[str, Any],
) -> None:
    """Belt and braces: `prepare()` already raises on a failed trial, so this
    can only happen if something mutated the action afterwards. It is still
    refused, because the check that matters is the one at the write."""
    action = an_action(world)
    action.prepare(FakeTarget(world["prod"]))
    action.trial.passed = False

    with pytest.raises(ActionError, match="no passing sandbox trial"):
        action.execute(FakeTarget(world["prod"]))
    assert (world["prod"] / "answer.txt").read_text(encoding="utf-8") == BEFORE


def test_executing_twice_writes_once(world: dict[str, Any]) -> None:
    """The second call is a no-op rather than a second application, which a
    unified diff would reject anyway - but an idempotent action is what the
    retry path in `loop.py` expects."""
    client = FakeTarget(world["prod"])
    action = an_action(world)
    action.prepare(client)
    action.execute(client)
    action.execute(client)
    assert (world["prod"] / "answer.txt").read_text(encoding="utf-8") == AFTER


def test_a_file_that_moved_between_approval_and_execution_is_not_overwritten(
    world: dict[str, Any],
) -> None:
    """§6.2.1's reason for a diff rather than a whole file. A HIGH action can
    sit in an approval queue for a long time."""
    client = FakeTarget(world["prod"])
    action = an_action(world)
    action.prepare(client)
    (world["prod"] / "answer.txt").write_text(
        "a human rewrote this\n", encoding="utf-8", newline="")

    with pytest.raises(ActionError):
        action.execute(client)
    assert (world["prod"] / "answer.txt").read_text(encoding="utf-8") == (
        "a human rewrote this\n"
    ), "the human's edit was overwritten"


# --- the inverse -----------------------------------------------------------


def test_the_inverse_restores_the_exact_prior_bytes(
    world: dict[str, Any],
) -> None:
    client = FakeTarget(world["prod"])
    action = an_action(world)
    action.prepare(client)
    action.execute(client)
    assert (world["prod"] / "answer.txt").read_text(encoding="utf-8") == AFTER

    action.invert(client)
    assert (world["prod"] / "answer.txt").read_text(encoding="utf-8") == BEFORE
    assert action.reverted


def test_the_inverse_is_recorded_data_and_needs_no_model(
    world: dict[str, Any],
) -> None:
    """§6.0. The inverse is bytes captured before the write, so undo works
    with the model unreachable."""
    action = an_action(world)
    action.prepare(FakeTarget(world["prod"]))
    assert action.inverse_text == {"prompts/answer.txt": BEFORE}


def test_inverting_without_a_witness_is_refused(world: dict[str, Any]) -> None:
    action = an_action(world)
    with pytest.raises(ActionError, match="no inverse recorded"):
        action.invert(FakeTarget(world["prod"]))


# --- verification asks the target ------------------------------------------


def test_verification_asks_the_target_not_the_file_it_just_wrote(
    world: dict[str, Any],
) -> None:
    """Re-reading the file this action wrote proves the write happened,
    which is never the thing in doubt. The question is whether the RUNNING
    target serves it."""
    client = FakeTarget(world["prod"])
    action = an_action(world)
    action.prepare(client)
    action.execute(client)

    before = client.calls
    ok, detail = action.verify_applied(client)
    assert ok, detail
    assert client.calls > before, "verify_applied did not ask the target"


def test_verify_applied_fails_when_the_target_still_serves_the_old_file(
    world: dict[str, Any],
) -> None:
    class Stale(FakeTarget):
        def config(self, timeout: float = 10.0) -> dict[str, Any]:
            return {"prompt_version": {"files": {"answer.txt": digest(BEFORE)}},
                    "config_hash": "cfg-1"}

    client = Stale(world["prod"])
    action = an_action(world)
    action.prepare(client)
    action.execute(client)
    ok, detail = action.verify_applied(client)
    assert not ok
    assert "not the patched" in detail


def test_verify_restored_wants_the_witness_back(world: dict[str, Any]) -> None:
    client = FakeTarget(world["prod"])
    action = an_action(world)
    action.prepare(client)
    action.execute(client)
    action.invert(client)
    ok, detail = action.verify_restored(client)
    assert ok, detail


def test_an_untouched_file_moving_is_reported(world: dict[str, Any]) -> None:
    client = FakeTarget(world["prod"])
    action = an_action(world)
    action.prepare(client)
    action.execute(client)
    (world["prod"] / "other.txt").write_text(
        "something else changed\n", encoding="utf-8", newline="")

    ok, detail = action.unchanged_elsewhere(client)
    assert not ok
    assert "other.txt" in detail


def test_the_patched_file_changing_is_not_reported_as_drift(
    world: dict[str, Any],
) -> None:
    client = FakeTarget(world["prod"])
    action = an_action(world)
    action.prepare(client)
    action.execute(client)
    ok, detail = action.unchanged_elsewhere(client)
    assert ok, detail


# --- the record ------------------------------------------------------------


def test_the_record_carries_the_diff_and_the_sandbox_result(
    world: dict[str, Any],
) -> None:
    """The one action whose full payload goes in the audit record. A
    generated write that cannot be read back afterwards is not auditable,
    and the diff budget keeps it to a few dozen lines."""
    client = FakeTarget(world["prod"])
    action = an_action(world)
    action.prepare(client)
    record = action.to_dict()

    assert record["risk_tier"] == "HIGH"
    assert record["diff"] == a_diff()
    assert record["sandbox_trial"]["passed"] is True
    assert record["inverse_settings"] == {"prompts/answer.txt": digest(BEFORE)}
    assert record["idempotency_key"]


def test_the_parameters_the_gate_sees_are_digests_not_prose(
    world: dict[str, Any],
) -> None:
    action = an_action(world)
    assert action.target_settings == {"prompts/answer.txt": digest(a_diff())}


# --- the registry ----------------------------------------------------------


def test_it_is_registered_high_with_a_tier_nothing_can_lower() -> None:
    from kavach.executor import catalogue  # noqa: F401 - registers
    from kavach.executor.base import registry

    assert registry.knows("apply_patch")
    assert registry.tier("apply_patch") == "HIGH"
    assert registry.tier_is_fixed("apply_patch") is True


def test_a_rejected_proposal_cannot_be_built_into_an_action(
    world: dict[str, Any],
) -> None:
    """The checks are re-asserted at construction so a caller cannot
    assemble an action out of a proposal that was already refused."""
    from kavach.rca.patch_engine import PatchResult
    from kavach.rca.patch_schema import PatchProposal

    refused = PatchResult(
        proposal=PatchProposal(target_path="prompts/answer.txt",
                               rationale="restore grounding", diff=a_diff()),
        reasons=["the deny-list refuses on content"],
    )
    assert not refused.usable
    with pytest.raises(ActionError, match="did not pass its checks"):
        apply_patch.build_from_proposal(
            "INC-1", FakeTarget(world["prod"]), refused,
            world["prod"], VERSIONED, DENIED, {},
        )


def test_a_proposal_that_never_produced_a_patch_is_a_different_refusal(
    world: dict[str, Any],
) -> None:
    from kavach.rca.patch_engine import PatchResult

    with pytest.raises(ActionError, match="no patch was produced"):
        apply_patch.build_from_proposal(
            "INC-1", FakeTarget(world["prod"]),
            PatchResult(proposal=None, error="connection refused"),
            world["prod"], VERSIONED, DENIED, {},
        )
