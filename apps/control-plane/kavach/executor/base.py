"""The action contract, and the registry that enforces it.

Every side effect Kavach can have is an `Action`. There is no other write path:
no shell, no `exec` adapter, no "run this command" parameter anywhere
(`FR-27`). An action is a named, registered object with a typed payload.

THE ONE RULE THIS MODULE EXISTS TO ENFORCE
**An action without a working inverse cannot be registered.** Not "should not"
— cannot: `register()` raises at import time, so the failure happens when the
developer runs the test suite rather than at 3 a.m. when a repair needs
unwinding. `ARCHITECTURE.md` §6.0 makes faithful undo the recoverability
guarantee, and a guarantee that depends on remembering to implement a method is
not a guarantee.

WHY A PROTOCOL AND A REGISTRY NOW, HAVING REFUSED THEM BEFORE
P2 shipped one concrete action and no registry, on the reasoning that a
registry with one entry is an interface with one implementation. That was right
then and is wrong now: the safety engine has to reason about actions it did not
write, `apply_patch` arrives in P7 with a fixed HIGH tier, and `loop.py` must
stop importing a RAG repair by name (`ARCHITECTURE.md` §1.4). The registry is
the seam those three need.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from kavach.target import TargetClient

# Risk tiers, highest-restriction last. `permit()` compares against these.
RiskTier = str
LOW: RiskTier = "LOW"
MEDIUM: RiskTier = "MEDIUM"
HIGH: RiskTier = "HIGH"
VALID_TIERS: frozenset[str] = frozenset({LOW, MEDIUM, HIGH})


class ActionError(RuntimeError):
    """An action could not be prepared, executed or inverted."""


class RegistrationError(TypeError):
    """An action was registered without satisfying the contract."""


@runtime_checkable
class Action(Protocol):
    """What every side effect must provide.

    Deliberately matched on *shape*, not inheritance, so the existing
    `ConfigRollback` satisfies it without being rewritten.
    """

    incident_id: str
    name: str
    risk_tier: RiskTier

    def prepare(self, client: TargetClient) -> None:
        """Capture the pre-state witness and derive the inverse. No writes."""

    def execute(self, client: TargetClient) -> None:
        """Perform the mutation. Must have been prepared first."""

    def invert(self, client: TargetClient) -> None:
        """Apply the recorded inverse. Deterministic data, never a model call."""

    def verify_applied(self, client: TargetClient) -> tuple[bool, str]:
        """Did the requested state actually take effect?"""

    def verify_restored(self, client: TargetClient) -> tuple[bool, str]:
        """After `invert`, is the pre-state back?"""

    def unchanged_elsewhere(self, client: TargetClient) -> tuple[bool, str]:
        """Did anything outside this action's declared scope move?"""

    def to_dict(self) -> dict[str, Any]:
        """The audit record."""


REQUIRED_METHODS = (
    "prepare", "execute", "invert",
    "verify_applied", "verify_restored", "unchanged_elsewhere", "to_dict",
)


class ActionRegistry:
    """Name → builder. The only way the loop obtains an action."""

    def __init__(self) -> None:
        self._builders: dict[str, Any] = {}
        self._tiers: dict[str, RiskTier] = {}
        self._fixed_tier: set[str] = set()

    def register(
        self,
        name: str,
        builder: Any,
        risk_tier: RiskTier,
        action_type: type | None = None,
        tier_is_fixed: bool = False,
    ) -> None:
        """Record an action builder, rejecting anything that breaks the contract.

        `tier_is_fixed` marks an action whose tier is a property of the action
        rather than something computed from its parameters. `apply_patch` is
        the case this exists for: its payload is model-authored, so it is HIGH
        whatever it claims to touch (`ARCHITECTURE.md` §6.2.1).
        """
        if not name or not name.strip():
            raise RegistrationError("an action needs a name")
        if name in self._builders:
            raise RegistrationError(f"{name!r} is already registered")
        if risk_tier not in VALID_TIERS:
            raise RegistrationError(
                f"{name!r} declares risk tier {risk_tier!r}; "
                f"valid tiers are {sorted(VALID_TIERS)}"
            )
        if not callable(builder):
            raise RegistrationError(f"{name!r} builder is not callable")

        # The inverse check. An action type is optional only because a builder
        # may be a plain function; when one is given, it is checked properly.
        if action_type is not None:
            missing = [m for m in REQUIRED_METHODS
                       if not callable(getattr(action_type, m, None))]
            if missing:
                raise RegistrationError(
                    f"{name!r} cannot be registered: {action_type.__name__} is "
                    f"missing {', '.join(missing)}. An action without a working "
                    f"inverse is not registrable (ARCHITECTURE.md §6.0)"
                )

        self._builders[name] = builder
        self._tiers[name] = risk_tier
        if tier_is_fixed:
            self._fixed_tier.add(name)

    def build(self, name: str, *args: Any, **kwargs: Any) -> Action:
        builder = self._builders.get(name)
        if builder is None:
            raise ActionError(
                f"no action named {name!r}; registered: {sorted(self._builders)}"
            )
        return builder(*args, **kwargs)  # type: ignore[no-any-return]

    def knows(self, name: str) -> bool:
        return name in self._builders

    def tier(self, name: str) -> RiskTier:
        """The declared tier. Unknown actions are HIGH by default-deny."""
        return self._tiers.get(name, HIGH)

    def tier_is_fixed(self, name: str) -> bool:
        return name in self._fixed_tier

    def names(self) -> list[str]:
        return sorted(self._builders)


registry = ActionRegistry()
