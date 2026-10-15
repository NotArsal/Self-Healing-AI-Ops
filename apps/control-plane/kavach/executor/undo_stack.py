"""The per-incident undo stack — `ARCHITECTURE.md` §6.0, faithful undo.

A stack, not a single inverse. One incident may run several actions, and
unwinding has to happen in reverse order: if A changed a config and B restarted
the container that read it, inverting A first leaves B's container running the
wrong config.

WHY THIS MATTERS MORE THAN ANY MODEL CHOICE
The STRATUS ablation is the reason this is not optional. On AIOpsLab's 13
mitigation problems, naive retry without undo scores 23.1% against 69.2% with
transactional no-regression. The undo mechanism is worth roughly 3x on
mitigation success — more than any model in this stack.

UNWINDING IS ITSELF VERIFIED
Applying the inverse is not the same as the prior state being back. Every
unwind checks `verify_restored()` against the pre-state witness and records the
answer. An unwind that silently failed would be the worst possible outcome:
Kavach would report a clean rollback over a target left in a third state that
is neither broken-as-found nor repaired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kavach.executor.base import Action
from kavach.target import TargetClient


@dataclass
class Entry:
    """One executed action and the evidence needed to undo it."""

    action: Action
    pushed_at: str
    unwound_at: str = ""
    unwind_ok: bool | None = None
    unwind_detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.name,
            "incident_id": self.action.incident_id,
            "pushed_at": self.pushed_at,
            "unwound_at": self.unwound_at,
            "unwind_ok": self.unwind_ok,
            "unwind_detail": self.unwind_detail,
        }


@dataclass
class UnwindReport:
    """What happened when the stack was unwound. Never raises; always reports."""

    attempted: int = 0
    restored: int = 0
    failures: list[str] = field(default_factory=list)
    entries: list[dict[str, Any]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """True only if every inverse applied AND verified."""
        return self.attempted > 0 and self.restored == self.attempted and not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "restored": self.restored,
            "clean": self.clean,
            "failures": self.failures,
            "entries": self.entries,
        }


class UndoStack:
    """Per-incident. Push before executing, unwind in reverse on failure."""

    def __init__(self, incident_id: str) -> None:
        self.incident_id = incident_id
        self._entries: list[Entry] = []

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def depth(self) -> int:
        return len(self._entries)

    def push(self, action: Action) -> Entry:
        """Record an action BEFORE it executes.

        Before, not after: an action that fails halfway has still mutated
        something, and an unwind that skips it leaves that change in place.
        """
        entry = Entry(
            action=action,
            pushed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self._entries.append(entry)
        return entry

    def unwind(self, client: TargetClient) -> UnwindReport:
        """Apply every inverse in reverse order, verifying each.

        Keeps going after a failure rather than stopping. A later entry's
        inverse may still succeed, and leaving it unapplied because an earlier
        one failed strands more state than it saves. Every failure is recorded.
        """
        report = UnwindReport()
        for entry in reversed(self._entries):
            if entry.unwound_at:
                continue  # already unwound; never apply an inverse twice
            report.attempted += 1
            entry.unwound_at = datetime.now(UTC).isoformat(timespec="seconds")
            try:
                entry.action.invert(client)
            except Exception as exc:
                entry.unwind_ok = False
                entry.unwind_detail = f"{type(exc).__name__}: {exc}"
                report.failures.append(
                    f"{entry.action.name}: inverse raised {entry.unwind_detail}"
                )
                report.entries.append(entry.to_dict())
                continue

            # Applying the inverse is not proof the prior state is back.
            ok, detail = entry.action.verify_restored(client)
            entry.unwind_ok = ok
            entry.unwind_detail = detail
            if ok:
                report.restored += 1
            else:
                report.failures.append(f"{entry.action.name}: {detail}")
            report.entries.append(entry.to_dict())

        return report

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "depth": self.depth,
            "entries": [e.to_dict() for e in self._entries],
        }
