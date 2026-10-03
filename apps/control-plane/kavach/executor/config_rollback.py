"""`rollback_config` — restore target settings to a captured prior state.

The ONE action this slice implements. Not a registry, not a generic executor;
those arrive with the full safety engine. What is here is the part that must be
right from the first action ever executed: the inverse is captured as data
before the write, and it restores the exact prior value.

TWO PROPERTIES WORTH BEING EXPLICIT ABOUT

The inverse is a RECORDED VALUE, never a constant. Restoring "0.35 because
that is the healthy default" would be a reset, not a rollback: it would be
wrong the moment the healthy value is anything else, and it would quietly
overwrite a deliberate operator change. The pre-state witness is read from the
target immediately before mutating it, and the inverse replays exactly that.

There is no shell. The only write path is the target's validated config
interface, which refuses denied keys (`embed_model`, the database settings),
unknown keys and out-of-range values, and applies all-or-nothing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kavach.target import TargetClient, TargetError

ACTION_NAME = "rollback_config"
RISK_TIER = "MEDIUM"  # changes application behaviour; reversible via the witness


class ActionError(RuntimeError):
    pass


def idempotency_key(incident_id: str, action: str, params: dict[str, Any]) -> str:
    """Stable across retries of the same logical action, different otherwise."""
    blob = json.dumps({"incident": incident_id, "action": action, "params": params},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


@dataclass
class ConfigRollback:
    """A rollback of specific settings, with its inverse captured up front."""

    incident_id: str
    target_settings: dict[str, Any]          # what to set
    name: str = ACTION_NAME
    risk_tier: str = RISK_TIER

    # Captured at prepare() time, before anything is written.
    pre_state: dict[str, Any] = field(default_factory=dict)
    inverse_settings: dict[str, Any] = field(default_factory=dict)
    config_hash_before: str = ""
    config_hash_after: str = ""
    idem_key: str = ""

    executed: bool = False
    reverted: bool = False
    error: str = ""
    prepared_at: str = ""
    executed_at: str = ""

    # --- preparation --------------------------------------------------------

    def prepare(self, client: TargetClient) -> None:
        """Capture the witness and derive the inverse. No writes."""
        cfg = client.config()
        settings = dict(cfg.get("settings", {}))

        unknown = set(self.target_settings) - set(settings)
        if unknown:
            raise ActionError(
                f"refusing to act on settings the target does not report: {sorted(unknown)}"
            )

        self.pre_state = {
            "settings": settings,
            "config_hash": cfg.get("config_hash", ""),
            "prompt_version": cfg.get("prompt_version", {}),
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        # The inverse is exactly the prior value of each key being changed.
        self.inverse_settings = {k: settings[k] for k in self.target_settings}
        self.config_hash_before = str(cfg.get("config_hash", ""))
        self.idem_key = idempotency_key(self.incident_id, self.name, self.target_settings)
        self.prepared_at = datetime.now(UTC).isoformat(timespec="seconds")

    # --- execution ----------------------------------------------------------

    def execute(self, client: TargetClient) -> None:
        if not self.prepared_at:
            raise ActionError("prepare() must run before execute(): without a "
                              "pre-state witness there is no inverse")
        if self.executed:
            # Idempotent by the same key: a duplicate is a no-op, not a second write.
            return
        try:
            result = client.apply_settings(self.target_settings)
        except TargetError as exc:
            self.error = str(exc)
            raise ActionError(f"{self.name} failed: {exc}") from exc
        self.config_hash_after = str(result.get("config_hash", ""))
        self.executed = True
        self.executed_at = datetime.now(UTC).isoformat(timespec="seconds")

    def invert(self, client: TargetClient) -> None:
        """Apply the recorded inverse, restoring the exact prior values."""
        if not self.inverse_settings:
            raise ActionError("no inverse recorded; nothing can be restored")
        try:
            client.apply_settings(self.inverse_settings)
        except TargetError as exc:
            self.error = str(exc)
            raise ActionError(f"inverse of {self.name} failed: {exc}") from exc
        self.reverted = True

    def verify_applied(self, client: TargetClient) -> tuple[bool, str]:
        """Confirm the REPAIR landed: live settings match what was requested.

        Distinct from verify_restored(). For an F06 repair the requested value
        is the baseline (0.35) while the inverse is the faulty value that was
        there before (0.999) - checking the wrong one of those would report
        success for a target still holding the fault.
        """
        live = client.settings()
        bad = {k: {"wanted": v, "live": live.get(k)}
               for k, v in self.target_settings.items() if live.get(k) != v}
        if bad:
            return False, f"repair not applied: {bad}"
        return True, f"live settings match the requested values {self.target_settings}"

    def verify_restored(self, client: TargetClient) -> tuple[bool, str]:
        """Confirm the INVERSE landed: live settings match the pre-state witness.

        Used after invert(), i.e. when a verification failure has unwound the
        repair and we need to prove the target is back where it started.
        """
        live = client.settings()
        bad = {k: {"witness": v, "live": live.get(k)}
               for k, v in self.inverse_settings.items() if live.get(k) != v}
        if bad:
            return False, f"inverse not restored: {bad}"
        return True, "live settings match the pre-state witness"

    def unchanged_elsewhere(self, client: TargetClient) -> tuple[bool, str]:
        """Confirm no setting outside the rollback scope moved.

        An action that fixes its target value while disturbing something else is
        not a rollback.
        """
        live = client.settings()
        before = self.pre_state.get("settings", {})
        touched = set(self.target_settings)
        drift = {
            k: (before.get(k), live.get(k))
            for k in before
            if k not in touched and live.get(k) != before.get(k)
        }
        if drift:
            return False, f"unrelated settings changed: {drift}"
        return True, "no settings outside the rollback scope changed"

    # --- record -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "action": self.name,
            "risk_tier": self.risk_tier,
            "idempotency_key": self.idem_key,
            "requested_settings": self.target_settings,
            "inverse_settings": self.inverse_settings,
            "pre_state": self.pre_state,
            "config_hash_before": self.config_hash_before,
            "config_hash_after": self.config_hash_after,
            "executed": self.executed,
            "reverted": self.reverted,
            "prepared_at": self.prepared_at,
            "executed_at": self.executed_at,
            "error": self.error,
        }


def build_rollback_for_retrieval_collapse(
    incident_id: str, client: TargetClient, known_good_threshold: float | None = None
) -> ConfigRollback:
    """Construct the F06 repair.

    `known_good_threshold` comes from the captured baseline. If it is None the
    action cannot be built: there is nothing to roll back TO, and inventing a
    default would turn a rollback into a guess.
    """
    if known_good_threshold is None:
        raise ActionError(
            "no baseline rerank_threshold available; rollback_config needs a "
            "recorded known-good value and must not fall back to a constant"
        )
    action = ConfigRollback(
        incident_id=incident_id,
        target_settings={"rerank_threshold": float(known_good_threshold)},
    )
    action.prepare(client)
    return action
