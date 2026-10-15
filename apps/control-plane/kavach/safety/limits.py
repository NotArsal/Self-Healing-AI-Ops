"""Blast radius and the circuit breaker — the two rate limits on automation.

Both answer the same question from different directions: *is Kavach doing too
much?* Blast radius caps work per incident and per hour. The breaker caps
repeated healing of the same thing, which is the signal that the repair is not
actually fixing the cause.

WHY THE BREAKER IS THE MORE IMPORTANT OF THE TWO
A repair that works three times in thirty minutes is not working. Something is
re-breaking it, and the fourth automatic heal hides the real fault for another
ten minutes. Escalating instead is the correct behaviour even though the repair
would have "succeeded" — the measure is whether the system stays healthy, not
whether the action returns cleanly.

IN-MEMORY, AND HONEST ABOUT IT
Counts live in this process and reset when it restarts. That is a real
weakness: a crash-looping control plane would forget it had already healed
three times. The fix is the same persistence that incidents need, and until
then this is a guard rather than a guarantee. It is not a reason to omit it —
a limit that holds for the life of a process is strictly better than none.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class Limits:
    """`ARCHITECTURE.md` §6.1 steps 8 and 9, as data."""

    actions_per_incident: int = 3
    incidents_per_hour: int = 5
    heals_per_pair: int = 3
    breaker_window: timedelta = field(default=timedelta(minutes=30))


class BlastRadius:
    """Caps actions within one incident, and incidents within an hour."""

    def __init__(self, limits: Limits | None = None) -> None:
        self.limits = limits or Limits()
        self._per_incident: dict[str, int] = {}
        self._incident_starts: deque[datetime] = deque()
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(hours=1)
        while self._incident_starts and self._incident_starts[0] < cutoff:
            self._incident_starts.popleft()

    def check(self, incident_id: str, now: datetime | None = None) -> tuple[bool, str]:
        """Read-only. True if another action is within both limits."""
        now = now or datetime.now(UTC)
        with self._lock:
            self._prune(now)
            used = self._per_incident.get(incident_id, 0)
            if used >= self.limits.actions_per_incident:
                return False, (
                    f"blast radius: {used} actions already run for "
                    f"{incident_id}, limit {self.limits.actions_per_incident}"
                )
            # A known incident does not re-consume the hourly budget.
            projected = len(self._incident_starts) + (
                0 if incident_id in self._seen else 1
            )
            if projected > self.limits.incidents_per_hour:
                return False, (
                    f"blast radius: {len(self._incident_starts)} incidents in the "
                    f"last hour, limit {self.limits.incidents_per_hour}; "
                    f"automation halts rather than widening"
                )
            return True, (
                f"{used}/{self.limits.actions_per_incident} actions this incident, "
                f"{len(self._incident_starts)}/{self.limits.incidents_per_hour} "
                f"incidents this hour"
            )

    def record(self, incident_id: str, now: datetime | None = None) -> None:
        """Count one executed action. Called after permit, not during it."""
        now = now or datetime.now(UTC)
        with self._lock:
            self._prune(now)
            if incident_id not in self._seen:
                self._seen.add(incident_id)
                self._incident_starts.append(now)
            self._per_incident[incident_id] = self._per_incident.get(incident_id, 0) + 1


class CircuitBreaker:
    """Caps repeated healing of the same (service, fault_class)."""

    def __init__(self, limits: Limits | None = None) -> None:
        self.limits = limits or Limits()
        self._heals: dict[tuple[str, str], deque[datetime]] = {}
        self._lock = threading.Lock()

    def _window(self, key: tuple[str, str], now: datetime) -> deque[datetime]:
        times = self._heals.setdefault(key, deque())
        cutoff = now - self.limits.breaker_window
        while times and times[0] < cutoff:
            times.popleft()
        return times

    def check(
        self, service: str, fault_class: str, now: datetime | None = None
    ) -> tuple[bool, str]:
        now = now or datetime.now(UTC)
        key = (service or "?", fault_class or "?")
        with self._lock:
            times = self._window(key, now)
            if len(times) >= self.limits.heals_per_pair:
                minutes = int(self.limits.breaker_window.total_seconds() // 60)
                return False, (
                    f"circuit breaker OPEN for {key[1]} on {key[0]}: "
                    f"{len(times)} heals in {minutes} min, limit "
                    f"{self.limits.heals_per_pair}. A repair that keeps being "
                    f"needed is not repairing the cause"
                )
            return True, (
                f"{len(times)}/{self.limits.heals_per_pair} heals for "
                f"{key[1]} on {key[0]} in window"
            )

    def record(
        self, service: str, fault_class: str, now: datetime | None = None
    ) -> None:
        now = now or datetime.now(UTC)
        key = (service or "?", fault_class or "?")
        with self._lock:
            self._window(key, now).append(now)

    def state(self) -> dict[str, int]:
        with self._lock:
            return {f"{s}/{f}": len(t) for (s, f), t in self._heals.items()}
