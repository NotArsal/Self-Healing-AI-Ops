"""The fault-injector contract.

Every injector captures the pre-state before it changes anything and can put it
back exactly. `revert()` must run in test teardown regardless of outcome, so a
failed run never leaves the target broken.

Two rules worth stating because breaking either invalidates every number
derived from an injection:

1. An injector NEVER mutates the corpus. A fault that changes the data is a
   different experiment from one run to the next.
2. An injector NEVER writes a value it did not first read. `revert()` replays
   the captured pre-state; it does not restore a constant.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class InjectionRecord:
    fault_class: str
    injected_at: str = ""
    reverted_at: str = ""
    pre_state: dict[str, Any] = field(default_factory=dict)
    applied: dict[str, Any] = field(default_factory=dict)
    corpus_before: dict[str, Any] = field(default_factory=dict)
    corpus_after: dict[str, Any] = field(default_factory=dict)

    @property
    def corpus_unchanged(self) -> bool:
        if not self.corpus_before or not self.corpus_after:
            return False
        return self.corpus_before == self.corpus_after


class Fault(ABC):
    """One catalogue entry's injector."""

    fault_class: str = ""
    fault_name: str = ""
    service: str = ""

    def __init__(self) -> None:
        self.record = InjectionRecord(fault_class=self.fault_class)

    @abstractmethod
    def inject(self) -> InjectionRecord:
        """Apply the fault, having first captured the pre-state."""

    @abstractmethod
    def revert(self) -> InjectionRecord:
        """Restore the captured pre-state exactly. Safe to call twice."""

    @abstractmethod
    def is_active(self) -> bool:
        """True when the fault is currently applied."""

    def _stamp_injected(self) -> None:
        self.record.injected_at = datetime.now(UTC).isoformat(timespec="seconds")

    def _stamp_reverted(self) -> None:
        self.record.reverted_at = datetime.now(UTC).isoformat(timespec="seconds")

    def __enter__(self) -> Fault:
        self.inject()
        return self

    def __exit__(self, *_exc: object) -> None:
        # Always reverts, including on an exception mid-test.
        self.revert()
