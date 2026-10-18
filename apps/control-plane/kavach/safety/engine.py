"""`permit()` — the gate. `ARCHITECTURE.md` §6.1.

One public entry point. Every side effect in Kavach passes through it, and it
is the only thing that may say yes.

THE ORDER IS THE DESIGN, NOT A STYLE CHOICE
Ownership runs first because it is the check that prevents Kavach touching
something it was never onboarded against — a wrong answer there is unbounded,
while a wrong answer on, say, blast radius merely does too much of a permitted
thing. The deny-list runs BEFORE the allow-list so that adding a forbidden
action to `allowed_actions` cannot enable it: deny wins, in every mode, always.

FAIL CLOSED, AND SAY WHY
Every check that cannot be evaluated denies. The verdict always carries
reasons, because a gate whose refusals are unexplained gets disabled by the
first operator it inconveniences.

WHAT THIS MODULE DOES NOT DO
It does not choose the repair and it does not execute anything. The loop
decides, `permit()` authorises, the executor acts; no component does two of
those three.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from kavach.config import Mode
from kavach.executor.base import HIGH, LOW, MEDIUM, ActionRegistry, RiskTier
from kavach.safety.limits import BlastRadius, CircuitBreaker

# Mutations that are never permitted, in any mode, for any project, however the
# allow-list is configured. `FR-30`. Names match the manifest's vocabulary.
DENIED_MUTATIONS: frozenset[str] = frozenset({
    "embed_model_change", "data_delete", "database_drop",
    "scale_to_zero", "migration",
})

# Parameter keys that mean a denied mutation whatever the action is called.
# Checked against the action's payload, so a permitted action cannot smuggle a
# forbidden change through its parameters.
DENIED_PARAM_KEYS: frozenset[str] = frozenset({
    "embed_model", "embedding_model", "database_url", "db_url",
})


class Verdict(StrEnum):
    ALLOW_AUTO = "ALLOW_AUTO"
    REQUIRE_SANDBOX = "REQUIRE_SANDBOX"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""

    def render(self) -> str:
        return f"  [{'ok' if self.passed else 'NO'}] {self.name}: {self.detail}"


@dataclass
class Decision:
    """The verdict, its reasons, and the evidence a human needs to review it."""

    verdict: Verdict
    action: str = ""
    risk_tier: RiskTier = HIGH
    mode: Mode = "SIMULATION"
    reasons: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )

    @property
    def allowed(self) -> bool:
        """True only for an unconditional yes. Sandbox and approval are not yes."""
        return self.verdict is Verdict.ALLOW_AUTO

    @property
    def denied(self) -> bool:
        return self.verdict is Verdict.DENY

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": str(self.verdict),
            "action": self.action,
            "risk_tier": self.risk_tier,
            "mode": str(self.mode),
            "reasons": self.reasons,
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail}
                       for c in self.checks],
            "at": self.at,
            # The Laya-shaped compression of this decision. Written from the
            # first commit so the fine-tuning corpus accrues at zero cost, long
            # before any shadow engine reads it (PRD §7.1).
            "typed_decision_frame": {
                "which_repair": self.action,
                "what_risk": self.risk_tier,
                "execute_automatically": self.verdict is Verdict.ALLOW_AUTO,
            },
        }

    def render(self) -> str:
        head = f"permit({self.action}) -> {self.verdict} [{self.risk_tier}, {self.mode}]"
        return "\n".join([head] + [c.render() for c in self.checks])


@dataclass
class ActionRequest:
    """Everything `permit()` needs. Deliberately not the Action object itself:
    the gate must be able to judge a proposal that was never constructed."""

    action: str
    incident_id: str
    service: str = ""
    fault_class: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    container: str = ""
    compose_project: str = ""
    has_inverse: bool = False
    confidence: float | None = None
    diagnosis_class: str = ""
    # The incident whose plan a human approved, or empty. This is NOT the same
    # as running under AUTONOMOUS and must not be modelled as it: AUTONOMOUS is
    # a standing permission to act on a class of faults, an approval is a
    # person having read THIS plan and said yes. Impersonating AUTONOMOUS on
    # approval is what made the approved path a dead end - the mode gate let it
    # through and the tier router then sent the same MEDIUM action to a sandbox
    # that does not exist until P7, so approving a repair healed nothing.
    operator_approved: str = ""


@dataclass
class ProjectPolicy:
    """The manifest's safety posture, as `permit()` reads it."""

    name: str
    compose_project: str
    services: frozenset[str] = frozenset()
    allowed_actions: frozenset[str] = frozenset()
    denied_mutations: frozenset[str] = DENIED_MUTATIONS
    mode: Mode = "SIMULATION"
    confidence_threshold: float = 0.75


class SafetyEngine:
    """Holds the rate limits across calls; `permit()` itself is a pure decision."""

    def __init__(
        self,
        registry: ActionRegistry,
        blast: BlastRadius | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.registry = registry
        self.blast = blast or BlastRadius()
        self.breaker = breaker or CircuitBreaker()

    def risk_tier(self, action: str) -> RiskTier:
        """Deterministic, from the registry. Unknown actions are HIGH."""
        return self.registry.tier(action)

    def permit(self, request: ActionRequest, policy: ProjectPolicy) -> Decision:
        """The ten steps, in order. First failure short-circuits."""
        decision = Decision(
            verdict=Verdict.DENY, action=request.action, mode=policy.mode
        )
        checks = decision.checks

        def deny(name: str, detail: str) -> Decision:
            checks.append(Check(name, False, detail))
            decision.reasons.append(f"{name}: {detail}")
            decision.verdict = Verdict.DENY
            return decision

        def ok(name: str, detail: str = "") -> None:
            checks.append(Check(name, True, detail))

        # --- 1. project ownership. First, because it is the unbounded one.
        if (request.container or request.compose_project) and (
            request.compose_project != policy.compose_project
        ):
            return deny(
                "project_ownership",
                f"{request.container or 'target'!r} belongs to compose project "
                f"{request.compose_project!r}, not {policy.compose_project!r}. "
                f"Kavach does not touch what it was not onboarded against",
            )
        if request.service and policy.services and request.service not in policy.services:
            return deny(
                "project_ownership",
                f"{request.service!r} is not a declared service of "
                f"{policy.name}: {sorted(policy.services)}"
            )
        ok("project_ownership", f"{request.service or policy.name} in {policy.compose_project}")

        # --- 2. deny-list. BEFORE the allow-list, so deny always wins.
        if request.action in policy.denied_mutations:
            return deny("deny_list",
                        f"{request.action!r} is a forbidden mutation, in every mode")
        smuggled = sorted(set(request.params) & DENIED_PARAM_KEYS)
        if smuggled:
            return deny(
                "deny_list",
                f"parameters {smuggled} reach a denied target. A permitted action "
                f"may not carry a forbidden change in its payload"
            )
        ok("deny_list", "no denied mutation or parameter")

        # --- 3. allow-list. Default empty; code must not add defaults.
        if request.action not in policy.allowed_actions:
            return deny(
                "allow_list",
                f"{request.action!r} is not in allowed_actions for {policy.name}: "
                f"{sorted(policy.allowed_actions) or 'empty'}"
            )
        ok("allow_list", request.action)

        # --- 4. the action must exist and be registrable
        if not self.registry.knows(request.action):
            return deny("action_known",
                        f"no registered action named {request.action!r}")
        ok("action_known", request.action)

        # --- 5. inverse exists
        if not request.has_inverse:
            return deny(
                "inverse_recorded",
                "no inverse captured. An action that cannot be undone never runs "
                "automatically (ARCHITECTURE.md §6.0)"
            )
        ok("inverse_recorded", "pre-state witness captured")

        # --- 6. unknown-failure gate (FR-29). Never auto, never sandbox-and-run.
        if request.diagnosis_class in ("UNKNOWN", "INSUFFICIENT_EVIDENCE"):
            return deny(
                "unknown_gate",
                f"diagnosis is {request.diagnosis_class}; it routes to the unknown "
                f"flow and never executes, in any mode (PRD §8.4)"
            )
        ok("unknown_gate", f"diagnosis {request.diagnosis_class or 'deterministic'}")

        # --- 7. confidence (FR-12). Below threshold is approval, not denial.
        below_confidence = (
            request.confidence is not None
            and request.confidence < policy.confidence_threshold
        )
        if below_confidence:
            checks.append(Check(
                "confidence", False,
                f"{request.confidence:.2f} < {policy.confidence_threshold:.2f}; "
                f"routes to a human rather than denying"
            ))
        else:
            ok("confidence",
               f"{request.confidence:.2f} >= {policy.confidence_threshold:.2f}"
               if request.confidence is not None else "not model-driven")

        # --- 8. risk tier, deterministic from the registry
        tier = self.risk_tier(request.action)
        decision.risk_tier = tier
        fixed = self.registry.tier_is_fixed(request.action)
        ok("risk_tier", f"{tier}{' (fixed by the action)' if fixed else ''}")

        # --- 9. blast radius
        within, blast_detail = self.blast.check(request.incident_id)
        if not within:
            return deny("blast_radius", blast_detail)
        ok("blast_radius", blast_detail)

        # --- 10. circuit breaker
        closed, breaker_detail = self.breaker.check(request.service, request.fault_class)
        if not closed:
            return deny("circuit_breaker", breaker_detail)
        ok("circuit_breaker", breaker_detail)

        # --- 11. mode policy. Last, because it routes rather than decides.
        decision.verdict = self._route(
            policy.mode, tier, below_confidence, request.operator_approved
        )
        checks.append(Check(
            "mode_policy", True,
            f"{policy.mode} + {tier}"
            + (" + below-threshold confidence" if below_confidence else "")
            + (f" + approved on {request.operator_approved}"
               if request.operator_approved else "")
            + f" -> {decision.verdict}"
        ))
        if decision.verdict is not Verdict.ALLOW_AUTO:
            decision.reasons.append(
                f"mode_policy: {decision.verdict} under {policy.mode} for a "
                f"{tier}-risk action"
            )
        return decision

    @staticmethod
    def _route(
        mode: Mode,
        tier: RiskTier,
        below_confidence: bool,
        approved: str = "",
    ) -> Verdict:
        """Mode and tier to a verdict. `PRD.md` §5.4.

        `SIMULATION` never executes — it is the default, and the default must
        be the one that cannot do damage. A below-threshold confidence always
        reaches a human, whatever the tier, because an action chosen by a model
        that is unsure is exactly the case approval exists for.

        AN APPROVAL SATISFIES THIS STEP AND ONLY THIS STEP.
        Steps 1-10 have already run when this is reached, so an approval can
        never widen the allow-list, revive a denied mutation, reopen the
        breaker or raise the blast-radius ceiling. What it does satisfy is the
        two gates whose whole content is "a human should look at this": the
        mode and the confidence floor. A human read this plan and said yes, so
        asking again is not caution, it is a loop — which is literally what the
        first live run did, parking the approved re-run a second time.

        HIGH is the exception and stays one. A fixed-HIGH action's sandbox is
        mandatory rather than routed (`ARCHITECTURE.md` §6.2.1), so an approval
        moves it to the sandbox and no further. `apply_patch` is the action
        this protects.

        "No further" is about THIS function, not about the incident. What an
        approval buys is a sandbox requirement, never a direct write. Whether
        a patch that has already satisfied that requirement may then be
        promoted is `loop.py`'s question and is answered in ADR 0012: only
        with an approval AND a clone that passed. Nothing here grants it.
        """
        if approved:
            return Verdict.REQUIRE_SANDBOX if tier == HIGH else Verdict.ALLOW_AUTO
        if mode == "SIMULATION":
            return Verdict.REQUIRE_APPROVAL
        if below_confidence:
            return Verdict.REQUIRE_APPROVAL
        if mode == "APPROVAL":
            return Verdict.REQUIRE_APPROVAL
        # AUTONOMOUS
        if tier == HIGH:
            # This covers every fixed-tier action without needing to know which
            # they are: `apply_patch` is HIGH by definition, so the tier check
            # alone stops it auto-executing (ARCHITECTURE.md §6.2.1).
            return Verdict.REQUIRE_APPROVAL
        if tier == MEDIUM:
            return Verdict.REQUIRE_SANDBOX
        if tier == LOW:
            return Verdict.ALLOW_AUTO
        return Verdict.REQUIRE_APPROVAL

    def record_execution(self, request: ActionRequest) -> None:
        """Count a real execution against both limits. After the act, not before."""
        self.blast.record(request.incident_id)
        self.breaker.record(request.service, request.fault_class)
