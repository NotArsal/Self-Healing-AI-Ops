"""The safety engine. **Every rule has a passing deny case** — that is this
phase's real deliverable, not `permit()` returning ALLOW on a happy path.

A gate is only worth what its refusals are worth. A test suite that proves the
gate says yes to good input proves almost nothing; what matters is that each
rule independently says no, for the stated reason, and that no combination of
configuration can talk it round.

Zero network. Nothing here touches the target, Prometheus, Ollama or Docker.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from kavach.audit.log import GENESIS, AuditLog
from kavach.executor.base import (
    HIGH,
    LOW,
    MEDIUM,
    ActionRegistry,
    RegistrationError,
)
from kavach.executor.undo_stack import UndoStack
from kavach.safety.engine import (
    ActionRequest,
    ProjectPolicy,
    SafetyEngine,
    Verdict,
)
from kavach.safety.limits import BlastRadius, CircuitBreaker, Limits
from kavach.safety.writer_lock import LockBusyError, WriterLock
from kavach.target import TargetClient

# The fake actions never touch a client, so the unwind tests pass none. Cast
# rather than build a stub: a stub would imply the unwind path uses it.
NO_CLIENT = cast(TargetClient, None)

# --- doubles ----------------------------------------------------------------


class FakeAction:
    """Satisfies the Action protocol without touching anything."""

    def __init__(self, name: str = "rollback_config", incident_id: str = "INC-1") -> None:
        self.incident_id = incident_id
        self.name = name
        self.risk_tier = MEDIUM
        self.target_settings: dict[str, Any] = {"rerank_threshold": 0.35}
        self.inverse_settings: dict[str, Any] = {"rerank_threshold": 0.999}
        self.executed = False
        self.inverted = False
        self.restore_ok = True
        self.invert_raises = False

    def prepare(self, client: Any) -> None: ...
    def execute(self, client: Any) -> None:
        self.executed = True

    def invert(self, client: Any) -> None:
        if self.invert_raises:
            raise RuntimeError("target refused the inverse")
        self.inverted = True

    def verify_applied(self, client: Any) -> tuple[bool, str]:
        return True, "applied"

    def verify_restored(self, client: Any) -> tuple[bool, str]:
        return (True, "restored") if self.restore_ok else (False, "still at 0.999")

    def unchanged_elsewhere(self, client: Any) -> tuple[bool, str]:
        return True, "scope respected"

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.name, "risk_tier": self.risk_tier}


class NoInverse:
    """Missing `invert` and friends — must be unregistrable."""

    incident_id = "INC-1"
    name = "reckless"
    risk_tier = LOW

    def prepare(self, client: Any) -> None: ...
    def execute(self, client: Any) -> None: ...


def a_registry() -> ActionRegistry:
    r = ActionRegistry()
    r.register("rollback_config", FakeAction, MEDIUM, FakeAction)
    r.register("restart_container", FakeAction, LOW, FakeAction)
    r.register("apply_patch", FakeAction, HIGH, FakeAction, tier_is_fixed=True)
    return r


def a_policy(**kw: Any) -> ProjectPolicy:
    base: dict[str, Any] = {
        "name": "simple-rag",
        "compose_project": "target_rag-app",
        "services": frozenset({"backend", "db"}),
        "allowed_actions": frozenset({"rollback_config", "restart_container", "apply_patch"}),
        "mode": "AUTONOMOUS",
        "confidence_threshold": 0.75,
    }
    base.update(kw)
    return ProjectPolicy(**base)


def a_request(**kw: Any) -> ActionRequest:
    base: dict[str, Any] = {
        "action": "rollback_config",
        "incident_id": "INC-1",
        "service": "backend",
        "fault_class": "F06",
        "compose_project": "target_rag-app",
        "has_inverse": True,
        "confidence": 0.90,
        "diagnosis_class": "F06",
    }
    base.update(kw)
    return ActionRequest(**base)


def engine() -> SafetyEngine:
    return SafetyEngine(a_registry())


def failed(decision: Any, rule: str) -> bool:
    return any(c.name == rule and not c.passed for c in decision.checks)


# --- a yes, so the deny cases mean something --------------------------------


def test_a_low_risk_allowed_action_runs_automatically() -> None:
    d = engine().permit(a_request(action="restart_container"), a_policy())
    assert d.verdict is Verdict.ALLOW_AUTO
    assert d.allowed is True
    assert d.risk_tier == LOW


# --- 1. project ownership ---------------------------------------------------


def test_deny_container_outside_the_compose_project() -> None:
    d = engine().permit(
        a_request(container="someone_elses_db", compose_project="other-project"),
        a_policy(),
    )
    assert d.denied
    assert failed(d, "project_ownership")
    assert "not onboarded against" in " ".join(d.reasons)


def test_deny_service_the_manifest_does_not_declare() -> None:
    d = engine().permit(a_request(service="redis"), a_policy())
    assert d.denied
    assert failed(d, "project_ownership")


def test_ownership_is_checked_before_everything_else() -> None:
    """A wrong answer here is unbounded, so it must short-circuit first."""
    d = engine().permit(
        a_request(action="not_registered", service="redis", has_inverse=False),
        a_policy(),
    )
    assert d.denied
    assert [c.name for c in d.checks] == ["project_ownership"]


# --- 2. deny-list, which beats the allow-list -------------------------------


def test_deny_list_wins_even_when_explicitly_allowed() -> None:
    """The rule that makes the allow-list safe to edit."""
    d = engine().permit(
        a_request(action="embed_model_change"),
        a_policy(allowed_actions=frozenset({"embed_model_change"})),
    )
    assert d.denied
    assert failed(d, "deny_list")


def test_deny_list_beats_autonomous_mode() -> None:
    for mode in ("SIMULATION", "APPROVAL", "AUTONOMOUS"):
        d = engine().permit(
            a_request(action="database_drop"),
            a_policy(mode=mode, allowed_actions=frozenset({"database_drop"})),
        )
        assert d.denied, mode


def test_deny_a_forbidden_change_smuggled_through_parameters() -> None:
    """A permitted action must not carry a denied mutation in its payload."""
    d = engine().permit(
        a_request(params={"rerank_threshold": 0.35, "embed_model": "nomic-v2"}),
        a_policy(),
    )
    assert d.denied
    assert failed(d, "deny_list")
    assert "embed_model" in " ".join(d.reasons)


# --- 3. allow-list ----------------------------------------------------------


def test_deny_action_not_on_the_allow_list() -> None:
    d = engine().permit(a_request(), a_policy(allowed_actions=frozenset()))
    assert d.denied
    assert failed(d, "allow_list")


def test_the_allow_list_defaults_to_empty() -> None:
    """Code must not add defaults. An unconfigured project can do nothing."""
    assert ProjectPolicy(name="p", compose_project="c").allowed_actions == frozenset()


# --- 4. the action must be registered ---------------------------------------


def test_deny_unregistered_action() -> None:
    d = engine().permit(
        a_request(action="rm_rf"),
        a_policy(allowed_actions=frozenset({"rm_rf"})),
    )
    assert d.denied
    assert failed(d, "action_known")


# --- 5. inverse ------------------------------------------------------------


def test_deny_action_with_no_recorded_inverse() -> None:
    d = engine().permit(a_request(has_inverse=False), a_policy())
    assert d.denied
    assert failed(d, "inverse_recorded")


def test_an_action_without_an_inverse_cannot_be_registered() -> None:
    """Enforced at registration, so it fails in the test suite, not at 3 a.m."""
    r = ActionRegistry()
    with pytest.raises(RegistrationError, match="without a working"):
        r.register("reckless", NoInverse, LOW, NoInverse)


def test_registry_rejects_bad_tiers_duplicates_and_non_callables() -> None:
    r = ActionRegistry()
    with pytest.raises(RegistrationError, match="valid tiers"):
        r.register("a", FakeAction, "CATASTROPHIC", FakeAction)
    with pytest.raises(RegistrationError, match="not callable"):
        r.register("b", "not a function", LOW)
    r.register("c", FakeAction, LOW, FakeAction)
    with pytest.raises(RegistrationError, match="already registered"):
        r.register("c", FakeAction, LOW, FakeAction)


def test_unknown_actions_are_high_by_default_deny() -> None:
    assert a_registry().tier("something_new") == HIGH


# --- 6. the unknown gate (FR-29) -------------------------------------------


def test_unknown_diagnosis_never_executes_in_any_mode() -> None:
    for mode in ("SIMULATION", "APPROVAL", "AUTONOMOUS"):
        for klass in ("UNKNOWN", "INSUFFICIENT_EVIDENCE"):
            d = engine().permit(
                a_request(action="restart_container", diagnosis_class=klass),
                a_policy(mode=mode),
            )
            assert d.denied, f"{mode}/{klass}"
            assert failed(d, "unknown_gate")


# --- 7. confidence ---------------------------------------------------------


def test_below_threshold_confidence_goes_to_a_human_not_to_denial() -> None:
    d = engine().permit(
        a_request(action="restart_container", confidence=0.40), a_policy()
    )
    assert d.verdict is Verdict.REQUIRE_APPROVAL
    assert not d.allowed
    assert failed(d, "confidence")


def test_a_deterministic_action_has_no_confidence_to_check() -> None:
    d = engine().permit(
        a_request(action="restart_container", confidence=None, diagnosis_class=""),
        a_policy(),
    )
    assert d.verdict is Verdict.ALLOW_AUTO


# --- 8. risk tier and mode routing -----------------------------------------


@pytest.mark.parametrize(
    ("mode", "action", "expected"),
    [
        ("SIMULATION", "restart_container", Verdict.REQUIRE_APPROVAL),
        ("SIMULATION", "rollback_config", Verdict.REQUIRE_APPROVAL),
        ("APPROVAL", "restart_container", Verdict.REQUIRE_APPROVAL),
        ("AUTONOMOUS", "restart_container", Verdict.ALLOW_AUTO),
        ("AUTONOMOUS", "rollback_config", Verdict.REQUIRE_SANDBOX),
        ("AUTONOMOUS", "apply_patch", Verdict.REQUIRE_APPROVAL),
    ],
)
def test_mode_and_tier_routing(mode: str, action: str, expected: Verdict) -> None:
    d = engine().permit(a_request(action=action), a_policy(mode=mode))
    assert d.verdict is expected


def test_simulation_is_the_default_and_never_executes() -> None:
    policy = ProjectPolicy(name="p", compose_project="c")
    assert policy.mode == "SIMULATION"
    d = engine().permit(
        a_request(action="restart_container", compose_project="c"),
        ProjectPolicy(name="p", compose_project="c",
                      services=frozenset({"backend"}),
                      allowed_actions=frozenset({"restart_container"})),
    )
    assert d.verdict is Verdict.REQUIRE_APPROVAL


def test_an_approval_executes_the_action_it_approved() -> None:
    """The hole the first live P5 run fell into.

    Approval used to be implemented by flipping the project to AUTONOMOUS for
    one run. AUTONOMOUS routes a MEDIUM action to the sandbox, and the sandbox
    does not exist until P7, so the approved re-run parked a second time and
    the operator's yes healed nothing. An approval is evidence on the request,
    not a mode.
    """
    d = engine().permit(
        a_request(action="rollback_config", operator_approved="INC-1"),
        a_policy(mode="APPROVAL"),
    )
    assert d.verdict is Verdict.ALLOW_AUTO
    assert d.allowed
    assert any("approved on INC-1" in c.detail for c in d.checks)


def test_an_approval_does_not_reopen_the_deny_list() -> None:
    """Approval satisfies step 11. Steps 1-10 already ran and still bind."""
    d = engine().permit(
        a_request(action="rollback_config", operator_approved="INC-1",
                  params={"embed_model": "nomic-embed-text"}),
        a_policy(mode="APPROVAL"),
    )
    assert d.verdict is Verdict.DENY


def test_an_approval_does_not_widen_the_allow_list() -> None:
    d = engine().permit(
        a_request(action="restart_container", operator_approved="INC-1"),
        a_policy(mode="APPROVAL", allowed_actions=frozenset({"rollback_config"})),
    )
    assert d.verdict is Verdict.DENY


def test_an_approved_high_action_still_requires_the_sandbox() -> None:
    """A fixed-HIGH action's sandbox is mandatory, not routed (ARCH §6.2.1), so
    an approval moves `apply_patch` to the sandbox and no further."""
    d = engine().permit(
        a_request(action="apply_patch", operator_approved="INC-1"),
        a_policy(mode="APPROVAL"),
    )
    assert d.verdict is Verdict.REQUIRE_SANDBOX
    assert not d.allowed


def test_apply_patch_is_high_even_in_autonomous_with_a_low_candidate_present() -> None:
    """The fixed tier is the whole defence for a model-authored payload."""
    e = engine()
    assert e.risk_tier("apply_patch") == HIGH
    assert e.registry.tier_is_fixed("apply_patch") is True
    d = e.permit(a_request(action="apply_patch"), a_policy(mode="AUTONOMOUS"))
    assert d.verdict is Verdict.REQUIRE_APPROVAL
    assert not d.allowed


# --- 9. blast radius -------------------------------------------------------


def test_blast_radius_caps_actions_within_one_incident() -> None:
    e = SafetyEngine(a_registry(), blast=BlastRadius(Limits(actions_per_incident=2)))
    request = a_request(action="restart_container")
    for _ in range(2):
        assert e.permit(request, a_policy()).allowed
        e.record_execution(request)
    d = e.permit(request, a_policy())
    assert d.denied
    assert failed(d, "blast_radius")


def test_blast_radius_caps_incidents_per_hour() -> None:
    e = SafetyEngine(a_registry(), blast=BlastRadius(Limits(incidents_per_hour=2)))
    for n in range(2):
        req = a_request(action="restart_container", incident_id=f"INC-{n}")
        assert e.permit(req, a_policy()).allowed
        e.record_execution(req)
    third = a_request(action="restart_container", incident_id="INC-99")
    d = e.permit(third, a_policy())
    assert d.denied
    assert "automation halts" in " ".join(d.reasons)


def test_a_known_incident_does_not_reconsume_the_hourly_budget() -> None:
    e = SafetyEngine(a_registry(), blast=BlastRadius(Limits(incidents_per_hour=1)))
    req = a_request(action="restart_container")
    assert e.permit(req, a_policy()).allowed
    e.record_execution(req)
    assert e.permit(req, a_policy()).allowed


# --- 10. circuit breaker ---------------------------------------------------


def test_breaker_opens_after_repeated_heals_of_the_same_pair() -> None:
    e = SafetyEngine(a_registry(), breaker=CircuitBreaker(Limits(heals_per_pair=3)))
    req = a_request(action="restart_container")
    for n in range(3):
        e.blast.record(f"INC-{n}")
        e.breaker.record("backend", "F06")
    d = e.permit(req, a_policy())
    assert d.denied
    assert failed(d, "circuit_breaker")
    assert "not repairing the cause" in " ".join(d.reasons)


def test_breaker_is_scoped_to_the_service_and_fault_pair() -> None:
    e = SafetyEngine(a_registry(), breaker=CircuitBreaker(Limits(heals_per_pair=1)))
    e.breaker.record("backend", "F06")
    assert e.permit(a_request(action="restart_container", fault_class="F01"),
                    a_policy()).allowed
    assert e.permit(a_request(action="restart_container", service="db"),
                    a_policy()).allowed


def test_breaker_forgets_outside_its_window() -> None:
    breaker = CircuitBreaker(Limits(heals_per_pair=1, breaker_window=timedelta(minutes=30)))
    long_ago = datetime.now(UTC) - timedelta(minutes=31)
    breaker.record("backend", "F06", now=long_ago)
    closed, _ = breaker.check("backend", "F06")
    assert closed is True


# --- the decision record ---------------------------------------------------


def test_every_decision_carries_a_laya_shaped_frame() -> None:
    """Written from the first commit so the corpus accrues before it is read."""
    frame = engine().permit(a_request(action="restart_container"),
                            a_policy()).to_dict()["typed_decision_frame"]
    assert frame == {
        "which_repair": "restart_container",
        "what_risk": LOW,
        "execute_automatically": True,
    }


def test_a_denial_always_explains_itself() -> None:
    d = engine().permit(a_request(has_inverse=False), a_policy())
    assert d.reasons and all(":" in r for r in d.reasons)


# --- the writer lock -------------------------------------------------------


def test_one_writer_per_project() -> None:
    lock = WriterLock()
    with lock.hold("simple-rag", "INC-1"), pytest.raises(
        LockBusyError, match="will not interleave"
    ), lock.hold("simple-rag", "INC-2"):
        pass
    # Released on exit, so the next incident proceeds.
    with lock.hold("simple-rag", "INC-2"):
        assert lock.holder("simple-rag") == "INC-2"


def test_the_lock_is_released_when_the_body_raises() -> None:
    lock = WriterLock()
    with pytest.raises(ValueError, match="boom"), lock.hold("p", "INC-1"):
        raise ValueError("boom")
    with lock.hold("p", "INC-2"):
        pass


def test_different_projects_do_not_block_each_other() -> None:
    lock = WriterLock()
    with lock.hold("a", "INC-1"), lock.hold("b", "INC-2"):
        pass


# --- the undo stack --------------------------------------------------------


def test_unwind_applies_inverses_in_reverse_order() -> None:
    stack = UndoStack("INC-1")
    order: list[str] = []

    class Recording(FakeAction):
        def invert(self, client: Any) -> None:
            order.append(self.name)

    for name in ("first", "second", "third"):
        stack.push(Recording(name=name))
    report = stack.unwind(NO_CLIENT)

    assert order == ["third", "second", "first"]
    assert report.clean is True
    assert report.restored == 3


def test_an_unwind_is_only_clean_when_the_prior_state_verifies() -> None:
    """Applying the inverse is not the same as the pre-state being back."""
    stack = UndoStack("INC-1")
    action = FakeAction()
    action.restore_ok = False
    stack.push(action)

    report = stack.unwind(NO_CLIENT)
    assert action.inverted is True      # the inverse DID run
    assert report.clean is False        # and the state is still wrong
    assert report.restored == 0
    assert "still at 0.999" in report.failures[0]


def test_unwind_continues_after_one_inverse_raises() -> None:
    stack = UndoStack("INC-1")
    exploding = FakeAction(name="explodes")
    exploding.invert_raises = True
    good = FakeAction(name="fine")
    stack.push(good)
    stack.push(exploding)

    report = stack.unwind(NO_CLIENT)
    assert report.attempted == 2
    assert report.restored == 1
    assert good.inverted is True
    assert any("explodes" in f for f in report.failures)
    assert report.clean is False


def test_an_inverse_is_never_applied_twice() -> None:
    stack = UndoStack("INC-1")
    action = FakeAction()
    stack.push(action)
    stack.unwind(NO_CLIENT)
    second = stack.unwind(NO_CLIENT)
    assert second.attempted == 0


def test_an_empty_stack_is_not_a_clean_unwind() -> None:
    assert UndoStack("INC-1").unwind(NO_CLIENT).clean is False


# --- the audit chain -------------------------------------------------------


def test_chain_links_each_row_to_the_one_before(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    first = log.append("permit", incident_id="INC-1", verdict="ALLOW_AUTO")
    second = log.append("execute", incident_id="INC-1", action="restart_container")

    assert first["prev"] == GENESIS
    assert second["prev"] == first["hash"]
    assert log.verify().intact is True
    assert log.verify().rows == 2


def test_editing_a_row_breaks_the_chain_and_names_the_row(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.append("permit", incident_id="INC-1", verdict="DENY")
    log.append("permit", incident_id="INC-2", verdict="DENY")
    log.append("permit", incident_id="INC-3", verdict="DENY")

    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"DENY"', '"ALLOW_AUTO"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    check = log.verify()
    assert check.intact is False
    assert check.broken_at == 1
    assert "does not match its recorded hash" in check.detail
    assert "CHAIN BROKEN" in check.render()


def test_deleting_a_row_breaks_the_chain(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    for n in range(3):
        log.append("permit", incident_id=f"INC-{n}")

    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    check = log.verify()
    assert check.intact is False
    assert check.broken_at == 1
    assert "changed or removed" in check.detail


def test_a_malformed_row_is_reported_not_skipped(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.append("permit")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("this is not json\n")

    check = log.verify()
    assert check.intact is False
    assert check.malformed == [1]


def test_an_empty_log_verifies(tmp_path: Path) -> None:
    check = AuditLog(tmp_path / "audit.jsonl").verify()
    assert check.intact is True
    assert check.rows == 0


def test_the_log_has_no_update_or_delete(tmp_path: Path) -> None:
    """The absence is the point (DESIGN_SYSTEM.md §7.10)."""
    log = AuditLog(tmp_path / "audit.jsonl")
    for forbidden in ("update", "delete", "edit", "remove", "truncate"):
        assert not hasattr(log, forbidden)
